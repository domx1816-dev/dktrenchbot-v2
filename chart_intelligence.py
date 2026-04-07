"""
chart_intelligence.py — Classify token market structure.
States: accumulation, pre_breakout, expansion, continuation, exhaustion, reversal_risk, dead
Tradeable states: pre_breakout, expansion, continuation
"""

import os
import json
from typing import Dict, List, Optional
from config import STATE_DIR

os.makedirs(STATE_DIR, exist_ok=True)

TRADEABLE_STATES = {"pre_breakout", "expansion", "continuation"}

CHART_STATES = [
    "accumulation",
    "pre_breakout",
    "expansion",
    "continuation",
    "exhaustion",
    "reversal_risk",
    "dead",
]


def classify(token_key: str, prices: List[float], tvl_readings: List[float],
             breakout_quality: int = 0) -> Dict:
    """
    Classify market structure from price and TVL history.

    Returns dict with: state, confidence, tradeable, details
    """
    if not prices or len(prices) < 2:
        return _result("dead", 0.5, "insufficient_data")

    n = len(prices)
    first = prices[0]
    last  = prices[-1]

    if first <= 0:
        return _result("dead", 0.9, "zero_price")

    pct_change   = (last - first) / first
    recent_3     = prices[-3:] if n >= 3 else prices
    recent_5     = prices[-5:] if n >= 5 else prices

    # Dead: price declining significantly
    if pct_change < -0.20:
        return _result("dead", 0.9, f"price_down_{pct_change:.1%}")

    # TVL trend
    tvl_trend = 0.0
    if len(tvl_readings) >= 2:
        tvl_trend = (tvl_readings[-1] - tvl_readings[0]) / tvl_readings[0] if tvl_readings[0] > 0 else 0

    # Reversal risk: was rising, now dropping, TVL also dropping
    if n >= 5:
        peak_idx  = prices.index(max(prices))
        is_peaked = peak_idx < n - 2
        if is_peaked and last < prices[peak_idx] * 0.90 and tvl_trend < -0.05:
            return _result("reversal_risk", 0.8, "peaked_and_declining")

    # Exhaustion: extreme extension + slowing momentum
    total_move = pct_change
    if total_move > 0.40 and _is_slowing(prices):
        return _result("exhaustion", 0.75, f"extended_{total_move:.1%}_slowing")

    # Expansion: strong uptrend, high breakout quality
    if breakout_quality >= 65 and pct_change > 0.05 and _is_trending_up(recent_5):
        confidence = min(1.0, breakout_quality / 100 + 0.1)
        return _result("expansion", confidence, f"bq={breakout_quality}")

    # Pre-breakout: compression with higher lows
    if breakout_quality >= 40 and abs(pct_change) < 0.08 and _has_higher_lows(prices):
        return _result("pre_breakout", 0.7, "compressed_higher_lows")

    # Continuation: uptrend with pullback-to-support pattern
    if pct_change > 0.03 and _is_continuation(prices):
        return _result("continuation", 0.65, "pullback_continuation")

    # Accumulation: tight range, low volatility, slight upward bias
    if abs(pct_change) < 0.05 and _is_tight_range(prices):
        return _result("accumulation", 0.6, "tight_range")

    # Default based on price direction
    if pct_change > 0.0:
        return _result("continuation", 0.4, "mild_uptrend")
    elif pct_change > -0.10:
        return _result("accumulation", 0.4, "mild_drift")
    else:
        return _result("dead", 0.6, f"declining_{pct_change:.1%}")


def _result(state: str, confidence: float, reason: str) -> Dict:
    return {
        "state":      state,
        "confidence": round(confidence, 3),
        "tradeable":  state in TRADEABLE_STATES,
        "reason":     reason,
    }


def _is_trending_up(prices: List[float]) -> bool:
    if len(prices) < 3:
        return False
    up = sum(1 for i in range(1, len(prices)) if prices[i] > prices[i - 1])
    return up / (len(prices) - 1) >= 0.6


def _is_slowing(prices: List[float]) -> bool:
    """Check if momentum is decelerating."""
    if len(prices) < 4:
        return False
    moves = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    first_half = moves[:len(moves) // 2]
    second_half = moves[len(moves) // 2:]
    avg_first  = sum(first_half) / len(first_half) if first_half else 0
    avg_second = sum(second_half) / len(second_half) if second_half else 0
    return avg_second < avg_first * 0.5


def _has_higher_lows(prices: List[float]) -> bool:
    """Detect higher low pattern."""
    lows = []
    for i in range(1, len(prices) - 1):
        if prices[i] <= prices[i - 1] and prices[i] <= prices[i + 1]:
            lows.append(prices[i])
    if len(lows) < 2:
        return False
    return lows[-1] > lows[0]


def _is_continuation(prices: List[float]) -> bool:
    """Detect pullback-and-resume pattern."""
    if len(prices) < 5:
        return False
    # Was higher, dipped, now recovering
    peak = max(prices[:-2])
    trough = min(prices[-3:])
    last = prices[-1]
    return peak > 0 and trough < peak and last > trough * 1.02


def _is_tight_range(prices: List[float]) -> bool:
    if not prices:
        return False
    high = max(prices)
    low  = min(prices)
    if low <= 0:
        return False
    return (high - low) / low < 0.05


def get_chart_state_score(state: str) -> int:
    """Return scoring points for chart state (used in scoring.py)."""
    return {
        "pre_breakout": 20,
        "accumulation": 12,
        "expansion":     4,   # DATA: 0% WR — keep low until proven otherwise
        "continuation":  6,   # DATA: 17% WR avg -1.4 XRP — real signal only via burst override
    }.get(state, 0)


if __name__ == "__main__":
    # Test with simulated price series
    prices_breakout = [1.0, 1.01, 0.99, 1.00, 1.02, 1.01, 1.02, 1.05, 1.09, 1.15]
    tvls = [5000] * len(prices_breakout)
    result = classify("test", prices_breakout, tvls, breakout_quality=72)
    print(f"Breakout series: {result}")

    prices_dead = [1.0, 0.95, 0.88, 0.80, 0.72, 0.65]
    result2 = classify("test2", prices_dead, [4000] * 6, breakout_quality=10)
    print(f"Dead series: {result2}")
