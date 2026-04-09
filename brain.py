"""
brain.py — DKTrenchBot Unified Decision Engine
==============================================
Single source of truth for ALL intelligence: sizing, slippage, routing,
pool safety, strategy weighting, and execution feedback.

Bot imports from here. Execution core is dumb — brain tells it what to do.

Architecture:
    bot.py → brain.py (decisions) → execution_core.py (execution only)
"""

from collections import defaultdict
import math
import logging

logger = logging.getLogger("brain")

# ═══════════════════════════════════════════════════════════════
# GLOBAL STATE — persisted across cycles via bot.py reload
# ═══════════════════════════════════════════════════════════════

# Per-strategy performance tracking
strategy_stats = defaultdict(lambda: {
    "wins": 0, "losses": 0, "pnl": 0.0, "trades": 0, "volatility": 0.0,
})

# Per-route slippage tracking
execution_stats = defaultdict(lambda: {
    "avg_slippage": 0.0, "route_score": 1.0, "samples": 0,
})

# Capital allocation weights per strategy
capital_allocation = defaultdict(lambda: 1.0)

# Per-pool behavior memory (rug signals + volatility)
pool_memory = defaultdict(lambda: {"volatility": 0.0, "rug_signals": 0})

# ═══════════════════════════════════════════════════════════════
# SAFETY CONSTANTS
# ═══════════════════════════════════════════════════════════════

MAX_SLIPPAGE      = 0.15   # hard cap — bot skips if predicted > 15%
MIN_CONFIDENCE    = 0.44   # minimum classifier confidence to proceed
MIN_POSITION_XRP  = 5.0   # absolute floor — no trades below this
MIN_LIQUIDITY_USD = 300    # micro-cap guard (USD)
POOL_RUG_THRESHOLD = 3     # 3 large losses = pool suspect
POOL_VOL_THRESHOLD = 0.5   # volatility > 0.5 = unsafe

# Strategy base risk (used in position_sizer)
STRATEGY_BASE_RISK = {
    # Reduced 40% from originals — protect capital until WR stabilizes
    # Avg position was 9.5 XRP on 200 XRP wallet = 4.75% per trade (correct target)
    "burst":        0.05,   # was 0.20 — BURST is high WR but micro-caps need small size
    "clob_launch":  0.05,   # was 0.20
    "pre_breakout": 0.04,   # was 0.15
    "trend":        0.04,   # was 0.12
    "micro_scalp":  0.03,   # was 0.06
    "none":         0.03,   # was 0.06
}

# ═══════════════════════════════════════════════════════════════
# FEEDBACK LOOP — called after every closed trade
# ═══════════════════════════════════════════════════════════════

def update_after_trade(trade: dict) -> None:
    """
    Called after every position close. Updates strategy weights,
    execution stats, and pool memory. All learning is cumulative.
    """
    strategy  = trade.get("strategy", "unknown")
    pnl       = trade.get("pnl_xrp", 0.0)
    win       = pnl > 0

    stats = strategy_stats[strategy]
    stats["trades"]  += 1
    stats["pnl"]     += pnl
    if win:
        stats["wins"]   += 1
    else:
        stats["losses"] += 1
    stats["volatility"] = _vol(stats["volatility"], pnl)

    # Execution quality tracking
    _update_execution_stats(trade)

    # Recompute strategy weight
    _recompute_strategy_weight(strategy)

    # Pool behavior tracking
    token = trade.get("token", {})
    if token:
        _update_pool_behavior(token, pnl)

    logger.debug(
        f"[brain] trade: {strategy} | pnl={pnl:+.4f} XRP | "
        f"wr={stats['wins']/max(1,stats['trades']):.1%} | "
        f"capital_weight={capital_allocation[strategy]:.2f}"
    )


# ═══════════════════════════════════════════════════════════════
# ADAPTIVE CAPITAL ALLOCATION
# ═══════════════════════════════════════════════════════════════

def _recompute_strategy_weight(strategy: str) -> None:
    stats = strategy_stats[strategy]
    if stats["trades"] < 5:
        capital_allocation[strategy] = 1.0
        return
    winrate = stats["wins"] / max(1, stats["trades"])
    score = (winrate * 0.5) + (_norm_pnl(stats["pnl"]) * 0.4) - (stats["volatility"] * 0.2)
    capital_allocation[strategy] = _clamp(score, 0.3, 1.5)


def adjust_size_for_strategy(size: float, strategy: str) -> float:
    """
    Scale position size by capital allocation weight for this strategy.
    Weights < 1.0 = underperforming strategy, reduce size.
    Weights > 1.0 = outperformers, increase size.
    Minimum weight: 0.3x | Maximum: 1.5x.
    """
    weight = capital_allocation.get(strategy, 1.0)
    return size * weight


