"""
ml_report.py — ML pipeline status and insights CLI tool.

Usage: python3 ml_report.py
"""

import os
import sys
import json
import logging
from collections import defaultdict

logging.disable(logging.CRITICAL)  # silence all logs during report

STATE_DIR = os.path.join(os.path.dirname(__file__), "state")
META_PATH = os.path.join(STATE_DIR, "ml_meta.json")


def load_dataset():
    path = os.path.join(STATE_DIR, "ml_dataset.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            data = json.load(f)
        return [d for d in data if d.get("won") is not None]
    except Exception:
        return []


def load_meta():
    if not os.path.exists(META_PATH):
        return {}
    try:
        with open(META_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def win_rate(records):
    if not records:
        return None
    wins = sum(1 for r in records if r.get("won"))
    return wins / len(records)


def format_pct(val):
    if val is None:
        return "N/A"
    return f"{val*100:.0f}%"


def main():
    dataset = load_dataset()
    meta    = load_meta()
    n       = len(dataset)

    # Phase detection (inline to avoid import issues)
    if n < 50:
        phase = "logging"
        next_phase = f"logistic regression at 50 trades"
    elif n < 200:
        phase = "logistic"
        next_phase = f"XGBoost at 200 trades"
    else:
        phase = "xgboost"
        next_phase = "already at top tier"

    print("=" * 50)
    print("=== ML Layer Status ===")
    print("=" * 50)
    print(f"Phase:      {phase} ({n}/{'50' if phase == 'logging' else '200'} trades)")
    print(f"Next phase: {next_phase}")

    if n > 0:
        wr = win_rate(dataset)
        print(f"Win rate:   {format_pct(wr)} across {n} trades")

    # Model meta
    if meta:
        import time
        trained_at = meta.get("trained_at", 0)
        age_h = (time.time() - trained_at) / 3600 if trained_at else 0
        print(f"\nModel type: {meta.get('model_type', 'none')}")
        print(f"Accuracy:   {meta.get('accuracy', 0)*100:.1f}% (in-sample)")
        print(f"Trained:    {age_h:.1f}h ago on {meta.get('n_trades', 0)} trades")
    else:
        print("\nModel:      not trained yet")

    # Feature importance
    fi = meta.get("feature_importance", {})
    if fi:
        print("\n=== Feature Importance ===")
        sorted_fi = sorted(fi.items(), key=lambda x: x[1], reverse=True)
        for i, (feat, imp) in enumerate(sorted_fi, 1):
            print(f"  {i:2}. {feat:<30} {imp:.3f}")

    if not dataset:
        print("\n[No data yet — trades will be logged as they occur]")
        return

    print("\n=== Win Rate by Feature ===")

    # By score band
    bands = defaultdict(list)
    for r in dataset:
        bands[r.get("score_band", "unknown")].append(r)
    band_str = " | ".join(f"{b}={format_pct(win_rate(recs))}" for b, recs in sorted(bands.items()))
    print(f"By score band:  {band_str}")

    # By chart state
    states = defaultdict(list)
    for r in dataset:
        states[r.get("chart_state", "unknown")].append(r)
    state_str = " | ".join(f"{s}={format_pct(win_rate(recs))}" for s, recs in sorted(states.items()))
    print(f"By chart state: {state_str}")

    # By cluster active
    cluster_on  = [r for r in dataset if r.get("cluster_active")]
    cluster_off = [r for r in dataset if not r.get("cluster_active")]
    print(f"By cluster:     active={format_pct(win_rate(cluster_on))} ({len(cluster_on)}) | inactive={format_pct(win_rate(cluster_off))} ({len(cluster_off)})")

    # By alpha signal
    alpha_on  = [r for r in dataset if r.get("alpha_signal_active")]
    alpha_off = [r for r in dataset if not r.get("alpha_signal_active")]
    print(f"By alpha signal: active={format_pct(win_rate(alpha_on))} ({len(alpha_on)}) | inactive={format_pct(win_rate(alpha_off))} ({len(alpha_off)})")

    # By regime
    regimes = defaultdict(list)
    for r in dataset:
        regimes[r.get("regime", "unknown")].append(r)
    regime_str = " | ".join(f"{reg}={format_pct(win_rate(recs))}" for reg, recs in sorted(regimes.items()))
    print(f"By regime:      {regime_str}")

    # By hour (group into blocks)
    hour_wins = defaultdict(list)
    for r in dataset:
        h = r.get("hour_utc")
        if h is not None:
            block = (h // 4) * 4  # 4-hour blocks: 0,4,8,12,16,20
            hour_wins[f"{block:02d}-{block+3:02d}UTC"].append(r)
    if hour_wins:
        hour_str = " | ".join(f"{h}={format_pct(win_rate(recs))}" for h, recs in sorted(hour_wins.items()))
        print(f"By hour block:  {hour_str}")
        # Identify peak hours
        best_block = max(hour_wins.items(), key=lambda x: win_rate(x[1]) or 0)
        print(f"Peak hours:     {best_block[0]} UTC ({format_pct(win_rate(best_block[1]))} WR, {len(best_block[1])} trades)")

    # Recent performance (last 10 trades)
    recent = sorted(dataset, key=lambda x: x.get("entry_time", 0))[-10:]
    if recent:
        wr_recent = win_rate(recent)
        avg_pnl   = sum(r.get("pnl_xrp", 0) for r in recent) / len(recent)
        print(f"\nLast {len(recent)} trades: WR={format_pct(wr_recent)} avg_pnl={avg_pnl:+.3f} XRP")

    print("=" * 50)


if __name__ == "__main__":
    main()
