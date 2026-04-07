"""
improve_loop.py — Self-improvement analysis loop for DKTrenchBot v2.
Analyzes trade history to find loss/win patterns and generate concrete parameter tweaks.
Logs to state/improvement_log.json.
Run every 50th cycle in bot.py, or directly:

CLI:
    python3 improve_loop.py
"""

import json
import os
import time
from collections import Counter, defaultdict
from typing import Dict, List, Optional

from config import STATE_DIR

IMPROVEMENT_LOG = os.path.join(STATE_DIR, "improvement_log.json")
STATE_FILE = os.path.join(STATE_DIR, "state.json")


def _load_trades() -> List[Dict]:
    if not os.path.exists(STATE_FILE):
        return []
    try:
        with open(STATE_FILE) as f:
            data = json.load(f)
        return data.get("trade_history", [])
    except Exception:
        return []


def _load_log() -> List[Dict]:
    if not os.path.exists(IMPROVEMENT_LOG):
        return []
    try:
        with open(IMPROVEMENT_LOG) as f:
            return json.load(f)
    except Exception:
        return []


def _save_log(entries: List[Dict]) -> None:
    entries = entries[-500:]  # keep last 500
    tmp = IMPROVEMENT_LOG + ".tmp"
    with open(tmp, "w") as f:
        json.dump(entries, f, indent=2)
    os.replace(tmp, IMPROVEMENT_LOG)


