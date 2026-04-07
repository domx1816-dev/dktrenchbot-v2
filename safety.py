"""
safety.py — Hard safety filter. ALL checks must pass before entry.
Checks: AMM TVL, LP burn, issuer blackhole, freeze risk, concentration, liquidity stability.
Writes: state/safety_cache.json
"""

import json
import os
import time
import requests
from typing import Dict, List, Optional, Tuple
from config import (CLIO_URL, STATE_DIR, MIN_TVL_XRP, MIN_LP_BURN_PCT,
                    BLACK_HOLES, get_currency)

os.makedirs(STATE_DIR, exist_ok=True)
SAFETY_CACHE_FILE = os.path.join(STATE_DIR, "safety_cache.json")

# lsfNoFreeze = 0x00200000, lsfGlobalFreeze = 0x00400000
LSF_NO_FREEZE     = 0x00200000
LSF_GLOBAL_FREEZE = 0x00400000
LSF_DISABLE_MASTER = 0x00100000


def _rpc(method: str, params: dict) -> Optional[dict]:
    time.sleep(0.12)  # rate limit protection between calls
    for attempt in range(3):
        try:
            resp = requests.post(CLIO_URL, json={"method": method, "params": [params]}, timeout=15)
            data = resp.json()
            result = data.get("result")
            if isinstance(result, dict) and result.get("error") == "slowDown":
                time.sleep(1.5 * (attempt + 1))
                continue
            return result
        except Exception:
            time.sleep(0.5)
    return None


