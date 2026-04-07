"""
clob_tracker.py — CLOB (DEX OfferCreate) Price & Volume Tracker

PROBLEM WE'RE SOLVING:
  Big runners like brizzly, PROPHET, PRSV trade on the CLOB orderbook,
  NOT AMM pools, in their early minutes. Our AMM scanner sees flat price
  while the real 300-600% moves happen on OfferCreate fills.

WHAT THIS MODULE DOES:
  - Tracks per-token CLOB buy volume in rolling windows
  - Tracks per-token CLOB price (derived from OfferCreate amounts)
  - Fires LAUNCH_SIGNAL when: TrustSet burst + 30+ XRP bought in 5 min
  - Fires MOMENTUM_SIGNAL when: price up 15%+ from CLOB baseline

DATA (from 8-runner analysis):
  brizzly:  102 TS/10min + 32 XRP/5min → +648% peak
  PROPHET:   99 TS/10min + 123 XRP/5min → +478% peak
  PRSV:     105 TS/10min + 130 XRP/5min → +380% peak
  ROOSEVELT:  2 TS/10min + 0 XRP/5min → missed entry
  Threshold: 80+ TS/10min AND 25+ XRP/5min = LAUNCH

Called by realtime_watcher.py when OfferCreate txs are received.
Results stored in state/realtime_signals.json under 'clob_launches'.
"""

import json, os, time, threading, logging

logger = logging.getLogger("clob_tracker")

STATE_DIR    = os.path.join(os.path.dirname(__file__), "state")
SIGNALS_FILE = os.path.join(STATE_DIR, "realtime_signals.json")

# Thresholds derived from 8-runner analysis
CLOB_VOL_WINDOW   = 300    # 5 min rolling window
CLOB_PRICE_WINDOW = 120    # 2 min for momentum detection
LAUNCH_XRP_MIN    = 25     # 25+ XRP bought in 5 min = launch signal
LAUNCH_TS_MIN     = 60     # 60+ TrustSets in 10 min (conservative from 80-105 range)
MOMENTUM_PCT      = 0.15   # 15% price move in 2 min = momentum

# Per-token data stores (in-memory, written to signals file)
_buy_times: dict   = {}   # key → [(ts, xrp_amount, price)]
_clob_prices: dict = {}   # key → [(ts, price)]
_launch_fired: set = set()  # keys that already fired launch signal
_last_flush     = 0.0
_lock           = threading.Lock()


def _save_signal(key: str, symbol: str, currency: str, issuer: str,
                 signal_type: str, data: dict):
    """Write signal to realtime_signals.json."""
    global _last_flush
    try:
        try:
            with open(SIGNALS_FILE) as f:
                signals = json.load(f)
        except:
            signals = {"new_tokens": {}, "velocity_alerts": {}, "momentum_alerts": {}, "clob_launches": {}}

        if "clob_launches" not in signals:
            signals["clob_launches"] = {}

        signals["clob_launches"][key] = {
            "symbol":      symbol,
            "currency":    currency,
            "issuer":      issuer,
            "signal_type": signal_type,
            "updated_at":  time.time(),
            **data,
        }
        signals["last_updated"] = time.time()

        now = time.time()
        if now - _last_flush >= 3:
            os.makedirs(STATE_DIR, exist_ok=True)
            with open(SIGNALS_FILE, "w") as f:
                json.dump(signals, f, indent=2)
            _last_flush = now
    except Exception as e:
        logger.debug(f"clob_tracker save error: {e}")


