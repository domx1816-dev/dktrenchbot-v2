#!/usr/bin/env python3
"""
amm_launch_watcher.py — Real-time XRPL AMM launch detector.

Subscribes to the XRPL ledger via WebSocket and watches for:
  1. AMMCreate transactions → brand new AMM pools launching
  2. Large OfferCreate bursts → early buy signals (whale accumulation)

When a new launch is detected:
  - Scores it with winner_dna.py immediately
  - Injects into active_registry.json so scanner picks it up
  - Writes a hot signal to state/hot_launches.json with score + DNA flags
  - Notifies via TG if score is strong enough

Latency: ~1-3 seconds from on-chain to registry. vs 15-60min via xpmarket API.
"""

import asyncio
import json
import os
import sys
import time
import requests
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from warden_security_patch import send_telegram_message, rpc_call

# ── Paths ─────────────────────────────────────────────────────────────────────
BOT_DIR    = Path(__file__).parent
STATE_DIR  = BOT_DIR / "state"
REGISTRY_F = STATE_DIR / "active_registry.json"
HOT_FILE   = STATE_DIR / "hot_launches.json"
LOG_FILE   = STATE_DIR / "amm_watcher.log"

WS_URL     = "wss://rpc.xrplclaw.com"

# Minimum XRP TVL to care about a new launch
MIN_LAUNCH_TVL = 500   # XRP — even very thin launches are worth watching

os.makedirs(STATE_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("amm_watcher")


def send_tg(msg: str):
    try:
        hot = load_hot_launches()
        chat_id = hot.get("tg_chat_id")
        if not chat_id:
            log.warning("No tg_chat_id set —TG notification skipped.")
            return
        send_telegram_message(msg, str(chat_id))
    except Exception as e:
        log.warning(f"TG send error: {e}")


def load_hot_launches() -> dict:
    try:
        if HOT_FILE.exists():
            return json.loads(HOT_FILE.read_text())
    except:
        pass
    return {"launches": {}, "tg_chat_id": None}


def save_hot_launches(data: dict):
    tmp = str(HOT_FILE) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, str(HOT_FILE))


def load_registry() -> list:
    try:
        if REGISTRY_F.exists():
            data = json.loads(REGISTRY_F.read_text())
            return data.get("tokens", data) if isinstance(data, dict) else data
    except:
        pass
    return []


def save_registry(tokens: list):
    tmp = str(REGISTRY_F) + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"tokens": tokens, "updated": time.time()}, f, indent=2)
    os.replace(tmp, str(REGISTRY_F))


def hex_to_symbol(hex_str: str) -> str:
    """Convert XRPL hex currency code to ASCII symbol."""
    try:
        if len(hex_str) == 3:
            return hex_str
        b = bytes.fromhex(hex_str)
        s = b.decode("ascii").strip("\x00").strip()
        return s if s.isprintable() and s.strip() else hex_str[:6]
    except:
        return hex_str[:8]


def get_amm_info(asset1: dict, asset2: dict) -> Optional[dict]:
    """Fetch AMM pool info for a token pair."""
    r = rpc_call("amm_info", {"asset": asset1, "asset2": asset2})
    return r.get("amm")


def analyze_launch(currency: str, issuer: str, amm_data: dict) -> dict:
    """
    Full analysis of a newly launched AMM pool.
    Returns enriched token data with DNA score.
    """
    symbol = hex_to_symbol(currency) if len(currency) > 3 else currency

    # Extract TVL from AMM data
    amount1 = amm_data.get("amount", "0")
    tvl_xrp = int(amount1) / 1e6 if isinstance(amount1, str) else 0

    log.info(f"Analyzing launch: {symbol} | TVL={tvl_xrp:.0f} XRP | issuer={issuer[:16]}...")

    # Score with winner DNA
    dna_score = 0
    dna_flags = []
    dna_details = {}
    try:
        sys.path.insert(0, str(BOT_DIR))
        import winner_dna as wdna
        result = wdna.get_winner_dna_score(symbol, issuer, currency, tvl_xrp)
        dna_score   = result.get("bonus", 0)
        dna_flags   = result.get("flags", [])
        dna_details = result.get("details", {})
    except Exception as e:
        log.warning(f"DNA score error for {symbol}: {e}")

    # Calculate price
    amount2 = amm_data.get("amount2", {})
    token_amount = float(amount2.get("value", 0)) if isinstance(amount2, dict) else 0
    price_xrp = tvl_xrp / token_amount if token_amount > 0 else 0

    return {
        "symbol":      symbol,
        "currency":    currency,
        "issuer":      issuer,
        "tvl_xrp":     tvl_xrp,
        "price_xrp":   price_xrp,
        "dna_score":   dna_score,
        "dna_flags":   dna_flags,
        "dna_details": dna_details,
        "launch_time": time.time(),
        "source":      "amm_watcher",
    }