class ImprovementLoop:
    """
    Analyzes trade history for patterns and generates actionable parameter tweaks.
    Suggestions are logged only — never auto-applied.
    """

    def analyze_losses(self, trades: List[Dict]) -> Dict:
        """Find patterns in losing trades."""
        losses = [t for t in trades if float(t.get("pnl_xrp", 0) or 0) < -0.1]

        if not losses:
            return {"count": 0, "patterns": [], "worst_exit_reasons": {}, "score_bands": {}}

        # Score distribution in losses
        score_bands = defaultdict(int)
        for t in losses:
            s = int(t.get("score", 0) or 0)
            if s < 40:
                score_bands["<40"] += 1
            elif s < 50:
                score_bands["40-49"] += 1
            elif s < 60:
                score_bands["50-59"] += 1
            elif s < 70:
                score_bands["60-69"] += 1
            else:
                score_bands["70+"] += 1

        # Chart states in losses
        chart_state_counter = Counter(t.get("chart_state", "unknown") for t in losses)

        # Exit reasons in losses
        exit_counter = Counter(t.get("exit_reason", "unknown") for t in losses)

        # Average PnL per chart state
        chart_pnl = defaultdict(list)
        for t in losses:
            cs = t.get("chart_state", "unknown")
            chart_pnl[cs].append(float(t.get("pnl_xrp", 0) or 0))
        chart_avg_pnl = {cs: sum(v) / len(v) for cs, v in chart_pnl.items()}

        # Stale exits
        stale_exits = [t for t in losses if "stale" in t.get("exit_reason", "")]
        stale_pnl = sum(float(t.get("pnl_xrp", 0) or 0) for t in stale_exits)

        # Hard stops
        hard_stops = [t for t in losses if "hard_stop" in t.get("exit_reason", "")]
        hard_stop_pnl = sum(float(t.get("pnl_xrp", 0) or 0) for t in hard_stops)

        # Avg hold time for losses (hours)
        hold_times = []
        for t in losses:
            et = t.get("entry_time", 0)
            xt = t.get("exit_time", 0)
            if et and xt and xt > et:
                hold_times.append((xt - et) / 3600)
        avg_hold_h = sum(hold_times) / len(hold_times) if hold_times else 0

        patterns = []
        # Pattern: most losses in score band
        if score_bands:
            worst_band = max(score_bands, key=lambda b: score_bands[b])
            pct = score_bands[worst_band] / len(losses) * 100
            patterns.append(f"{pct:.0f}% of losses scored in band {worst_band}")

        # Pattern: all trades in same chart state
        if chart_state_counter:
            top_cs, top_cs_cnt = chart_state_counter.most_common(1)[0]
            pct = top_cs_cnt / len(losses) * 100
            if pct > 60:
                patterns.append(f"{pct:.0f}% of losses entered at chart_state={top_cs}")

        # Pattern: stale exits
        if stale_exits:
            patterns.append(f"Stale exits: {len(stale_exits)} trades totaling {stale_pnl:.2f} XRP")

        # Pattern: long hold times on losses
        if avg_hold_h > 2.0:
            patterns.append(f"Average loss hold time: {avg_hold_h:.1f}h — consider tighter stale timer")

        return {
            "count": len(losses),
            "total_pnl": round(sum(float(t.get("pnl_xrp", 0) or 0) for t in losses), 4),
            "patterns": patterns,
            "score_bands": dict(score_bands),
            "chart_states": dict(chart_state_counter),
            "worst_exit_reasons": dict(exit_counter.most_common(5)),
            "stale_count": len(stale_exits),
            "stale_pnl": round(stale_pnl, 4),
            "hard_stop_count": len(hard_stops),
            "hard_stop_pnl": round(hard_stop_pnl, 4),
            "avg_hold_h": round(avg_hold_h, 2),
            "chart_avg_pnl": {cs: round(v, 4) for cs, v in chart_avg_pnl.items()},
        }

    def analyze_winners(self, trades: List[Dict]) -> Dict:
        """Find patterns in winning trades."""
        wins = [t for t in trades if float(t.get("pnl_xrp", 0) or 0) > 0.1]

        if not wins:
            return {"count": 0, "patterns": [], "chart_states": {}, "score_bands": {}}

        chart_state_counter = Counter(t.get("chart_state", "unknown") for t in wins)

        score_bands = defaultdict(int)
        for t in wins:
            s = int(t.get("score", 0) or 0)
            if s < 40:
                score_bands["<40"] += 1
            elif s < 50:
                score_bands["40-49"] += 1
            elif s < 60:
                score_bands["50-59"] += 1
            elif s < 70:
                score_bands["60-69"] += 1
            else:
                score_bands["70+"] += 1

        exit_counter = Counter(t.get("exit_reason", "unknown") for t in wins)

        # Average PnL per score band
        band_pnl = defaultdict(list)
        for t in wins:
            s = int(t.get("score", 0) or 0)
            band = "<40" if s < 40 else ("40-49" if s < 50 else ("50-59" if s < 60 else ("60-69" if s < 70 else "70+")))
            band_pnl[band].append(float(t.get("pnl_xrp", 0) or 0))

        # Hold times for wins
        hold_times = []
        for t in wins:
            et = t.get("entry_time", 0)
            xt = t.get("exit_time", 0)
            if et and xt and xt > et:
                hold_times.append((xt - et) / 3600)
        avg_hold_h = sum(hold_times) / len(hold_times) if hold_times else 0

        patterns = []
        if chart_state_counter:
            top_cs, top_cnt = chart_state_counter.most_common(1)[0]
            patterns.append(f"Best chart state for wins: {top_cs} ({top_cnt}/{len(wins)} wins)")
        if score_bands:
            best_band = max(score_bands, key=lambda b: score_bands[b])
            patterns.append(f"Best score band for wins: {best_band} ({score_bands[best_band]} wins)")
        if avg_hold_h > 0:
            patterns.append(f"Average win hold time: {avg_hold_h:.1f}h")

        return {
            "count": len(wins),
            "total_pnl": round(sum(float(t.get("pnl_xrp", 0) or 0) for t in wins), 4),
            "patterns": patterns,
            "chart_states": dict(chart_state_counter),
            "score_bands": dict(score_bands),
            "best_exit_reasons": dict(exit_counter.most_common(5)),
            "avg_hold_h": round(avg_hold_h, 2),
            "band_avg_pnl": {b: round(sum(v) / len(v), 4) for b, v in band_pnl.items()},
        }

    def generate_tweaks(self, win_analysis: Dict, loss_analysis: Dict) -> List[Dict]:
        """
        Generate concrete parameter change suggestions based on analysis.
        These are SUGGESTIONS ONLY — never auto-applied.
        """
        tweaks = []

        # Tweak 1: Score threshold (if most losses in low score bands)
        score_bands_losses = loss_analysis.get("score_bands", {})
        low_score_losses = score_bands_losses.get("<40", 0) + score_bands_losses.get("40-49", 0) + score_bands_losses.get("50-59", 0)
        total_losses = loss_analysis.get("count", 0)
        if total_losses > 0 and low_score_losses / total_losses >= 0.60:
            tweaks.append({
                "type": "score_threshold",
                "current": "SCORE_TRADEABLE=42",
                "suggested": "SCORE_TRADEABLE=50",
                "rationale": f"{low_score_losses/total_losses:.0%} of losses scored <60",
                "expected_impact": "Reduce low-quality entries, accept fewer trades",
                "priority": "high",
            })

        # Tweak 2: Chart state diversity
        loss_chart_states = loss_analysis.get("chart_states", {})
        if loss_chart_states:
            top_cs = max(loss_chart_states, key=lambda cs: loss_chart_states[cs])
            top_pct = loss_chart_states[top_cs] / total_losses if total_losses > 0 else 0
            if top_pct >= 0.80:
                tweaks.append({
                    "type": "chart_state_gate",
                    "issue": f"{top_pct:.0%} of losses entered at chart_state={top_cs}",
                    "suggested": f"Add momentum confirmation gate for {top_cs} entries",
                    "rationale": "No chart state diversity = relying on single signal type",
                    "priority": "critical",
                })

        # Tweak 3: Stale exit timer (if stale exits are significant)
        stale_pnl = loss_analysis.get("stale_pnl", 0)
        stale_count = loss_analysis.get("stale_count", 0)
        if stale_count >= 2 and stale_pnl < -1.0:
            avg_hold = loss_analysis.get("avg_hold_h", 0)
            suggested_stale = max(0.75, avg_hold * 0.5)
            tweaks.append({
                "type": "stale_exit_timer",
                "current": "STALE_EXIT_HOURS=1.5",
                "suggested": f"STALE_EXIT_HOURS={suggested_stale:.2f}",
                "rationale": f"{stale_count} stale exits totaling {stale_pnl:.2f} XRP. Avg loss hold: {avg_hold:.1f}h",
                "expected_impact": f"Recover ~{abs(stale_pnl):.1f} XRP over time by cutting dead positions earlier",
                "priority": "high",
            })

        # Tweak 4: Sizing for losses (if losses significantly larger than wins)
        win_pnl = win_analysis.get("total_pnl", 0)
        loss_pnl = abs(loss_analysis.get("total_pnl", 0))
        if win_analysis.get("count", 0) > 0 and loss_analysis.get("count", 0) > 0:
            avg_win = win_pnl / win_analysis["count"]
            avg_loss = loss_pnl / loss_analysis["count"]
            if avg_loss > avg_win * 1.5:
                tweaks.append({
                    "type": "position_sizing",
                    "issue": f"Avg loss ({avg_loss:.2f} XRP) > 1.5x avg win ({avg_win:.2f} XRP)",
                    "suggested": "Reduce XRP_PER_TRADE_BASE by 20% or implement hard stop earlier",
                    "rationale": "Kelly criterion violation — risk/reward imbalanced",
                    "priority": "high",
                })

        # Tweak 5: Pre-breakout signal confirmation (if all losses are pre_breakout)
        if loss_chart_states.get("pre_breakout", 0) == total_losses and total_losses >= 3:
            tweaks.append({
                "type": "pre_breakout_confirmation",
                "issue": "100% of losses entered at pre_breakout — signal not confirmed",
                "suggested": "Require +3% price movement in 2 readings before entering pre_breakout",
                "rationale": "Pre-breakout is a setup signal, not an entry signal. Need price confirmation.",
                "priority": "critical",
            })

        return tweaks

    def run_loop(self) -> Dict:
        """
        Main improvement loop.
        Loads trades, analyzes, generates tweaks, and logs to state/improvement_log.json.
        """
        trades = _load_trades()

        if len(trades) < 5:
            result = {
                "ts": time.time(),
                "ts_human": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "status": "insufficient_data",
                "min_trades_needed": 5,
                "current_trades": len(trades),
                "message": f"Need at least 5 trades for analysis. Have {len(trades)}.",
            }
            log = _load_log()
            log.append(result)
            _save_log(log)
            return result

        loss_analysis = self.analyze_losses(trades)
        win_analysis = self.analyze_winners(trades)
        tweaks = self.generate_tweaks(win_analysis, loss_analysis)

        result = {
            "ts": time.time(),
            "ts_human": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "status": "ok",
            "trades_analyzed": len(trades),
            "win_analysis": win_analysis,
            "loss_analysis": loss_analysis,
            "tweaks": tweaks,
            "critical_tweaks": sum(1 for t in tweaks if t.get("priority") == "critical"),
            "high_tweaks": sum(1 for t in tweaks if t.get("priority") == "high"),
        }

        log = _load_log()
        log.append(result)
        _save_log(log)
        return result


