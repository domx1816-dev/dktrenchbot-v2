"""
trustset_watcher.py — TrustSet Velocity Detector

Watches newly launched XRPL tokens for rapid TrustSet accumulation.
This is the PHX signal: 137 holders in the first hour on a token seeded
with only 51 XRP → 2200x move over 4 days.

Signal: NEW AMM (< 6h old, TVL < 500 XRP) with 15+ TrustSets in last hour
        = coordinated community launch, enter BEFORE price moves.

Entry: 5 XRP (micro-cap sizing). Stop: -20%. Hold for the wave.
"""

import json, time, os, logging, requests
from typing import Dict, List

logger = logging.getLogger("trustset_watcher")

CLIO = os.environ.get("CLIO_URL", "https://rpc.xrplclaw.com")
STATE_FILE = os.path.join(os.path.dirname(__file__), "state", "trustset_watchlist.json")

# Signal thresholds
MIN_TRUSTSETS_1H  = 8      # min TrustSets in last hour to flag (was 15 — lowered to catch DKLEDGER-type early launches)
MIN_TRUSTSETS_ABS = 15     # min total TrustSets on the token (was 25)
MAX_AMM_AGE_H     = 24     # only watch tokens launched in last 24h
MAX_SEED_XRP      = 1000   # seed XRP < this = micro-launch (PHX was 51)
MAX_ENTRY_TVL     = 3000   # don't enter if TVL already > 3000 XRP (missed it)
MIN_ENTRY_TVL     = 30     # need at least 30 XRP TVL to have a working AMM

XRPL_EPOCH = 946684800

def _rpc(method, params, timeout=10):
    try:
        r = requests.post(CLIO, json={"method": method, "params": [params]}, timeout=timeout)
        return r.json().get("result", {})
    except Exception as e:
        logger.debug(f"RPC error {method}: {e}")
        return {}

def _load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except:
        return {"watchlist": {}, "alerted": [], "last_scan": 0}

def _save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def _get_trustset_velocity(issuer: str) -> dict:
    """Count TrustSets in last 1h and total for a token issuer."""
    now = time.time()
    cutoff_1h = now - 3600
    cutoff_6h = now - 21600

    txs = _rpc("account_tx", {"account": issuer, "limit": 400, "forward": False})
    transactions = txs.get("transactions", [])

    total_trustsets = 0
    last_1h = 0
    last_6h = 0
    unique_wallets = set()
    oldest_ts = now

    for t in transactions:
        tx = t.get("tx", t.get("transaction", {}))
        if tx.get("TransactionType") != "TrustSet":
            continue
        ts = tx.get("date", 0) + XRPL_EPOCH
        acct = tx.get("Account", "")
        total_trustsets += 1
        unique_wallets.add(acct)
        if ts < oldest_ts:
            oldest_ts = ts
        if ts >= cutoff_1h:
            last_1h += 1
        if ts >= cutoff_6h:
            last_6h += 1

    age_h = (now - oldest_ts) / 3600 if oldest_ts < now else 0

    return {
        "total": total_trustsets,
        "last_1h": last_1h,
        "last_6h": last_6h,
        "unique_wallets": len(unique_wallets),
        "age_h": age_h,
    }

def _get_amm_info(issuer: str, currency: str) -> dict:
    """
    Get current AMM state with fallback for CLIO RPC bugs.
    Uses scanner.get_amm_info which has 4-method fallback chain.
    """
    try:
        from scanner import get_amm_info as robust_get_amm, hex_to_name
        symbol = hex_to_name(currency) if len(currency) > 3 else currency
        amm_dict = robust_get_amm(symbol, issuer, currency=currency)
        if not amm_dict:
            return {}
        amm = amm_dict
        xrp = int(amm.get("amount", 0)) / 1e6
        tok = float(amm.get("amount2", {}).get("value", 1))
        price = xrp / tok if tok > 0 else 0
        return {
            "tvl_xrp": xrp,
            "price": price,
            "fee": amm.get("trading_fee", 0) / 1000,
            "lp_tokens": float(amm.get("lp_token", {}).get("value", 0)),
        }
    except Exception:
        # Fallback to direct RPC
        r = _rpc("amm_info", {"asset": {"currency": "XRP"}, "asset2": {"currency": currency, "issuer": issuer}})
        if not r.get("amm"):
            return {}
        amm = r["amm"]
        xrp = int(amm.get("amount", 0)) / 1e6
        tok = float(amm.get("amount2", {}).get("value", 1))
        price = xrp / tok if tok > 0 else 0
        return {
            "tvl_xrp": xrp,
            "price": price,
            "fee": amm.get("trading_fee", 0) / 1000,
            "lp_tokens": float(amm.get("lp_token", {}).get("value", 0)),
        }

