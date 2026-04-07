"""
improve.py — Every 6 hours: analyze last 20+ trades, adjust parameters.
Only adjusts if >= 10 trades in a category.
Writes: state/improvements.json
"""

import json
import os
import time
from typing import Dict, List, Optional
from config import (STATE_DIR, SCORE_ELITE, SCORE_TRADEABLE, SCORE_SMALL,
                    STALE_EXIT_HOURS, MAX_POSITIONS)
import state as state_mod

os.makedirs(STATE_DIR, exist_ok=True)
IMPROVEMENTS_FILE = os.path.join(STATE_DIR, "improvements.json")


def _load_improvements() -> Dict:
    if os.path.exists(IMPROVEMENTS_FILE):
        try:
            with open(IMPROVEMENTS_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "score_threshold_adj": 0,      # added to SCORE_TRADEABLE
        "size_multiplier":     1.0,
        "stale_exit_hours":    STALE_EXIT_HOURS,
        "max_positions":       MAX_POSITIONS,
        "ts":                  0,
        "history":             [],
    }


def _save_improvements(imp: Dict) -> None:
    imp["ts"] = time.time()
    with open(IMPROVEMENTS_FILE, "w") as f:
        json.dump(imp, f, indent=2)


def _analyze_by_category(trades: List[Dict], key: str) -> Dict:
    """Group trades by a category key, compute win rate per group."""
    groups: Dict[str, List] = {}
    for t in trades:
        val = t.get(key, "unknown")
        groups.setdefault(str(val), []).append(t)
    result = {}
    for cat, cat_trades in groups.items():
        wins = sum(1 for t in cat_trades if t.get("pnl_pct", 0) > 0)
        total = len(cat_trades)
        result[cat] = {
            "count":    total,
            "wins":     wins,
            "win_rate": wins / total if total > 0 else 0.0,
            "avg_pnl":  sum(t.get("pnl_pct", 0) for t in cat_trades) / total if total > 0 else 0.0,
        }
    return result


def run_improve(bot_state: Dict, force: bool = False) -> Dict:
    """
    Analyze recent performance and adjust parameters.
    Only runs every 6 hours unless force=True.
    """
    last = bot_state.get("last_improve", 0)
    if not force and (time.time() - last) < 6 * 3600:
        return {"skipped": True, "reason": "ran_recently"}

    trades = state_mod.get_recent_trades(bot_state, n=50)
    imp    = _load_improvements()

    if len(trades) < 20:
        bot_state["last_improve"] = time.time()
        state_mod.save(bot_state)
        return {"skipped": True, "reason": f"insufficient_trades:{len(trades)}"}

    changes = []

    # 1. Analyze by chart state
    by_chart = _analyze_by_category(trades, "chart_state")
    for state_name, metrics in by_chart.items():
        if metrics["count"] >= 10:
            if metrics["win_rate"] < 0.30 and state_name in ("expansion", "continuation"):
                # This state performing poorly — note it
                changes.append(f"chart_state:{state_name} win_rate={metrics['win_rate']:.0%} (poor)")

    # 2. Analyze by score band
    by_band = _analyze_by_category(trades, "score_band")
    for band, metrics in by_band.items():
        if metrics["count"] >= 10:
            if band == "small_size" and metrics["win_rate"] < 0.35:
                # Small size trades losing — raise threshold
                new_adj = min(25, imp["score_threshold_adj"] + 5)
                if new_adj != imp["score_threshold_adj"]:
                    imp["score_threshold_adj"] = new_adj
                    changes.append(f"score_threshold +5 → {SCORE_TRADEABLE + new_adj}")
            elif band == "tradeable" and metrics["win_rate"] > 0.65:
                # Good performance — allow slightly more
                new_adj = max(0, imp["score_threshold_adj"] - 5)
                if new_adj != imp["score_threshold_adj"]:
                    imp["score_threshold_adj"] = new_adj
                    changes.append(f"score_threshold -5 → {SCORE_TRADEABLE + new_adj}")

    # 3. Analyze by liquidity band
    def liq_band(tvl: float) -> str:
        if tvl >= 50000:  return "high"
        elif tvl >= 10000: return "mid"
        else:              return "low"

    for t in trades:
        t["_liq_band"] = liq_band(t.get("entry_tvl", 0))

    by_liq = _analyze_by_category(trades, "_liq_band")
    for band, metrics in by_liq.items():
        if metrics["count"] >= 10:
            if band == "low" and metrics["win_rate"] < 0.35:
                changes.append("low_liquidity_trades performing poorly — consider raising MIN_TVL")

    # 4. Overall size multiplier
    overall_wr = bot_state["performance"].get("win_rate", 0.5)
    if overall_wr > 0.65:
        new_mult = min(1.5, imp["size_multiplier"] + 0.1)
        if new_mult != imp["size_multiplier"]:
            imp["size_multiplier"] = new_mult
            changes.append(f"size_multiplier +0.1 → {new_mult:.1f}")
    elif overall_wr < 0.35:
        new_mult = max(0.5, imp["size_multiplier"] - 0.1)
        if new_mult != imp["size_multiplier"]:
            imp["size_multiplier"] = new_mult
            changes.append(f"size_multiplier -0.1 → {new_mult:.1f}")

    # 5. Stale exit timing
    stale_exits = [t for t in trades if t.get("exit_reason", "").startswith("stale")]
    if len(stale_exits) >= 10:
        stale_pnl = sum(t.get("pnl_pct", 0) for t in stale_exits) / len(stale_exits)
        if stale_pnl < -0.02:
            # Stale exits losing — reduce stale time
            new_stale = max(1.0, imp["stale_exit_hours"] - 0.5)
            if new_stale != imp["stale_exit_hours"]:
                imp["stale_exit_hours"] = new_stale
                changes.append(f"stale_exit_hours → {new_stale}")

    # Record adjustment history
    imp.setdefault("history", []).append({
        "ts":      time.time(),
        "changes": changes,
        "trades_analyzed": len(trades),
        "win_rate": overall_wr,
    })
    imp["history"] = imp["history"][-20:]  # keep last 20

    _save_improvements(imp)
    bot_state["last_improve"]   = time.time()
    bot_state["score_overrides"] = {
        "score_threshold_adj": imp["score_threshold_adj"],
        "size_multiplier":     imp["size_multiplier"],
        "stale_exit_hours":    imp["stale_exit_hours"],
    }
    state_mod.save(bot_state)

    return {
        "changes":         changes,
        "improvements":    imp,
        "trades_analyzed": len(trades),
    }


def get_current_adjustments() -> Dict:
    imp = _load_improvements()
    return {
        "score_threshold_adj": imp.get("score_threshold_adj", 0),
        "size_multiplier":     imp.get("size_multiplier", 1.0),
        "stale_exit_hours":    imp.get("stale_exit_hours", STALE_EXIT_HOURS),
        "max_positions":       imp.get("max_positions", MAX_POSITIONS),
    }


if __name__ == "__main__":
    s = state_mod.load()
    result = run_improve(s, force=True)
    print(f"Changes: {result.get('changes', [])}")
    print(f"Trades analyzed: {result.get('trades_analyzed', 0)}")
