"""
scoring.py — Composite token score (0-100).
Components:
  breakout_quality:   0-25 pts
  chart_state:        0-20 pts
  liquidity_depth:    0-15 pts
  issuer_safety:      0-10 pts
  route_quality:      0-10 pts
  smart_money:        0-10 pts
  extension_penalty: -20-0 pts
  regime_bonus:      -10-+5 pts

Thresholds: 85+=elite, 70-84=tradeable, 60-69=small_size, <60=skip
"""

from typing import Dict, Optional
from config import SCORE_ELITE, SCORE_TRADEABLE, SCORE_SMALL


def compute_score(
    breakout_quality:  int   = 0,
    chart_state:       str   = "dead",
    chart_confidence:  float = 0.5,
    tvl_xrp:          float = 0.0,
    issuer_safe:       bool  = False,
    issuer_warnings:   int   = 0,
    route_slippage:    float = 0.05,
    route_exit_ok:     bool  = True,
    smart_money_boost: int   = 0,     # 0, 10, or 20
    extension_pct:     float = 0.0,   # total price move from entry
    tvl_change_pct:    float = 0.0,   # TVL % change vs last reading (momentum signal)
    regime:            str   = "neutral",
    regime_override:   bool  = False,
    symbol:            str   = "",    # for TG signal lookup
) -> Dict:
    """
    Compute composite score. Returns dict with total and breakdown.
    """
    breakdown = {}

    # 1. Breakout quality: 0-35 pts (primary signal — learned 2026-04-03)
    # Linear up to BQ=60, then bonus acceleration for high conviction
    if breakout_quality >= 80:
        bq_pts = 35
    elif breakout_quality >= 60:
        bq_pts = 25 + int((breakout_quality - 60) * 0.5)   # 25-35 pts
    else:
        bq_pts = int(breakout_quality * 0.42)               # 0-25 pts
    breakdown["breakout_quality"] = bq_pts

    # 2. Chart state quality: 0-20 pts
    from chart_intelligence import get_chart_state_score
    cs_pts = get_chart_state_score(chart_state)
    # Scale by confidence
    cs_pts = int(cs_pts * chart_confidence)
    breakdown["chart_state"] = cs_pts

    # 3. Liquidity depth: 0-30 pts
    # DATA REBUILD 2026-04-06: Score 80-100 (high TVL, established pools) = 0% WR, all stales.
    # Winners cluster in MICRO TVL (under 3K XRP) — fresh launches, not discovered yet.
    # INVERTED from previous: reward fresh/micro, penalise large/established.
    if 500 <= tvl_xrp < 2_000:
        liq_pts = 30   # ⭐ sweet spot — fresh launch, not yet discovered
    elif 200 <= tvl_xrp < 500:
        liq_pts = 25   # very early, high volatility, PHX-type launch window
    elif 2_000 <= tvl_xrp < 5_000:
        liq_pts = 20   # early stage — still moveable
    elif 5_000 <= tvl_xrp < 15_000:
        liq_pts = 10   # mid — already partially discovered
    elif 15_000 <= tvl_xrp < 40_000:
        liq_pts = 5    # large — slow mover, stale risk
    elif tvl_xrp >= 40_000:
        liq_pts = 0    # very large — won't move meaningfully, skip
    else:
        liq_pts = 0    # too thin (<200 XRP) — ghost pool

    # TVL momentum bonus: rapidly growing pool = community piling in (+0 to +10 pts)
    if tvl_change_pct >= 0.50:
        liq_pts = min(liq_pts + 10, 30)  # TVL up 50%+ — live launch happening
    elif tvl_change_pct >= 0.25:
        liq_pts = min(liq_pts + 6, 30)
    elif tvl_change_pct >= 0.10:
        liq_pts = min(liq_pts + 3, 30)

    breakdown["liquidity_depth"] = liq_pts

    # 4. Issuer safety: 0-10 pts
    if issuer_safe:
        issuer_pts = 10
    elif issuer_warnings == 0:
        issuer_pts = 6
    else:
        issuer_pts = max(0, 6 - issuer_warnings * 2)
    breakdown["issuer_safety"] = issuer_pts

    # 5. Route quality: 0-10 pts
    if route_slippage <= 0.005:
        route_pts = 10
    elif route_slippage <= 0.01:
        route_pts = 8
    elif route_slippage <= 0.02:
        route_pts = 5
    elif route_slippage <= 0.03:
        route_pts = 2
    else:
        route_pts = 0
    if not route_exit_ok:
        route_pts = max(0, route_pts - 5)
    breakdown["route_quality"] = route_pts

    # 6. Smart money: 0-10 pts
    sm_pts = min(10, smart_money_boost)
    breakdown["smart_money"] = sm_pts

    # 6b. Wallet Cluster boost (Audit #2): +30 if 2+ smart wallets entering same token
    cluster_boost = 0
    try:
        import wallet_cluster as _wc
        cluster_boost = _wc.get_cluster_boost(symbol, issuer) if symbol and issuer else 0
    except Exception:
        pass
    breakdown["wallet_cluster"] = cluster_boost

    # 6d. Alpha Recycler boost (Audit #3): +25 if a tracked wallet just recycled into this token
    recycler_boost = 0
    try:
        import alpha_recycler as _ar
        recycler_boost = _ar.get_alpha_recycler_boost(symbol, issuer) if symbol and issuer else 0
    except Exception:
        pass
    breakdown["alpha_recycler"] = recycler_boost

    # 7. Extension penalty: -20 to 0
    if extension_pct >= 0.50:
        ext_penalty = -20
    elif extension_pct >= 0.35:
        ext_penalty = -15
    elif extension_pct >= 0.25:
        ext_penalty = -10
    elif extension_pct >= 0.15:
        ext_penalty = -5
    else:
        ext_penalty = 0
    breakdown["extension_penalty"] = ext_penalty

    # 8. Regime bonus: -10 to +5
    regime_bonus = {
        "hot":     5,
        "neutral": 0,
        "cold":   -5,
        "danger": -10,
    }.get(regime, 0)
    breakdown["regime_bonus"] = regime_bonus

    # 9. ML score adjustment (active only after 50+ trades; silent in logging phase)
    ml_adj = 0
    try:
        from config import ML_ENABLED
        if ML_ENABLED:
            import ml_model as _ml
            from datetime import datetime
            _ml_features = {
                "total_score":              sum(breakdown.values()),
                "entry_tvl_xrp":            tvl_xrp,
                "hour_utc":                 datetime.utcnow().hour,
                "wallet_cluster_boost":     cluster_boost,
                "alpha_recycler_boost":     recycler_boost,
                "smart_wallet_count":       0,   # unknown at scoring time
                "cluster_active":           cluster_boost > 0,
                "alpha_signal_active":      recycler_boost > 0,
                "momentum_score_at_entry":  float(cs_pts),
            }
            ml_adj = _ml.get_ml_score_adjustment(_ml_features)
    except Exception:
        pass
    breakdown["ml_adjustment"] = ml_adj

    total = sum(breakdown.values())
    total = max(0, min(100, total))

    band = "skip"
    if total >= SCORE_ELITE:
        band = "elite"
    elif total >= SCORE_TRADEABLE:
        band = "tradeable"
    elif total >= SCORE_SMALL:
        band = "small_size"

    return {
        "total":     total,
        "band":      band,
        "breakdown": breakdown,
    }


