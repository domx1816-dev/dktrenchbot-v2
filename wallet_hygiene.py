"""
wallet_hygiene.py — On startup + daily:
  - Liquidate dust positions (< 0.5 XRP value)
  - Close zero-balance trustlines
  - Cancel old/orphaned offers
Writes: state/hygiene.log
"""

import json
import os
import time
import logging
import requests
from typing import Dict, List, Optional
from config import CLIO_URL, STATE_DIR, BOT_WALLET_ADDRESS, WS_URL, get_currency
import state as state_mod

os.makedirs(STATE_DIR, exist_ok=True)
HYGIENE_LOG = os.path.join(STATE_DIR, "hygiene.log")

logger = logging.getLogger("wallet_hygiene")
DUST_XRP_VALUE = 2.0  # anything under 2 XRP value = dust, not worth keeping trustline reserve


def _rpc(method: str, params: dict) -> Optional[dict]:
    try:
        resp = requests.post(CLIO_URL, json={"method": method, "params": [params]}, timeout=15)
        return resp.json().get("result")
    except Exception:
        return None


def _log(msg: str) -> None:
    ts   = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    with open(HYGIENE_LOG, "a") as f:
        f.write(line)
    logger.info(msg)


def _get_wallet():
    from execution import _get_wallet as _gw
    return _gw()


def get_all_trustlines() -> List[Dict]:
    result = _rpc("account_lines", {
        "account":      BOT_WALLET_ADDRESS,
        "ledger_index": "validated",
    })
    if result and result.get("status") == "success":
        return result.get("lines", [])
    return []


def get_token_price_xrp(currency: str, issuer: str) -> float:
    """Estimate token price in XRP via AMM."""
    result = _rpc("amm_info", {
        "asset":  {"currency": "XRP"},
        "asset2": {"currency": currency, "issuer": issuer},
    })
    if result and result.get("status") == "success":
        amm = result.get("amm", {})
        try:
            xrp   = int(amm["amount"]) / 1e6
            token = float(amm["amount2"]["value"])
            return xrp / token if token > 0 else 0.0
        except Exception:
            pass
    return 0.0


def close_trustline(currency: str, issuer: str) -> bool:
    """
    Close a zero-balance trustline by setting limit to 0.
    """
    try:
        from xrpl.clients import WebsocketClient
        from xrpl.models.transactions import TrustSet
        from xrpl.models.amounts import IssuedCurrencyAmount
        from xrpl.transaction import submit_and_wait

        wallet = _get_wallet()
        tx = TrustSet(
            account    = wallet.address,
            limit_amount = IssuedCurrencyAmount(
                currency = currency,
                issuer   = issuer,
                value    = "0",
            ),
        )
        with WebsocketClient(WS_URL) as ws:
            response = submit_and_wait(tx, ws, wallet)
            return response.is_successful()
    except Exception as e:
        _log(f"ERROR close_trustline {currency}:{issuer}: {e}")
        return False


def sell_dust(currency: str, issuer: str, balance: float,
              price_xrp: float) -> bool:
    """Sell dust token balance."""
    try:
        from execution import sell_token
        result = sell_token(
            symbol         = currency if len(currency) <= 3 else currency,
            issuer         = issuer,
            token_amount   = balance,
            expected_price = price_xrp,
            slippage_tolerance = 0.10,  # wider tolerance for dust
        )
        return result.get("success", False)
    except Exception as e:
        _log(f"ERROR sell_dust {currency}: {e}")
        return False


def cancel_old_offers() -> int:
    """Cancel all open offers."""
    from reconcile import get_open_offers, cancel_offer
    offers    = get_open_offers()
    cancelled = 0
    for offer in offers:
        seq = offer.get("seq", 0)
        _log(f"Cancelling offer seq={seq}")
        if cancel_offer(seq):
            cancelled += 1
    return cancelled


def run_hygiene(bot_state: Dict, force: bool = False) -> Dict:
    """
    Run wallet hygiene. Skip if run in last 23 hours (unless force=True).
    """
    last = bot_state.get("last_hygiene", 0)
    if not force and (time.time() - last) < 4 * 3600:  # run every 4hr (was 23hr)
        return {"skipped": True, "reason": "ran_recently"}

    _log("=== Hygiene start ===")
    start_ts = time.time()

    lines         = get_all_trustlines()
    dust_sold     = 0
    lines_closed  = 0
    cancelled     = 0

    for line in lines:
        currency = line.get("currency", "")
        issuer   = line.get("account", "")
        balance  = float(line.get("balance", 0))

        if balance <= 0:
            # Zero balance — close trustline
            _log(f"Closing zero-balance trustline: {currency}:{issuer}")
            if close_trustline(currency, issuer):
                lines_closed += 1
            continue

        # Check if dust
        price_xrp = get_token_price_xrp(currency, issuer)
        value_xrp = balance * price_xrp

        if 0 < value_xrp < DUST_XRP_VALUE:
            if value_xrp < 0.5:
                # Gas cost > proceeds — abandon without selling, just close line
                _log(f"Abandoning micro-dust: {currency} = {value_xrp:.4f} XRP (gas > value)")
                time.sleep(1)
                if close_trustline(currency, issuer):
                    lines_closed += 1
            else:
                _log(f"Selling dust: {balance:.4f} {currency} = {value_xrp:.4f} XRP")
                sold = sell_dust(currency, issuer, balance, price_xrp)
                if sold:
                    dust_sold += 1
                    time.sleep(1)
                    if close_trustline(currency, issuer):
                        lines_closed += 1

    # Cancel any stale offers
    cancelled = cancel_old_offers()

    bot_state["last_hygiene"] = start_ts
    state_mod.save(bot_state)

    summary = {
        "ts":           start_ts,
        "dust_sold":    dust_sold,
        "lines_closed": lines_closed,
        "offers_cancelled": cancelled,
        "duration_ms":  int((time.time() - start_ts) * 1000),
    }
    _log(f"Hygiene done: {summary}")
    return summary


if __name__ == "__main__":
    s = state_mod.load()
    result = run_hygiene(s, force=True)
    print(result)
