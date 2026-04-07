"""
sizing.py — Confidence-based position sizing for DKTrenchBot v2.
Replaces fixed sizing in bot.py entry logic.

Usage:
    from sizing import calculate_position_size
    size = calculate_position_size(score=65, confidence_inputs={...})
"""

import logging
from typing import Dict

from config import MAX_POSITIONS

logger = logging.getLogger("sizing")

# Maximum position in XRP — hard ceiling enforced always
MAX_POSITION_XRP = 40.0


def calculate_position_size(score: int, confidence_inputs: Dict) -> float:
    """
    Confidence-based position sizing.

    Args:
        score: Composite token score (0-100)
        confidence_inputs: Dict with keys:
            wallet_cluster_active (bool)
            alpha_signal_active (bool)
            ml_probability (float, 0-1)
            regime (str: 'bull'|'bear'|'neutral')
            smart_wallet_count (int)
            tvl_xrp (float)

    Returns:
        Position size in XRP, capped at MAX_POSITION_XRP.

    Example:
        score=65, cluster=True, ml=0.75 →
        base=25, +20%+15%+15% = 25 * 1.50 = 37.5, * liquidity_factor(1.0) = 37.5
    """

    # ── 1. Base size from score tier ─────────────────────────────────────────
    if score >= 65:
        base = 25.0
    elif score >= 50:
        base = 15.0
    elif score >= 40:
        base = 8.0
    else:
        base = 5.0  # below threshold but caller chose to enter (scalp/micro)

    # ── 2. Confidence multiplier (additive bonuses, then apply) ──────────────
    multiplier = 1.0

    # Wallet cluster confirmation
    if confidence_inputs.get("wallet_cluster_active", False):
        multiplier += 0.20
        logger.debug(f"sizing: +20% wallet_cluster_active")

    # Alpha signal (recycler / TrustSet velocity / realtime burst)
    if confidence_inputs.get("alpha_signal_active", False):
        multiplier += 0.15
        logger.debug(f"sizing: +15% alpha_signal_active")

    # ML probability
    ml_prob = float(confidence_inputs.get("ml_probability", 0.5))
    if ml_prob >= 0.75:
        multiplier += 0.15
        logger.debug(f"sizing: +15% ml_prob={ml_prob:.2f}")
    elif ml_prob <= 0.25:
        multiplier -= 0.20
        logger.debug(f"sizing: -20% ml_prob={ml_prob:.2f}")

    # Market regime
    regime = confidence_inputs.get("regime", "neutral")
    if regime == "bull":
        multiplier += 0.10
        logger.debug(f"sizing: +10% regime=bull")
    elif regime == "bear":
        multiplier -= 0.20
        logger.debug(f"sizing: -20% regime=bear")

    # Smart wallet count (tracked wallets in this token)
    sw_count = int(confidence_inputs.get("smart_wallet_count", 0))
    sw_bonus = min(sw_count * 0.05, 0.25)  # +5% per wallet, max +25%
    if sw_bonus > 0:
        multiplier += sw_bonus
        logger.debug(f"sizing: +{sw_bonus:.0%} smart_wallets={sw_count}")

    # Clamp multiplier to [0.5x, 2.0x]
    multiplier = max(0.5, min(2.0, multiplier))

    # ── 3. Liquidity factor (TVL-based, 0.5–1.5) ─────────────────────────────
    tvl = float(confidence_inputs.get("tvl_xrp", 2000))
    liquidity_factor = max(0.5, min(1.5, tvl / 2000.0))
    logger.debug(f"sizing: liquidity_factor={liquidity_factor:.2f} (tvl={tvl:.0f})")

    # ── 4. Final size ─────────────────────────────────────────────────────────
    raw_size = base * multiplier * liquidity_factor
    final_size = min(raw_size, MAX_POSITION_XRP)

    logger.info(
        f"sizing: score={score} base={base} mult={multiplier:.2f} "
        f"liq={liquidity_factor:.2f} raw={raw_size:.1f} final={final_size:.1f} XRP"
    )
    return round(final_size, 2)


if __name__ == "__main__":
    # Self-test
    examples = [
        {
            "label": "score=65, cluster=True, ml=0.75",
            "score": 65,
            "inputs": {
                "wallet_cluster_active": True,
                "alpha_signal_active": False,
                "ml_probability": 0.75,
                "regime": "neutral",
                "smart_wallet_count": 0,
                "tvl_xrp": 2000,
            },
        },
        {
            "label": "score=65, cluster=True, ml=0.75, alpha=True, 2 smart wallets, bull",
            "score": 65,
            "inputs": {
                "wallet_cluster_active": True,
                "alpha_signal_active": True,
                "ml_probability": 0.75,
                "regime": "bull",
                "smart_wallet_count": 2,
                "tvl_xrp": 2000,
            },
        },
        {
            "label": "score=50, bear, ml=0.20",
            "score": 50,
            "inputs": {
                "wallet_cluster_active": False,
                "alpha_signal_active": False,
                "ml_probability": 0.20,
                "regime": "bear",
                "smart_wallet_count": 0,
                "tvl_xrp": 1500,
            },
        },
        {
            "label": "score=40, neutral, no signals",
            "score": 40,
            "inputs": {
                "wallet_cluster_active": False,
                "alpha_signal_active": False,
                "ml_probability": 0.5,
                "regime": "neutral",
                "smart_wallet_count": 0,
                "tvl_xrp": 800,
            },
        },
    ]

    print("=== Confidence-Based Position Sizing Examples ===\n")
    for ex in examples:
        size = calculate_position_size(ex["score"], ex["inputs"])
        print(f"  {ex['label']}")
        print(f"  → {size:.2f} XRP\n")
