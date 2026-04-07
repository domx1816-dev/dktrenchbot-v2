"""
learn.py — DKTrenchBot Self-Learning Module

Reads trade history, computes what's actually working, and writes
learned adjustments back to state/learned_weights.json.

The bot reads learned_weights.json every cycle and applies signal
multipliers and score bonuses/penalties based on real outcomes.

Run automatically after every trade exit OR via:
    python3 learn.py --report
"""

import json
import os
import time
import logging
import argparse
from collections import defaultdict

logger = logging.getLogger("learn")

STATE_DIR    = os.path.join(os.path.dirname(__file__), "state")
WEIGHTS_FILE = os.path.join(STATE_DIR, "learned_weights.json")
MIN_TRADES   = 5    # minimum trades in a bucket before we trust the stats
DECAY        = 0.85 # how much to weight recent trades vs old (1.0 = no decay)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_history() -> list:
    """Load all closed trades from state.json trade_history + execution_log sells."""
    trades = []

    # Primary: state.json trade_history (has score, chart_state, pnl_xrp)
    state_path = os.path.join(STATE_DIR, "state.json")
    if os.path.exists(state_path):
        try:
            with open(state_path) as f:
                d = json.load(f)
            trades += d.get("trade_history", [])
        except Exception:
            pass

    # Fallback: bot_state files
    for fname in ["bot_state.json"]:
        fpath = os.path.join(STATE_DIR, fname)
        if os.path.exists(fpath):
            try:
                with open(fpath) as f:
                    d = json.load(f)
                trades += d.get("trade_history", [])
            except Exception:
                pass

    # Deduplicate by exit hash if available
    seen = set()
    unique = []
    for t in trades:
        key = t.get("exit_hash") or t.get("hash") or f"{t.get('symbol')}{t.get('ts',0)}"
        if key not in seen:
            seen.add(key)
            unique.append(t)

    return unique


def _win(trade: dict) -> bool:
    return trade.get("pnl_xrp", 0) > 0


def _weighted_wr(trades: list) -> float:
    """Win rate with recency decay — recent trades weighted more."""
    if not trades:
        return 0.5
    # Sort oldest first
    sorted_trades = sorted(trades, key=lambda t: t.get("ts", 0))
    weights = [DECAY ** (len(sorted_trades) - i - 1) for i in range(len(sorted_trades))]
    weighted_wins   = sum(w for t, w in zip(sorted_trades, weights) if _win(t))
    total_weight    = sum(weights)
    return weighted_wins / total_weight if total_weight > 0 else 0.5


def _avg_pnl(trades: list) -> float:
    if not trades:
        return 0.0
    return sum(t.get("pnl_xrp", 0) for t in trades) / len(trades)


# ── Analysis Functions ────────────────────────────────────────────────────────

def analyze_chart_states(trades: list) -> dict:
    """WR and avg PnL by chart_state."""
    by_state = defaultdict(list)
    for t in trades:
        state = t.get("chart_state", "unknown")
        by_state[state].append(t)

    results = {}
    for state, bucket in by_state.items():
        if len(bucket) < MIN_TRADES:
            continue
        wr  = _weighted_wr(bucket)
        avg = _avg_pnl(bucket)
        results[state] = {
            "n": len(bucket),
            "wr": round(wr, 3),
            "avg_pnl": round(avg, 4),
            # Score modifier: +bonus for outperforming, -penalty for underperforming
            # wr > 0.50 = bonus, wr < 0.35 = penalty
            "score_adj": round((wr - 0.42) * 20, 1),  # 42% = baseline
        }
    return results


def analyze_score_bands(trades: list) -> dict:
    """WR and avg PnL by score band (elite/normal/small)."""
    by_band = defaultdict(list)
    for t in trades:
        band = t.get("score_band", "unknown")
        by_band[band].append(t)

    results = {}
    for band, bucket in by_band.items():
        if len(bucket) < MIN_TRADES:
            continue
        wr  = _weighted_wr(bucket)
        avg = _avg_pnl(bucket)
        results[band] = {
            "n": len(bucket),
            "wr": round(wr, 3),
            "avg_pnl": round(avg, 4),
            # Size multiplier: outperforming = bet more, underperforming = bet less
            "size_mult": round(0.5 + wr, 2),  # wr=0.5 → 1.0x, wr=0.7 → 1.2x, wr=0.3 → 0.8x
        }
    return results