# ═══════════════════════════════════════════════════════════════
# SLIPPAGE PREDICTION
# ═══════════════════════════════════════════════════════════════

def predict_slippage(token: dict, size: float) -> float:
    """
    Predict realized slippage based on pool depth, position size,
    and our rolling global average slippage.
    """
    liquidity = token.get("liquidity_usd", 0) or token.get("tvl_xrp", 0)
    if not liquidity:
        return 0.05
    base = size / liquidity
    global_avg = _global_avg_slippage()
    return _clamp(base * (1 + global_avg), 0.0, 0.5)


def _global_avg_slippage() -> float:
    vals = [v["avg_slippage"] for v in execution_stats.values() if v["samples"] > 0]
    return sum(vals) / len(vals) if vals else 0.05


# ═══════════════════════════════════════════════════════════════
# EXECUTION INTELLIGENCE
# ═══════════════════════════════════════════════════════════════

def update_execution_stats(trade: dict) -> None:
    route    = trade.get("route", "default")
    expected = trade.get("entry_price", 1.0)
    actual   = trade.get("exit_price", expected)
    if not expected:
        return
    slippage = abs(actual - expected) / expected
    stats    = execution_stats[route]
    n        = stats["samples"] + 1
    stats["samples"]      = n
    stats["avg_slippage"] = (stats["avg_slippage"] * (n - 1) + slippage) / n
    stats["route_score"]   = 1.0 / (1.0 + stats["avg_slippage"])


def select_best_route(routes: list) -> str:
    """
    Given a list of route names, return the best one based on
    rolling slippage performance.
    """
    if not routes:
        return "default"
    best_score = -1
    best_route = routes[0]
    for route in routes:
        score = execution_stats[route].get("route_score", 0)
        if score > best_score:
            best_score = score
            best_route = route
    return best_route


# ═══════════════════════════════════════════════════════════════
# POOL SAFETY
# ═══════════════════════════════════════════════════════════════

def update_pool_behavior(token: dict, trade: dict) -> None:
    """Track pool volatility and rug events for safety gating."""
    pool_id = token.get("pool_id") or token.get("key", "unknown")
    mem     = pool_memory[pool_id]
    pnl     = trade.get("pnl_xrp", 0)
    mem["volatility"] = _vol(mem["volatility"], pnl)
    if pnl < -0.3:
        mem["rug_signals"] += 1


def is_pool_safe(token: dict) -> bool:
    """
    Pool is UNSAFE and should be skipped if:
    - 3+ rug events (large losses), OR
    - Volatility exceeds 0.5 (50% drawdown per trade on avg)
    """
    pool_id = token.get("pool_id") or token.get("key", "unknown")
    mem     = pool_memory[pool_id]
    if mem["rug_signals"] >= POOL_RUG_THRESHOLD:
        logger.info(f"[brain] POOL_UNSAFE {pool_id}: rug_signals={mem['rug_signals']}")
        return False
    if mem["volatility"] > POOL_VOL_THRESHOLD:
        logger.info(f"[brain] POOL_UNSAFE {pool_id}: volatility={mem['volatility']:.3f}")
        return False
    return True


# ═══════════════════════════════════════════════════════════════
# PRE-TRADE VALIDATION GATES
# ═══════════════════════════════════════════════════════════════

def pre_trade_validator(token: dict, size: float, confidence: float, route_quality: str = "GOOD") -> tuple[bool, str]:
    """
    Non-bypassable safety gates. Returns (pass, reason).
    reason = "" if passed, else human-readable skip reason.
    """
    symbol = token.get("symbol", "?")

    # Gate 1: Confidence
    if confidence < MIN_CONFIDENCE:
        return False, f"confidence {confidence:.2f} < {MIN_CONFIDENCE}"

    # Gate 2: Predicted slippage (uses brain's learned slippage model)
    predicted = predict_slippage(token, size)
    if predicted > MAX_SLIPPAGE:
        return False, f"slippage {predicted:.1%} > {MAX_SLIPPAGE:.1%}"

    # Gate 3: Liquidity floor
    liquidity = token.get("liquidity_usd", 0)
    if liquidity < MIN_LIQUIDITY_USD:
        return False, f"liquidity ${liquidity} < ${MIN_LIQUIDITY_USD}"

    # Gate 4: Pool safety
    if not is_pool_safe(token):
        return False, "pool unsafe — volatility/rug signal"

    # Gate 5: Route quality
    if route_quality != "GOOD":
        return False, f"route={route_quality}"

    return True, ""


# ═══════════════════════════════════════════════════════════════
# POSITION SIZER
# ═══════════════════════════════════════════════════════════════

