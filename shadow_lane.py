"""
shadow_lane.py — Phantom paper-trading system.
Runs in parallel with ZERO effect on real funds or live execution.
Evaluates hypothetical entries/exits using same signals as the live bot.
Saves shadow state to state/shadow_state.json only.

CLI:
    python3 shadow_lane.py --report
"""

import argparse
import json
import os
import time
from typing import Dict, List, Optional, Tuple

from config import STATE_DIR

SHADOW_STATE_FILE = os.path.join(STATE_DIR, "shadow_state.json")


def _load_shadow() -> Dict:
    if os.path.exists(SHADOW_STATE_FILE):
        try:
            with open(SHADOW_STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "positions": {},
        "trade_history": [],
        "performance": {
            "wins": 0,
            "losses": 0,
            "total_pnl_xrp": 0.0,
            "win_rate": 0.0,
        },
        "strategy_version": "shadow_v1",
        "created_at": time.time(),
    }


def _save_shadow(state: Dict) -> None:
    tmp = SHADOW_STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, SHADOW_STATE_FILE)


class ShadowLane:
    """
    Paper-trading shadow lane.
    - NEVER touches real funds
    - NEVER influences live execution
    - Uses an alternative entry/exit strategy to A/B test against production
    """

    # Shadow strategy: more aggressive entries (lower threshold) + wider TPs
    SHADOW_SCORE_THRESHOLD = 45   # vs production ~60
    SHADOW_TP1_PCT = 0.15         # +15% → sell 40%
    SHADOW_TP1_FRAC = 0.40
    SHADOW_TP2_PCT = 0.40         # +40% → sell 40%
    SHADOW_TP2_FRAC = 0.40
    SHADOW_STOP_PCT = 0.12        # -12% hard stop
    SHADOW_MAX_HOLD_H = 3.0       # 3hr max
    SHADOW_BASE_SIZE = 10.0       # XRP equivalent (paper only)

    def __init__(self):
        self._state = _load_shadow()

    def _shadow_position_size(self, score: int) -> float:
        """Shadow sizing based on score tier."""
        if score >= 65:
            return 20.0
        elif score >= 50:
            return 15.0
        return self.SHADOW_BASE_SIZE

    def evaluate_entry(self, candidate: Dict, score: int, bot_state: Dict) -> Dict:
        """
        Evaluate whether shadow would enter this candidate.
        Returns dict with action + reason. NEVER executes real trades.
        """
        symbol = candidate.get("symbol", "")
        key = candidate.get("key", f"{symbol}:shadow")
        price = candidate.get("price", 0)
        chart_state = candidate.get("chart_state", "unknown")

        result = {
            "action": "skip",
            "reason": "",
            "symbol": symbol,
            "score": score,
            "size_xrp": 0.0,
            "ts": time.time(),
        }

        if not price or price <= 0:
            result["reason"] = "no_price"
            return result

        if key in self._state.get("positions", {}):
            result["reason"] = "already_in"
            return result

        if score < self.SHADOW_SCORE_THRESHOLD:
            result["reason"] = f"score_{score}_below_{self.SHADOW_SCORE_THRESHOLD}"
            return result

        # Shadow enters on pre_breakout AND continuation (more aggressive)
        allowed_states = {"pre_breakout", "continuation", "accumulation", "expansion"}
        if chart_state not in allowed_states:
            result["reason"] = f"chart_state_{chart_state}_not_allowed"
            return result

        size = self._shadow_position_size(score)
        pos = {
            "symbol": symbol,
            "key": key,
            "issuer": candidate.get("issuer", ""),
            "entry_price": price,
            "entry_time": time.time(),
            "size_xrp": size,
            "peak_price": price,
            "tp1_hit": False,
            "tp2_hit": False,
            "score": score,
            "chart_state": chart_state,
        }
        self._state.setdefault("positions", {})[key] = pos
        _save_shadow(self._state)

        result["action"] = "enter"
        result["reason"] = f"score={score} chart={chart_state}"
        result["size_xrp"] = size
        return result

    def evaluate_exit(self, position: Dict, current_price: float, bot_state: Dict) -> Dict:
        """
        Evaluate whether shadow should exit a position.
        Returns dict with action + reason. NEVER executes real trades.
        """
        symbol = position.get("symbol", "")
        key = position.get("key", "")
        entry_price = position.get("entry_price", current_price)
        entry_time = position.get("entry_time", time.time())
        peak_price = max(position.get("peak_price", entry_price), current_price)
        hold_hours = (time.time() - entry_time) / 3600
        size_xrp = position.get("size_xrp", self.SHADOW_BASE_SIZE)

        pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0

        result = {
            "action": "hold",
            "reason": "holding",
            "pnl_pct": pnl_pct,
            "pnl_xrp": size_xrp * pnl_pct,
            "symbol": symbol,
        }

        # Update peak
        if key in self._state.get("positions", {}):
            self._state["positions"][key]["peak_price"] = peak_price

        # Hard stop
        if pnl_pct <= -self.SHADOW_STOP_PCT:
            result["action"] = "exit"
            result["reason"] = f"shadow_hard_stop_{pnl_pct:.1%}"
            self._close_shadow_position(key, current_price, result["reason"], size_xrp)
            return result

        # Max hold
        if hold_hours >= self.SHADOW_MAX_HOLD_H:
            result["action"] = "exit"
            result["reason"] = f"shadow_max_hold_{hold_hours:.1f}h"
            self._close_shadow_position(key, current_price, result["reason"], size_xrp)
            return result

        # TP2 (full exit)
        if pnl_pct >= self.SHADOW_TP2_PCT and position.get("tp1_hit"):
            result["action"] = "exit"
            result["reason"] = f"shadow_tp2_{pnl_pct:.1%}"
            self._close_shadow_position(key, current_price, result["reason"], size_xrp)
            return result

        # TP1 (partial — mark hit)
        if pnl_pct >= self.SHADOW_TP1_PCT and not position.get("tp1_hit"):
            result["action"] = "partial"
            result["reason"] = f"shadow_tp1_{pnl_pct:.1%}"
            if key in self._state.get("positions", {}):
                self._state["positions"][key]["tp1_hit"] = True
                _save_shadow(self._state)
            return result

        return result

    def _close_shadow_position(self, key: str, exit_price: float, reason: str, size_xrp: float) -> None:
        positions = self._state.get("positions", {})
        pos = positions.pop(key, None)
        if not pos:
            return

        entry_price = pos.get("entry_price", exit_price)
        pnl_pct = (exit_price - entry_price) / entry_price if entry_price > 0 else 0
        pnl_xrp = size_xrp * pnl_pct

        trade = {
            "symbol": pos.get("symbol"),
            "entry_price": entry_price,
            "exit_price": exit_price,
            "entry_time": pos.get("entry_time"),
            "exit_time": time.time(),
            "pnl_pct": pnl_pct,
            "pnl_xrp": pnl_xrp,
            "exit_reason": reason,
            "score": pos.get("score", 0),
            "chart_state": pos.get("chart_state"),
            "size_xrp": size_xrp,
        }
        self._state.setdefault("trade_history", []).append(trade)

        perf = self._state.setdefault("performance", {"wins": 0, "losses": 0, "total_pnl_xrp": 0.0, "win_rate": 0.0})
        perf["total_pnl_xrp"] = perf.get("total_pnl_xrp", 0.0) + pnl_xrp
        if pnl_xrp > 0:
            perf["wins"] = perf.get("wins", 0) + 1
        elif pnl_xrp < -0.1:
            perf["losses"] = perf.get("losses", 0) + 1

        total = perf["wins"] + perf["losses"]
        perf["win_rate"] = perf["wins"] / total if total > 0 else 0.0
        _save_shadow(self._state)

    def run_cycle_check(self, candidates: List[Dict], bot_state: Dict) -> None:
        """
        Called once per bot cycle (non-blocking, try/except wrapped at call site).
        Evaluates entries for new candidates and exits for open shadow positions.
        """
        # Evaluate exits on existing shadow positions
        import scanner as scanner_mod
        for key, pos in list(self._state.get("positions", {}).items()):
            try:
                symbol = pos.get("symbol", "")
                issuer = pos.get("issuer", "")
                price, _, _, _ = scanner_mod.get_token_price_and_tvl(symbol, issuer)
                if price and price > 0:
                    self.evaluate_exit(pos, price, bot_state)
            except Exception:
                pass

        # Evaluate entries for new candidates
        for candidate in candidates:
            try:
                score = candidate.get("score", 0)
                self.evaluate_entry(candidate, score, bot_state)
            except Exception:
                pass

    def get_comparison_report(self) -> Dict:
        """
        Compare shadow performance vs production performance.
        """
        # Load production state
        prod_state_file = os.path.join(STATE_DIR, "state.json")
        prod_trades = []
        prod_perf = {}
        try:
            with open(prod_state_file) as f:
                prod_state = json.load(f)
            prod_trades = prod_state.get("trade_history", [])
            prod_perf = prod_state.get("performance", {})
        except Exception:
            pass

        shadow_trades = self._state.get("trade_history", [])
        shadow_perf = self._state.get("performance", {})

        # Production stats
        prod_wins = sum(1 for t in prod_trades if float(t.get("pnl_xrp", 0) or 0) > 0.1)
        prod_losses = sum(1 for t in prod_trades if float(t.get("pnl_xrp", 0) or 0) < -0.1)
        prod_total_pnl = sum(float(t.get("pnl_xrp", 0) or 0) for t in prod_trades)
        prod_wr = prod_wins / (prod_wins + prod_losses) if (prod_wins + prod_losses) > 0 else 0.0

        # Shadow stats
        shadow_wins = shadow_perf.get("wins", 0)
        shadow_losses = shadow_perf.get("losses", 0)
        shadow_pnl = shadow_perf.get("total_pnl_xrp", 0.0)
        shadow_wr = shadow_perf.get("win_rate", 0.0)

        report = {
            "timestamp": time.time(),
            "production": {
                "total_trades": len(prod_trades),
                "wins": prod_wins,
                "losses": prod_losses,
                "win_rate": round(prod_wr, 3),
                "total_pnl_xrp": round(prod_total_pnl, 4),
                "avg_pnl_xrp": round(prod_total_pnl / max(len(prod_trades), 1), 4),
            },
            "shadow": {
                "total_trades": len(shadow_trades),
                "wins": shadow_wins,
                "losses": shadow_losses,
                "win_rate": round(shadow_wr, 3),
                "total_pnl_xrp": round(shadow_pnl, 4),
                "avg_pnl_xrp": round(shadow_pnl / max(len(shadow_trades), 1), 4),
            },
            "delta": {
                "win_rate_delta": round(shadow_wr - prod_wr, 3),
                "pnl_delta_xrp": round(shadow_pnl - prod_total_pnl, 4),
            },
            "open_shadow_positions": len(self._state.get("positions", {})),
            "recommendation": self._generate_recommendation(shadow_wr, prod_wr, shadow_pnl, prod_total_pnl),
        }
        return report

    def _generate_recommendation(self, shadow_wr: float, prod_wr: float,
                                  shadow_pnl: float, prod_pnl: float) -> str:
        if len(self._state.get("trade_history", [])) < 5:
            return "Insufficient shadow data — need 5+ trades for comparison"
        if shadow_wr > prod_wr + 0.10 and shadow_pnl > prod_pnl:
            return "Shadow outperforming on WR and PnL — consider reviewing shadow parameters for adoption"
        elif shadow_wr > prod_wr + 0.10:
            return "Shadow has higher WR but lower PnL — may be taking smaller profits"
        elif prod_wr > shadow_wr + 0.10:
            return "Production outperforming shadow — current strategy is better calibrated"
        else:
            return "Shadow and production performing similarly — insufficient signal differentiation"

    def promote_strategy(self) -> Optional[Dict]:
        """
        Suggests (never auto-applies) parameter changes if shadow significantly outperforms.
        Returns None if insufficient data or shadow not clearly better.
        """
        report = self.get_comparison_report()
        shadow = report["shadow"]
        prod = report["production"]

        if shadow["total_trades"] < 10:
            return None

        if shadow["win_rate"] > prod["win_rate"] + 0.15 and shadow["total_pnl_xrp"] > prod["total_pnl_xrp"]:
            return {
                "suggestion": "Lower SCORE_TRADEABLE to 45",
                "rationale": f"Shadow WR={shadow['win_rate']:.1%} vs prod WR={prod['win_rate']:.1%}",
                "impact": f"+{shadow['total_pnl_xrp'] - prod['total_pnl_xrp']:.2f} XRP over same period",
                "action_required": "Manual review and config change by operator",
                "auto_applied": False,
            }
        return None


