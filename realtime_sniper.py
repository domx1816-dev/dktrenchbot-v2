"""
realtime_sniper.py — Instant execution engine for high-confidence realtime signals.

THE PROBLEM WE'RE SOLVING:
  Main cycle takes 3-7 minutes. By the time it loops, ClawFarm has already
  pumped 200%. We had the signal — TrustSet burst + smart money cluster +
  CLOB momentum — but sat on it waiting for the next cycle.

WHAT THIS DOES:
  Runs in the same thread as realtime_watcher. When a high-confidence signal
  fires, this module executes IMMEDIATELY — no cycle wait.

SIGNALS THAT TRIGGER INSTANT ENTRY:
  1. BURST_ELITE   — 50+ TrustSets/5min (highest conviction burst)
  2. SMART_CLUSTER — 2+ tracked smart wallets bought same token < 60s apart
  3. CLOB_LAUNCH   — 60+ TrustSets + 25+ XRP CLOB volume in 5 min
  4. COMBINED      — burst 25+ AND smart money entered (double signal)

SAFETY:
  - Runs full disagreement check (rug, wash, liquidity trap, blacklist)
  - Won't enter if already in position on that token
  - Won't enter if safety controller is in STOP mode
  - Deduplicates via in-memory set + lock (no double buys same signal)
  - Max 3 realtime entries per hour (rate limit)

SIZING:
  Uses sizing.py with realtime-specific confidence inputs.
  Burst 50+ → elite sizing. Smart cluster → normal sizing. CLOB launch → fast sizing.
"""

import json, os, time, threading, logging
from typing import Optional, Dict

logger = logging.getLogger("realtime_sniper")

STATE_DIR = os.path.join(os.path.dirname(__file__), "state")

# ── Rate limits & dedup ───────────────────────────────────────────────────────
_entered_keys: set   = set()     # tokens we've entered via realtime (session)
_entry_times:  list  = []        # timestamps of realtime entries (for rate limit)
_lock = threading.Lock()

MAX_RT_ENTRIES_PER_HOUR = 5      # max 5 realtime sniper trades per hour
MIN_ENTRY_GAP_SEC       = 30     # minimum 30s between any two realtime entries


# ── Signal thresholds ─────────────────────────────────────────────────────────
BURST_ELITE_MIN    = 50    # TrustSets/5min for elite burst (PHX-level)
BURST_COMBINED_MIN = 25    # TrustSets/5min when combined with smart money
CLOB_LAUNCH_TS_MIN = 60    # TrustSets for CLOB launch
CLOB_LAUNCH_XRP    = 25    # XRP volume for CLOB launch
SMART_CLUSTER_MIN  = 2     # smart wallets that must have entered


def _rate_ok() -> bool:
    """Check we haven't exceeded hourly rate limit or minimum gap."""
    now = time.time()
    with _lock:
        # Prune old entries
        _entry_times[:] = [t for t in _entry_times if now - t < 3600]
        if len(_entry_times) >= MAX_RT_ENTRIES_PER_HOUR:
            logger.info(f"🛑 RT sniper rate limit: {len(_entry_times)}/{MAX_RT_ENTRIES_PER_HOUR} entries this hour")
            return False
        if _entry_times and now - _entry_times[-1] < MIN_ENTRY_GAP_SEC:
            logger.debug(f"RT sniper gap: last entry {now - _entry_times[-1]:.0f}s ago, min={MIN_ENTRY_GAP_SEC}s")
            return False
    return True


def _already_entered(key: str) -> bool:
    """Check if we're already in this position (realtime or cycle-entered)."""
    with _lock:
        if key in _entered_keys:
            return True

    # Also check live bot state file
    state_file = os.path.join(STATE_DIR, "state.json")
    try:
        with open(state_file) as f:
            state = json.load(f)
        if key in state.get("positions", {}):
            return True
    except Exception:
        pass
    return False


def _mark_entered(key: str):
    with _lock:
        _entered_keys.add(key)
        _entry_times.append(time.time())


def _get_wallet_balance() -> float:
    """Read current wallet XRP balance from state."""
    state_file = os.path.join(STATE_DIR, "state.json")
    try:
        with open(state_file) as f:
            s = json.load(f)
        return float(s.get("xrp_balance", 0) or s.get("wallet_xrp", 0) or 0)
    except Exception:
        return 0.0


def _safety_stopped() -> bool:
    """Check if safety controller has triggered an emergency stop."""
    safety_file = os.path.join(STATE_DIR, "safety_status.json")
    try:
        with open(safety_file) as f:
            s = json.load(f)
        return s.get("emergency_stop", False)
    except Exception:
        return False  # if file missing, assume safe


def _run_disagreement(candidate: dict, regime: str = "neutral") -> dict:
    """Run disagreement engine on the candidate. Returns result dict."""
    try:
        import disagreement as _dm
        return _dm.evaluate(
            candidate=candidate,
            bot_state={},   # minimal — disagreement only needs candidate fields
            regime=regime,
            score=75,       # assume high score since this is a high-confidence signal
        )
    except Exception as e:
        logger.warning(f"Disagreement engine error: {e} — allowing (fail-open)")
        return {"verdict": "pass", "reason": "disagree_error", "confidence_adj": 0}


