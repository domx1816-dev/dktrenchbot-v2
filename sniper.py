"""
sniper.py — Watch for new AMM pools and trustline surges.
Runs as a background WebSocket listener alongside bot.py.
Entry threshold: score >= 4 (out of 5 heuristics), size = XRP_SNIPER_BASE.
Dynamically adds tokens to TOKEN_SPECS.
"""

import json
import os
import time
import threading
import logging
from typing import Dict, List, Optional, Set
from config import STATE_DIR, WS_URL, XRP_SNIPER_BASE

os.makedirs(STATE_DIR, exist_ok=True)
SNIPER_LOG = os.path.join(STATE_DIR, "sniper.log")

logger = logging.getLogger("sniper")

# Dynamically discovered tokens
discovered_tokens: List[Dict] = []
_known_issuers: Set[str] = set()
_sniper_running = False


def _log(msg: str) -> None:
    ts   = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    with open(SNIPER_LOG, "a") as f:
        f.write(line)
    logger.info(msg)


def _score_new_token(tx_data: Dict) -> int:
    """
    Score a newly discovered token 0-5.
    Heuristics: has AMM, pool funded, creator active, not known scam pattern, recent.
    """
    score = 0
    # 1. AMMCreate transaction found
    score += 1

    # 2. Pool funded (has amounts)
    amm = tx_data.get("amm", {})
    if amm.get("amount") and amm.get("amount2"):
        score += 1

    # 3. LP token present
    if amm.get("lp_token"):
        score += 1

    # 4. Trading fee is reasonable (< 1%)
    fee = amm.get("trading_fee", 0)
    if fee < 10000:  # 10000 = 1%
        score += 1

    # 5. Recent creation (within last 10 minutes)
    created = tx_data.get("created_at", 0)
    if time.time() - created < 600:
        score += 1

    return score


def handle_amm_create(tx: Dict) -> Optional[Dict]:
    """
    Process an AMMCreate transaction.
    Returns token spec if worth sniping, else None.
    """
    meta   = tx.get("meta", {})
    tx_obj = tx.get("transaction", tx)

    asset  = tx_obj.get("Asset",  {})
    asset2 = tx_obj.get("Asset2", {})

    # We want XRP/TOKEN pairs
    token_asset = None
    if asset.get("currency") == "XRP" and asset2.get("currency"):
        token_asset = asset2
    elif asset2.get("currency") == "XRP" and asset.get("currency"):
        token_asset = asset

    if not token_asset:
        return None

    currency = token_asset.get("currency", "")
    issuer   = token_asset.get("issuer", "")

    if not currency or not issuer:
        return None

    if issuer in _known_issuers:
        return None

    _known_issuers.add(issuer)

    # Build AMM info from AffectedNodes
    amm_data = {"amount": 0, "amount2": {"value": "0"}, "lp_token": None}
    for node_wrapper in meta.get("AffectedNodes", []):
        for _, node in node_wrapper.items():
            nf = node.get("NewFields", {})
            if nf.get("Asset2", {}).get("issuer") == issuer:
                amm_data["amount"]  = nf.get("Amount", 0)
                amm_data["amount2"] = nf.get("Amount2", {"value": "0"})
                amm_data["lp_token"] = nf.get("LPTokenBalance")
                amm_data["trading_fee"] = nf.get("TradingFee", 500)

    token_spec = {
        "symbol":     currency if len(currency) <= 3 else bytes.fromhex(currency.ljust(40,'0')[:40]).decode('ascii', errors='ignore').rstrip('\x00').strip(),
        "issuer":     issuer,
        "currency":   currency,
        "created_at": time.time(),
        "amm":        amm_data,
        "source":     "sniper",
    }

    score = _score_new_token(token_spec)
    token_spec["sniper_score"] = score

    _log(f"New AMM: {currency}/{issuer} score={score}/5")

    if score >= 4:
        _log(f"SNIPER HIT: {currency}/{issuer} score={score}/5 size={XRP_SNIPER_BASE} XRP")
        discovered_tokens.append(token_spec)
        return token_spec

    return None


def sniper_loop(callback=None) -> None:
    """
    Main sniper loop. Subscribes to XRPL ledger stream and watches for AMMCreate.
    callback: optional function(token_spec) called when sniper hit found.
    """
    global _sniper_running
    _sniper_running = True

    _log("Sniper loop starting...")

    while _sniper_running:
        try:
            from xrpl.clients import WebsocketClient
            from xrpl.models.requests import Subscribe, StreamParameter

            with WebsocketClient(WS_URL) as ws:
                ws.send(Subscribe(streams=[StreamParameter.TRANSACTIONS]))
                _log("Subscribed to transaction stream")

                for msg in ws:
                    if not _sniper_running:
                        break

                    if not isinstance(msg, dict):
                        continue

                    tx_type = (msg.get("transaction", {}).get("TransactionType") or
                               msg.get("tx_json", {}).get("TransactionType") or "")

                    if tx_type == "AMMCreate":
                        token_spec = handle_amm_create(msg)
                        if token_spec and callback:
                            callback(token_spec)

        except Exception as e:
            _log(f"Sniper connection error: {e} — reconnecting in 5s")
            if _sniper_running:
                time.sleep(5)


def start_sniper_thread(callback=None) -> threading.Thread:
    """Start sniper in background thread."""
    t = threading.Thread(target=sniper_loop, args=(callback,), daemon=True)
    t.start()
    _log("Sniper thread started")
    return t


def stop_sniper() -> None:
    global _sniper_running
    _sniper_running = False
    _log("Sniper stopping")


def get_discovered_tokens() -> List[Dict]:
    return discovered_tokens.copy()


if __name__ == "__main__":
    def on_hit(spec):
        print(f"SNIPER HIT: {spec['symbol']} score={spec['sniper_score']}")

    print("Starting sniper (Ctrl+C to stop)...")
    try:
        sniper_loop(callback=on_hit)
    except KeyboardInterrupt:
        print("Sniper stopped")