# Module-level singleton
_shadow_lane: Optional[ShadowLane] = None


def get_shadow_lane() -> ShadowLane:
    global _shadow_lane
    if _shadow_lane is None:
        _shadow_lane = ShadowLane()
    return _shadow_lane


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Shadow lane paper trading report")
    parser.add_argument("--report", action="store_true", help="Print comparison report")
    args = parser.parse_args()

    lane = get_shadow_lane()

    if args.report or True:  # always show report in CLI mode
        report = lane.get_comparison_report()
        print("\n=== SHADOW LANE COMPARISON REPORT ===")
        print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(report['timestamp']))}")
        print(f"\n--- PRODUCTION ---")
        p = report["production"]
        print(f"  Trades:    {p['total_trades']}")
        print(f"  Win rate:  {p['win_rate']:.1%}")
        print(f"  Total PnL: {p['total_pnl_xrp']:+.4f} XRP")
        print(f"  Avg PnL:   {p['avg_pnl_xrp']:+.4f} XRP/trade")
        print(f"\n--- SHADOW LANE (score≥{ShadowLane.SHADOW_SCORE_THRESHOLD}, wider TPs) ---")
        s = report["shadow"]
        print(f"  Trades:    {s['total_trades']}")
        print(f"  Win rate:  {s['win_rate']:.1%}")
        print(f"  Total PnL: {s['total_pnl_xrp']:+.4f} XRP")
        print(f"  Avg PnL:   {s['avg_pnl_xrp']:+.4f} XRP/trade")
        print(f"\n--- DELTA ---")
        d = report["delta"]
        print(f"  WR delta:  {d['win_rate_delta']:+.1%}")
        print(f"  PnL delta: {d['pnl_delta_xrp']:+.4f} XRP")
        print(f"\n  Open shadow positions: {report['open_shadow_positions']}")
        print(f"\n  Recommendation: {report['recommendation']}")

        promo = lane.promote_strategy()
        if promo:
            print(f"\n⚡ PROMOTE SUGGESTION: {promo['suggestion']}")
            print(f"   Rationale: {promo['rationale']}")
            print(f"   Note: {promo['action_required']}")
        print()