def analyze_exit_reasons(trades: list) -> dict:
    """What exits are actually profitable?"""
    by_exit = defaultdict(list)
    for t in trades:
        reason = t.get("exit_reason", "unknown")
        # Normalize reason to category
        if "hard_stop" in reason:
            cat = "hard_stop"
        elif "trail" in reason:
            cat = "trailing_stop"
        elif "tp1" in reason or "tp2" in reason or "tp3" in reason:
            cat = "take_profit"
        elif "stale" in reason or "timeout" in reason:
            cat = "stale_exit"
        elif "spread" in reason or "lower_high" in reason or "momentum_stall" in reason:
            cat = "dynamic_exit"
        else:
            cat = "other"
        by_exit[cat].append(t)

    results = {}
    for cat, bucket in by_exit.items():
        if len(bucket) < 3:
            continue
        results[cat] = {
            "n": len(bucket),
            "wr": round(_weighted_wr(bucket), 3),
            "avg_pnl": round(_avg_pnl(bucket), 4),
        }
    return results


def analyze_tvl_buckets(trades: list) -> dict:
    """Does TVL at entry predict performance?"""
    buckets = {
        "micro":  [],   # < 1000 XRP
        "small":  [],   # 1000–5000
        "medium": [],   # 5000–20000
        "large":  [],   # 20000+
    }
    for t in trades:
        tvl = t.get("entry_tvl", 0) or 0
        if tvl < 1000:
            buckets["micro"].append(t)
        elif tvl < 5000:
            buckets["small"].append(t)
        elif tvl < 20000:
            buckets["medium"].append(t)
        else:
            buckets["large"].append(t)

    results = {}
    for bucket, trades_in in buckets.items():
        if len(trades_in) < MIN_TRADES:
            continue
        results[bucket] = {
            "n": len(trades_in),
            "wr": round(_weighted_wr(trades_in), 3),
            "avg_pnl": round(_avg_pnl(trades_in), 4),
        }
    return results


def analyze_smart_wallet_signal(trades: list) -> dict:
    """Do smart wallet signals improve outcomes?"""
    with_sm  = [t for t in trades if t.get("smart_wallets")]
    without  = [t for t in trades if not t.get("smart_wallets")]

    results = {}
    if len(with_sm) >= MIN_TRADES:
        results["with_smart_wallet"] = {
            "n": len(with_sm),
            "wr": round(_weighted_wr(with_sm), 3),
            "avg_pnl": round(_avg_pnl(with_sm), 4),
        }
    if len(without) >= MIN_TRADES:
        results["without_smart_wallet"] = {
            "n": len(without),
            "wr": round(_weighted_wr(without), 3),
            "avg_pnl": round(_avg_pnl(without), 4),
        }
    return results


def compute_regime_bias(trades: list) -> dict:
    """Recent trade WR (last 10) vs baseline — detects hot/cold streaks."""
    recent = sorted(trades, key=lambda t: t.get("ts", 0))[-10:]
    if len(recent) < 5:
        return {"recent_wr": None, "bias": "neutral"}

    recent_wr = _weighted_wr(recent)
    if recent_wr > 0.55:
        bias = "hot"      # increase size slightly
    elif recent_wr < 0.35:
        bias = "cold"     # reduce size, raise bar
    else:
        bias = "neutral"

    return {
        "recent_wr": round(recent_wr, 3),
        "recent_n": len(recent),
        "bias": bias,
        # Size multiplier based on hot/cold performance
        "size_mult": 1.15 if bias == "hot" else (0.80 if bias == "cold" else 1.0),
    }


# ── Main Learning Function ────────────────────────────────────────────────────

def run_learning() -> dict:
    """
    Full learning pass. Returns weights dict and saves to file.
    Called after every trade exit.
    """
    trades = _load_history()
    if len(trades) < MIN_TRADES:
        return {}

    weights = {
        "ts":           time.time(),
        "trade_count":  len(trades),
        "chart_states": analyze_chart_states(trades),
        "score_bands":  analyze_score_bands(trades),
        "exit_reasons": analyze_exit_reasons(trades),
        "tvl_buckets":  analyze_tvl_buckets(trades),
        "smart_wallet": analyze_smart_wallet_signal(trades),
        "regime_bias":  compute_regime_bias(trades),
    }

    # ── Derived Score Adjustments ──────────────────────────────────────────
    # Flat lookup: given chart_state, what score bonus/penalty to apply?
    score_adjustments = {}
    for state, stats in weights["chart_states"].items():
        score_adjustments[state] = stats["score_adj"]
    weights["score_adjustments"] = score_adjustments

    # ── Derived Size Multipliers ───────────────────────────────────────────
    size_multipliers = {}
    # From score band performance
    for band, stats in weights["score_bands"].items():
        size_multipliers[f"band_{band}"] = stats["size_mult"]
    # From hot/cold streak
    size_multipliers["streak"] = weights["regime_bias"]["size_mult"]
    weights["size_multipliers"] = size_multipliers

    # ── Top Insights ──────────────────────────────────────────────────────
    insights = []
    for state, stats in weights["chart_states"].items():
        if stats["wr"] > 0.55:
            insights.append(f"✅ {state}: {stats['wr']:.0%} WR on {stats['n']} trades — boost score +{stats['score_adj']:.0f}")
        elif stats["wr"] < 0.30:
            insights.append(f"⚠️  {state}: {stats['wr']:.0%} WR on {stats['n']} trades — penalty {stats['score_adj']:.0f}")

    bias = weights["regime_bias"]
    if bias.get("bias") == "hot":
        insights.append(f"🔥 Hot streak: {bias['recent_wr']:.0%} WR last {bias['recent_n']} — sizing up {bias['size_mult']}x")
    elif bias.get("bias") == "cold":
        insights.append(f"❄️  Cold streak: {bias['recent_wr']:.0%} WR last {bias['recent_n']} — sizing down {bias['size_mult']}x")

    weights["insights"] = insights

    # Save
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(WEIGHTS_FILE, "w") as f:
        json.dump(weights, f, indent=2)

    logger.info(f"[learn] Updated weights from {len(trades)} trades")
    for insight in insights:
        logger.info(f"[learn] {insight}")

    return weights