def on_offer_create(currency: str, issuer: str, symbol: str,
                    xrp_amount: float, token_amount: float,
                    side: str, ts_burst_count: int = 0):
    """
    Called by realtime_watcher.py for every OfferCreate that involves
    this token as the asset being bought (side='BUY') with XRP.

    xrp_amount: XRP spent on this buy
    token_amount: tokens received
    side: 'BUY' (spending XRP to get token) or 'SELL'
    ts_burst_count: current TrustSet burst count for this token (from realtime_watcher)
    """
    if side != 'BUY' or xrp_amount < 0.5:
        return  # Only track real buys, ignore dust

    key = f"{currency}:{issuer}"
    now = time.time()
    price = xrp_amount / token_amount if token_amount > 0 else 0

    with _lock:
        # Track buy volume
        if key not in _buy_times:
            _buy_times[key] = []
        _buy_times[key].append((now, xrp_amount, price))
        # Keep only CLOB_VOL_WINDOW seconds
        _buy_times[key] = [(t, v, p) for t, v, p in _buy_times[key]
                           if now - t <= CLOB_VOL_WINDOW]

        # Track price history
        if key not in _clob_prices:
            _clob_prices[key] = []
        if price > 0:
            _clob_prices[key].append((now, price))
            _clob_prices[key] = [(t, p) for t, p in _clob_prices[key]
                                  if now - t <= 600]  # 10 min price window

        vol_5min  = sum(v for t, v, p in _buy_times[key])
        buy_count = len(_buy_times[key])
        prices    = [p for t, v, p in _buy_times[key] if p > 0]
        first_p   = _clob_prices[key][0][1] if _clob_prices[key] else 0
        latest_p  = price

    if vol_5min > 0:
        logger.debug(f"CLOB {symbol}: vol={vol_5min:.1f} XRP/5min buys={buy_count} ts_burst={ts_burst_count}")

    # ── LAUNCH SIGNAL ─────────────────────────────────────────────────────
    # Pattern: 60+ TrustSets/10min AND 25+ XRP bought in 5 min
    # Fired from 8-runner analysis: brizzly/PROPHET/PRSV all hit this
    if (key not in _launch_fired and
            ts_burst_count >= LAUNCH_TS_MIN and
            vol_5min >= LAUNCH_XRP_MIN and
            buy_count >= 3):

        _launch_fired.add(key)
        logger.info(
            f"🚀 CLOB LAUNCH: {symbol} — "
            f"{vol_5min:.0f} XRP bought/5min | {buy_count} buys | "
            f"ts_burst={ts_burst_count} | price={price:.8f}"
        )
        _save_signal(key, symbol, currency, issuer, "clob_launch", {
            "vol_5min_xrp":  round(vol_5min, 2),
            "buy_count":     buy_count,
            "ts_burst":      ts_burst_count,
            "clob_price":    price,
            "entry_trigger": True,
        })

    # ── MOMENTUM SIGNAL ───────────────────────────────────────────────────
    # Pattern: price up 15%+ from first price in this window
    elif (key in _launch_fired or ts_burst_count >= 20) and first_p > 0 and latest_p > 0:
        price_chg = (latest_p - first_p) / first_p
        if price_chg >= MOMENTUM_PCT and vol_5min >= 10:
            logger.info(
                f"📈 CLOB MOMENTUM: {symbol} — "
                f"+{price_chg*100:.0f}% from {first_p:.8f} → {latest_p:.8f} | "
                f"vol={vol_5min:.0f} XRP"
            )
            _save_signal(key, symbol, currency, issuer, "clob_momentum", {
                "vol_5min_xrp":  round(vol_5min, 2),
                "buy_count":     buy_count,
                "ts_burst":      ts_burst_count,
                "clob_price":    latest_p,
                "price_chg_pct": round(price_chg * 100, 1),
                "baseline_price": first_p,
                "entry_trigger": True,
            })


def get_clob_price(currency: str, issuer: str) -> float:
    """Get latest known CLOB price for a token. Returns 0 if unknown."""
    key = f"{currency}:{issuer}"
    with _lock:
        pts = _clob_prices.get(key, [])
        if pts:
            return pts[-1][1]
    return 0.0


def get_clob_vol_5min(currency: str, issuer: str) -> float:
    """Get XRP buy volume in last 5 minutes from CLOB."""
    key = f"{currency}:{issuer}"
    now = time.time()
    with _lock:
        pts = _buy_times.get(key, [])
        return sum(v for t, v, p in pts if now - t <= CLOB_VOL_WINDOW)
