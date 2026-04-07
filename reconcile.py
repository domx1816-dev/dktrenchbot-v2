"""
reconcile.py — On startup and every 30 min: sync chain state with local state.
Rebuilds positions if discrepancy. Cancels stale offers.
Writes: state/reconcile.log
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
RECONCILE_LOG = os.path.join(STATE_DIR, "reconcile.log")

logger = logging.getLogger("reconcile")


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


def _log(msg: str) -> None:
    ts  = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    with open(RECONCILE_LOG, "a") as f:
        f.write(line)
    logger.info(msg)


def get_chain_balances() -> Dict:
    """Get XRP balance and all token balances from chain."""
    result = _rpc("account_info", {
        "account":      BOT_WALLET_ADDRESS,
        "ledger_index": "validated",
    })
    xrp_balance = 0.0
    if result and result.get("status") == "success":
        xrp_balance = int(result["account_data"]["Balance"]) / 1e6

    # Token balances
    lines_result = _rpc("account_lines", {
        "account":      BOT_WALLET_ADDRESS,
        "ledger_index": "validated",
    })
    token_balances = {}
    if lines_result and lines_result.get("status") == "success":
        for line in lines_result.get("lines", []):
            bal = float(line.get("balance", 0))
            if bal > 0:
                key = f"{line['currency']}:{line['account']}"
                token_balances[key] = bal

    return {"xrp": xrp_balance, "tokens": token_balances}


def get_open_offers() -> List[Dict]:
    """Get all open DEX offers for bot wallet."""
    result = _rpc("account_offers", {
        "account":      BOT_WALLET_ADDRESS,
        "ledger_index": "validated",
    })
    if result and result.get("status") == "success":
        return result.get("offers", [])
    return []


def cancel_offer(sequence: int) -> bool:
    """Cancel a specific offer by sequence number."""
    try:
        from xrpl.clients import WebsocketClient
        from xrpl.models.transactions import OfferCancel
        from xrpl.transaction import submit_and_wait
        from execution import _get_wallet

        wallet = _get_wallet()
        tx = OfferCancel(
            account          = wallet.address,
            offer_sequence   = sequence,
        )
        with WebsocketClient(WS_URL) as ws:
            response = submit_and_wait(tx, ws, wallet)
            return response.is_successful()
    except Exception as e:
        _log(f"ERROR cancel_offer seq={sequence}: {e}")
        return False


def reconcile(bot_state: Dict, cancel_stale_hours: float = 2.0) -> Dict:
    """
    Full reconciliation run.
    Returns summary dict.
    """
    _log("=== Reconcile start ===")
    start_ts = time.time()

    chain = get_chain_balances()
    _log(f"Chain XRP balance: {chain['xrp']:.4f}")
    _log(f"Chain tokens: {list(chain['tokens'].keys())}")

    # SAFETY: if chain returned no data at all (RPC slowDown/failure), abort — don't wipe positions
    n_local_positions = len(bot_state.get("positions", {}))
    if chain["xrp"] == 0.0 and len(chain["tokens"]) == 0 and n_local_positions > 0:
        _log(f"⚠️  Chain returned empty data but we have {n_local_positions} local positions — RPC likely slowDown. Aborting reconcile to protect positions.")
        return {"ts": time.time(), "xrp_balance": 0, "chain_tokens": 0, "discrepancies": 0, "offers_cancelled": 0, "duration_ms": 0, "aborted": True}

    # Check for position discrepancies
    positions = bot_state.get("positions", {})
    discrepancies = []

    for pos_key, pos in list(positions.items()):
        symbol = pos.get("symbol", "")
        issuer = pos.get("issuer", "")
        currency = get_currency(symbol)
        chain_key_hex  = f"{currency}:{issuer}"
        chain_key_raw  = f"{symbol}:{issuer}"

        chain_bal = chain["tokens"].get(chain_key_hex) or chain["tokens"].get(chain_key_raw, 0)
        local_bal = pos.get("tokens_held", 0)

        if chain_bal <= 0 and local_bal > 0:
            _log(f"DISCREPANCY: {symbol} has local={local_bal} but chain=0 — removing position")
            discrepancies.append(pos_key)
            state_mod.remove_position(bot_state, pos_key)
        elif abs(chain_bal - local_bal) / max(local_bal, 1) > 0.05:
            _log(f"DISCREPANCY: {symbol} local={local_bal:.4f} chain={chain_bal:.4f} — updating")
            bot_state["positions"][pos_key]["tokens_held"] = chain_bal
            discrepancies.append(pos_key)

    # Check for tokens on chain not in positions (orphaned positions)
    # DATA AUDIT 2026-04-06: orphan adoption = 14% WR, -8.5 XRP avg loss. Don't ADOPT, but DO sell.
    KEEP_TOKENS = {"PHX"}  # tokens to never auto-sell
    for chain_key, balance in chain["tokens"].items():
        if balance <= 0.001:
            continue
        # Skip if already tracked as a position
        if any(chain_key.startswith(pos.get("symbol","")) or chain_key.endswith(pos.get("issuer","")) for pos in positions.values()):
            continue
        if chain_key in positions:
            continue
        currency, _, issuer = chain_key.partition(":")
        # Skip known KEEP tokens
        symbol_short = currency.strip("0")[:6] if len(currency) > 6 else currency.strip()
        if any(k in chain_key.upper() for k in KEEP_TOKENS):
            _log(f"ORPHAN token on chain: {chain_key} balance={balance:.6f} — KEEPING (KEEP_TOKENS)")
            continue
        _log(f"ORPHAN token on chain: {chain_key} balance={balance:.6f} — attempting sell to recover XRP")
        try:
            from execution import sell_token
            import scanner as _sc
            _live_price, _, _, _ = _sc.get_token_price_and_tvl(currency, issuer)
            if not _live_price:
                _log(f"⚠️  Cannot fetch live price for {chain_key} — skipping orphan sell")
                continue
            sell_result = sell_token(
                symbol         = currency,
                issuer         = issuer,
                token_amount   = balance,
                expected_price = _live_price,
                slippage_tolerance = 0.15,
            )
            if sell_result.get("success"):
                _log(f"✅ Orphan sell succeeded: {chain_key} → {sell_result.get('xrp_received', 0):.4f} XRP")
            else:
                _log(f"❌ Orphan sell failed: {chain_key}: {sell_result.get('error','unknown')}")
                orphans = bot_state.setdefault("orphan_positions", {})
                orphans[currency] = {"tokens": balance, "issuer": issuer, "currency": currency, "ts": time.time()}
        except Exception as _oe:
            _log(f"❌ Orphan sell exception: {chain_key}: {_oe}")

    # Cancel stale offers
    offers = get_open_offers()
    cancelled = 0
    for offer in offers:
        _log(f"Open offer seq={offer.get('seq')} — cancelling stale offer")
        if cancel_offer(offer.get("seq", 0)):
            cancelled += 1

    # Update state
    bot_state["last_reconcile"] = start_ts
    state_mod.save(bot_state)

    summary = {
        "ts":              start_ts,
        "xrp_balance":     chain["xrp"],
        "chain_tokens":    len(chain["tokens"]),
        "discrepancies":   len(discrepancies),
        "offers_cancelled": cancelled,
        "duration_ms":     int((time.time() - start_ts) * 1000),
    }
    _log(f"Reconcile done: {summary}")
    return summary


if __name__ == "__main__":
    s = state_mod.load()
    result = reconcile(s)
    print(result)