def position_sizer(
    token: dict,
    classification: dict,
    wallet_state: dict,
    strategy_name: str = "none",
) -> float:
    """
    Centralized position sizing:
    - Strategy base risk
    - Confidence multiplier (0.5x–1.5x)
    - Liquidity cap (never exceed safe pool depth)
    - Drawdown protection (halve if wallet down >20%)
    - Adaptive weight from capital_allocation
    """
    strat_name  = strategy_name or classification.get("primary", "none")
    base_risk   = STRATEGY_BASE_RISK.get(strat_name, 0.12)
    balance     = wallet_state.get("balance", 0)
    base_size   = balance * base_risk

    # Confidence multiplier: 0.5 + confidence → 0.94–1.5x for 0.44–1.0 confidence
    conf = classification.get("confidence", 0.5)
    base_size *= (0.5 + conf)

    # Liquidity cap (safe entry size based on pool depth)
    max_safe = _get_safe_entry_size(token)
    size     = min(base_size, max_safe)

    # Drawdown protection
    drawdown = wallet_state.get("drawdown", 0)
    if drawdown > 0.20:
        size *= 0.5

    # Apply capital allocation weight
    size *= capital_allocation.get(strat_name, 1.0)

    # Floor
    if size < MIN_POSITION_XRP:
        return 0.0

    return round(size, 2)


def _get_safe_entry_size(token: dict) -> float:
    """
    Maximum safe position size (XRP) based on pool depth.

    Uses tvl_xrp (always populated from AMM/CLOB) as the source of truth.
    liquidity_usd is often 0 (only set from discovery.py external API path),
    so we never rely on it here — that was causing 1 XRP sizing on large-MC tokens.

    Slippage caps by TVL (XRP):
      TVL < 200 XRP  → 3.5% of TVL (tiny pool, toe in)
      TVL < 1k XRP   → 4.0% of TVL
      TVL < 5k XRP   → 5.0% of TVL
      TVL ≥ 5k XRP   → 6.0% of TVL (deep pool, can size up)

    These percentages are aggressive enough to matter but won't move the
    price more than ~1-2% on entry.
    """
    tvl_xrp = float(token.get("tvl_xrp", 0) or 0)

    # Fallback: if tvl_xrp missing, try to derive from liquidity_usd via XRP price
    if tvl_xrp <= 0:
        liquidity_usd = float(token.get("liquidity_usd", 0) or 0)
        if liquidity_usd > 0:
            try:
                import json as _j
                import os as _os
                _briefing = _os.path.join(_os.path.dirname(__file__), "state", "market", "briefing.json")
                with open(_briefing) as _f:
                    _d = _j.load(_f)
                _xrp_price = float(_d.get("prices", {}).get("xrp", {}).get("usd", 2.0) or 2.0)
            except Exception:
                _xrp_price = 2.0  # conservative fallback
            tvl_xrp = liquidity_usd / _xrp_price

    if tvl_xrp <= 0:
        return MIN_POSITION_XRP

    if tvl_xrp < 200:
        pct = 0.035
    elif tvl_xrp < 1000:
        pct = 0.040
    elif tvl_xrp < 5000:
        pct = 0.050
    else:
        pct = 0.060

    safe = tvl_xrp * pct
    logger.debug(f"_get_safe_entry_size: tvl={tvl_xrp:.0f} XRP pct={pct:.1%} → safe={safe:.1f} XRP")
    return max(safe, MIN_POSITION_XRP)


# ═══════════════════════════════════════════════════════════════
# INTELLIGENCE ACCESS — bot.py queries these
# ═══════════════════════════════════════════════════════════════

def get_strategy_weight(strategy: str) -> float:
    """Current capital allocation weight for a strategy."""
    return capital_allocation.get(strategy, 1.0)


def get_strategy_stats(strategy: str) -> dict:
    """Full stats for a strategy (for dashboards/reporting)."""
    return dict(strategy_stats.get(strategy, {}))


def get_pool_stats(pool_id: str) -> dict:
    """Pool memory (rug_signals, volatility)."""
    return dict(pool_memory.get(pool_id, {}))


def get_route_stats(route: str) -> dict:
    """Route execution quality (avg_slippage, route_score, samples)."""
    return dict(execution_stats.get(route, {}))


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _vol(current: float, new_pnl: float) -> float:
    """Exponentially weighted volatility tracking."""
    return current * 0.9 + abs(new_pnl) * 0.1

def _norm_pnl(pnl: float) -> float:
    """Bounded PnL normalization: maps to ~[-1, 1]"""
    return math.tanh(pnl / 10.0)

def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(value, hi))
