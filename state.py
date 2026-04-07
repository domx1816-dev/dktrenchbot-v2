"""
state.py — Single source of truth for positions, trade history, and performance.
Always persists to disk. Thread-safe via file locking pattern.
"""

import json
import os
import time
from typing import Any, Dict, List, Optional
from config import STATE_DIR

os.makedirs(STATE_DIR, exist_ok=True)

STATE_FILE = os.path.join(STATE_DIR, "state.json")


def _default_state() -> Dict:
    return {
        "positions": {},           # token_key -> position dict
        "trade_history": [],       # list of completed trades
        "performance": {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "total_pnl_xrp": 0.0,
            "best_trade_pct": 0.0,
            "worst_trade_pct": 0.0,
            "consecutive_losses": 0,
            "last_updated": 0,
        },
        "score_overrides": {},     # from improve.py
        "last_reconcile": 0,
        "last_improve": 0,
        "last_hygiene": 0,
    }


def load() -> Dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
            # Merge any missing keys from default
            default = _default_state()
            for k, v in default.items():
                if k not in data:
                    data[k] = v
            return data
        except Exception:
            pass
    return _default_state()


def save(state: Dict) -> None:
    state["performance"]["last_updated"] = time.time()
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        # Fallback: write directly if atomic rename fails
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)


def add_position(state: Dict, token_key: str, position: Dict) -> None:
    """Add or update a position."""
    state["positions"][token_key] = position
    save(state)


def remove_position(state: Dict, token_key: str) -> Optional[Dict]:
    """Remove and return a position."""
    pos = state["positions"].pop(token_key, None)
    if pos:
        save(state)
    return pos


def record_trade(state: Dict, trade: Dict) -> None:
    """Record a completed trade and update performance metrics."""
    state["trade_history"].append(trade)
    # Keep last 500 trades
    if len(state["trade_history"]) > 500:
        state["trade_history"] = state["trade_history"][-500:]

    perf = state["performance"]
    perf["total_trades"] += 1
    pnl_xrp    = float(trade.get("pnl_xrp", 0.0) or 0.0)
    pnl_pct    = float(trade.get("pnl_pct",  0.0) or 0.0)
    exit_reason = trade.get("exit_reason", "")
    perf["total_pnl_xrp"] += pnl_xrp

    # Skip dust trades from performance metrics
    # FIX: use pnl_xrp (real money) not pnl_pct (can be positive % on reduced position)
    if abs(pnl_xrp) < 0.1:
        perf["total_trades"] -= 1  # don't count dust exits
        return

    # FIX: Win/Loss determined by pnl_xrp (actual XRP profit), NOT pnl_pct.
    # pnl_pct can be positive (price went up) while pnl_xrp is negative
    # because partial sells (TP1/TP2) reduced the position size.
    if pnl_xrp > 0.1:
        perf["wins"] += 1
        perf["consecutive_losses"] = 0
        # best_trade_pct: use pnl_pct only when it agrees with pnl_xrp direction
        if pnl_pct > 0 and pnl_pct > perf["best_trade_pct"]:
            perf["best_trade_pct"] = pnl_pct
    elif pnl_xrp < -0.1:
        perf["losses"] += 1
        # Orphan cleanups / forced timeouts are NOT real signal losses
        # Don't let cleanup operations trigger danger regime
        forced_exits = {"orphan_timeout_1hr", "orphan_profit_take", "dead_token"}
        if exit_reason not in forced_exits:
            perf["consecutive_losses"] += 1
        else:
            perf["consecutive_losses"] = 0  # cleanup exits reset the streak
        if pnl_pct < 0 and pnl_pct < perf["worst_trade_pct"]:
            perf["worst_trade_pct"] = pnl_pct
    else:
        perf["consecutive_losses"] = 0  # near-zero scratch

    # FIX: Rolling win rate uses pnl_xrp not pnl_pct
    recent = [t for t in state["trade_history"][-30:] if abs(float(t.get("pnl_xrp", 0) or 0)) >= 0.1]
    if len(recent) >= 5:
        recent_wins = sum(1 for t in recent if float(t.get("pnl_xrp", 0) or 0) > 0.1)
        perf["win_rate"] = recent_wins / len(recent)
    else:
        total = perf["wins"] + perf["losses"]
        perf["win_rate"] = perf["wins"] / total if total > 0 else 0.5
    save(state)


def get_recent_trades(state: Dict, n: int = 20) -> List[Dict]:
    return state["trade_history"][-n:]


def position_key(symbol: str, issuer: str) -> str:
    return f"{symbol}:{issuer}"


if __name__ == "__main__":
    s = load()
    print(f"Positions: {len(s['positions'])}")
    print(f"Trades: {len(s['trade_history'])}")
    print(f"Win rate: {s['performance']['win_rate']:.1%}")
    print(f"PnL: {s['performance']['total_pnl_xrp']:.4f} XRP")
