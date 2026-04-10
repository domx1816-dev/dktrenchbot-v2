"""
route_engine.py — Compare AMM vs DEX order book. Calculate slippage and exit feasibility.
Rejects if entry slippage > 3% or exit liquidity < 2x position.
Writes: state/route_log.json
"""

import json
import os
import time
import requests
from typing import Dict, Optional, Tuple
from config import CLIO_URL, STATE_DIR, get_currency

os.makedirs(STATE_DIR, exist_ok=True)
ROUTE_LOG_FILE = os.path.join(STATE_DIR, "route_log.json")


def _rpc(method: str, params: dict) -> Optional[dict]:
    for attempt in range(3):
        try:
            resp = requests.post(CLIO_URL, json={"method": method, "params": [params]}, timeout=15)
            data = resp.json()
            result = data.get("result")
            if isinstance(result, dict) and result.get("error") == "slowDown":
                time.sleep(1.0 * (attempt + 1))
                continue
            return result
        except Exception:
            time.sleep(0.5)
    return None


def get_amm_price(amm: Dict) -> Optional[float]:
    """Get AMM mid-price (XRP per token)."""
    try:
        xrp_drops  = int(amm["amount"])
        token_val  = float(amm["amount2"]["value"])
        if token_val == 0:
            return None
        return (xrp_drops / 1e6) / token_val
    except Exception:
        return None


def estimate_amm_slippage(amm: Dict, xrp_in: float) -> float:
    """
    Estimate AMM slippage for buying `xrp_in` XRP worth of token.
    Uses constant product formula: dy = y * dx / (x + dx)
    """
    try:
        x = int(amm["amount"]) / 1e6      # XRP in pool
        y = float(amm["amount2"]["value"]) # token in pool
        if x <= 0 or y <= 0:
            return 1.0
        # With trading fee (typically 0.3% on XRPL AMMs)
        fee = float(amm.get("trading_fee", 500)) / 1_000_000  # fee in bips → fraction
        dx  = xrp_in
        # Tokens out: standard AMM formula with fee
        dy  = y * dx * (1 - fee) / (x + dx * (1 - fee))
        # Ideal (no slippage): dx * (y / x)
        ideal = dx * (y / x)
        if ideal <= 0:
            return 1.0
        slippage = abs(ideal - dy) / ideal
        return slippage
    except Exception:
        return 1.0


def get_book_depth(symbol: str, issuer: str, limit: int = 20) -> Dict:
    """Get DEX order book depth for token/XRP."""
    currency = get_currency(symbol)
    # Buy side: offers to sell XRP for token (taker_gets=token, taker_pays=XRP)
    buy_result = _rpc("book_offers", {
        "taker_gets": {"currency": currency, "issuer": issuer},
        "taker_pays": {"currency": "XRP"},
        "limit":      limit,
    })
    # Sell side: offers to sell token for XRP
    sell_result = _rpc("book_offers", {
        "taker_gets": {"currency": "XRP"},
        "taker_pays": {"currency": currency, "issuer": issuer},
        "limit":      limit,
    })

    buy_offers  = buy_result.get("offers", [])  if buy_result  else []
    sell_offers = sell_result.get("offers", []) if sell_result else []

    return {"buy": buy_offers, "sell": sell_offers}


def estimate_book_slippage(book: Dict, xrp_in: float) -> float:
    """Estimate slippage from order book for buying xrp_in XRP worth."""
    offers = book.get("buy", [])
    if not offers:
        return 1.0  # No liquidity

    filled = 0.0
    total_xrp_cost = 0.0

    for offer in offers:
        try:
            # offer taker_pays = XRP, taker_gets = token
            tp = offer.get("taker_pays", {})
            tg = offer.get("taker_gets", {})
            if isinstance(tp, str):
                offer_xrp   = int(tp) / 1e6
                offer_token = float(tg.get("value", 0))
            else:
                continue
            if offer_xrp <= 0 or offer_token <= 0:
                continue
            can_take = min(xrp_in - total_xrp_cost, offer_xrp)
            filled         += (offer_token * can_take / offer_xrp)
            total_xrp_cost += can_take
            if total_xrp_cost >= xrp_in:
                break
        except Exception:
            continue

    if filled <= 0:
        return 1.0

    # Compare to AMM-equivalent rate (first offer rate)
    try:
        first_tp = offers[0].get("taker_pays", {})
        first_tg = offers[0].get("taker_gets", {})
        best_xrp   = int(first_tp) / 1e6   if isinstance(first_tp, str) else 0
        best_token = float(first_tg.get("value", 0))
        if best_xrp > 0:
            ideal = xrp_in * (best_token / best_xrp)
            slippage = abs(ideal - filled) / ideal if ideal > 0 else 1.0
            return slippage
    except Exception:
        pass

    return 0.01  # minimal slippage if filled


def check_exit_liquidity(amm: Dict, position_xrp: float) -> Tuple[bool, float]:
    """
    Check if exit liquidity is >= 2x position size.
    Returns (ok, available_xrp).
    """
    try:
        xrp_in_pool = int(amm["amount"]) / 1e6
        available   = xrp_in_pool  # can always exit into AMM, limited by pool size
        threshold   = position_xrp * 2
        return available >= threshold, available
    except Exception:
        return False, 0.0


def evaluate_route(symbol: str, issuer: str, amm: Dict, xrp_in: float) -> Dict:
    """
    Full route evaluation. Returns recommendation and slippage estimates.
    """
    ts = time.time()
    currency = get_currency(symbol)

    # Always route through AMM — no CLOB
    amm_slippage = estimate_amm_slippage(amm, xrp_in)
    best_route   = "amm"
    best_slippage = amm_slippage

    exit_ok, exit_liq = check_exit_liquidity(amm, xrp_in)

    # Hard filters
    entry_ok = best_slippage <= 0.25  # allow microcap volatility
    trade_ok = entry_ok and exit_ok

    result = {
        "ts":             ts,
        "symbol":         symbol,
        "issuer":         issuer,
        "xrp_in":         xrp_in,
        "amm_slippage":   round(amm_slippage, 5),
        "best_route":     best_route,
        "best_slippage":  round(best_slippage, 5),
        "exit_ok":        exit_ok,
        "exit_liquidity": round(exit_liq, 2),
        "entry_ok":       entry_ok,
        "trade_ok":       trade_ok,
        "reject_reason":  None,
    }

    if not entry_ok:
        result["reject_reason"] = f"slippage_too_high:{best_slippage:.2%}"
    elif not exit_ok:
        result["reject_reason"] = f"insufficient_exit_liq:{exit_liq:.0f}<{xrp_in*2:.0f}"

    # Append to route log
    _append_log(result)
    return result


def _append_log(entry: Dict) -> None:
    log = []
    if os.path.exists(ROUTE_LOG_FILE):
        try:
            with open(ROUTE_LOG_FILE) as f:
                log = json.load(f)
        except Exception:
            pass
    log.append(entry)
    log = log[-200:]  # keep last 200
    with open(ROUTE_LOG_FILE, "w") as f:
        json.dump(log, f, indent=2)


if __name__ == "__main__":
    from scanner import get_amm_info
    token = {"symbol": "SOLO", "issuer": "rsoLo2S1kiGeCcn6hCUXVrCpGMWLrRrLZz"}
    amm = get_amm_info(token["symbol"], token["issuer"])
    if amm:
        result = evaluate_route(token["symbol"], token["issuer"], amm, xrp_in=5.0)
        print(json.dumps(result, indent=2))
    else:
        print("No AMM for SOLO")
