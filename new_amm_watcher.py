"""
new_amm_watcher.py — Detect newly created AMM pools on XRPL.

Polls recent ledgers for AMMCreate transactions, adds qualifying tokens
to the active registry for the scanner to track.

PHX lesson: launched with 102 XRP TVL — never appeared in xpmarket because
it sorts by liquidity desc and tiny pools don't make the cut.
Solution: watch for AMMCreate events directly from ledger history.

Run: standalone (python3 new_amm_watcher.py) or imported by bot.py.
"""

import json, os, time, requests, logging
from datetime import datetime, timezone
from config import CLIO_URL, STATE_DIR

log = logging.getLogger("bot")

WATCHER_STATE = os.path.join(STATE_DIR, "amm_watcher.json")
REGISTRY_FILE = os.path.join(STATE_DIR, "active_registry.json")

# Min XRP to consider a new pool (don't track pure dust)
MIN_NEW_POOL_XRP = 50

# Max age (ledgers) to look back each check — ~20 ledgers = ~1 min
LOOKBACK_LEDGERS = 300   # ~15 min window


def _rpc(method, params):
    try:
        r = requests.post(CLIO_URL, json={"method": method, "params": [params]}, timeout=12)
        result = r.json().get("result", {})
        if isinstance(result, dict) and result.get("error") == "slowDown":
            time.sleep(2)
            return {}
        return result
    except Exception as e:
        log.debug(f"rpc error: {e}")
        return {}


def _load_state():
    try:
        with open(WATCHER_STATE) as f:
            return json.load(f)
    except:
        return {"last_ledger": 0, "seen_amms": []}


def _save_state(state):
    with open(WATCHER_STATE, "w") as f:
        json.dump(state, f, indent=2)


def _hex_to_sym(h):
    """Convert XRPL hex currency to readable symbol."""
    if not h or len(h) <= 3:
        return h or ""
    try:
        padded = h.ljust(40, "0")[:40]
        raw = bytes.fromhex(padded).decode("ascii", errors="ignore")
        name = raw.rstrip("\x00").strip()
        if name and name.isprintable():
            return name
        cleaned = h.rstrip("0")
        if len(cleaned) % 2 != 0:
            cleaned += "0"
        return bytes.fromhex(cleaned).decode("ascii").rstrip("\x00").strip()
    except:
        return h[:6]


def _merge_into_registry(token: dict):
    """Add a new token to active_registry.json."""
    try:
        with open(REGISTRY_FILE) as f:
            d = json.load(f)
    except:
        d = {"tokens": []}

    tokens = d.get("tokens", d) if isinstance(d, dict) else d
    existing = {(t.get("currency",""), t.get("issuer","")) for t in tokens}

    key = (token.get("currency",""), token.get("issuer",""))
    if key not in existing:
        tokens.append(token)
        out = {"tokens": tokens} if isinstance(d, dict) else tokens
        with open(REGISTRY_FILE, "w") as f:
            json.dump(out, f, indent=2)
        log.info(f"🆕 New AMM token added to registry: {token['symbol']} (TVL={token['tvl_xrp']:.0f} XRP)")
        return True
    return False


def scan_new_amms() -> list:
    """
    Check recent ledgers for new AMMCreate transactions.
    Returns list of new tokens found.
    """
    state = _load_state()
    new_tokens = []

    # Get current validated ledger
    result = _rpc("ledger", {"ledger_index": "validated"})
    current_ledger = result.get("ledger_index", 0)
    if not current_ledger:
        return []

    start_ledger = max(state.get("last_ledger", current_ledger - LOOKBACK_LEDGERS), 
                       current_ledger - LOOKBACK_LEDGERS)

    if start_ledger >= current_ledger:
        return []

    log.debug(f"Scanning ledgers {start_ledger}–{current_ledger} for new AMMs")

    # Walk ledgers looking for AMMCreate txs
    # Use account_tx on the AMM factory isn't possible; scan via tx search
    # Instead: poll txns on recent ledgers in chunks
    # Efficient approach: scan a sample of recent ledgers

    checked = 0
    for ledger_idx in range(current_ledger - min(LOOKBACK_LEDGERS, 200), current_ledger, 10):
        time.sleep(0.15)
        result = _rpc("ledger", {"ledger_index": ledger_idx, "transactions": True, "expand": True})
        txs = result.get("ledger", {}).get("transactions", [])

        for tx in txs:
            if not isinstance(tx, dict):
                continue
            if tx.get("TransactionType") != "AMMCreate":
                continue

            # Parse the new AMM
            amt1 = tx.get("Amount", "0")
            amt2 = tx.get("Amount2", {})

            # Determine which side is XRP
            if isinstance(amt1, str) and isinstance(amt2, dict):
                xrp_drops = int(amt1)
                token_side = amt2
            elif isinstance(amt2, str) and isinstance(amt1, dict):
                xrp_drops = int(amt2)
                token_side = amt1
            else:
                continue

            xrp = xrp_drops / 1e6
            if xrp < MIN_NEW_POOL_XRP:
                continue   # Too small even to track

            currency = token_side.get("currency", "")
            issuer   = token_side.get("issuer", "")
            symbol   = _hex_to_sym(currency) if len(currency) > 3 else currency

            if not currency or not issuer or not symbol:
                continue

            # Check we haven't seen this already
            amm_key = f"{currency}:{issuer}"
            if amm_key in state.get("seen_amms", []):
                continue

            state.setdefault("seen_amms", []).append(amm_key)

            token = {
                "symbol": symbol,
                "currency": currency,
                "issuer": issuer,
                "tvl_xrp": xrp * 2,
                "source": "amm_watcher",
            }
            new_tokens.append(token)
            _merge_into_registry(token)

            dt = datetime.now(timezone.utc).strftime("%H:%M")
            log.info(f"🆕 New AMM detected at {dt}: {symbol} | {xrp:.0f} XRP launch | issuer={issuer}")

        checked += 1

    state["last_ledger"] = current_ledger
    # Keep seen_amms list manageable (last 500)
    state["seen_amms"] = state.get("seen_amms", [])[-500:]
    _save_state(state)

    return new_tokens


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    print("Scanning for new AMMs...")
    found = scan_new_amms()
    print(f"Found {len(found)} new AMM tokens:")
    for t in found:
        print(f"  {t['symbol']} | {t['tvl_xrp']:.0f} XRP TVL | {t['issuer']}")
