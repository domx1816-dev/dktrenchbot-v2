"""
regime.py — Market regime detection.
Regimes: hot, neutral, cold, danger
Writes: state/regime.json
"""

import json
import os
import time
from typing import Dict, List
import state as state_mod
from config import STATE_DIR

os.makedirs(STATE_DIR, exist_ok=True)
REGIME_FILE = os.path.join(STATE_DIR, "regime.json")


def detect_regime(bot_state: Dict, candidates_above_70: int = 0) -> str:
    """
    Determine market regime from performance metrics and scan results.
    Returns: 'hot' | 'neutral' | 'cold' | 'danger'
    """
    perf = bot_state.get("performance", {})
    cons_loss  = perf.get("consecutive_losses", 0)
    total      = perf.get("total_trades", 0)

    # Use RECENT win rate (last 15 trades) not all-time — avoids old losses poisoning regime
    history = bot_state.get("trade_history", [])
    recent  = history[-15:] if len(history) >= 15 else history
    if len(recent) >= 5:
        recent_wins = sum(1 for t in recent if "tp" in t.get("exit_reason",""))
        win_rate = recent_wins / len(recent)
    else:
        win_rate = perf.get("win_rate", 0.5)

    # Need at least 15 trades for regime to be meaningful — less than that is noise
    if total < 15:
        return "neutral"

    # Danger: 10+ consecutive losses
    if cons_loss >= 10:
        return "danger"

    # Cold: low recent win rate
    if win_rate < 0.35:
        return "cold"

    # Hot: high win rate + at least one strong candidate
    if win_rate > 0.60 and candidates_above_70 >= 1:
        return "hot"

    return "neutral"


def get_regime_adjustments(regime: str) -> Dict:
    """Return behavior adjustments for the current regime."""
    return {
        "hot": {
            "size_mult":       1.0,
            "score_threshold": 0,   # no bonus threshold
            "max_positions":   5,
            "allow_entry":     True,
        },
        "neutral": {
            "size_mult":       1.0,
            "score_threshold": 0,
            "max_positions":   5,
            "allow_entry":     True,
        },
        "cold": {
            "size_mult":       0.75,  # was 0.5 — don't be too timid, miss winners
            "score_threshold": 5,     # was +10 — looser so we don't miss entries
            "max_positions":   4,     # was 3
            "allow_entry":     True,
        },
        "danger": {
            "size_mult":       0.5,   # half size — stay in the game, don't ghost
            "score_threshold": 8,     # +8 threshold (was +20 — was killing all entries)
            "max_positions":   3,     # 3 max in danger
            "allow_entry":     True,
        },
    }.get(regime, {
        "size_mult":       1.0,
        "score_threshold": 0,
        "max_positions":   5,
        "allow_entry":     True,
    })


def load_regime() -> Dict:
    if os.path.exists(REGIME_FILE):
        try:
            with open(REGIME_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"regime": "neutral", "ts": 0, "details": {}}


def save_regime(regime: str, details: Dict = None) -> None:
    data = {
        "regime":      regime,
        "ts":          time.time(),
        "details":     details or {},
        "adjustments": get_regime_adjustments(regime),
    }
    with open(REGIME_FILE, "w") as f:
        json.dump(data, f, indent=2)


def update_and_get_regime(bot_state: Dict, candidates_above_70: int = 0) -> str:
    regime = detect_regime(bot_state, candidates_above_70)
    perf   = bot_state.get("performance", {})
    details = {
        "win_rate":           perf.get("win_rate", 0),
        "consecutive_losses": perf.get("consecutive_losses", 0),
        "total_trades":       perf.get("total_trades", 0),
        "candidates_above_70": candidates_above_70,
    }
    save_regime(regime, details)
    return regime


if __name__ == "__main__":
    s = state_mod.load()
    regime = update_and_get_regime(s, candidates_above_70=3)
    print(f"Regime: {regime}")
    print(json.dumps(get_regime_adjustments(regime), indent=2))