def position_size(score: int, regime: str, base_xrp: float = 5.0,
                  elite_xrp: float = 7.5, small_xrp: float = 2.5,
                  bq: int = 50, wallet_xrp: float = 0.0) -> float:
    """
    Score-band primary sizing with BQ and regime multipliers.
    Kelly was giving negative edge on low BQ tokens — unreliable as primary.
    Band is the anchor, BQ and regime are modifiers.
    """
    if regime == "danger":
        # Danger doesn't return 0 — half size, stay in the game
        return max(small_xrp, base_xrp * 0.5)

    regime_mult = {"hot": 1.2, "neutral": 1.0, "cold": 0.85}.get(regime, 1.0)

    # ── Capital-aware sizing ─────────────────────────────────────────────────
    # Scale base sizes proportionally to available capital.
    # Target: 8-10% of spendable per hold trade, 3% per scalp.
    # At 90 XRP spendable: base=9, elite=13.5
    # At 180 XRP spendable: base=14, elite=20
    if wallet_xrp > 50:
        capital_scalar = min(wallet_xrp / 90.0, 1.8)  # cap at 1.8x base
        base_xrp  = round(base_xrp  * capital_scalar, 1)
        elite_xrp = round(elite_xrp * capital_scalar, 1)
        small_xrp = round(small_xrp * capital_scalar, 1)

    # Primary size from score band
    if score >= SCORE_ELITE:
        base = elite_xrp
    elif score >= SCORE_TRADEABLE:
        base = base_xrp
    else:
        base = small_xrp

    # BQ conviction multiplier
    if bq >= 80:   bq_mult = 1.3
    elif bq >= 65: bq_mult = 1.15
    elif bq >= 50: bq_mult = 1.0
    else:          bq_mult = 0.9

    # Score conviction bonus
    if score >= SCORE_ELITE:
        score_mult = min(1.0 + (score - SCORE_ELITE) * 0.01, 1.3)
    else:
        score_mult = 1.0

    size = base * regime_mult * bq_mult * score_mult

    # Hard cap: never more than 20% of wallet in one trade
    if wallet_xrp > 0:
        size = min(size, wallet_xrp * 0.20)

    # Floor
    size = max(size, small_xrp)

    return round(size, 2)


def size_multiplier(score: int, regime: str) -> float:
    """Legacy multiplier — kept for compatibility."""
    if regime == "danger":
        return 0.0
    base = {"hot": 1.2, "neutral": 1.0, "cold": 0.5}.get(regime, 1.0)
    if score >= SCORE_ELITE:
        return base * 1.5
    elif score >= SCORE_TRADEABLE:
        return base * 1.0
    elif score >= SCORE_SMALL:
        return base * 0.5
    else:
        return 0.0


if __name__ == "__main__":
    result = compute_score(
        breakout_quality=75,
        chart_state="pre_breakout",
        chart_confidence=0.8,
        tvl_xrp=15000,
        issuer_safe=True,
        route_slippage=0.015,
        route_exit_ok=True,
        smart_money_boost=10,
        extension_pct=0.08,
        regime="neutral",
    )
    print(f"Score: {result['total']} ({result['band']})")
    print(f"Breakdown: {result['breakdown']}")
