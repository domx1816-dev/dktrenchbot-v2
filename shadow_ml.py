"""
shadow_ml.py — Simple phantom paper-trading system.
Runs independently of production scoring. Evaluates ALL raw candidates.
Saves state to state/shadow_state.json every cycle.
"""

import json
import os
import time
from datetime import datetime

STATE_DIR = os.path.join(os.path.dirname(__file__), "state")
SHADOW_STATE_FILE = os.path.join(STATE_DIR, "shadow_state.json")


class ShadowML:
    def __init__(self):
        self.state = self._load_state()

    # -------------------------
    # STATE MANAGEMENT
    # -------------------------
    def _load_state(self):
        if os.path.exists(SHADOW_STATE_FILE):
            try:
                with open(SHADOW_STATE_FILE, "r") as f:
                    data = json.load(f)
                # Ensure 'trades' key exists (migrate from old format if needed)
                if "trades" not in data:
                    data["trades"] = data.get("trade_history", [])
                return data
            except Exception:
                pass
        return {
            "trades": [],
            "last_updated": None,
        }

    def _save_state(self):
        self.state["last_updated"] = datetime.utcnow().isoformat()
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = SHADOW_STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.state, f, indent=2)
        os.replace(tmp, SHADOW_STATE_FILE)

    # -------------------------
    # SIMPLE SCORING (independent of production)
    # -------------------------
    def score_candidate(self, candidate):
        score = 0

        # Volume / TVL signal — most important
        vol = candidate.get("tvl_xrp", 0) or candidate.get("volume", 0)
        if vol > 10000:
            score += 25
        elif vol > 2000:
            score += 15
        elif vol > 500:
            score += 8

        # Price change / momentum
        pct = abs(candidate.get("pct_change", 0) or candidate.get("price_change", 0))
        if pct > 10:
            score += 25
        elif pct > 3:
            score += 15
        elif pct > 0.5:
            score += 5

        # Burst / activity count
        burst = candidate.get("burst_count", 0) or candidate.get("tx_count", 0)
        if burst > 20:
            score += 20
        elif burst > 5:
            score += 10

        # Chart state bonus
        chart = candidate.get("chart_state", "")
        if chart in ("pre_breakout", "accumulation"):
            score += 10

        # Always give a small base score so something enters
        score += 5

        return score

    # -------------------------
    # PHANTOM TRADE EXECUTION
    # -------------------------
    def simulate_trade(self, candidate, score):
        token = candidate.get("symbol", candidate.get("token", "UNKNOWN"))
        price = candidate.get("price", 0)

        # Don't enter if already open
        for t in self.state["trades"]:
            if t.get("token") == token and t.get("status") == "OPEN":
                return

        trade = {
            "token": token,
            "entry_time": time.time(),
            "entry_price": price,
            "score": score,
            "size": self._position_size(score),
            "status": "OPEN",
        }

        self.state["trades"].append(trade)

    def _position_size(self, score):
        base = 1.0
        return round(base * (score / 100), 4)

    # -------------------------
    # UPDATE OPEN TRADES
    # -------------------------
    def update_trades(self, market_data):
        for trade in self.state["trades"]:
            if trade["status"] != "OPEN":
                continue

            token = trade["token"]
            current_price = market_data.get(token, {}).get("price")

            if not current_price or current_price <= 0:
                continue

            entry = trade["entry_price"]
            if not entry or entry <= 0:
                continue

            pnl = (current_price - entry) / entry

            # Simple exit rules: +20% TP or -10% stop
            if pnl > 0.20 or pnl < -0.10:
                trade["exit_price"] = current_price
                trade["exit_time"] = time.time()
                trade["pnl"] = round(pnl, 4)
                trade["status"] = "CLOSED"

    # -------------------------
    # MAIN ENTRY POINT
    # -------------------------
    def run_cycle(self, raw_candidates, market_data):
        """
        raw_candidates = list of dicts from scanner
        market_data = dict[token] = {price: float}
        """
        entered = 0
        for c in raw_candidates:
            score = self.score_candidate(c)

            # Low threshold — shadow should enter frequently to accumulate data
            if score >= 15:
                self.simulate_trade(c, score)
                entered += 1

        self.update_trades(market_data)

        # ALWAYS SAVE (this was the bug)
        self._save_state()

        return entered

    def get_strategy_weights(self) -> dict:
        """
        Returns per-strategy win rate weights based on closed shadow trades.
        Used by bot.py to adjust score thresholds per strategy type.

        Output: { "burst": 0.72, "clob_launch": 0.58, "pre_breakout": 0.65, ... }
        Returns equal weights (0.65) if insufficient data (<10 closed per strategy).
        """
        trades = self.state.get("trades", [])
        closed = [t for t in trades if t.get("status") == "CLOSED"]

        strategies = ["burst", "clob_launch", "pre_breakout", "trend", "micro_scalp"]
        weights = {}

        for strat in strategies:
            strat_trades = [t for t in closed if t.get("strategy_type") == strat]
            if len(strat_trades) < 10:
                weights[strat] = 0.65   # default until enough data
            else:
                wins = [t for t in strat_trades if t.get("pnl", 0) > 0]
                weights[strat] = round(len(wins) / len(strat_trades), 3)

        return weights

    def record_real_outcome(self, symbol: str, strategy_type: str,
                             entry_price: float, exit_price: float,
                             exit_reason: str):
        """
        Called from bot.py when a REAL position closes.
        Feeds actual outcomes back into shadow state so strategy weights
        are calibrated against live performance, not just paper trades.
        """
        pnl = (exit_price - entry_price) / entry_price if entry_price > 0 else 0
        record = {
            "symbol":        symbol,
            "strategy_type": strategy_type,
            "entry_price":   entry_price,
            "exit_price":    exit_price,
            "pnl":           round(pnl, 4),
            "exit_reason":   exit_reason,
            "ts":            time.time(),
            "source":        "real",   # distinguishes from shadow paper trades
        }
        if "real_outcomes" not in self.state:
            self.state["real_outcomes"] = []
        self.state["real_outcomes"].append(record)

        # Keep last 500 real outcomes
        self.state["real_outcomes"] = self.state["real_outcomes"][-500:]
        self._save_state()

    def get_real_strategy_weights(self) -> dict:
        """
        Win rates computed from REAL trade outcomes only.
        Preferred over shadow weights once 10+ real trades per strategy.
        """
        outcomes = self.state.get("real_outcomes", [])
        strategies = ["burst", "clob_launch", "pre_breakout", "trend", "micro_scalp"]
        weights = {}

        for strat in strategies:
            strat_trades = [t for t in outcomes if t.get("strategy_type") == strat]
            if len(strat_trades) < 5:
                weights[strat] = None   # not enough data yet
            else:
                wins = [t for t in strat_trades if t.get("pnl", 0) > 0]
                wr = round(len(wins) / len(strat_trades), 3)
                weights[strat] = wr

        return weights

    def get_report(self):
        """Return summary of shadow performance."""
        trades = self.state.get("trades", [])
        closed = [t for t in trades if t.get("status") == "CLOSED"]
        open_pos = [t for t in trades if t.get("status") == "OPEN"]

        wins = [t for t in closed if t.get("pnl", 0) > 0]
        losses = [t for t in closed if t.get("pnl", 0) <= 0]

        total_pnl = sum(t.get("pnl", 0) for t in closed)
        wr = len(wins) / max(len(closed), 1) * 100

        # Include real outcome stats
        real_weights = self.get_real_strategy_weights()
        real_outcomes = self.state.get("real_outcomes", [])

        return {
            "total_trades":    len(trades),
            "closed":          len(closed),
            "open":            len(open_pos),
            "wins":            len(wins),
            "losses":          len(losses),
            "win_rate":        round(wr, 1),
            "total_pnl":       round(total_pnl, 4),
            "last_updated":    self.state.get("last_updated"),
            "real_outcomes":   len(real_outcomes),
            "strategy_weights": real_weights,
        }


# Global singleton
_shadow_instance = None


def get_shadow_ml():
    global _shadow_instance
    if _shadow_instance is None:
        _shadow_instance = ShadowML()
    return _shadow_instance


if __name__ == "__main__":
    shadow = ShadowML()
    report = shadow.get_report()
    print(json.dumps(report, indent=2))
