"""
report.py — Daily summary report.
Writes: state/daily_report.txt
"""

import os
import time
import json
import requests
from typing import Dict, List
from config import STATE_DIR, CLIO_URL, BOT_WALLET_ADDRESS
import state as state_mod

os.makedirs(STATE_DIR, exist_ok=True)
REPORT_FILE = os.path.join(STATE_DIR, "daily_report.txt")


def _rpc(method: str, params: dict):
    try:
        r = requests.post(CLIO_URL, json={"method": method, "params": [params]}, timeout=15)
        return r.json().get("result")
    except Exception:
        return None


def get_xrp_balance() -> float:
    r = _rpc("account_info", {"account": BOT_WALLET_ADDRESS, "ledger_index": "validated"})
    if r and r.get("status") == "success":
        return int(r["account_data"]["Balance"]) / 1e6
    return 0.0


def generate_report(bot_state: Dict) -> str:
    ts      = time.strftime("%Y-%m-%d %H:%M UTC")
    perf    = bot_state.get("performance", {})
    trades  = state_mod.get_recent_trades(bot_state, n=50)

    xrp_bal       = get_xrp_balance()
    total_trades  = perf.get("total_trades", 0)
    wins          = perf.get("wins", 0)
    losses        = perf.get("losses", 0)
    win_rate      = perf.get("win_rate", 0.0)
    total_pnl     = perf.get("total_pnl_xrp", 0.0)
    best_trade    = perf.get("best_trade_pct", 0.0)
    worst_trade   = perf.get("worst_trade_pct", 0.0)
    cons_loss     = perf.get("consecutive_losses", 0)

    # Regime
    regime_file = os.path.join(STATE_DIR, "regime.json")
    regime = "unknown"
    if os.path.exists(regime_file):
        try:
            with open(regime_file) as f:
                regime = json.load(f).get("regime", "unknown")
        except Exception:
            pass

    # Best chart states
    state_counts: Dict[str, List] = {}
    for t in trades:
        cs = t.get("chart_state", "unknown")
        state_counts.setdefault(cs, []).append(t.get("pnl_pct", 0))
    state_perf = {
        cs: {
            "count":    len(pnls),
            "win_rate": sum(1 for p in pnls if p > 0) / len(pnls),
            "avg_pnl":  sum(pnls) / len(pnls),
        }
        for cs, pnls in state_counts.items() if pnls
    }

    # Improvements
    imp_file = os.path.join(STATE_DIR, "improvements.json")
    recent_changes = []
    if os.path.exists(imp_file):
        try:
            with open(imp_file) as f:
                imp = json.load(f)
            history = imp.get("history", [])
            if history:
                recent_changes = history[-1].get("changes", [])
        except Exception:
            pass

    # System health
    status_file = os.path.join(STATE_DIR, "status.json")
    last_cycle_ts = 0
    if os.path.exists(status_file):
        try:
            with open(status_file) as f:
                status = json.load(f)
            last_cycle_ts = status.get("last_cycle", 0)
        except Exception:
            pass

    health_lag = time.time() - last_cycle_ts
    health_str = "OK" if health_lag < 300 else f"WARNING: last cycle {health_lag/60:.0f}m ago"

    # Best and worst trades
    if trades:
        best  = max(trades, key=lambda t: t.get("pnl_pct", 0))
        worst = min(trades, key=lambda t: t.get("pnl_pct", 0))
    else:
        best = worst = None

    lines = [
        "=" * 60,
        f"  DKTrenchBot Daily Report — {ts}",
        "=" * 60,
        "",
        "── BALANCE ──────────────────────────────────────",
        f"  XRP Balance:      {xrp_bal:.4f} XRP",
        f"  Total PnL:        {total_pnl:+.4f} XRP",
        "",
        "── PERFORMANCE ──────────────────────────────────",
        f"  Total Trades:     {total_trades}",
        f"  Wins / Losses:    {wins} / {losses}",
        f"  Win Rate:         {win_rate:.1%}",
        f"  Best Trade:       {best_trade:+.1%}",
        f"  Worst Trade:      {worst_trade:+.1%}",
        f"  Consecutive Loss: {cons_loss}",
        "",
        "── REGIME ───────────────────────────────────────",
        f"  Current Regime:   {regime.upper()}",
        "",
    ]

    if best:
        lines += [
            "── TOP TRADES ───────────────────────────────────",
            f"  Best:  {best.get('symbol','?')} {best.get('pnl_pct',0):+.1%} ({best.get('exit_reason','?')})",
            f"  Worst: {worst.get('symbol','?')} {worst.get('pnl_pct',0):+.1%} ({worst.get('exit_reason','?')})",
            "",
        ]

    if state_perf:
        lines.append("── CHART STATE PERFORMANCE ──────────────────────")
        for cs, metrics in sorted(state_perf.items(), key=lambda x: -x[1]["avg_pnl"]):
            lines.append(f"  {cs:<20} n={metrics['count']} wr={metrics['win_rate']:.0%} avg={metrics['avg_pnl']:+.1%}")
        lines.append("")

    if recent_changes:
        lines.append("── RECENT IMPROVEMENTS ──────────────────────────")
        for c in recent_changes:
            lines.append(f"  • {c}")
        lines.append("")

    lines += [
        "── SYSTEM HEALTH ────────────────────────────────",
        f"  Bot Loop:         {health_str}",
        "=" * 60,
        "",
    ]

    report = "\n".join(lines)

    with open(REPORT_FILE, "w") as f:
        f.write(report)

    # Archive
    archive = os.path.join(STATE_DIR, f"report_{time.strftime('%Y%m%d')}.txt")
    with open(archive, "w") as f:
        f.write(report)

    return report


if __name__ == "__main__":
    s = state_mod.load()
    print(generate_report(s))