def inject_to_registry(token_data: dict):
    """Add new token to active_registry so scanner picks it up immediately."""
    tokens = load_registry()
    issuer = token_data["issuer"]
    currency = token_data["currency"]

    # Check if already tracked
    for t in tokens:
        if t.get("issuer") == issuer and t.get("currency") == currency:
            log.info(f"Already in registry: {token_data['symbol']}")
            return False

    tokens.append({
        "symbol":    token_data["symbol"],
        "issuer":    issuer,
        "currency":  currency,
        "last_tvl":  token_data["tvl_xrp"],
        "source":    "amm_watcher",
        "added_at":  time.time(),
    })
    save_registry(tokens)
    log.info(f"✅ Injected {token_data['symbol']} into registry ({len(tokens)} total)")
    return True


def write_hot_signal(token_data: dict):
    """Write to hot_launches.json — bot reads this for immediate score boost."""
    hot = load_hot_launches()
    key = f"{token_data['currency']}:{token_data['issuer']}"

    hot["launches"][key] = {
        "symbol":      token_data["symbol"],
        "dna_score":   token_data["dna_score"],
        "dna_flags":   token_data["dna_flags"],
        "tvl_xrp":     token_data["tvl_xrp"],
        "launch_time": token_data["launch_time"],
        "expires":     time.time() + 3600,  # signal valid for 1h
        "notified":    False,
    }
    save_hot_launches(hot)


def notify_if_strong(token_data: dict):
    """Send TG alert if this launch looks like a winner."""
    score = token_data["dna_score"]
    sym   = token_data["symbol"]
    tvl   = token_data["tvl_xrp"]
    flags = token_data["dna_flags"]
    details = token_data["dna_details"]

    if score < 20:
        return  # not interesting enough

    stars = "🔥🔥🔥" if score >= 50 else ("🔥🔥" if score >= 35 else "🔥")
    flag_str = " | ".join(flags[:4]) if flags else "none"
    holders = details.get("holder_count", "?")
    age_h = details.get("age_hours", "?")
    if isinstance(age_h, float):
        age_h = f"{age_h:.1f}h"

    msg = (
        f"{stars} *NEW LAUNCH DETECTED*\n"
        f"Token: `{sym}`\n"
        f"DNA Score: `+{score} pts`\n"
        f"TVL: `{tvl:.0f} XRP`\n"
        f"Holders: `{holders}` | Age: `{age_h}`\n"
        f"Signals: `{flag_str}`\n"
        f"_Bot will auto-scan next cycle_"
    )
    send_tg(msg)
    log.info(f"TG alert sent for {sym} (DNA={score})")


async def watch_ledger():
    """Subscribe to XRPL WebSocket and watch for AMMCreate transactions."""
    import websockets

    log.info(f"Connecting to {WS_URL}...")
    reconnect_delay = 5

    while True:
        try:
            async with websockets.connect(WS_URL, ping_interval=20, ping_timeout=10) as ws:
                # Subscribe to all validated transactions
                await ws.send(json.dumps({
                    "command": "subscribe",
                    "streams": ["transactions"]
                }))

                resp = await ws.recv()
                sub = json.loads(resp)
                log.info(f"Subscribed: {sub.get('status', 'unknown')}")
                reconnect_delay = 5  # reset on success

                while True:
                    raw = await ws.recv()
                    msg = json.loads(raw)

                    # Only care about validated transactions
                    if msg.get("type") != "transaction":
                        continue
                    if msg.get("status") != "closed" and msg.get("validated") is not True:
                        # Some nodes send engine_result instead
                        meta = msg.get("meta", {})
                        if meta.get("TransactionResult") != "tesSUCCESS":
                            continue

                    tx = msg.get("transaction", msg.get("tx_json", {}))
                    if not tx:
                        continue

                    tx_type = tx.get("TransactionType", "")

                    # ── AMMCreate: brand new pool ──────────────────────────────
                    if tx_type == "AMMCreate":
                        await handle_amm_create(tx, msg.get("meta", {}))

                    # ── Large OfferCreate burst: whale accumulation ────────────
                    elif tx_type == "OfferCreate":
                        await handle_offer_burst(tx, msg.get("meta", {}))

        except Exception as e:
            log.warning(f"WS error: {e} — reconnecting in {reconnect_delay}s")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 60)


async def handle_amm_create(tx: dict, meta: dict):
    """Handle a new AMMCreate transaction."""
    # Extract token info from the transaction
    a1 = tx.get("Amount", {})
    a2 = tx.get("Amount2", {})

    # Figure out which side is XRP and which is the token
    if isinstance(a1, str) and isinstance(a2, dict):
        xrp_drops = int(a1)
        token = a2
    elif isinstance(a2, str) and isinstance(a1, dict):
        xrp_drops = int(a2)
        token = a1
    else:
        return  # token/token pair, not XRP/token

    tvl_xrp = xrp_drops / 1e6
    if tvl_xrp < MIN_LAUNCH_TVL:
        log.debug(f"AMMCreate too thin: {tvl_xrp:.0f} XRP — skipping")
        return

    currency = token.get("currency", "")
    issuer   = token.get("issuer", "")
    if not currency or not issuer:
        return

    symbol = hex_to_symbol(currency)
    log.info(f"🚀 NEW AMM LAUNCH: {symbol} | {tvl_xrp:.0f} XRP | creator={tx.get('Account','?')[:16]}")

    # Small delay to let ledger settle then fetch full AMM data
    await asyncio.sleep(2)
    amm = get_amm_info({"currency": "XRP"}, {"currency": currency, "issuer": issuer})
    if not amm:
        # Build minimal AMM data from tx itself
        amm = {"amount": str(xrp_drops), "amount2": token}

    token_data = analyze_launch(currency, issuer, amm)
    write_hot_signal(token_data)
    inject_to_registry(token_data)
    notify_if_strong(token_data)

    log.info(f"  {symbol}: DNA={token_data['dna_score']} flags={token_data['dna_flags']}")


