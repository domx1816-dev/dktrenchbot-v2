"""
breakout.py — Price breakout detection and quality scoring.
Tracks price over up to 20 readings, detects higher lows, compression,
breakout strength, wick quality, and extension.
Returns breakout_quality: 0-100
"""

import os
import json
from typing import Dict, List, Optional, Tuple
from config import STATE_DIR

os.makedirs(STATE_DIR, exist_ok=True)

BREAKOUT_FILE = os.path.join(STATE_DIR, "breakout_data.json")


def _load_data() -> Dict:
    if os.path.exists(BREAKOUT_FILE):
        try:
            with open(BREAKOUT_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_data(data: Dict) -> None:
    with open(BREAKOUT_FILE, "w") as f:
        json.dump(data, f)


def update_price(token_key: str, price: float, volume_proxy: float = 0.0) -> None:
    """Add a price reading to history (max 20 kept)."""
    data = _load_data()
    if token_key not in data:
        data[token_key] = []
    data[token_key].append({"price": price, "vol": volume_proxy})
    if len(data[token_key]) > 20:
        data[token_key] = data[token_key][-20:]
    _save_data(data)


def _higher_lows(prices: List[float]) -> float:
    """Score 0-1 based on proportion of higher lows."""
    if len(prices) < 3:
        return 0.5
    lows = []
    for i in range(1, len(prices) - 1):
        if prices[i] < prices[i - 1] and prices[i] < prices[i + 1]:
            lows.append(prices[i])
    if len(lows) < 2:
        return 0.5
    higher_low_count = sum(1 for i in range(1, len(lows)) if lows[i] > lows[i - 1])
    return higher_low_count / (len(lows) - 1)


def _compression_score(prices: List[float]) -> float:
    """
    Measure price compression (tight range before breakout).
    Score 0-1: 1.0 = very tight compression.
    """
    if len(prices) < 4:
        return 0.5
    # Look at the middle portion of history
    window = prices[max(0, len(prices) - 6):-1] if len(prices) > 6 else prices[:-1]
    if not window:
        return 0.5
    high = max(window)
    low  = min(window)
    if low <= 0:
        return 0.0
    range_pct = (high - low) / low
    # < 3% range = very compressed
    if range_pct < 0.03:
        return 1.0
    elif range_pct < 0.06:
        return 0.8
    elif range_pct < 0.10:
        return 0.6
    elif range_pct < 0.15:
        return 0.4
    else:
        return 0.2


def _breakout_strength(prices: List[float]) -> float:
    """
    Compare last price to the recent range high.
    Returns 0-1 score.
    """
    if len(prices) < 3:
        return 0.0
    recent = prices[-5:] if len(prices) >= 5 else prices
    prior  = prices[:-1]
    if not prior:
        return 0.0
    prior_high = max(prior[-5:]) if len(prior) >= 5 else max(prior)
    last = prices[-1]
    if prior_high <= 0:
        return 0.0
    strength = (last - prior_high) / prior_high
    # Score: 0%=0, 3%=0.5, 8%+=1.0
    if strength <= 0:
        return 0.0
    elif strength >= 0.08:
        return 1.0
    else:
        return strength / 0.08


def _wick_quality(prices: List[float]) -> float:
    """
    Estimate wick quality from price action.
    We don't have candle data, so proxy: steady uptrend = good wicks.
    Score 0-1.
    """
    if len(prices) < 3:
        return 0.5
    # Count how many periods closed above open (price higher than prior)
    bullish = sum(1 for i in range(1, len(prices)) if prices[i] > prices[i - 1])
    return bullish / (len(prices) - 1)


def _extension_check(prices: List[float]) -> float:
    """
    Penalty for being overextended. Returns 0-1 (1=not extended, 0=fully extended).
    """
    if len(prices) < 3:
        return 1.0
    start = prices[0]
    last  = prices[-1]
    if start <= 0:
        return 1.0
    total_move = (last - start) / start
    # > 50% move without pullback = extended
    if total_move > 0.50:
        return 0.0
    elif total_move > 0.30:
        return 0.3
    elif total_move > 0.20:
        return 0.6
    elif total_move > 0.10:
        return 0.85
    else:
        return 1.0


def compute_breakout_quality(token_key: str) -> Dict:
    """
    Compute breakout_quality (0-100) and component scores.
    """
    data = _load_data()
    readings = data.get(token_key, [])

    if len(readings) < 2:
        return {
            "breakout_quality": 0,
            "reason": "insufficient_data",
            "readings": len(readings),
        }

    prices = [r["price"] for r in readings if r.get("price", 0) > 0]
    if len(prices) < 2:
        return {"breakout_quality": 0, "reason": "no_prices"}

    hl_score      = _higher_lows(prices)
    comp_score    = _compression_score(prices)
    strength      = _breakout_strength(prices)
    wick_q        = _wick_quality(prices)
    extension     = _extension_check(prices)

    # Weighted composite → 0-100
    raw = (
        hl_score   * 25 +
        comp_score * 20 +
        strength   * 30 +
        wick_q     * 15 +
        extension  * 10
    )
    quality = min(100, max(0, int(raw)))

    return {
        "breakout_quality": quality,
        "higher_lows":      round(hl_score, 3),
        "compression":      round(comp_score, 3),
        "strength":         round(strength, 3),
        "wick_quality":     round(wick_q, 3),
        "extension":        round(extension, 3),
        "readings":         len(prices),
        "price_first":      prices[0],
        "price_last":       prices[-1],
        "pct_change":       round((prices[-1] - prices[0]) / prices[0] * 100, 2) if prices[0] > 0 else 0,
    }


def get_breakout_quality(token_key: str, current_price: float) -> int:
    """Update price history and return breakout_quality score."""
    update_price(token_key, current_price)
    result = compute_breakout_quality(token_key)
    return result.get("breakout_quality", 0)


if __name__ == "__main__":
    import time
    key = "TEST:rTest123"
    # Simulate accumulation then breakout
    prices = [1.0, 1.01, 0.99, 1.00, 1.02, 1.01, 1.03, 1.05, 1.08, 1.12]
    for p in prices:
        update_price(key, p)
        time.sleep(0.01)
    result = compute_breakout_quality(key)
    print(json.dumps(result, indent=2))
