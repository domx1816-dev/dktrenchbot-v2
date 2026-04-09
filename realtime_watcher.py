"""
realtime_watcher.py — Real-time XRPL transaction stream watcher.

Connects to XRPL via WebSocket and watches the live ledger stream.
Catches AMMCreate and TrustSet transactions the MOMENT they happen
— no polling delay, no missed launches.

What it catches:
  1. AMMCreate → new token launched, immediately adds to registry
  2. TrustSet bursts → existing token gaining holders fast → velocity alert
  3. OfferCreate clusters → coordinated buying on a token → momentum alert

Output: writes to state/realtime_signals.json — bot.py reads this
        and injects signals directly into the scan cycle.

Run alongside bot.py — launched as a background thread from bot.py.
"""

import json, os, time, logging, threading
import asyncio
import websockets

logger = logging.getLogger("realtime")

WS_URL       = "wss://rpc.xrplclaw.com/ws"
STATE_DIR    = os.path.join(os.path.dirname(__file__), "state")
SIGNALS_FILE = os.path.join(STATE_DIR, "realtime_signals.json")
REGISTRY_FILE = os.path.join(STATE_DIR, "active_registry.json")

XRPL_EPOCH   = 946684800
MIN_AMM_XRP  = 50      # ignore dust pools < 50 XRP
MAX_AMM_XRP  = 10000   # ignore already-large pools at launch (not a new launch)
BURST_WINDOW = 300     # 5 min window to count TrustSet bursts
BURST_MIN    = 8       # 8 TrustSets in 5 min = burst signal (lowered from 10 — missed PROPHET at early stage)

# Offer volume tracking for price momentum detection
OFFER_WINDOW   = 120   # 2 min window for offer clustering
OFFER_MIN      = 5     # 5 OfferCreates in 2 min = buy pressure signal

# Per-issuer TrustSet timestamps for burst detection
_trustset_times: dict = {}
# Per-token offer timestamps for momentum detection
_offer_times: dict = {}
_lock = threading.Lock()

# Throttle signal file writes — max once every 5s
_last_signals_flush = 0.0

def _save_signals_throttled(signals: dict):
    global _last_signals_flush
    now = time.time()
    if now - _last_signals_flush >= 5:
        _save_signals(signals)
        _last_signals_flush = now


def _load_signals() -> dict:
    try:
        with open(SIGNALS_FILE) as f:
            return json.load(f)
    except:
        return {"new_tokens": {}, "velocity_alerts": {}, "last_updated": 0}


def _save_signals(signals: dict):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(SIGNALS_FILE, "w") as f:
        json.dump(signals, f, indent=2)


def _hex_to_sym(h: str) -> str:
    if not h or len(h) <= 3:
        return h or ""
    try:
        padded = h.ljust(40, "0")[:40]
        raw = bytes.fromhex(padded).decode("ascii", errors="ignore")
        name = raw.rstrip("\x00").strip()
        return name if name and name.isprintable() and len(name) >= 2 else h[:8]
    except:
        return h[:8]


