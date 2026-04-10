"""
sizing.py — Dynamic capital-based position sizing for DKTrenchBot v2.
Scales position size based on available wallet balance and confidence signals.

Usage:
    from sizing import calculate_position_size
    size = calculate_position_size(score=65, wallet_balance=150, confidence_inputs={...})
"""

import logging
from typing import Dict

logger = logging.getLogger("sizing")

# Position sizing as % of available balance
# Reduced from 20/12/6/3% — avg 9.5 XRP on 200 XRP wallet was 4.75%
# but stale exits at -1.29 XRP avg mean each loss = 13.5% of intended size
# Target: max 5% per trade on standard, 8% on elite burst signals
BASE_PCT_ELITE = 0.06   # 6% of balance for elite (score≥65) — cut from 8% (QuantX patch Apr 10)
BASE_PCT_NORMAL = 0.05  # 5% of balance for normal (score≥50) — was 12%
BASE_PCT_SMALL = 0.03   # 3% of balance for small (score≥40) — was 6%
BASE_PCT_SCALP = 0.02   # 2% of balance for scalp/micro — was 3%

# Hard limits per position (safety ceiling)
MAX_POSITION_XRP = 10.0   # Hard cap per trade — cut from 15 (QuantX patch Apr 10)
MIN_POSITION_XRP = 3.0    # Minimum viable position


def calculate_position_size(score: int, wallet_balance: float, confidence_inputs: Dict) -> float:
    """
    Dynamic position sizing based on wallet balance and confidence.

    Args:
        score: Composite token score (0-100)
        wallet_balance: Available XRP balance in wallet
        confidence_inputs: Dict with keys:
            wallet_cluster_active (bool)
            alpha_signal_active (bool)
            ml_probability (float, 0-1)
            regime (str: 'bull'|'bear'|'neutral')
            smart_wallet_count (int)
            tvl_xrp (float)

    Returns:
        Position size in XRP, scaled to balance.
    """
    if wallet_balance <= 0:
        return 0.0

    # ── 1. Base size as % of balance ─────────────────────────────────────────
    if score >= 65:
        base_pct = BASE_PCT_ELITE
    elif score >= 50:
        base_pct = BASE_PCT_NORMAL
    elif score >= 40:
        base_pct = BASE_PCT_SMALL
    else:
        base_pct = BASE_PCT_SCALP

    base_xrp = wallet_balance * base_pct

    # ── 2. Confidence multiplier (additive bonuses) ──────────────────────────
    multiplier = 1.0

    if confidence_inputs.get("wallet_cluster_active", False):
        multiplier += 0.20

    if confidence_inputs.get("alpha_signal_active", False):
        multiplier += 0.15

    # TrustSet burst signal — explosive early launch, max aggression
    if confidence_inputs.get("ts_burst_active", False):
        ts_count = int(confidence_inputs.get("ts_burst_count", 0))
        if ts_count >= 50:
            multiplier += 0.50   # PHX-level burst — all in
        elif ts_count >= 25:
            multiplier += 0.35   # strong burst
        elif ts_count >= 8:
            multiplier += 0.20   # early burst signal

    ml_prob = float(confidence_inputs.get("ml_probability", 0.5))
    if ml_prob >= 0.75:
        multiplier += 0.15
    elif ml_prob <= 0.25:
        multiplier -= 0.20

    regime = confidence_inputs.get("regime", "neutral")
    if regime == "bull":
        multiplier += 0.10
    elif regime == "bear":
        multiplier -= 0.20

    sw_count = int(confidence_inputs.get("smart_wallet_count", 0))
    sw_bonus = min(sw_count * 0.05, 0.25)
    if sw_bonus > 0:
        multiplier += sw_bonus

    # Clamp multiplier to [0.5x, 2.5x]
    multiplier = max(0.5, min(2.5, multiplier))

    # ── 3. Liquidity factor (TVL-based, 0.5–1.5) ─────────────────────────────
    tvl = float(confidence_inputs.get("tvl_xrp", 2000))

    # TrustSet burst entries: size is slippage-constrained by TVL.
    # A thin pool (50-200 XRP) will move 20-40% against you if you throw 20+ XRP in.
    # Cap aggressively on micro pools, open up once pool can absorb the position.
    if confidence_inputs.get("ts_burst_active", False):
        if tvl < 200:
            # Ghost-thin pool — toe in only, 7 XRP max regardless of score
            liquidity_factor = 0.0   # overridden below by hard cap
            raw_size = 7.0
            final_size = max(MIN_POSITION_XRP, min(7.0, raw_size))
            logger.info(
                f"sizing: BURST micro-pool TVL={tvl:.0f} XRP → hard cap 7 XRP (slippage protection)"
            )
            return round(final_size, 2)
        elif tvl < 500:
            # Sub-$1000 MC zone — scale 7–15 XRP proportionally to TVL
            # At TVL=200 → 7 XRP, at TVL=500 → 15 XRP
            capped_size = 7.0 + (tvl - 200) / 300 * 8.0   # linear 7→15 over 200-500 XRP TVL
            raw_size = base_xrp * multiplier
            final_size = max(MIN_POSITION_XRP, min(capped_size, raw_size))
            logger.info(
                f"sizing: BURST thin-pool TVL={tvl:.0f} XRP → slippage cap {capped_size:.1f} XRP → {final_size:.1f} XRP"
            )
            return round(final_size, 2)
        else:
            # TVL ≥ 500 XRP — pool can absorb it, 1.0x flat
            liquidity_factor = 1.0
    else:
        liquidity_factor = max(0.5, min(1.5, tvl / 2000.0))

    # ── 4. Final size with safety caps ────────────────────────────────────────
    raw_size = base_xrp * multiplier * liquidity_factor
    final_size = max(MIN_POSITION_XRP, min(raw_size, MAX_POSITION_XRP))

    logger.info(
        f"sizing: score={score} bal={wallet_balance:.0f} base={base_xrp:.1f} "
        f"mult={multiplier:.2f} liq={liquidity_factor:.2f} → {final_size:.1f} XRP"
    )
    return round(final_size, 2)


if __name__ == "__main__":
    examples = [
        {"label": "150 XRP, score=65, cluster=True, ml=0.75", "bal": 150, "score": 65,
         "inputs": {"wallet_cluster_active": True, "ml_probability": 0.75, "tvl_xrp": 2000}},
        {"label": "225 XRP, score=65, all signals+", "bal": 225, "score": 65,
         "inputs": {"wallet_cluster_active": True, "alpha_signal_active": True,
                    "ml_probability": 0.75, "regime": "bull", "smart_wallet_count": 2, "tvl_xrp": 3000}},
        {"label": "150 XRP, score=50, neutral", "bal": 150, "score": 50,
         "inputs": {"ml_probability": 0.5, "tvl_xrp": 1500}},
    ]
    print("=== Dynamic Position Sizing ===\n")
    for ex in examples:
        size = calculate_position_size(ex["score"], ex["bal"], ex["inputs"])
        print(f"  {ex['label']}")
        print(f"  → {size:.2f} XRP ({size/ex['bal']*100:.1f}% of balance)\n")
