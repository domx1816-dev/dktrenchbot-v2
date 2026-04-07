"""
data_layer.py — Unified data access layer for DKTrenchBot v2.
Single source of truth replacing scattered state/*.json reads.
Wraps state.json with typed accessors and atomic writes.
"""

import json
import os
import time
from typing import Dict, List, Optional, Any

from config import STATE_DIR


class DataLayer:
    """
    Unified data layer. All reads/writes go through this class.
    Keeps one in-memory cache; flushes atomically via .tmp → os.replace.
    """

    def __init__(self, state_dir: str = STATE_DIR):
        self.state_dir = state_dir
        self._state_file = os.path.join(state_dir, "state.json")
        self._wallet_file = os.path.join(state_dir, "wallet_scores.json")
        os.makedirs(state_dir, exist_ok=True)
        self._cache: Dict = self._load_raw()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _load_raw(self) -> Dict:
        if os.path.exists(self._state_file):
            try:
                with open(self._state_file) as f:
                    data = json.load(f)
                # ensure all required keys exist
                for k, v in self._defaults().items():
                    if k not in data:
                        data[k] = v
                return data
            except Exception:
                pass
        return self._defaults()

    @staticmethod
    def _defaults() -> Dict:
        return {
            "positions": {},
            "trade_history": [],
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
            "score_overrides": {},
            "last_reconcile": 0,
            "last_improve": 0,
            "last_hygiene": 0,
        }

    def _save(self) -> None:
        """Atomic write: .tmp → os.replace."""
        self._cache["performance"]["last_updated"] = time.time()
        tmp = self._state_file + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self._cache, f, indent=2)
        os.replace(tmp, self._state_file)

    def reload(self) -> None:
        """Force reload from disk (e.g. after external write)."""
        self._cache = self._load_raw()

    # ── Trade management ──────────────────────────────────────────────────────

    def record_trade(self, trade: Dict) -> None:
        history = self._cache.setdefault("trade_history", [])
        history.append(trade)
        if len(history) > 500:
            self._cache["trade_history"] = history[-500:]
        self._update_performance(trade)
        self._save()

    def get_all_trades(self) -> List[Dict]:
        return list(self._cache.get("trade_history", []))

    def get_wins(self) -> List[Dict]:
        return [t for t in self.get_all_trades() if float(t.get("pnl_xrp", 0) or 0) > 0.1]

    def get_losses(self) -> List[Dict]:
        return [t for t in self.get_all_trades() if float(t.get("pnl_xrp", 0) or 0) < -0.1]

    def _update_performance(self, trade: Dict) -> None:
        perf = self._cache.setdefault("performance", self._defaults()["performance"])
        pnl_xrp = float(trade.get("pnl_xrp", 0) or 0)
        pnl_pct = float(trade.get("pnl_pct", 0) or 0)
        exit_reason = trade.get("exit_reason", "")

        if abs(pnl_xrp) < 0.1:
            return  # dust trade

        perf["total_trades"] = perf.get("total_trades", 0) + 1
        perf["total_pnl_xrp"] = perf.get("total_pnl_xrp", 0.0) + pnl_xrp

        forced_exits = {"orphan_timeout_1hr", "orphan_profit_take", "dead_token"}
        if pnl_xrp > 0.1:
            perf["wins"] = perf.get("wins", 0) + 1
            perf["consecutive_losses"] = 0
            if pnl_pct > 0 and pnl_pct > perf.get("best_trade_pct", 0):
                perf["best_trade_pct"] = pnl_pct
        elif pnl_xrp < -0.1:
            perf["losses"] = perf.get("losses", 0) + 1
            if exit_reason not in forced_exits:
                perf["consecutive_losses"] = perf.get("consecutive_losses", 0) + 1
            else:
                perf["consecutive_losses"] = 0
            if pnl_pct < 0 and pnl_pct < perf.get("worst_trade_pct", 0):
                perf["worst_trade_pct"] = pnl_pct
        else:
            perf["consecutive_losses"] = 0

        # rolling win rate
        recent = [t for t in self._cache.get("trade_history", [])[-30:]
                  if abs(float(t.get("pnl_xrp", 0) or 0)) >= 0.1]
        if len(recent) >= 5:
            wins = sum(1 for t in recent if float(t.get("pnl_xrp", 0) or 0) > 0.1)
            perf["win_rate"] = wins / len(recent)
        else:
            total = perf.get("wins", 0) + perf.get("losses", 0)
            perf["win_rate"] = perf["wins"] / total if total > 0 else 0.5

    # ── Position management ───────────────────────────────────────────────────

    def add_position(self, key: str, position: Dict) -> None:
        self._cache.setdefault("positions", {})[key] = position
        self._save()

    def remove_position(self, key: str) -> Optional[Dict]:
        pos = self._cache.get("positions", {}).pop(key, None)
        if pos is not None:
            self._save()
        return pos

    def get_positions(self) -> Dict[str, Dict]:
        return dict(self._cache.get("positions", {}))

    def update_position(self, key: str, updates: Dict) -> None:
        positions = self._cache.setdefault("positions", {})
        if key in positions:
            positions[key].update(updates)
            self._save()

    # ── Performance metrics ───────────────────────────────────────────────────

    def get_metrics(self) -> Dict:
        trades = self.get_all_trades()
        wins = self.get_wins()
        losses = self.get_losses()
        perf = self._cache.get("performance", {})

        # best chart state
        chart_state_stats: Dict[str, Dict] = {}
        for t in trades:
            cs = t.get("chart_state", "unknown")
            if cs not in chart_state_stats:
                chart_state_stats[cs] = {"wins": 0, "total": 0}
            chart_state_stats[cs]["total"] += 1
            if float(t.get("pnl_xrp", 0) or 0) > 0.1:
                chart_state_stats[cs]["wins"] += 1
        best_chart_state = max(
            chart_state_stats,
            key=lambda cs: chart_state_stats[cs]["wins"] / max(chart_state_stats[cs]["total"], 1),
            default="unknown",
        )

        # best score band
        band_stats: Dict[str, Dict] = {}
        for t in trades:
            band = t.get("score_band", "unknown")
            if band not in band_stats:
                band_stats[band] = {"wins": 0, "total": 0}
            band_stats[band]["total"] += 1
            if float(t.get("pnl_xrp", 0) or 0) > 0.1:
                band_stats[band]["wins"] += 1
        best_score_band = max(
            band_stats,
            key=lambda b: band_stats[b]["wins"] / max(band_stats[b]["total"], 1),
            default="unknown",
        )

        # best hour
        import datetime
        hour_stats: Dict[int, Dict] = {}
        for t in trades:
            et = t.get("entry_time", 0)
            if et:
                h = datetime.datetime.utcfromtimestamp(et).hour
                if h not in hour_stats:
                    hour_stats[h] = {"wins": 0, "total": 0}
                hour_stats[h]["total"] += 1
                if float(t.get("pnl_xrp", 0) or 0) > 0.1:
                    hour_stats[h]["wins"] += 1
        best_hour_utc = max(
            hour_stats,
            key=lambda h: hour_stats[h]["wins"] / max(hour_stats[h]["total"], 1),
            default=-1,
        )

        # streak
        streak = 0
        for t in reversed(trades):
            pnl = float(t.get("pnl_xrp", 0) or 0)
            if abs(pnl) < 0.1:
                continue
            if pnl > 0:
                if streak >= 0:
                    streak += 1
                else:
                    break
            else:
                if streak <= 0:
                    streak -= 1
                else:
                    break

        avg_win = (sum(float(t.get("pnl_xrp", 0) or 0) for t in wins) / len(wins)) if wins else 0.0
        avg_loss = (sum(float(t.get("pnl_xrp", 0) or 0) for t in losses) / len(losses)) if losses else 0.0

        return {
            "win_rate": perf.get("win_rate", 0.0),
            "avg_win_xrp": avg_win,
            "avg_loss_xrp": avg_loss,
            "total_pnl": perf.get("total_pnl_xrp", 0.0),
            "best_chart_state": best_chart_state,
            "best_score_band": best_score_band,
            "best_hour_utc": best_hour_utc,
            "streak": streak,
            "total_trades": perf.get("total_trades", 0),
            "wins": perf.get("wins", 0),
            "losses": perf.get("losses", 0),
            "consecutive_losses": perf.get("consecutive_losses", 0),
        }

    # ── Wallet intelligence ───────────────────────────────────────────────────

    def _load_wallet_scores(self) -> Dict:
        if os.path.exists(self._wallet_file):
            try:
                with open(self._wallet_file) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_wallet_scores(self, scores: Dict) -> None:
        tmp = self._wallet_file + ".tmp"
        with open(tmp, "w") as f:
            json.dump(scores, f, indent=2)
        os.replace(tmp, self._wallet_file)

    def update_wallet_score(self, wallet: str, result: Dict) -> None:
        """Update tracked wallet performance (win/loss/pnl)."""
        scores = self._load_wallet_scores()
        entry = scores.get(wallet, {"wins": 0, "losses": 0, "total_pnl": 0.0, "trades": []})
        pnl = float(result.get("pnl_xrp", 0) or 0)
        entry["total_pnl"] = entry.get("total_pnl", 0.0) + pnl
        if pnl > 0:
            entry["wins"] = entry.get("wins", 0) + 1
        elif pnl < 0:
            entry["losses"] = entry.get("losses", 0) + 1
        entry.setdefault("trades", []).append({
            "ts": time.time(),
            "symbol": result.get("symbol"),
            "pnl_xrp": pnl,
        })
        entry["trades"] = entry["trades"][-50:]  # keep last 50
        scores[wallet] = entry
        self._save_wallet_scores(scores)

    def get_top_wallets(self, n: int = 10) -> List[Dict]:
        scores = self._load_wallet_scores()
        ranked = []
        for wallet, data in scores.items():
            total = data.get("wins", 0) + data.get("losses", 0)
            wr = data.get("wins", 0) / total if total > 0 else 0.0
            ranked.append({
                "wallet": wallet,
                "win_rate": wr,
                "total_pnl": data.get("total_pnl", 0.0),
                "total_trades": total,
            })
        return sorted(ranked, key=lambda x: x["total_pnl"], reverse=True)[:n]

    # ── Raw state access (for backward compat with state.py) ─────────────────

    def get_raw(self) -> Dict:
        """Return underlying state dict (for modules that need the whole dict)."""
        return self._cache

    def set_key(self, key: str, value: Any) -> None:
        self._cache[key] = value
        self._save()

    def get_key(self, key: str, default: Any = None) -> Any:
        return self._cache.get(key, default)


# Module-level singleton for easy import
_instance: Optional[DataLayer] = None


def get_data_layer() -> DataLayer:
    global _instance
    if _instance is None:
        _instance = DataLayer()
    return _instance


if __name__ == "__main__":
    dl = get_data_layer()
    metrics = dl.get_metrics()
    print("=== DataLayer Metrics ===")
    for k, v in metrics.items():
        print(f"  {k}: {v}")
    print(f"\nPositions: {len(dl.get_positions())}")
    print(f"Trades: {len(dl.get_all_trades())}")
    print(f"Top wallets: {dl.get_top_wallets(3)}")
