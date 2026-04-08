"""
learn_engine.py — Adaptive Learning + Adaptation System
Wired into bot.py: after every trade, before sizing, pool safety, route selection.
"""

from collections import defaultdict
import math

# ── GLOBAL STATE ───────────────────────────────────────────────────────
strategy_stats = defaultdict(lambda: {
    "wins": 0,
    "losses": 0,
    "pnl": 0.0,
    "trades": 0,
    "volatility": 0.0,
})

execution_stats = defaultdict(lambda: {
    "avg_slippage": 0.0,
    "route_score": 1.0,
    "samples": 0,
})

capital_allocation = defaultdict(lambda: 1.0)

pool_memory = defaultdict(lambda: {"volatility": 0.0, "rug_signals": 0})

# ── AFTER TRADE: update strategy stats ──────────────────────────────────
def update_after_trade(trade):
    strategy = trade.get("strategy", "unknown")
    pnl = trade.get("pnl_xrp", 0.0)
    win = pnl > 0
    stats = strategy_stats[strategy]
    stats["trades"] += 1
    stats["pnl"] += pnl
    if win:
        stats["wins"] += 1
    else:
        stats["losses"] += 1
    stats["volatility"] = _vol(stats["volatility"], pnl)
    update_execution_stats(trade)
    recompute_strategy_weight(strategy)

# ── CAPITAL ALLOCATION WEIGHT ───────────────────────────────────
def recompute_strategy_weight(strategy):
    stats = strategy_stats[strategy]
    if stats["trades"] < 5:
        capital_allocation[strategy] = 1.0
        return
    winrate = stats["wins"] / max(1, stats["trades"])
    score = (winrate * 0.5) + (_norm_pnl(stats["pnl"]) * 0.4 - stats["volatility"] * 0.2)
    capital_allocation[strategy] = _clamp(score, 0.3, 1.5)

# ── ADAPTIVE SIZE ──────────────────────────────────────────────
def adjust_size_for_strategy(size, strategy):
    weight = capital_allocation.get(strategy, 1.0)
    return size * weight

# ── SLIPPAGE PREDICTION ──────────────────────────────────────
def predict_slippage(token, size):
    liquidity = token.get("liquidity_usd", 0) or token.get("tvl_xrp", 0)
    if not liquidity:
        return 0.05
    base = size / liquidity
    global_avg = _global_slippage()
    return _clamp(base * (1 + global_avg), 0.0, 0.5)

def _global_slippage():
    vals = [v["avg_slippage"] for v in execution_stats.values() if v["samples"] > 0]
    return sum(vals) / len(vals) if vals else 0.05

# ── EXECUTION INTELLIGENCE ─────────────────────────────────
def update_execution_stats(trade):
    route = trade.get("route", "default")
    expected = trade.get("entry_price", 1.0)
    actual = trade.get("exit_price", expected)
    if not expected:
        return
    slippage = abs(actual - expected) / expected
    stats = execution_stats[route]
    n = stats["samples"] + 1
    stats["samples"] = n
    stats["avg_slippage"] = (stats["avg_slippage"] * (n - 1) + slippage) / n
    stats["route_score"] = 1.0 / (1.0 + stats["avg_slippage"])

def select_best_route(routes):
    best = routes[0] if routes else None
    best_score = -1
    for route in routes:
        score = execution_stats[route]["route_score"]
        if score > best_score:
            best_score = score
            best = route
    return best

# ── POOL SAFETY ───────────────────────────────────────────────
POOL_RUG_THRESHOLD = 3
POOL_VOL_THRESHOLD = 0.5

def update_pool_behavior(token, trade):
    pool_id = token.get("pool_id") or token.get("key", "unknown")
    mem = pool_memory[pool_id]
    pnl = trade.get("pnl_xrp", 0)
    mem["volatility"] = _vol(mem["volatility"], pnl)
    if pnl < -0.3:
        mem["rug_signals"] += 1

def is_pool_safe(token):
    pool_id = token.get("pool_id") or token.get("key", "unknown")
    mem = pool_memory[pool_id]
    if mem["rug_signals"] >= POOL_RUG_THRESHOLD:
        return False
    if mem["volatility"] > POOL_VOL_THRESHOLD:
        return False
    return True

# ── HELPERS ─────────────────────────────────────────────────
def _vol(current, new_pnl):
    return current * 0.9 + abs(new_pnl) * 0.1

def _norm_pnl(pnl):
    return math.tanh(pnl / 10.0)

def _clamp(value, lo, hi):
    return max(lo, min(value, hi))