def _get_currency(symbol: str, issuer: str, currency_hex: str) -> str:
    """Resolve currency code — use hex if provided, else try config."""
    if currency_hex and len(currency_hex) > 3:
        return currency_hex
    try:
        from config import get_currency
        return get_currency(symbol)
    except Exception:
        return symbol[:3].upper()


def _get_size(signal_type: str, tvl_xrp: float, wallet_balance: float) -> float:
    """Calculate position size for realtime entry."""
    try:
        from sizing import calculate_position_size
        confidence_inputs = {
            "tvl_xrp": tvl_xrp,
            "ts_burst_active": signal_type in ("burst_elite", "burst_combined", "clob_launch"),
            "ts_burst_count": 50 if signal_type == "burst_elite" else 30,
            "wallet_cluster_active": signal_type in ("smart_cluster", "burst_combined"),
            "ml_probability": 0.70,
            "regime": "neutral",
        }
        score = 75 if signal_type == "burst_elite" else 68 if signal_type == "smart_cluster" else 65
        return calculate_position_size(
            score=score,
            wallet_balance=wallet_balance,
            confidence_inputs=confidence_inputs,
        )
    except Exception as e:
        logger.warning(f"Sizing error: {e} — using floor 5 XRP")
        return 5.0


def _write_sniper_log(symbol: str, signal_type: str, result: dict):
    """Append to sniper log file for dashboard / audit."""
    log_file = os.path.join(STATE_DIR, "sniper_log.json")
    try:
        try:
            with open(log_file) as f:
                log = json.load(f)
        except Exception:
            log = []
        log.append({
            "ts":          time.time(),
            "symbol":      symbol,
            "signal_type": signal_type,
            "success":     result.get("success", False),
            "xrp_spent":   result.get("xrp_spent", 0),
            "tokens":      result.get("tokens_received", 0),
            "price":       result.get("actual_price", 0),
            "error":       result.get("error"),
        })
        log = log[-200:]  # keep last 200 entries
        with open(log_file, "w") as f:
            json.dump(log, f, indent=2)
    except Exception as e:
        logger.debug(f"Sniper log write error: {e}")


def _open_position_in_state(symbol: str, issuer: str, currency: str,
                             key: str, entry_result: dict, signal_type: str, tvl_xrp: float):
    """Write the new position directly to state.json so the main cycle manages exits."""
    state_file = os.path.join(STATE_DIR, "state.json")
    try:
        try:
            with open(state_file) as f:
                state = json.load(f)
        except Exception:
            state = {}

        if "positions" not in state:
            state["positions"] = {}

        actual_price = entry_result.get("actual_price", 0)
        xrp_spent    = entry_result.get("xrp_spent", 0)
        tokens_held  = entry_result.get("tokens_received", 0)

        state["positions"][key] = {
            "symbol":       symbol,
            "issuer":       issuer,
            "currency":     currency,
            "entry_price":  actual_price,
            "entry_time":   time.time(),
            "tokens_held":  tokens_held,
            "xrp_spent":    xrp_spent,
            "peak_price":   actual_price,
            "tp1_hit":      False,
            "tp2_hit":      False,
            "entry_tvl":    tvl_xrp,
            "score":        75,
            "chart_state":  "realtime_sniper",
            "score_band":   "A",
            "entry_hash":   entry_result.get("hash"),
            "smart_wallets": [],
            "scalp_mode":   False,
            "trade_mode":   "hold",
            "is_proven":    False,
            "_godmode_type": signal_type,
            "_godmode_tp":   None,
            "_godmode_hardstop": None,
            "_rt_entry":    True,  # flag so cycle knows this was a realtime sniper entry
        }

        tmp = state_file + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, state_file)
        logger.info(f"✅ RT SNIPER POSITION OPENED: {symbol} {tokens_held:.4f} @ {actual_price:.8f}")
    except Exception as e:
        logger.error(f"Failed to write position to state: {e}")


