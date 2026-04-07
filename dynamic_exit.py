"""
dynamic_exit.py — Dynamic exit logic for open positions.

Philosophy: Let winners run. Cut losers fast. Protect profits.

Key rules:
  - Break-even protection: once up 5%, trail stop floor = entry (never lose on a winner)
  - Tiered trailing: tighter trail as profit grows (lock in more as it moons)
  - Dynamic exits only trigger at meaningful losses (-5%+), not tiny dips
  - Stale exit is generous (6hr) — meme tokens need time
"""

import time
from typing import Dict, List, Optional
from config import (HARD_STOP_PCT, HARD_STOP_EARLY_PCT, HARD_STOP_GRACE_SEC,
                    TRAIL_STOP_PCT, TP1_PCT, TP1_SELL_FRAC,
                    TP2_PCT, TP2_SELL_FRAC, TP3_PCT, TP3_SELL_FRAC,
                    TP4_PCT, STALE_EXIT_HOURS, MAX_HOLD_HOURS,
                    SCALP_TP_PCT, SCALP_STOP_PCT, SCALP_MAX_HOLD_MIN)


def check_exit(position: Dict, current_price: float,
               current_tvl: float = 0.0,
               breakout_quality: int = 50,
               price_history: List[float] = None) -> Dict:
    """
    Check all exit conditions for a position.
    Returns: { exit, partial, reason, fraction }
    """
    if price_history is None:
        price_history = []

    entry_price  = position["entry_price"]
    entry_time   = position["entry_time"]
    peak_price   = position.get("peak_price", entry_price)
    entry_tvl    = position.get("entry_tvl", current_tvl)
    tp1_hit      = position.get("tp1_hit", False)
    tp2_hit      = position.get("tp2_hit", False)
    tp3_hit      = position.get("tp3_hit", False)
    is_orphan    = position.get("orphan", False)
    now          = time.time()
    hold_secs    = now - entry_time
    hold_hours   = hold_secs / 3600

    if entry_price <= 0:
        return _exit_signal("invalid_entry_price", 1.0)

    # FIX: Use XRP-value based P&L not price-based.
    # After partial TP sells, tokens_held is reduced. Real P&L =
    # (tokens_held * current_price) vs xrp_spent (remaining cost basis).
    # Price-based pnl_pct was showing +300% on trades that actually lost XRP.
    tokens_held = float(position.get("tokens_held", 0) or 0)
    xrp_spent   = float(position.get("xrp_spent", 0) or 0)

    if tokens_held > 0 and xrp_spent > 0:
        current_value = tokens_held * current_price
        pnl_pct       = (current_value - xrp_spent) / xrp_spent
    else:
        # Fallback to price-based if no token count
        pnl_pct = (current_price - entry_price) / entry_price

    # Peak pnl still price-based (for trailing stop calculation)
    peak_pnl_pct = (peak_price - entry_price) / entry_price

    # ── Scalp Mode: tight TP/stop/time exits ─────────────────────────────────
    if position.get("scalp_mode"):
        hold_min = hold_secs / 60
        if pnl_pct >= SCALP_TP_PCT:
            return _exit_signal("scalp_tp", 1.0)
        if pnl_pct <= -SCALP_STOP_PCT:
            return _exit_signal("scalp_stop", 1.0)
        if hold_min >= SCALP_MAX_HOLD_MIN:
            return _exit_signal(f"scalp_timeout_{hold_min:.0f}m", 1.0)
        return {"exit": False, "partial": False, "reason": "hold_scalp", "fraction": 0.0}

    # ── Orphan Fast Exit ─────────────────────────────────────────────────
    # DATA: orphan = 0% WR, -18.5 XRP total — worst performing category
    # Any orphan with fast_exit=True: sell at first profit, or cut at 1h
    if position.get("fast_exit") and is_orphan:
        if pnl_pct >= 0.005:  # any tiny profit → take it immediately
            return _exit_signal("orphan_profit_take", 1.0)
        if hold_hours >= 1.0:  # held 1h with no profit → cut it
            return _exit_signal("orphan_timeout_1hr", 1.0)

    # ── Hard Stop ────────────────────────────────────────────────────────
    # Unified stop — no tight early filter (meme tokens get stop hunted in first 30min)
    # Require 2 consecutive readings below stop before exiting (avoids single bad tick)
    consecutive_below_stop = position.get("consecutive_below_stop", 0)
    if pnl_pct <= -HARD_STOP_PCT:
        position["consecutive_below_stop"] = consecutive_below_stop + 1
        if consecutive_below_stop >= 1:  # 2nd consecutive reading = real stop
            position["consecutive_below_stop"] = 0
            return _exit_signal("hard_stop", 1.0)
        # First reading below stop — warn but hold one more cycle
    else:
        position["consecutive_below_stop"] = 0  # reset on any recovery

    # ── Break-even Protection ─────────────────────────────────────────────
    # DATA: breakeven_protection = 28.6% WR, -0.82 avg — triggering too early.
    # Raised from 5% to 8% so trades get more room before floor locks in.
    # We NEVER turn an 8%+ winner into a loser.
    if peak_pnl_pct >= 0.08:
        # Floor: never exit below entry
        if pnl_pct < 0.0:
            return _exit_signal("breakeven_protection", 1.0)

    # ── Tiered Trailing Stop ──────────────────────────────────────────────
    # Tighter trails as profit grows — lock in more of the gain as it moons.
    # Only applies once peak is above entry.
    if peak_price > entry_price:
        trail_drawdown = (peak_price - current_price) / peak_price
        # Peak >100%: trail at 15% (2x — lock in moonshot gains)
        if peak_pnl_pct >= 1.00 and trail_drawdown >= 0.15:
            return _exit_signal(f"trail_tight_{trail_drawdown:.1%}", 1.0)
        # Peak >50%: trail at 20%
        elif peak_pnl_pct >= 0.50 and trail_drawdown >= 0.20:
            return _exit_signal(f"trail_mid_{trail_drawdown:.1%}", 1.0)
        # Peak >25%: trail at 22%
        elif peak_pnl_pct >= 0.25 and trail_drawdown >= 0.22:
            return _exit_signal(f"trail_wide_{trail_drawdown:.1%}", 1.0)
        # Default: trail at 25% (TRAIL_STOP_PCT config)
        elif trail_drawdown >= TRAIL_STOP_PCT:
            return _exit_signal(f"trailing_stop_{trail_drawdown:.1%}", 1.0)

    # ── Take Profit Levels ────────────────────────────────────────────────
    # 4-tier TP system — designed to let real runners go to 600%+
    # After each TP, trailing stop protects remaining position
    # Must be genuinely profitable (pnl_pct > 0) to prevent stale price false exits

    # TP4: +600% → full exit — M1N/moonshot tier
    if pnl_pct >= TP4_PCT and pnl_pct > 0:
        return _exit_signal("tp4_moon", 1.0)

    # TP3: +300% → sell 30% of remainder (~34% of original still running free)
    if not tp3_hit and tp2_hit and pnl_pct >= TP3_PCT and pnl_pct > 0:
        return _partial_signal("tp3_runner", TP3_SELL_FRAC)

    # TP2: +50% → sell 30% of remainder (~49% of original still running)
    if not tp2_hit and tp1_hit and pnl_pct >= TP2_PCT:
        return _partial_signal("tp2_remainder", TP2_SELL_FRAC)

    # TP1: +20% → sell 30% (keep 70% running)
    if not tp1_hit and pnl_pct >= TP1_PCT:
        return _partial_signal("tp1_partial", TP1_SELL_FRAC)

    # ── Dynamic Stale Exit ────────────────────────────────────────────────
    # DATA: BXE -6.65 XRP, 589 -2.74 XRP, AMEN -1.71 XRP all bled on 3hr stale
    #       gei +5.73 XRP, TABS +5.25 XRP both won via longer hold
    # Fix: timer scales with position health — cut losers fast, let winners run
    xrp_spent    = float(position.get("xrp_spent", 0) or 0)
    pnl_xrp_est  = xrp_spent * pnl_pct  # rough XRP P&L estimate

    if pnl_xrp_est < -1.0:
        dynamic_stale = 2.0            # bleeding — cut at 2h
    elif pnl_xrp_est < -0.3:
        dynamic_stale = STALE_EXIT_HOURS  # small loss — normal 3h
    elif pnl_xrp_est > 2.0:
        dynamic_stale = MAX_HOLD_HOURS # strong winner — max hold
    elif pnl_xrp_est > 0.3:
        dynamic_stale = 8.0            # positive — let it breathe
    else:
        dynamic_stale = STALE_EXIT_HOURS  # flat — normal timer

    if hold_hours >= dynamic_stale and pnl_pct < 0.02:
        return _exit_signal(f"stale_{hold_hours:.1f}hr", 1.0)

    # Max hold: absolute time limit
    if hold_hours >= MAX_HOLD_HOURS:
        return _exit_signal(f"max_hold_{hold_hours:.1f}hr", 1.0)

    # ── Dynamic Exit Signals ──────────────────────────────────────────────
    # Only apply after position has had time to develop (30min+)
    # And only trigger on meaningful losses (-5%+), not tiny dips
    # Skip entirely for orphans in first 2hr (no real price history)
    can_dynamic = not (is_orphan and hold_hours < 2.0) and hold_hours >= 0.5

    if can_dynamic:
        # Profit giveback: peaked well, now giving it all back
        # Only exit if we had significant peak AND are now deeply in red
        if peak_pnl_pct >= 0.20 and pnl_pct < -0.05:
            return _exit_signal("profit_giveback", 1.0)

        # Liquidity deterioration: TVL dropped >30% (much more tolerant — meme pools swing)
        if entry_tvl > 0 and current_tvl > 0:
            tvl_drop = (entry_tvl - current_tvl) / entry_tvl
            if tvl_drop > 0.30 and pnl_pct < -0.05:
                return _exit_signal(f"liquidity_drop_{tvl_drop:.1%}", 1.0)

        # Rapid price dump: dropped >8% in last 5 readings AND losing
        if len(price_history) >= 5 and pnl_pct < -0.05:
            recent_drop = (price_history[-5] - current_price) / price_history[-5]
            if recent_drop > 0.08:
                return _exit_signal("rapid_dump", 1.0)

        # Momentum stall: completely flat + losing + held >1hr
        # Requires 5 readings flat (tighter window = fewer false triggers)
        if len(price_history) >= 5 and hold_hours > 1.0 and pnl_pct < -0.05:
            recent = price_history[-5:]
            high, low = max(recent), min(recent)
            if high > 0 and (high - low) / high < 0.003:
                return _exit_signal("momentum_stall", 1.0)

    return {"exit": False, "partial": False, "reason": "hold", "fraction": 0.0}


def _exit_signal(reason: str, fraction: float) -> Dict:
    return {"exit": True, "partial": False, "reason": reason, "fraction": fraction}


def _partial_signal(reason: str, fraction: float) -> Dict:
    return {"exit": True, "partial": True, "reason": reason, "fraction": fraction}


def _has_lower_highs(prices: List[float]) -> bool:
    highs = []
    for i in range(1, len(prices) - 1):
        if prices[i] >= prices[i - 1] and prices[i] >= prices[i + 1]:
            highs.append(prices[i])
    if len(highs) < 2:
        return False
    return highs[-1] < highs[-2]


def update_peak(position: Dict, current_price: float) -> Dict:
    if current_price > position.get("peak_price", 0):
        position["peak_price"] = current_price
    return position
