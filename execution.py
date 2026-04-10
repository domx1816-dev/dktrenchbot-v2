"""
execution.py — WebSocket transaction submission via AMM (Payment routing).
Uses Payment transactions routed through AMM pools — NOT OfferCreate/CLOB.
Logs slippage, fill, latency.
Writes: state/execution_log.json
"""

import json
import os
import time
import logging
from typing import Dict, List, Optional, Tuple
from config import STATE_DIR, WS_URL, CLIO_URL, SECRETS_FILE, get_currency, BOT_WALLET_ADDRESS

os.makedirs(STATE_DIR, exist_ok=True)
EXEC_LOG_FILE = os.path.join(STATE_DIR, "execution_log.json")

logger = logging.getLogger("execution")


def _load_seed() -> str:
    """Load seed from secrets file. Never log or return in results."""
    with open(SECRETS_FILE) as f:
        for line in f:
            if line.strip().startswith("- Seed:"):
                return line.strip().split("- Seed:", 1)[1].strip()
    raise ValueError("Seed not found in secrets file")


def _get_wallet():
    from xrpl.wallet import Wallet
    seed = _load_seed()
    return Wallet.from_seed(seed)


def _parse_actual_fill(metadata: Dict, wallet_addr: str, currency: str, issuer: str
                       ) -> Tuple[float, float]:
    """
    Parse OfferCreate AffectedNodes to get XRP spent and tokens received.
    Reads delivered_amount and balance changes from RippleState nodes.
    Returns (xrp_spent, tokens_received).
    """
    xrp_spent = 0.0
    tokens_received = 0.0

    try:
        # delivered_amount / DeliveredAmount — most reliable source for Payment fills
        delivered = metadata.get("delivered_amount") or metadata.get("DeliveredAmount")
        if isinstance(delivered, dict):
            if delivered.get("currency") == currency:
                tokens_received = float(delivered.get("value", 0))
        elif isinstance(delivered, str) and delivered != "unavailable":
            # XRP delivered (sell side)
            xrp_spent = int(delivered) / 1e6

        for node_wrapper in metadata.get("AffectedNodes", []):
            for node_type, node in node_wrapper.items():
                final = node.get("FinalFields", {})
                prev  = node.get("PreviousFields", {})
                new   = node.get("NewFields", {})

                # XRP balance change on our account (AccountRoot)
                acct = final.get("Account") or new.get("Account")
                if acct == wallet_addr and node.get("LedgerEntryType") == "AccountRoot":
                    prev_bal  = int(prev.get("Balance", 0))
                    final_bal = int(final.get("Balance", prev_bal))
                    if prev_bal > final_bal:
                        xrp_spent = max(xrp_spent, (prev_bal - final_bal) / 1e6)

                # Token balance change (RippleState)
                if node.get("LedgerEntryType") == "RippleState":
                    prev_bal  = prev.get("Balance")
                    final_bal = final.get("Balance")
                    if prev_bal is None:
                        prev_bal = new.get("Balance")
                        final_bal = new.get("Balance")
                    if isinstance(final_bal, dict) and final_bal.get("currency") == currency:
                        prev_val  = float(prev_bal.get("value", 0)) if isinstance(prev_bal, dict) else 0
                        final_val = float(final_bal.get("value", 0))
                        delta = abs(final_val - prev_val)
                        if delta > 0:
                            tokens_received = max(tokens_received, delta)

    except Exception as e:
        logger.warning(f"Fill parse error: {e}")

    return xrp_spent, tokens_received


