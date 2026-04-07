"""
smart_money.py — Track profitable wallets and detect coordinated buying.
Boost score +10 (single wallet) or +20 (multiple wallets) when they buy
the same token within 5 minutes.
Writes: state/smart_money.json
"""

import json
import os
import time
import requests
from typing import Dict, List, Set, Optional
from config import CLIO_URL, STATE_DIR, WHALE_XRP_THRESHOLD, get_currency

os.makedirs(STATE_DIR, exist_ok=True)
SM_FILE = os.path.join(STATE_DIR, "smart_money.json")

# Wallets considered "smart money" — populated from trade history winners
SMART_MONEY_WALLETS: Set[str] = set()


def _rpc(method: str, params: dict) -> Optional[dict]:
    try:
        resp = requests.post(CLIO_URL, json={"method": method, "params": [params]}, timeout=15)
        return resp.json().get("result")
    except Exception:
        return None


def _load_sm() -> Dict:
    if os.path.exists(SM_FILE):
        try:
            with open(SM_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"wallets": [], "recent_buys": {}, "signals": {}}


def _save_sm(data: Dict) -> None:
    with open(SM_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_recent_token_buys(symbol: str, issuer: str,
                          lookback_seconds: int = 300) -> List[Dict]:
    """
    Get recent AMM/DEX buys for a token in the last `lookback_seconds`.
    Returns list of {wallet, amount_xrp, ts}.
    """
    currency = get_currency(symbol)
    result   = _rpc("account_tx", {
        "account":         issuer,
        "limit":           50,
        "ledger_index_min": -1,
        "ledger_index_max": -1,
    })
    if not result or result.get("status") != "success":
        return []

    cutoff  = time.time() - lookback_seconds
    buys    = []

    for tx_wrapper in result.get("transactions", []):
        tx   = tx_wrapper.get("tx", {})
        meta = tx_wrapper.get("meta", {})

        # Look for OfferCreate or Payment involving this token
        tx_type  = tx.get("TransactionType", "")
        tx_time  = tx.get("date", 0) + 946684800  # Ripple epoch

        if tx_time < cutoff:
            continue

        sender = tx.get("Account", "")

        if tx_type == "OfferCreate":
            tp = tx.get("TakerPays", {})
            tg = tx.get("TakerGets", {})
            # Buying token: TakerPays=token, TakerGets=XRP
            if (isinstance(tp, dict) and tp.get("currency") == currency and
                    tp.get("issuer") == issuer and isinstance(tg, str)):
                xrp_val = int(tg) / 1e6
                buys.append({"wallet": sender, "amount_xrp": xrp_val, "ts": tx_time})

    return buys


def check_smart_money_signal(symbol: str, issuer: str,
                              known_wallets: Set[str] = None) -> Dict:
    """
    Check if smart money wallets are buying this token.
    Returns {boost: int, wallets: list, signal: str}
    """
    sm_data = _load_sm()
    tracked = set(sm_data.get("wallets", [])) | (known_wallets or SMART_MONEY_WALLETS)

    if not tracked:
        return {"boost": 0, "wallets": [], "signal": "no_tracked_wallets"}

    recent_buys = get_recent_token_buys(symbol, issuer, lookback_seconds=300)
    smart_buyers = [b for b in recent_buys if b["wallet"] in tracked]

    key    = f"{symbol}:{issuer}"
    ts_now = time.time()

    # Record signal
    sm_data.setdefault("signals", {})[key] = {
        "ts":           ts_now,
        "smart_buyers": len(smart_buyers),
        "all_buyers":   len(recent_buys),
    }

    if len(smart_buyers) >= 2:
        _save_sm(sm_data)
        return {"boost": 20, "wallets": [b["wallet"] for b in smart_buyers],
                "signal": "multiple_smart_money"}
    elif len(smart_buyers) == 1:
        _save_sm(sm_data)
        return {"boost": 10, "wallets": [b["wallet"] for b in smart_buyers],
                "signal": "single_smart_money"}
    else:
        _save_sm(sm_data)
        return {"boost": 0, "wallets": [], "signal": "no_signal"}


def update_smart_wallets_from_trades(trade_history: List[Dict]) -> None:
    """
    Identify consistently profitable wallets from trade history.
    Wallets that appeared in our winning trades' concurrent buys.
    """
    sm_data = _load_sm()
    # Simple: store wallets seen in smart_money signals on winning trades
    wallet_wins: Dict[str, int] = {}
    for trade in trade_history:
        if trade.get("pnl_pct", 0) > 0.05:
            for w in trade.get("smart_wallets", []):
                wallet_wins[w] = wallet_wins.get(w, 0) + 1

    # Wallets with 2+ wins = smart money
    sm_wallets = [w for w, wins in wallet_wins.items() if wins >= 2]
    sm_data["wallets"] = sm_wallets[:50]  # cap at 50
    _save_sm(sm_data)


if __name__ == "__main__":
    result = check_smart_money_signal("SOLO", "rsoLo2S1kiGeCcn6hCUXVrCpGMWLrRrLZz")
    print(json.dumps(result, indent=2))