# Track recent OfferCreate activity per issuer to detect accumulation bursts
_offer_tracker: Dict[str, list] = {}

async def handle_offer_burst(tx: dict, meta: dict):
    """
    Detect whale accumulation: 3+ large buy offers on the same token
    within 60 seconds = early signal even before price moves.
    """
    # Check if this is a token buy (taker_pays=XRP, taker_gets=token)
    pays = tx.get("TakerPays", {})
    gets = tx.get("TakerGets", {})

    if not (isinstance(pays, str) and isinstance(gets, dict)):
        return  # not a buy

    xrp_amount = int(pays) / 1e6
    if xrp_amount < 50:  # only care about 50+ XRP orders
        return

    currency = gets.get("currency", "")
    issuer   = gets.get("issuer", "")
    if not currency or not issuer:
        return

    # Skip stablecoins and known large-volume non-meme tokens
    symbol_check = hex_to_symbol(currency).upper()
    SKIP_SYMBOLS = {"USD", "USDC", "USDT", "RLUSD", "BTC", "ETH", "XLM",
                    "EUR", "EURO", "EUROP", "GBP", "JPY", "CNY", "AUD", "CAD",
                    "SOLO", "CSC", "SGB", "FLR", "XAH", "CORE", "EVR",
                    "XUSD", "MXRP", "AUDD", "XSGD", "XCHF", "GYEN"}
    # Also skip anything that looks like a fiat peg by name
    FIAT_PATTERNS = ("USD", "EUR", "GBP", "JPY", "CNY", "AUD", "CAD", "STABLE", "PEGGED")
    if symbol_check in SKIP_SYMBOLS:
        return
    if any(symbol_check.startswith(p) or symbol_check.endswith(p) for p in FIAT_PATTERNS):
        return

    # Track this buy
    key = f"{currency}:{issuer}"
    now = time.time()
    if key not in _offer_tracker:
        _offer_tracker[key] = []
    _offer_tracker[key].append({"time": now, "xrp": xrp_amount})

    # Clean old entries (>60s)
    _offer_tracker[key] = [e for e in _offer_tracker[key] if now - e["time"] < 60]

    buys = _offer_tracker[key]
    total_xrp = sum(e["xrp"] for e in buys)
    count = len(buys)

    # 3+ buys totaling 200+ XRP in 60s = accumulation burst
    if count >= 3 and total_xrp >= 200:
        symbol = hex_to_symbol(currency)
        log.info(f"⚡ ACCUMULATION BURST: {symbol} — {count} buys, {total_xrp:.0f} XRP in 60s")

        # Check if already in registry
        registry = load_registry()
        already = any(t.get("issuer") == issuer for t in registry)

        if not already:
            # New token — fetch AMM and add
            amm = get_amm_info({"currency": "XRP"}, {"currency": currency, "issuer": issuer})
            if amm:
                token_data = analyze_launch(currency, issuer, amm)
                token_data["dna_flags"].append(f"whale_burst_{count}buys_{total_xrp:.0f}xrp")
                token_data["dna_score"] = min(token_data["dna_score"] + 20, 60)  # burst bonus
                write_hot_signal(token_data)
                inject_to_registry(token_data)
                notify_if_strong(token_data)
        else:
            # Already tracked — boost its hot signal score
            hot = load_hot_launches()
            if key in hot.get("launches", {}):
                hot["launches"][key]["dna_score"] = min(
                    hot["launches"][key].get("dna_score", 0) + 15, 60
                )
                hot["launches"][key]["dna_flags"].append(f"burst_{count}x_{total_xrp:.0f}xrp")
                hot["launches"][key]["expires"] = time.time() + 1800
                save_hot_launches(hot)
                log.info(f"  Boosted hot signal for {symbol}")

        # Reset tracker so we don't spam
        _offer_tracker[key] = []


def main():
    log.info("AMM Launch Watcher starting...")
    log.info(f"Registry: {REGISTRY_F}")
    log.info(f"Hot signals: {HOT_FILE}")
    log.info(f"Min TVL: {MIN_LAUNCH_TVL} XRP")

    try:
        import websockets
    except ImportError:
        log.info("Installing websockets...")
        os.system("pip install websockets -q")
        import websockets

    asyncio.run(watch_ledger())


if __name__ == "__main__":
    main()