def scan(registry: dict) -> List[dict]:
    """
    Scan registry tokens for TrustSet velocity signals.
    Returns list of high-conviction launch candidates.
    
    Called from main bot loop every 4 cycles (~20 min).
    """
    state = _load_state()
    signals = []
    now = time.time()

    # Only check tokens that appear new (low TVL, recently added to registry)
    candidates = []
    for key, token in registry.items():
        tvl = token.get("tvl_xrp", 0)
        if MIN_ENTRY_TVL <= tvl <= MAX_ENTRY_TVL:
            candidates.append((key, token))

    if not candidates:
        return []

    logger.info(f"TrustSet scan: checking {len(candidates)} micro-TVL tokens")

    for key, token in candidates:
        symbol = token.get("symbol", key)
        issuer = token.get("issuer", "")
        currency = token.get("currency", symbol)

        if not issuer:
            continue

        # Skip already alerted tokens
        if key in state.get("alerted", []):
            continue

        # Get TrustSet velocity
        vel = _get_trustset_velocity(issuer)

        # Must be relatively new AND accumulating holders fast
        if vel["age_h"] > MAX_AMM_AGE_H:
            continue
        if vel["total"] < MIN_TRUSTSETS_ABS:
            continue
        if vel["last_1h"] < MIN_TRUSTSETS_1H:
            continue

        # Get AMM state
        amm = _get_amm_info(issuer, currency)
        if not amm:
            continue

        tvl = amm["tvl_xrp"]
        if tvl > MAX_ENTRY_TVL or tvl < MIN_ENTRY_TVL:
            continue

        # Score the signal
        score = 0
        score += min(30, vel["last_1h"] * 2)       # up to 30pts for 1h velocity
        score += min(20, vel["total"] // 5)          # up to 20pts for total holders
        score += min(20, vel["unique_wallets"] // 5) # up to 20pts for unique wallets
        if tvl < 200:
            score += 15   # ultra-early bonus
        elif tvl < 500:
            score += 10   # early entry bonus

        signal = {
            "key": key,
            "symbol": symbol,
            "issuer": issuer,
            "currency": currency,
            "score": score,
            "trustsets_1h": vel["last_1h"],
            "trustsets_total": vel["total"],
            "unique_wallets": vel["unique_wallets"],
            "age_h": round(vel["age_h"], 1),
            "tvl_xrp": tvl,
            "price": amm["price"],
            "signal_type": "trustset_velocity",
            "ts": now,
        }

        signals.append(signal)
        logger.info(
            f"🔥 TRUSTSET SIGNAL {symbol}: {vel['last_1h']} TrustSets/1h "
            f"| total={vel['total']} | TVL={tvl:.0f} XRP | age={vel['age_h']:.1f}h | score={score}"
        )

        # Mark as alerted so we don't re-signal
        state.setdefault("alerted", []).append(key)
        # Trim alerted list to last 200
        state["alerted"] = state["alerted"][-200:]

    state["last_scan"] = now
    _save_state(state)

    return sorted(signals, key=lambda x: x["score"], reverse=True)


if __name__ == "__main__":
    # Test mode
    logging.basicConfig(level=logging.INFO)
    test_registry = {
        "PHX:rskkPc3Eea3phZmzYqdoRFXeHg1GF7oVzG": {
            "symbol": "PHX", "issuer": "rskkPc3Eea3phZmzYqdoRFXeHg1GF7oVzG",
            "currency": "PHX", "tvl_xrp": 4940
        }
    }
    # PHX has 4940 XRP TVL now — too high for entry, but test velocity
    issuer = "rskkPc3Eea3phZmzYqdoRFXeHg1GF7oVzG"
    vel = _get_trustset_velocity(issuer)
    print(f"\nPHX TrustSet profile:")
    print(f"  Total TrustSets:  {vel['total']}")
    print(f"  Last 1h:          {vel['last_1h']}")
    print(f"  Last 6h:          {vel['last_6h']}")
    print(f"  Unique wallets:   {vel['unique_wallets']}")
    print(f"  Token age:        {vel['age_h']:.1f}h")
    print(f"\n  At launch, PHX had 137 TrustSets in first 1h")
    print(f"  Seed XRP: 51.14 | Move: +2208x over 4 days")
    print(f"  Entry at 5 XRP → potential ~11,000 XRP return")