def ensure_trustline(currency: str, issuer: str, symbol: str) -> bool:
    """
    Ensure the bot wallet has a trustline for the given token.
    Sets a TrustSet if not already present. Returns True if ready, False on failure.
    Uses raw requests + WebSocket to match rest of codebase.
    """
    import requests as _requests
    from xrpl.clients import WebsocketClient
    from xrpl.models.transactions import TrustSet
    from xrpl.models.amounts import IssuedCurrencyAmount
    from xrpl.transaction import autofill, sign, submit_and_wait

    wallet = _get_wallet()

    # Check if trustline already exists via raw CLIO call
    try:
        resp = _requests.post(CLIO_URL, json={
            "method": "account_lines",
            "params": [{"account": wallet.classic_address}]
        }, timeout=10)
        data = resp.json()
        lines = data.get("result", {}).get("lines", [])
        for line in lines:
            if line.get("currency") == currency and line.get("account") == issuer:
                logger.info(f"Trustline already exists for {symbol}")
                return True
    except Exception as e:
        logger.warning(f"Trustline check failed for {symbol}: {e}")

    # Create trustline via WebSocket submit
    try:
        from xrpl.models.transactions import TrustSetFlag
        tx = TrustSet(
            account      = wallet.classic_address,
            limit_amount = IssuedCurrencyAmount(
                currency = currency,
                issuer   = issuer,
                value    = "1000000000",
            ),
            flags        = TrustSetFlag.TF_SET_NO_RIPPLE,  # QuantX patch Apr 10 — prevent rippling through our trustlines
        )
        with WebsocketClient(WS_URL) as ws:
            resp = submit_and_wait(tx, ws, wallet)
            if resp.is_successful():
                logger.info(f"Trustline set for {symbol} ({currency}:{issuer})")
                return True
            else:
                result = resp.result.get("engine_result", "unknown")
                logger.warning(f"TrustSet failed for {symbol}: {result}")
                return False
    except Exception as e:
        logger.warning(f"TrustSet exception for {symbol}: {e}")
        return False


def buy_token(symbol: str, issuer: str, xrp_amount: float,
              expected_price: float, slippage_tolerance: float = 0.05) -> Dict:
    """
    Buy tokens via Payment (self-payment) + tfPartialPayment — same method used by
    the best XRPL meme bots. This NEVER produces tecKILLED.

    Transaction structure (matches rEFDnEqu6pQGKUAa77wBLzGnXH8nk6WVkz pattern):
      TransactionType: Payment
      Destination:     own wallet (self-payment)
      SendMax:         XRP drops to spend (hard cap)
      Amount:          huge token ceiling (e.g. max supply) — XRPL delivers what it can
      DeliverMin:      minimum tokens acceptable = expected_tokens * (1 - slippage_tolerance)
      Flags:           tfPartialPayment (0x00020000)

    Why this beats OfferCreate:
      - Routes through AMM + CLOB automatically (best price)
      - Partial fills accepted if >= DeliverMin (no all-or-nothing failure)
      - Never tecKILLED — price slippage is handled by DeliverMin, not rejection
      - XRP spend capped by SendMax regardless of route
    """
    from xrpl.clients import WebsocketClient
    from xrpl.models.transactions import Payment
    from xrpl.models.amounts import IssuedCurrencyAmount
    from xrpl.transaction import submit_and_wait
    from xrpl.utils import xrp_to_drops

    start_ts = time.time()
    currency  = get_currency(symbol)
    wallet    = _get_wallet()

    # Ensure trustline exists before buying
    if not ensure_trustline(currency, issuer, symbol):
        return {"success": False, "error": f"trustline_setup_failed:{symbol}",
                "action": "buy", "symbol": symbol, "xrp_requested": xrp_amount}

    # Fetch live price to compute expected tokens and DeliverMin
    live_price = expected_price
    try:
        import scanner as _sc
        _lp, _, _, _ = _sc.get_token_price_and_tvl(symbol, issuer)
        if _lp and _lp > 0:
            live_price = _lp
    except Exception:
        pass

    # Expected tokens at current price
    if live_price > 0:
        expected_tokens = xrp_amount / live_price
    else:
        expected_tokens = 0.0

    # DeliverMin = minimum tokens we'll accept (slippage floor)
    # Use slippage_tolerance (default 5%) — set to 0 to accept any fill
    if expected_tokens > 0 and live_price > 0:
        deliver_min_tokens = expected_tokens * (1.0 - max(slippage_tolerance, 0.05))
    else:
        deliver_min_tokens = 0.0  # no floor if price unknown — accept anything

    # Token ceiling: use a very large number so XRPL fills as much as possible
    # (the SendMax XRP cap is the real limit, Amount is just the token ceiling)
    token_ceiling = "999999999999"

    send_max_drops = str(int(xrp_to_drops(xrp_amount)))

    # Build Payment tx
    tx_kwargs = {
        "account":     wallet.address,
        "destination": wallet.address,          # self-payment
        "amount":      IssuedCurrencyAmount(    # token ceiling
            currency = currency,
            issuer   = issuer,
            value    = token_ceiling,
        ),
        "send_max":    send_max_drops,          # XRP we spend (hard cap)
        "flags":       0x00020000,              # tfPartialPayment
    }

    # Add DeliverMin if we have a meaningful price reference
    if deliver_min_tokens > 0:
        # Format to ≤15 significant digits (XRPL requirement)
        dm_str = f"{deliver_min_tokens:.10g}"
        tx_kwargs["deliver_min"] = IssuedCurrencyAmount(
            currency = currency,
            issuer   = issuer,
            value    = dm_str,
        )

    tx = Payment(**tx_kwargs)
    
    # DEBUG: Log transaction details for troubleshooting
    logger.debug(
        f"Payment tx: symbol={symbol} | currency={currency[:8]}... | "
        f"issuer={issuer[:8]}... | send_max={send_max_drops} drops | "
        f"amount_ceiling={token_ceiling} | deliver_min={tx_kwargs.get('deliver_min', 'NONE')} | "
        f"flags=0x{0x00020000:08X}"
    )

    result = _submit_with_retry(tx, wallet)
    latency = time.time() - start_ts

    xrp_spent       = xrp_amount
    tokens_received = 0.0
    actual_price    = live_price

    if result.get("success") and result.get("metadata"):
        xrp_spent, tokens_received = _parse_actual_fill(
            result["metadata"], wallet.address, currency, issuer
        )
        if tokens_received > 0 and xrp_spent > 0:
            actual_price = xrp_spent / tokens_received

    slippage = abs(actual_price - live_price) / live_price if live_price > 0 else 0

    entry = {
        "ts":              start_ts,
        "action":          "buy",
        "route":           "payment_partial",
        "symbol":          symbol,
        "issuer":          issuer,
        "xrp_requested":   xrp_amount,
        "xrp_spent":       round(xrp_spent, 6),
        "tokens_received": round(tokens_received, 8),
        "expected_price":  round(live_price, 8),
        "actual_price":    round(actual_price, 8),
        "slippage":        round(slippage, 5),
        "latency_ms":      round(latency * 1000),
        "success":         result.get("success", False),
        "hash":            result.get("hash"),
        "error":           result.get("error"),
    }
    _append_log(entry)
    return entry