def get_score_adjustment(chart_state: str) -> float:
    """Call from scoring.py — returns score bonus/penalty for this chart_state."""
    if not os.path.exists(WEIGHTS_FILE):
        return 0.0
    try:
        with open(WEIGHTS_FILE) as f:
            w = json.load(f)
        # Only apply if fresh (< 24h old)
        if time.time() - w.get("ts", 0) > 86400:
            return 0.0
        return w.get("score_adjustments", {}).get(chart_state, 0.0)
    except Exception:
        return 0.0


def get_size_multiplier(band: str) -> float:
    """Call from scoring.py — returns size multiplier for this score band."""
    if not os.path.exists(WEIGHTS_FILE):
        return 1.0
    try:
        with open(WEIGHTS_FILE) as f:
            w = json.load(f)
        if time.time() - w.get("ts", 0) > 86400:
            return 1.0
        band_mult   = w.get("size_multipliers", {}).get(f"band_{band}", 1.0)
        streak_mult = w.get("size_multipliers", {}).get("streak", 1.0)
        # Compound but cap: never go above 1.3x or below 0.6x
        combined = band_mult * streak_mult
        return round(max(0.6, min(1.3, combined)), 2)
    except Exception:
        return 1.0


def print_report():
    """Human-readable learning report."""
    trades = _load_history()
    print(f"\n{'='*60}")
    print(f"  DKTrenchBot Learning Report — {len(trades)} trades")
    print(f"{'='*60}\n")

    if len(trades) < MIN_TRADES:
        print(f"  Not enough trades ({len(trades)} < {MIN_TRADES} minimum)")
        return

    weights = run_learning()

    print("── Chart State Performance ──────────────────────────────")
    for state, stats in weights["chart_states"].items():
        adj = stats['score_adj']
        sign = "+" if adj > 0 else ""
        print(f"  {state:20} n={stats['n']:3}  WR={stats['wr']:.0%}  avg={stats['avg_pnl']:+.3f} XRP  score_adj={sign}{adj:.0f}")

    print("\n── Score Band Performance ───────────────────────────────")
    for band, stats in weights["score_bands"].items():
        print(f"  {band:12} n={stats['n']:3}  WR={stats['wr']:.0%}  avg={stats['avg_pnl']:+.3f} XRP  size={stats['size_mult']:.2f}x")

    print("\n── TVL Bucket Performance ───────────────────────────────")
    for bucket, stats in weights["tvl_buckets"].items():
        print(f"  {bucket:10} n={stats['n']:3}  WR={stats['wr']:.0%}  avg={stats['avg_pnl']:+.3f} XRP")

    print("\n── Exit Reason Performance ──────────────────────────────")
    for reason, stats in weights["exit_reasons"].items():
        print(f"  {reason:20} n={stats['n']:3}  WR={stats['wr']:.0%}  avg={stats['avg_pnl']:+.3f} XRP")

    print("\n── Smart Wallet Signal ──────────────────────────────────")
    for label, stats in weights["smart_wallet"].items():
        print(f"  {label:30} n={stats['n']:3}  WR={stats['wr']:.0%}  avg={stats['avg_pnl']:+.3f} XRP")

    bias = weights["regime_bias"]
    print(f"\n── Current Streak ───────────────────────────────────────")
    print(f"  Last {bias.get('recent_n','?')} trades: WR={bias.get('recent_wr','?')}  bias={bias.get('bias','?')}  size_mult={bias.get('size_mult','?')}x")

    print(f"\n── Insights ─────────────────────────────────────────────")
    for insight in weights.get("insights", []):
        print(f"  {insight}")
    print()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true", help="Print learning report")
    args = parser.parse_args()

    if args.report:
        print_report()
    else:
        run_learning()
        print("Weights updated.")