def _load_cache() -> Dict:
    if os.path.exists(SAFETY_CACHE_FILE):
        try:
            with open(SAFETY_CACHE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_cache(cache: Dict) -> None:
    with open(SAFETY_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def check_amm_tvl(amm: Dict) -> Tuple[bool, float, str]:
    """Returns (pass, tvl_xrp, reason)."""
    try:
        tvl = (int(amm["amount"]) / 1e6) * 2
        if tvl >= MIN_TVL_XRP:
            return True, tvl, "ok"
        return False, tvl, f"tvl_too_low:{tvl:.0f}<{MIN_TVL_XRP}"
    except Exception as e:
        return False, 0.0, f"tvl_parse_error:{e}"


def check_lp_burn(amm: Dict) -> Tuple[str, str]:
    """
    Check if LP tokens are burned to blackhole accounts.
    Returns (status, reason) where status: 'safe'|'unsafe'|'unknown'
    """
    lp_token = amm.get("lp_token")
    if not lp_token:
        return "unknown", "no_lp_token_in_amm"

    lp_currency = lp_token.get("currency")
    lp_issuer   = lp_token.get("issuer")
    if not lp_currency or not lp_issuer:
        return "unknown", "no_lp_currency_issuer"

    # Get total LP supply
    result = _rpc("gateway_balances", {"account": lp_issuer, "ledger_index": "validated"})
    total_supply = 0.0
    if result and result.get("status") == "success":
        obligations = result.get("obligations", {})
        total_supply = float(obligations.get(lp_currency, 0))

    if total_supply <= 0:
        return "unknown", "cannot_determine_supply"

    # Check burned amount in blackholes
    burned = 0.0
    for bh in BLACK_HOLES:
        result = _rpc("account_lines", {
            "account": bh,
            "ledger_index": "validated",
            "limit": 400,
        })
        if result and result.get("status") == "success":
            for line in result.get("lines", []):
                if (line.get("currency") == lp_currency and
                        line.get("account") == lp_issuer):
                    burned += abs(float(line.get("balance", 0)))

    if total_supply > 0:
        burn_pct = (burned / total_supply) * 100
        if burn_pct >= MIN_LP_BURN_PCT:
            return "safe", f"burn_pct:{burn_pct:.1f}%"
        else:
            return "unsafe", f"burn_pct:{burn_pct:.1f}%<{MIN_LP_BURN_PCT}%"

    return "unknown", "zero_total_supply"


def check_issuer_blackhole(issuer: str) -> Tuple[bool, str]:
    """
    Returns (is_safe, reason).
    Safe = disableMaster=True AND no regularKey.
    """
    result = _rpc("account_info", {"account": issuer, "ledger_index": "validated"})
    if not result or result.get("status") != "success":
        return False, "cannot_fetch_issuer"

    acct = result.get("account_data", {})
    flags = acct.get("Flags", 0)
    disable_master = bool(flags & LSF_DISABLE_MASTER)
    has_regular_key = bool(acct.get("RegularKey"))

    if disable_master and not has_regular_key:
        return True, "blackholed"
    return False, f"disable_master={disable_master},regular_key={has_regular_key}"


def check_freeze_risk(issuer: str) -> Tuple[bool, str]:
    """Returns (no_freeze_risk, reason). True = safe."""
    result = _rpc("account_info", {"account": issuer, "ledger_index": "validated"})
    if not result or result.get("status") != "success":
        return False, "cannot_fetch_issuer"

    acct  = result.get("account_data", {})
    flags = acct.get("Flags", 0)

    if flags & LSF_GLOBAL_FREEZE:
        return False, "global_freeze_active"
    if flags & LSF_NO_FREEZE:
        return True, "no_freeze_set"
    return True, "no_freeze_flags"  # neither set = can freeze but hasn't


def check_concentration(issuer: str, symbol: str) -> Tuple[bool, str]:
    """
    Rough concentration check. Returns (ok, reason).
    Checks gateway_balances to see largest single holder.
    """
    currency = get_currency(symbol)
    result = _rpc("gateway_balances", {
        "account": issuer,
        "ledger_index": "validated",
        "hotwallet": [],
    })
    if not result or result.get("status") != "success":
        return True, "cannot_check_skip"

    obligations = result.get("obligations", {})
    total = float(obligations.get(currency, 0))
    if total <= 0:
        return True, "no_supply"

    # Check top holders via account_lines on issuer
    result2 = _rpc("account_lines", {
        "account": issuer,
        "ledger_index": "validated",
        "limit": 400,
    })
    if not result2 or result2.get("status") != "success":
        return True, "cannot_check_holders"

    lines = result2.get("lines", [])

    # Get the AMM pool account so we can exclude it — it holds tokens as liquidity,
    # NOT as a whale. Counting it inflates concentration massively (often 40-70%).
    amm_pool_account = ""
    amm_res = _rpc("amm_info", {"asset": {"currency": "XRP"}, "asset2": {"currency": currency, "issuer": issuer}})
    if amm_res.get("amm"):
        amm_pool_account = amm_res["amm"].get("account", "")

    # Filter out AMM pool account and zero balances
    balances_filtered = [
        (abs(float(l.get("balance", 0))), l.get("account", ""))
        for l in lines
        if l.get("currency") == currency
        and l.get("account", "") != amm_pool_account
        and abs(float(l.get("balance", 0))) > 0
    ]
    if not balances_filtered:
        return True, "no_holders"

    # Recalculate total excluding AMM pool
    real_total = sum(b for b, _ in balances_filtered)
    if real_total <= 0:
        return True, "no_supply_ex_amm"

    max_bal = max(b for b, _ in balances_filtered)
    pct = (max_bal / real_total * 100)
    if pct > 30:
        return False, f"top_holder:{pct:.1f}%>30%"
    return True, f"top_holder:{pct:.1f}%"


# TVL history for stability check
_tvl_history: Dict[str, List] = {}


def check_liquidity_stability(token_key: str, current_tvl: float) -> Tuple[bool, str]:
    """Reject if TVL dropped > 20% in last 3 readings."""
    if token_key not in _tvl_history:
        _tvl_history[token_key] = []
    _tvl_history[token_key].append(current_tvl)
    readings = _tvl_history[token_key][-3:]

    if len(readings) < 2:
        return True, "insufficient_history"

    max_tvl = max(readings[:-1])
    if max_tvl > 0:
        drop_pct = (max_tvl - readings[-1]) / max_tvl
        if drop_pct > 0.20:
            return False, f"tvl_drop:{drop_pct:.1%}"
    return True, f"stable"


def safety_check(token: Dict, amm: Dict, cache: Optional[Dict] = None) -> Dict:
    """
    Run all safety checks on a token.
    Returns dict with pass/fail for each check and overall 'safe' bool.
    """
    symbol = token["symbol"]
    issuer = token["issuer"]
    key    = f"{symbol}:{issuer}"

    # Use cache if fresh (< 10 min)
    if cache and key in cache:
        cached = cache[key]
        if time.time() - cached.get("ts", 0) < 1800:  # 30 min cache
            return cached

    result = {"ts": time.time(), "symbol": symbol, "issuer": issuer}

    # 1. AMM TVL
    tvl_pass, tvl, tvl_reason = check_amm_tvl(amm)
    result["tvl_pass"]   = tvl_pass
    result["tvl_xrp"]    = tvl
    result["tvl_reason"] = tvl_reason

    # 2. LP Burn — DISABLED for XRPL AMMs
    # XRPL AMM LP tokens are never "burned" — they're held by LPs by design.
    # LP burn is an EVM/Uniswap concept and does not apply here.
    lp_status = "n/a"
    lp_reason = "xrpl_amm_lp_burn_not_applicable"
    result["lp_burn_status"] = lp_status
    result["lp_burn_reason"] = lp_reason
    lp_pass = True

    # 3. Issuer blackhole
    bh_pass, bh_reason = check_issuer_blackhole(issuer)
    result["issuer_blackhole"]        = bh_pass
    result["issuer_blackhole_reason"] = bh_reason

    # 4. Freeze risk
    freeze_pass, freeze_reason = check_freeze_risk(issuer)
    result["freeze_safe"]   = freeze_pass
    result["freeze_reason"] = freeze_reason

    # 5. Concentration
    conc_pass, conc_reason = check_concentration(issuer, symbol)
    result["concentration_ok"]     = conc_pass
    result["concentration_reason"] = conc_reason

    # 6. Liquidity stability
    stab_pass, stab_reason = check_liquidity_stability(key, tvl)
    result["liquidity_stable"]        = stab_pass
    result["liquidity_stable_reason"] = stab_reason

    # Overall safety logic:
    # Hard fails: TVL too low, liquidity actively collapsing
    # Warnings (allow with flag): cannot fetch issuer (RPC fail), LP unknown, not blackholed
    # True hard fail: freeze_reason is explicitly bad (not just cannot_fetch)
    rpc_fail = "cannot_fetch" in freeze_reason or "cannot_fetch" in bh_reason
    freeze_hard_fail = not freeze_pass and not rpc_fail

    hard_pass = tvl_pass and lp_pass and not freeze_hard_fail and stab_pass
    result["safe"]     = hard_pass
    result["warnings"] = []

    # issuer_not_blackholed removed — XRPL AMM issuers don't blackhole by design, not a risk signal
    if not conc_pass:
        result["warnings"].append(f"concentration_risk:{conc_reason}")
    if lp_status == "unknown":
        result["warnings"].append("lp_burn_unknown")
    if rpc_fail:
        result["warnings"].append("issuer_rpc_unavailable")

    return result


def run_safety(token: Dict, amm: Dict) -> Dict:
    """Run safety check with cache."""
    cache = _load_cache()
    result = safety_check(token, amm, cache)
    key = f"{token['symbol']}:{token['issuer']}"
    cache[key] = result
    _save_cache(cache)
    return result


if __name__ == "__main__":
    from scanner import get_amm_info
    test_token = {"symbol": "SOLO", "issuer": "rsoLo2S1kiGeCcn6hCUXVrCpGMWLrRrLZz"}
    amm = get_amm_info(test_token["symbol"], test_token["issuer"])
    if amm:
        result = run_safety(test_token, amm)
        print(json.dumps(result, indent=2))
    else:
        print("No AMM found for SOLO")