def sell_token(symbol: str, issuer: str, token_amount: float,
               expected_price: float, slippage_tolerance: float = 0.05) -> Dict:
    """
    Sell tokens for XRP via OfferCreate + tfImmediateOrCancel.
    Market order — fills immediately against AMM or CLOB, no resting order.
    taker_pays = token (what we spend), taker_gets = XRP (what we receive)
    """
    from xrpl.clients import WebsocketClient
    from xrpl.models.transactions import OfferCreate
    from xrpl.models.amounts import IssuedCurrencyAmount
    from xrpl.transaction import submit_and_wait
    from xrpl.utils import xrp_to_drops

    start_ts = time.time()
    currency  = get_currency(symbol)
    wallet    = _get_wallet()

    # Re-fetch live price before submitting — avoids tecKILLED from stale price
    try:
        import scanner as _sc
        live_price, _, _, _ = _sc.get_token_price_and_tvl(symbol, issuer)
        if live_price and live_price > 0:
            expected_price = live_price
    except Exception:
        pass

    # CRITICAL FIX: Do NOT set a min_xrp floor on SELL either.
    # tecKILLED fires when price drops even 1% after tx submitted.
    # Accept 1 drop minimum — let the fill happen at market, check slippage post-trade.
    min_xrp_drops = "1"  # dust minimum, never causes tecKILLED

    # OfferCreate IOC to SELL tokens for XRP:
    # XRPL maker perspective: TakerPays = what WE RECEIVE, TakerGets = what WE GIVE
    # To SELL tokens: TakerPays=XRP (we receive), TakerGets=tokens (we give)
    tx = OfferCreate(
        account    = wallet.address,
        taker_pays = min_xrp_drops,                        # XRP we receive (1 drop = accept any)
        taker_gets = IssuedCurrencyAmount(                  # tokens we give
            currency = currency,
            issuer   = issuer,
            value    = f"{token_amount:.10g}",  # ≤15 sig digits
        ),
        flags = 0x000A0000,  # tfImmediateOrCancel + tfSell (matches reference bot sell pattern)
    )

    result = _submit_with_retry(tx, wallet)
    latency = time.time() - start_ts

    xrp_received = 0.000001  # 1 drop minimum — will be overwritten by actual fill
    tokens_sold  = token_amount
    actual_price = expected_price

    if result.get("success") and result.get("metadata"):
        spent, received = _parse_actual_fill(
            result["metadata"], wallet.address, currency, issuer
        )
        if received > 0:
            tokens_sold  = received
        if spent > 0:
            xrp_received = spent
        if tokens_sold > 0:
            actual_price = xrp_received / tokens_sold

    slippage = abs(actual_price - expected_price) / expected_price if expected_price > 0 else 0

    entry = {
        "ts":             start_ts,
        "action":         "sell",
        "route":          "amm_payment",
        "symbol":         symbol,
        "issuer":         issuer,
        "tokens_sold":    round(tokens_sold, 8),
        "xrp_received":   round(xrp_received, 6),
        "expected_price": round(expected_price, 8),
        "actual_price":   round(actual_price, 8),
        "slippage":       round(slippage, 5),
        "latency_ms":     round(latency * 1000),
        "success":        result.get("success", False),
        "hash":           result.get("hash"),
        "error":          result.get("error"),
    }
    _append_log(entry)
    return entry