def _add_to_registry(symbol: str, currency: str, issuer: str, tvl_xrp: float, source: str):
    """Inject a new token into the active registry immediately."""
    try:
        with open(REGISTRY_FILE) as f:
            reg = json.load(f)
    except:
        reg = {"tokens": [], "updated": ""}

    tokens = reg.get("tokens", [])
    key = f"{currency}:{issuer}"

    # Check not already in registry
    for t in tokens:
        if t.get("currency") == currency and t.get("issuer") == issuer:
            return  # already tracked

    tokens.append({
        "symbol":   symbol,
        "currency": currency,
        "issuer":   issuer,
        "tvl_xrp":  round(tvl_xrp, 2),
        "source":   source,
    })
    reg["tokens"] = tokens
    reg["updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    with open(REGISTRY_FILE, "w") as f:
        json.dump(reg, f, indent=2)

    logger.info(f"🆕 REALTIME: Added {symbol} to registry ({source}) TVL={tvl_xrp:.0f} XRP")


def _handle_amm_create(tx: dict):
    """New AMM pool created — add token to registry immediately."""
    amount  = tx.get("Amount", 0)
    amount2 = tx.get("Amount2", {})

    # We want XRP/Token pairs
    if isinstance(amount, str) and isinstance(amount2, dict):
        xrp_drops = int(amount)
        xrp = xrp_drops / 1e6
        currency = amount2.get("currency", "")
        issuer   = amount2.get("issuer", "")
        value    = float(amount2.get("value", 0))
    elif isinstance(amount, dict) and isinstance(amount2, str):
        xrp_drops = int(amount2)
        xrp = xrp_drops / 1e6
        currency = amount.get("currency", "")
        issuer   = amount.get("issuer", "")
        value    = float(amount.get("value", 0))
    else:
        return  # token/token pair, skip

    if not currency or not issuer:
        return
    if xrp < MIN_AMM_XRP:
        return
    if xrp > MAX_AMM_XRP:
        logger.debug(f"AMMCreate: {currency[:8]} TVL {xrp:.0f} XRP too large, skipping")
        return

    symbol = _hex_to_sym(currency)
    logger.info(f"🚀 NEW AMM: {symbol} | TVL={xrp:.1f} XRP | issuer={issuer[:12]}")

    # Add to registry immediately
    _add_to_registry(symbol, currency, issuer, xrp, "realtime_ammcreate")

    # Add to signals file
    signals = _load_signals()
    signals["new_tokens"][f"{currency}:{issuer}"] = {
        "symbol":      symbol,
        "currency":    currency,
        "issuer":      issuer,
        "tvl_xrp":     xrp,
        "detected_at": time.time(),
        "source":      "ammcreate",
    }
    signals["last_updated"] = time.time()
    _save_signals_throttled(signals)


def _handle_trustset(tx: dict):
    """TrustSet transaction — track bursts per issuer."""
    limit = tx.get("LimitAmount", {})
    if not isinstance(limit, dict):
        return

    currency = limit.get("currency", "")
    issuer   = limit.get("issuer", "")
    if not currency or not issuer:
        return

    key = f"{currency}:{issuer}"
    now = time.time()

    with _lock:
        if key not in _trustset_times:
            _trustset_times[key] = []
        _trustset_times[key].append(now)

        # Keep only last BURST_WINDOW seconds
        _trustset_times[key] = [t for t in _trustset_times[key] if now - t <= BURST_WINDOW]
        burst_count = len(_trustset_times[key])

    # Check if burst threshold hit
    if burst_count >= BURST_MIN and burst_count % 5 == 0:  # alert every 5 new ones after threshold
        symbol = _hex_to_sym(currency)
        logger.info(f"⚡ BURST: {symbol} — {burst_count} TrustSets in last {BURST_WINDOW//60}m")

        signals = _load_signals()
        alert_key = key
        prev = signals["velocity_alerts"].get(alert_key, {})
        prev_count = prev.get("burst_count", 0)

        # Only update if meaningfully new
        if burst_count > prev_count:
            signals["velocity_alerts"][alert_key] = {
                "symbol":      symbol,
                "currency":    currency,
                "issuer":      issuer,
                "burst_count": burst_count,
                "window_min":  BURST_WINDOW // 60,
                "updated_at":  now,
            }
            signals["last_updated"] = now
            _save_signals_throttled(signals)

            # Also inject into registry if not there
            _add_to_registry(symbol, currency, issuer, 0, "realtime_trustset_burst")

        # ── REALTIME SNIPER: fire immediately on elite burst (50+ TS/5min) ──
        # Only fire at exact 50 threshold (not every 5 after) — one shot per token
        if burst_count == 50:
            try:
                import realtime_sniper
                import scanner as _sc
                _price, _tvl, _, _ = _sc.get_token_price_and_tvl(symbol, issuer, currency=currency)
                realtime_sniper.on_burst_elite(
                    symbol=symbol, currency=currency, issuer=issuer,
                    burst_count=burst_count, tvl_xrp=_tvl or 0.0, price=_price or 0.0,
                )
            except Exception as _rse:
                logger.debug(f"Realtime sniper burst error: {_rse}")


def _handle_offer_create(tx: dict):
    """
    OfferCreate — track buy-side clusters AND CLOB price/volume.

    Two signals:
    1. Buy cluster: 5+ buys in 2 min = coordinated buying
    2. CLOB launch: 60+ TrustSets + 25+ XRP/5min = runner launching on orderbook
       (catches brizzly/PROPHET/PRSV which moved on CLOB not AMM)
    """
    taker_gets = tx.get("TakerGets", {})
    if not isinstance(taker_gets, dict):
        return  # XRP offer, not a token buy

    currency = taker_gets.get("currency", "")
    issuer   = taker_gets.get("issuer", "")
    taker_pays = tx.get("TakerPays", 0)

    # Must be buying a token WITH XRP (TakerPays = XRP drops)
    if not currency or not issuer or not isinstance(taker_pays, (int, str)):
        return

    try:
        xrp_spent = int(taker_pays) / 1_000_000
    except (ValueError, TypeError):
        return

    if xrp_spent < 0.5:  # ignore dust orders
        return

    # Skip stablecoins and fiat-pegged tokens — no meme upside
    sym = _hex_to_sym(currency).upper()
    try:
        from config import STABLECOIN_SKIP as _SC_SKIP
    except Exception:
        _SC_SKIP = {"USD","USDC","USDT","RLUSD","EUR","GBP","JPY","CNY","SGB","FLR","XAH","BTC","ETH","SOL"}
    if sym in _SC_SKIP:
        return

    symbol   = _hex_to_sym(currency)
    tok_amt  = float(taker_gets.get("value", 0))
    key      = f"{currency}:{issuer}"
    now      = time.time()

    # ── CLOB price/volume tracking (the brizzly fix) ──────────────────────
    # Get current TrustSet burst count for this token
    with _lock:
        ts_burst = len(_trustset_times.get(key, []))

    try:
        import clob_tracker
        clob_tracker.on_offer_create(
            currency    = currency,
            issuer      = issuer,
            symbol      = symbol,
            xrp_amount  = xrp_spent,
            token_amount= tok_amt,
            side        = "BUY",
            ts_burst_count = ts_burst,
        )
    except Exception as _cte:
        logger.debug(f"clob_tracker error: {_cte}")

    # ── Buy cluster tracking (count-based, existing logic) ────────────────
    with _lock:
        if key not in _offer_times:
            _offer_times[key] = []
        _offer_times[key].append({"ts": now, "xrp": xrp_spent})
        # Keep only last OFFER_WINDOW seconds
        _offer_times[key] = [o for o in _offer_times[key] if now - o["ts"] <= OFFER_WINDOW]
        offer_count = len(_offer_times[key])
        total_xrp   = sum(o["xrp"] for o in _offer_times[key])

    if offer_count >= OFFER_MIN and offer_count % 3 == 0:
        logger.info(f"📈 BUY CLUSTER: {symbol} — {offer_count} buys / {OFFER_WINDOW}s | {total_xrp:.1f} XRP volume")

        signals = _load_signals()
        if "momentum_alerts" not in signals:
            signals["momentum_alerts"] = {}

        prev = signals["momentum_alerts"].get(key, {})
        prev_count = prev.get("offer_count", 0)

        if offer_count > prev_count:
            signals["momentum_alerts"][key] = {
                "symbol":      symbol,
                "currency":    currency,
                "issuer":      issuer,
                "offer_count": offer_count,
                "total_xrp":   round(total_xrp, 2),
                "window_sec":  OFFER_WINDOW,
                "updated_at":  now,
            }
            signals["last_updated"] = now
            _save_signals_throttled(signals)

            # Inject into registry so bot can score it
            _add_to_registry(symbol, currency, issuer, 0, "realtime_buy_cluster")


async def _stream():
    """Main WebSocket stream loop."""
    subscribe_msg = {
        "command": "subscribe",
        "streams": ["transactions"]
    }

    logger.info("📡 Realtime watcher connecting to XRPL stream...")

    while True:
        try:
            async with websockets.connect(WS_URL, ping_interval=30, ping_timeout=10) as ws:
                await ws.send(json.dumps(subscribe_msg))
                resp = await ws.recv()
                logger.info("📡 Realtime watcher connected — watching live ledger")

                while True:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=60)
                        data = json.loads(msg)

                        if data.get("type") != "transaction":
                            continue

                        tx = data.get("transaction", {})
                        meta = data.get("meta", {})
                        result = meta.get("TransactionResult", "")

                        # Only process successful txs
                        if result != "tesSUCCESS":
                            continue

                        tt = tx.get("TransactionType", "")

                        if tt == "AMMCreate":
                            _handle_amm_create(tx)
                        elif tt == "TrustSet":
                            _handle_trustset(tx)
                        elif tt == "OfferCreate":
                            _handle_offer_create(tx)

                    except asyncio.TimeoutError:
                        # Send ping to keep alive
                        await ws.ping()

        except Exception as e:
            logger.warning(f"📡 Stream disconnected: {e} — reconnecting in 5s")
            await asyncio.sleep(5)


def _run_loop():
    """Run the async stream in a dedicated event loop (for threading)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_stream())
    except Exception as e:
        logger.error(f"Realtime watcher fatal: {e}")
    finally:
        loop.close()


def start_background():
    """Start the realtime watcher as a daemon thread. Call from bot.py."""
    t = threading.Thread(target=_run_loop, name="realtime-watcher", daemon=True)
    t.start()
    logger.info("📡 Realtime watcher thread started")
    return t


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s"
    )
    logger.info("Starting realtime watcher standalone...")
    asyncio.run(_stream())
