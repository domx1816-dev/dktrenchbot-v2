"""
execution_hardener.py — Resilient execution wrapper for DKTrenchBot v2

Sits in front of execution.py to add:
  - 3-attempt retry with exponential backoff
  - Fail-fast on unrecoverable XRPL errors
  - Ghost fill detection (buy succeeds but 0 tokens received)
  - Orphan position tracking on partial failures
  - State save on any failure
  - Unified buy/sell surface (safe_buy / safe_sell)

All function names match the actual codebase (execution.buy_token, brain.pre_trade_validator, etc.)
"""

import time
import logging
import traceback
from typing import Dict, Optional, Any, Tuple

log = logging.getLogger("execution_hardener")

# ── Config ─────────────────────────────────────────────────────────────────
MAX_RETRIES           = 3
RETRY_BASE_SLEEP      = 0.6   # seconds (doubles each retry)
SELL_RETRY_BASE_SLEEP = 0.8
MIN_SUCCESS_TOKENS    = 1e-12  # ghost fill threshold
DEFAULT_BUY_SLIP      = 0.12
DEFAULT_SELL_SLIP     = 0.12

# XRPL result codes that will NEVER succeed on retry — bail immediately
FAIL_FAST_ERRORS = {
    "tecINSUF_FUND", "tecUNFUNDED_OFFER", "tecPATH_DRY",
    "tecNO_AUTH", "temBAD_AMOUNT", "temBAD_OFFER", "tecNO_LINE",
    "tecNO_PERMISSION", "temDISABLED",
}


# ── Helpers ─────────────────────────────────────────────────────────────────

def _safe_get(d: Optional[Dict], key: str, default=None):
    if not isinstance(d, dict):
        return default
    return d.get(key, default)


def _sleep_backoff(base: float, attempt: int):
    time.sleep(base * (2 ** attempt))


def _normalize_result(result: Any, side: str) -> Dict:
    if isinstance(result, dict):
        return result
    return {
        "success": False,
        "error": f"invalid_result_type:{type(result).__name__}",
        "side": side,
    }


def _is_fail_fast(err: str) -> bool:
    e = (err or "").upper().replace("-", "_").replace(" ", "_")
    return any(k in e for k in FAIL_FAST_ERRORS)


def _call_brain_pretrade(brain, token: Dict, size: float,
                         confidence: float, route_quality: str) -> Tuple[bool, str]:
    """Call brain.pre_trade_validator safely."""
    try:
        return brain.pre_trade_validator(token, size, confidence, route_quality)
    except Exception as e:
        return False, f"pretrade_exception:{e}"


def _call_buy(execution, token: Dict, size: float,
              expected_price: float, slippage: float) -> Dict:
    return execution.buy_token(
        symbol            = _safe_get(token, "symbol"),
        issuer            = _safe_get(token, "issuer"),
        xrp_amount        = size,
        expected_price    = expected_price,
        slippage_tolerance = slippage,
    )


def _call_sell(execution, token: Dict, size: float,
               expected_price: float, slippage: float) -> Dict:
    token_amount = (
        _safe_get(token, "tokens_held", 0)
        or _safe_get(token, "balance", 0)
        or size
    )
    return execution.sell_token(
        symbol            = _safe_get(token, "symbol"),
        issuer            = _safe_get(token, "issuer"),
        token_amount      = token_amount,
        expected_price    = expected_price,
        slippage_tolerance = slippage,
    )


# ── Core ────────────────────────────────────────────────────────────────────

