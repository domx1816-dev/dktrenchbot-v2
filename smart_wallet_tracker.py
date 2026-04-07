"""
smart_wallet_tracker.py — Track known smart wallets on XRPL.

These wallets were identified as early movers / top holders in PHX, ROOSEVELT, DONNIE.
When any of them opens a new trustline = they just bought a new token = early signal.

Runs alongside the bot. When a new token is detected, it's injected into
active_registry.json with a +20 score bonus in the scanner.
"""

import json, os, time, requests, logging
from datetime import datetime, timezone
from config import CLIO_URL, STATE_DIR

log = logging.getLogger("bot")

TRACKER_STATE = os.path.join(STATE_DIR, "smart_wallet_state.json")
REGISTRY_FILE = os.path.join(STATE_DIR, "active_registry.json")

# ── Known smart wallets ────────────────────────────────────────────────────
# Discovered by studying PHX / ROOSEVELT / DONNIE top holders & early buyers
SMART_WALLETS = {
    # ROOSEVELT top holder — 414 XRP balance, 27 token holdings, serial meme buyer
    "rGeaXk8Hgh9qA3aQYj9MACMwqzUdB38DH6": {"name": "ROOS_FirstMover",  "trust": "high"},
    # ROOSEVELT largest bag holder — 682 XRP, active trader
    "rfgSotfAUmCueXUiBAg4nhBAgcHmKgBZ54": {"name": "ROOS_TopHolder",   "trust": "high"},
    # DONNIE top holder — holds FUZZY + STIMPY + DONNIE = political meme specialist
    "rHoLiJz8tkvzFUz3HyE5AJGvi5vGTTHF3w": {"name": "DONNIE_TopHolder", "trust": "high"},
    # DONNIE #2 holder — 216M tokens
    "rUEnHSg3tLbvD89yDXggsTH62K8kT9BEHD": {"name": "DONNIE_Holder2",   "trust": "medium"},
    # PHX top holder — holds PHX + another unknown token
    "r9PnQbMnno1knm4WT1paLqtGRQiN2ztUzt": {"name": "PHX_TopHolder",    "trust": "medium"},
    # PHX dev / first buyer
    "rNZLDrnqtoiXiqEN971txs8ptTvnJ7JnVj": {"name": "PHX_Dev",          "trust": "medium"},
    # DONNIE #3 holder
    "rwtPwXNZ2Dne6ZXfAU5qWSMzGPmJtH3KyC": {"name": "DONNIE_Holder3",   "trust": "medium"},
}

# Score bonus to inject when a smart wallet buys a new token
SCORE_BONUS = {
    "high":   25,   # high-trust wallet buy = +25 to score
    "medium": 15,   # medium-trust = +15
}

# ── Helpers ────────────────────────────────────────────────────────────────

def _rpc(method, params):
    try:
        r = requests.post(CLIO_URL, json={"method": method, "params": [params]}, timeout=10)
        res = r.json().get("result", {})
        if isinstance(res, dict) and res.get("error") == "slowDown":
            time.sleep(2)
            return {}
        return res
    except:
        return {}

def _hex_to_sym(h):
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

def _load_state():
    try:
        with open(TRACKER_STATE) as f:
            return json.load(f)
    except:
        # Bootstrap: snapshot current trustlines for all wallets
        return {"wallet_trustlines": {}, "alerts": []}

def _save_state(state):
    os.makedirs(os.path.dirname(TRACKER_STATE), exist_ok=True)
    with open(TRACKER_STATE, "w") as f:
        json.dump(state, f, indent=2)

def _merge_into_registry(token: dict, score_bonus: int = 0):
    """Add newly discovered token to active_registry.json."""
    try:
        with open(REGISTRY_FILE) as f:
            d = json.load(f)
        tokens = d.get("tokens", d) if isinstance(d, dict) else d
    except:
        tokens = []

    existing_keys = {(t.get("currency",""), t.get("issuer","")) for t in tokens}
    key = (token.get("currency",""), token.get("issuer",""))
    if key in existing_keys:
        return False

    token["score_bonus"] = score_bonus
    token["source"] = "smart_wallet"
    tokens.append(token)

    if isinstance(d, dict):
        d["tokens"] = tokens
        out = d
    else:
        out = tokens

    with open(REGISTRY_FILE, "w") as f:
        json.dump(out, f, indent=2)
    return True

# ── Main scan ──────────────────────────────────────────────────────────────

def scan_smart_wallets():
    """
    Check each smart wallet's current trustlines.
    If any NEW trustline appeared since last scan → they bought a new token.
    Inject that token into the registry immediately.
    Returns list of new token alerts.
    """
    state = _load_state()
    alerts = []

    for address, meta in SMART_WALLETS.items():
        wallet_name = meta["name"]
        trust_level = meta["trust"]
        time.sleep(0.4)

        # Fetch current trustlines
        result = _rpc("account_lines", {"account": address, "limit": 200})
        lines = result.get("lines", [])

        current_issuers = {}
        for line in lines:
            issuer   = line.get("account", "")
            currency = line.get("currency", "")
            balance  = abs(float(line.get("balance", 0)))
            if balance > 0 and issuer and currency:
                current_issuers[f"{currency}:{issuer}"] = {
                    "currency": currency,
                    "issuer":   issuer,
                    "balance":  balance,
                    "symbol":   _hex_to_sym(currency) if len(currency) > 3 else currency,
                }

        prev_issuers = set(state.get("wallet_trustlines", {}).get(address, []))
        current_keys = set(current_issuers.keys())
        new_keys = current_keys - prev_issuers

        for key in new_keys:
            token_info = current_issuers[key]
            sym    = token_info["symbol"]
            issuer = token_info["issuer"]
            currency = token_info["currency"]
            bonus  = SCORE_BONUS.get(trust_level, 10)

            added = _merge_into_registry({
                "symbol":   sym,
                "currency": currency,
                "issuer":   issuer,
                "tvl_xrp":  0,
            }, score_bonus=bonus)

            alert = {
                "ts":          datetime.now(timezone.utc).isoformat(),
                "wallet":      wallet_name,
                "wallet_addr": address,
                "trust":       trust_level,
                "symbol":      sym,
                "issuer":      issuer,
                "score_bonus": bonus,
                "new_to_registry": added,
            }
            alerts.append(alert)
            log.info(
                f"🚨 SMART WALLET ALERT: {wallet_name} bought {sym} "
                f"(trust={trust_level}, +{bonus} score bonus)"
            )

        # Update snapshot
        state.setdefault("wallet_trustlines", {})[address] = list(current_keys)

    # Keep last 100 alerts
    state["alerts"] = (state.get("alerts", []) + alerts)[-100:]
    _save_state(state)
    return alerts


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    print(f"Scanning {len(SMART_WALLETS)} smart wallets...")
    found = scan_smart_wallets()
    if found:
        print(f"\n🚨 {len(found)} NEW TOKEN ALERTS:")
        for a in found:
            print(f"  {a['wallet']:20} bought {a['symbol']:10} | +{a['score_bonus']} score bonus")
    else:
        print("No new purchases detected.")