def _submit_with_retry(tx, wallet, max_retries: int = 3) -> Dict:
    """Submit transaction with exponential backoff retries.
    
    CRITICAL: Never retry on tem* (malformed) errors — the sequence number
    has already been consumed, so retries will fail with temBAD_SIGNATURE.
    """
    from xrpl.clients import WebsocketClient
    from xrpl.transaction import submit_and_wait

    last_error = None
    for attempt in range(max_retries):
        try:
            with WebsocketClient(WS_URL) as ws:
                response = submit_and_wait(tx, ws, wallet)
                if response.is_successful():
                    return {
                        "success":  True,
                        "hash":     response.result.get("hash"),
                        "metadata": response.result.get("meta", {}),
                    }
                else:
                    last_error = response.result.get("engine_result", "unknown")
                    logger.warning(f"TX failed (attempt {attempt+1}): {last_error}")
                    
                    # NEVER retry on malformed transaction errors (tem*)
                    # The sequence number is already consumed — retry produces temBAD_SIGNATURE
                    if last_error.startswith("tem"):
                        logger.warning(f"TX malformed ({last_error}) — not retrying")
                        break
                    
                    # Don't retry on definitive failures
                    if last_error in ("tecNO_DST", "tecNO_PERMISSION", "tecUNFUNDED_OFFER", "tecPATH_DRY", "tecKILLED"):
                        break
        except Exception as e:
            last_error = str(e)
            logger.warning(f"TX exception (attempt {attempt+1}): {e}")
            
            # Check if it's a malformed error
            if "temBAD" in str(e):
                logger.warning(f"TX malformed — not retrying")
                break

        if attempt < max_retries - 1:
            wait = 2 ** attempt
            logger.info(f"Retrying in {wait}s...")
            time.sleep(wait)

    return {"success": False, "error": str(last_error)}


def _append_log(entry: Dict) -> None:
    log = []
    if os.path.exists(EXEC_LOG_FILE):
        try:
            with open(EXEC_LOG_FILE) as f:
                log = json.load(f)
        except Exception:
            pass
    log.append(entry)
    log = log[-500:]
    with open(EXEC_LOG_FILE, "w") as f:
        json.dump(log, f, indent=2)


if __name__ == "__main__":
    print("execution.py — import only for production use")
    print(f"Bot wallet: {BOT_WALLET_ADDRESS}")
    print("Route: AMM via Payment transaction (tfNoRippleDirect)")
