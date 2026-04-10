"""
execution_core.py — DKTrenchBot Trade Execution
==============================================
Pure execution layer. All intelligence lives in brain.py.
This module only submits transactions and manages split entries.

bot.py → brain.py (decisions) → execution_core.py (execution)
"""

import logging
import time
from typing import Dict, Optional

from config import BOT_WALLET_ADDRESS
import brain  # all sizing/safety decisions

logger = logging.getLogger("execution_core")

# ═══════════════════════════════════════════════════════════════
# Re-export brain functions so callers don't need a second import
# ═══════════════════════════════════════════════════════════════

estimate_slippage   = brain.predict_slippage  # renamed for backward compat
get_safe_entry_size = brain._get_safe_entry_size
pre_trade_validator = brain.pre_trade_validator
position_sizer      = brain.position_sizer

# Safety constants (mirror brain so execution_core consumers don't break)
MAX_SLIPPAGE     = brain.MAX_SLIPPAGE
MIN_CONFIDENCE   = brain.MIN_CONFIDENCE
MIN_POSITION_XRP = brain.MIN_POSITION_XRP
MIN_LIQUIDITY_USD = brain.MIN_LIQUIDITY_USD

# ═══════════════════════════════════════════════════════════════
# Execution Guards — derived from brain's pre_trade_validator
# ═══════════════════════════════════════════════════════════════

def pre_trade_validator(token: Dict, route_quality: str = "GOOD") -> bool:
    """
    Wrapper for brain.pre_trade_validator.
    Kept for backward compatibility with any direct callers.
    """
    size, confidence = _emergency_size_confidence(token)
    ok, reason = brain.pre_trade_validator(token, size, confidence, route_quality)
    if not ok:
        logger.info(f"[execution_core] {token.get('symbol','?')}: {reason}")
    return ok


def _emergency_size_confidence(token: Dict):
    """Fallback size/confidence when not available from caller context."""
    return token.get("last_size", 10.0), token.get("confidence", 0.5)


# ═══════════════════════════════════════════════════════════════
# Split Execution
# ═══════════════════════════════════════════════════════════════

def split_execute(token: Dict, size: float, side: str = "buy") -> Dict:
    """
    Split entry: 40% then 60% after 2s stability wait.
    Reduces price impact on larger positions.
    """
    import execution as exec_mod

    leg1 = size * 0.40
    leg2 = size * 0.60

    if side == "buy":
        result1 = exec_mod.buy_token(
            symbol=token["symbol"], issuer=token["issuer"],
            xrp_amount=leg1, expected_price=token.get("price", 0),
            slippage_tolerance=0.10,
        )
    else:
        result1 = exec_mod.sell_token(
            symbol=token["symbol"], issuer=token["issuer"],
            token_amount=token.get("balance", 0),
            expected_price=token.get("price", 0),
            slippage_tolerance=0.10,
        )

    if not result1.get("success"):
        return {"first": result1, "second": None, "split": False}

    time.sleep(2.0)

    if side == "buy":
        result2 = exec_mod.buy_token(
            symbol=token["symbol"], issuer=token["issuer"],
            xrp_amount=leg2, expected_price=token.get("price", 0),
            slippage_tolerance=0.10,
        )
    else:
        result2 = exec_mod.sell_token(
            symbol=token["symbol"], issuer=token["issuer"],
            token_amount=token.get("balance", 0),
            expected_price=token.get("price", 0),
            slippage_tolerance=0.10,
        )

    return {"first": result1, "second": result2, "split": True, "size": size}


# ═══════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════

def execute_trade(
    token: Dict,
    classification: Dict,
    strategy,
    wallet_state: Dict,
    route_quality: str = "GOOD",
    side: str = "buy",
) -> Optional[Dict]:
    """
    Centralized execution pipeline. All intelligence gates are in brain.pre_trade_validator.
    This function only handles transaction submission and split entries.
    """
    symbol = token.get("symbol", "?")

    # Brain-based validation
    size = brain.position_sizer(token, classification, wallet_state)
    if size <= 0:
        logger.info(f"[execution_core] {symbol}: position_sizer returned 0")
        return None

    ok, reason = brain.pre_trade_validator(
        token, size,
        classification.get("confidence", 0.5),
        route_quality
    )
    if not ok:
        logger.info(f"[execution_core] {symbol}: {reason}")
        return None

    # Strategy confirm gate
    try:
        if not strategy or not hasattr(strategy, "valid"):
            logger.error(f"INVALID STRATEGY OBJECT — skipping {token.symbol}")
            return None

        if not strategy.valid(token):
            logger.info(f"[execution_core] {symbol}: strategy.valid()=False")
            return None
        if not strategy.confirm(token):
            logger.info(f"[execution_core] {symbol}: strategy.confirm()=False")
            return None
    except Exception as e:
        logger.warning(f"[execution_core] {symbol}: strategy check exception: {e}")
        return None

    # Execute
    logger.info(f"[execution_core] EXECUTE {symbol}: {size:.2f} XRP ({side})")
    result = split_execute(token, size, side=side)
    return result


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("execution_core.py — decisions delegated to brain.py")
    print(f"  MAX_SLIPPAGE     : {MAX_SLIPPAGE:.1%}")
    print(f"  MIN_CONFIDENCE   : {MIN_CONFIDENCE}")
    print(f"  MIN_POSITION_XRP : {MIN_POSITION_XRP}")
    print(f"  MIN_LIQUIDITY_USD: ${MIN_LIQUIDITY_USD}")