def robust_execute(
    *,
    brain,
    execution,
    token: Dict,
    classification: Dict,
    wallet_state: Dict,
    route_quality: str    = "GOOD",
    side: str             = "buy",
    expected_price: Optional[float] = None,
    size: Optional[float] = None,
    max_retries: int      = MAX_RETRIES,
    buy_slippage: float   = DEFAULT_BUY_SLIP,
    sell_slippage: float  = DEFAULT_SELL_SLIP,
    # Hooks (all optional)
    update_orphan_fn      = None,
    save_state_fn         = None,
    on_success_fn         = None,
    on_failure_fn         = None,
) -> Dict:
    token          = token or {}
    classification = classification or {}
    wallet_state   = wallet_state or {}

    symbol     = _safe_get(token, "symbol", "?")
    confidence = _safe_get(classification, "confidence", 0.5)

    # ── Sizing ─────────────────────────────────────────────────────────────
    if size is None:
        size = _safe_get(token, "size", None)
    if size is None:
        try:
            size = brain.position_sizer(token, classification, wallet_state)
        except Exception as e:
            return {"success": False, "error": f"sizer_exception:{e}", "symbol": symbol}

    if not size or size <= 0:
        return {"success": False, "error": "size_zero", "symbol": symbol}

    # ── Pre-trade gate ──────────────────────────────────────────────────────
    ok, reason = _call_brain_pretrade(brain, token, size, confidence, route_quality)
    if not ok:
        log.info("pretrade_reject symbol=%s reason=%s", symbol, reason)
        return {"success": False, "error": f"pretrade_reject:{reason}",
                "symbol": symbol, "size": size}

    # ── Execution with retry ────────────────────────────────────────────────
    slip     = buy_slippage if side == "buy" else sell_slippage
    px       = expected_price if expected_price is not None else _safe_get(token, "price", 0) or 0
    last_err = None

    for attempt in range(max_retries):
        try:
            if side == "buy":
                raw = _call_buy(execution, token, size, px, slip)
            else:
                raw = _call_sell(execution, token, size, px, slip)

            result = _normalize_result(raw, side)

            if result.get("success"):
                # Ghost fill check
                if side == "buy":
                    tokens_rx = float(result.get("tokens_received", 0) or 0)
                    if tokens_rx < MIN_SUCCESS_TOKENS:
                        last_err = f"ghost_fill:{tokens_rx}"
                        log.warning("ghost_fill symbol=%s tokens_received=%s", symbol, tokens_rx)
                        result = {"success": False, "error": last_err}
                    else:
                        if on_success_fn:
                            try:
                                on_success_fn(result, token, classification, wallet_state)
                            except Exception as hook_err:
                                log.warning("success_hook_failed:%s", hook_err)
                        return result
                else:
                    if on_success_fn:
                        try:
                            on_success_fn(result, token, classification, wallet_state)
                        except Exception as hook_err:
                            log.warning("success_hook_failed:%s", hook_err)
                    return result
            else:
                last_err = str(result.get("error") or "unknown")
                log.warning("exec_failed symbol=%s side=%s attempt=%d err=%s",
                            symbol, side, attempt + 1, last_err)

                # Fail fast on unrecoverable XRPL errors
                if _is_fail_fast(last_err):
                    log.info("fail_fast symbol=%s err=%s", symbol, last_err)
                    break

                # Sell: try wider slippage once on UNFUNDED
                if side == "sell" and "UNFUNDED" in last_err.upper():
                    try:
                        alt = _normalize_result(
                            _call_sell(execution, token, size, px, min(0.30, slip * 2.0)),
                            "sell"
                        )
                        if alt.get("success"):
                            log.info("alt_sell_succeeded symbol=%s", symbol)
                            return alt
                    except Exception as alt_err:
                        last_err = f"alt_sell:{alt_err}"

        except Exception as e:
            last_err = f"exception:{traceback.format_exc(limit=2)}"
            log.error("exec_exception symbol=%s side=%s: %s", symbol, side, e)

        if attempt < max_retries - 1:
            _sleep_backoff(SELL_RETRY_BASE_SLEEP if side == "sell" else RETRY_BASE_SLEEP, attempt)

    # ── All attempts exhausted ──────────────────────────────────────────────
    failure = {
        "success":      False,
        "error":        last_err or "execution_failed",
        "symbol":       symbol,
        "side":         side,
        "size":         size,
        "route_quality": route_quality,
    }

    if side == "buy" and update_orphan_fn:
        try:
            update_orphan_fn(token, size, failure)
        except Exception as e:
            log.warning("orphan_fn_failed:%s", e)

    if save_state_fn:
        try:
            save_state_fn()
        except Exception as e:
            log.warning("save_state_failed:%s", e)

    if on_failure_fn:
        try:
            on_failure_fn(failure, token, classification, wallet_state)
        except Exception as e:
            log.warning("failure_fn_failed:%s", e)

    return failure


# ── Public API ──────────────────────────────────────────────────────────────

def safe_buy(*, brain, execution, token, classification,
             wallet_state, route_quality="GOOD",
             expected_price=None, **kwargs) -> Dict:
    """Resilient buy with retry, ghost fill detection, orphan tracking."""
    return robust_execute(
        brain=brain, execution=execution, token=token,
        classification=classification, wallet_state=wallet_state,
        route_quality=route_quality, side="buy",
        expected_price=expected_price, **kwargs,
    )


def safe_sell(*, brain, execution, token, classification,
              wallet_state, route_quality="GOOD",
              expected_price=None, **kwargs) -> Dict:
    """Resilient sell with retry and wider-slippage fallback."""
    return robust_execute(
        brain=brain, execution=execution, token=token,
        classification=classification, wallet_state=wallet_state,
        route_quality=route_quality, side="sell",
        expected_price=expected_price, **kwargs,
    )