if __name__ == "__main__":
    loop = ImprovementLoop()
    result = loop.run_loop()

    print("\n=== IMPROVEMENT LOOP ANALYSIS ===")
    print(f"Timestamp: {result.get('ts_human', 'N/A')}")
    print(f"Trades analyzed: {result.get('trades_analyzed', 0)}")

    if result.get("status") == "insufficient_data":
        print(f"\n⚠️  {result['message']}")
    else:
        wa = result.get("win_analysis", {})
        la = result.get("loss_analysis", {})

        print(f"\n--- WINNERS ({wa.get('count', 0)} trades, {wa.get('total_pnl', 0):+.2f} XRP) ---")
        for p in wa.get("patterns", []):
            print(f"  ✅ {p}")

        print(f"\n--- LOSSES ({la.get('count', 0)} trades, {la.get('total_pnl', 0):+.2f} XRP) ---")
        for p in la.get("patterns", []):
            print(f"  ❌ {p}")

        print(f"\n--- CHART STATES (losses) ---")
        for cs, cnt in la.get("chart_states", {}).items():
            print(f"  {cs}: {cnt}")

        print(f"\n--- SCORE BANDS (losses) ---")
        for band, cnt in la.get("score_bands", {}).items():
            print(f"  {band}: {cnt}")

        print(f"\n--- GENERATED TWEAKS ({len(result.get('tweaks', []))}) ---")
        for i, tweak in enumerate(result.get("tweaks", []), 1):
            priority_icon = "🔴" if tweak["priority"] == "critical" else "🟡"
            print(f"\n  {i}. {priority_icon} [{tweak['priority'].upper()}] {tweak['type']}")
            if "suggested" in tweak:
                print(f"     Suggested: {tweak['suggested']}")
            if "rationale" in tweak:
                print(f"     Rationale: {tweak['rationale']}")
            if "expected_impact" in tweak:
                print(f"     Impact: {tweak['expected_impact']}")

        print(f"\n  Logged to: {IMPROVEMENT_LOG}")
    print()