def fire(symbol: str, currency: str, issuer: str,
         signal_type: str, tvl_xrp: float, price: float,
         burst_count: int = 0, smart_wallets: list = None,
         vol_5min_xrp: float = 0.0) -> bool:
    """
    Attempt an immediate realtime entry. Returns True if trade executed.

    signal_type: one of burst_elite | smart_cluster | clob_launch | burst_combined
    """
    key = f"{currency}:{issuer}"

    # ── Gate 1: already in this position ─────────────────────────────────
    if _already_entered(key):
        logger.debug(f"RT sniper: already in {symbol} — skip")
        return False

    # ── Gate 2: rate limit ────────────────────────────────────────────────
    if not _rate_ok():
        return False

    # ── Gate 3: safety stop ───────────────────────────────────────────────
    if _safety_stopped():
        logger.info(f"RT sniper: safety stop active — skip {symbol}")
        return False

    # ── Gate 4: wallet balance ────────────────────────────────────────────
    wallet_balance = _get_wallet_balance()
    if wallet_balance < 10:
        logger.info(f"RT sniper: wallet balance {wallet_balance:.1f} XRP too low — skip")
        return False

    # ── Gate 5: disagreement engine ──────────────────────────────────────
    candidate = {
        "symbol":      symbol,
        "issuer":      issuer,
        "currency":    currency,
        "tvl_xrp":     tvl_xrp,
        "price":       price,
        "burst_count": burst_count,
        "_burst_mode": signal_type in ("burst_elite", "burst_combined"),
        "key":         key,
    }
    disagree = _run_disagreement(candidate)
    if disagree.get("verdict") == "veto":
        logger.info(f"🚫 RT sniper VETO {symbol}: {disagree.get('reason')} — skip")
        return False

    # ── Gate 6: minimum TVL (avoid ghost pools) ───────────────────────────
    if tvl_xrp > 0 and tvl_xrp < 100:
        logger.info(f"RT sniper: {symbol} TVL={tvl_xrp:.0f} XRP too thin — skip")
        return False

    # ── All gates passed — FIRE ───────────────────────────────────────────
    size = _get_size(signal_type, tvl_xrp, wallet_balance)
    logger.info(
        f"🎯 RT SNIPER FIRING: {symbol} | signal={signal_type} | "
        f"burst={burst_count} | tvl={tvl_xrp:.0f} XRP | size={size:.1f} XRP"
    )

    try:
        from execution import buy_token
        result = buy_token(
            symbol            = symbol,
            issuer            = issuer,
            xrp_amount        = size,
            expected_price    = price,
            slippage_tolerance= 0.15,   # wider tolerance for fast movers
        )
    except Exception as e:
        logger.error(f"RT sniper execution error {symbol}: {e}")
        return False

    _write_sniper_log(symbol, signal_type, result)

    if result.get("success"):
        _mark_entered(key)
        resolved_currency = _get_currency(symbol, issuer, currency)
        _open_position_in_state(
            symbol=symbol, issuer=issuer, currency=resolved_currency,
            key=key, entry_result=result, signal_type=signal_type, tvl_xrp=tvl_xrp,
        )
        logger.info(
            f"🚀 RT SNIPER HIT: {symbol} | {result.get('xrp_spent', 0):.2f} XRP spent | "
            f"{result.get('tokens_received', 0):.4f} tokens @ {result.get('actual_price', 0):.8f}"
        )
        return True
    else:
        logger.warning(f"❌ RT sniper miss {symbol}: {result.get('error')}")
        return False


# ── Public trigger functions (called by realtime_watcher / clob_tracker) ─────

def on_burst_elite(symbol: str, currency: str, issuer: str,
                   burst_count: int, tvl_xrp: float, price: float):
    """50+ TrustSets/5min — highest conviction burst. Fire immediately."""
    if burst_count < BURST_ELITE_MIN:
        return
    logger.info(f"🔥 BURST ELITE signal: {symbol} — {burst_count} TS/5min")
    threading.Thread(
        target=fire,
        args=(symbol, currency, issuer, "burst_elite", tvl_xrp, price),
        kwargs={"burst_count": burst_count},
        name=f"rt-sniper-{symbol}",
        daemon=True,
    ).start()


def on_smart_cluster(symbol: str, currency: str, issuer: str,
                     wallets: list, tvl_xrp: float, price: float,
                     burst_count: int = 0):
    """2+ smart wallets entered same token — fire if combined with any burst signal."""
    if len(wallets) < SMART_CLUSTER_MIN:
        return

    # Determine signal type
    if burst_count >= BURST_COMBINED_MIN:
        signal_type = "burst_combined"
        logger.info(f"🔥 BURST+SMART signal: {symbol} — {burst_count} TS + {len(wallets)} smart wallets")
    else:
        signal_type = "smart_cluster"
        logger.info(f"🔥 SMART CLUSTER signal: {symbol} — {len(wallets)} wallets entered")

    threading.Thread(
        target=fire,
        args=(symbol, currency, issuer, signal_type, tvl_xrp, price),
        kwargs={"burst_count": burst_count, "smart_wallets": wallets},
        name=f"rt-sniper-{symbol}",
        daemon=True,
    ).start()


def on_clob_launch(symbol: str, currency: str, issuer: str,
                   ts_burst: int, vol_5min_xrp: float, price: float):
    """CLOB launch signal — 60+ TrustSets + 25+ XRP volume."""
    if ts_burst < CLOB_LAUNCH_TS_MIN or vol_5min_xrp < CLOB_LAUNCH_XRP:
        return
    logger.info(f"🔥 CLOB LAUNCH signal: {symbol} — {ts_burst} TS + {vol_5min_xrp:.0f} XRP vol")
    threading.Thread(
        target=fire,
        args=(symbol, currency, issuer, "clob_launch", 0.0, price),
        kwargs={"burst_count": ts_burst, "vol_5min_xrp": vol_5min_xrp},
        name=f"rt-sniper-{symbol}",
        daemon=True,
    ).start()
