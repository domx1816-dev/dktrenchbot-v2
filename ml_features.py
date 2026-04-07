"""
ml_features.py — Feature extractor and logger for the ML pipeline.

Logs a rich feature vector for every trade:
- log_entry_features(position, bot_state, score_breakdown) at entry
- log_exit_features(position, trade_result) at exit

Storage:
  state/ml_features.jsonl  — append-only raw log (one JSON per line)
  state/ml_dataset.json    — clean list of completed feature dicts for training
"""

import os
import json
import time
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Any

logger = logging.getLogger("ml_features")

STATE_DIR     = os.path.join(os.path.dirname(__file__), "state")
FEATURES_JSONL = os.path.join(STATE_DIR, "ml_features.jsonl")
DATASET_JSON   = os.path.join(STATE_DIR, "ml_dataset.json")

os.makedirs(STATE_DIR, exist_ok=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _atomic_write_json(path: str, data: Any) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def _append_jsonl(path: str, record: dict) -> None:
    """Atomically append one JSON line to a .jsonl file."""
    line = json.dumps(record) + "\n"
    tmp = path + ".tmp_append"
    # Read existing then write all — simple and safe for small files
    existing = ""
    if os.path.exists(path):
        with open(path, "r") as f:
            existing = f.read()
    with open(tmp, "w") as f:
        f.write(existing + line)
    os.replace(tmp, path)


def _load_dataset() -> list:
    if os.path.exists(DATASET_JSON):
        try:
            with open(DATASET_JSON) as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_dataset(dataset: list) -> None:
    _atomic_write_json(DATASET_JSON, dataset)


def _position_key(position: dict) -> str:
    return f"{position.get('symbol','?')}:{position.get('issuer','?')}"


def _get_score_band(score: int) -> str:
    if score >= 50:
        return "elite"
    elif score >= 42:
        return "normal"
    else:
        return "small"


# ── Entry Feature Logging ──────────────────────────────────────────────────────

def log_entry_features(position: dict, bot_state: dict, score_breakdown: dict) -> None:
    """
    Called at trade entry. Saves partial feature vector (no outcome yet).
    position: the position dict recorded in bot_state['positions']
    bot_state: full bot state
    score_breakdown: dict from scoring_mod.compute_score()['breakdown']
    """
    try:
        now_dt = datetime.now(timezone.utc)
        symbol = position.get("symbol", "?")
        score  = position.get("score", 0)

        # Extract breakdown components safely
        bd = score_breakdown or {}
        cluster_boost   = bd.get("wallet_cluster", 0)
        recycler_boost  = bd.get("alpha_recycler", 0)
        tvl_vel_score   = bd.get("liquidity_depth", 0)
        trustline_score = bd.get("issuer_safety", 0)
        momentum_score  = bd.get("chart_state", 0)
        dna_bonus       = bd.get("smart_money", 0)

        # Smart wallets from position
        smart_wallets = position.get("smart_wallets", [])

        # Signals from bot_state
        signals = bot_state.get("signals", {})
        cluster_signal = signals.get("wallet_cluster", {})
        alpha_signal   = signals.get("alpha_recycler", {})

        cluster_active = (
            cluster_boost > 0
            or (cluster_signal.get("token", "").startswith(symbol) and
                time.time() - cluster_signal.get("ts", 0) < 300)
        )
        alpha_active = (
            recycler_boost > 0
            or bool(alpha_signal)
        )

        record = {
            # Identity
            "trade_id":    f"{symbol}_{int(position.get('entry_time', time.time()))}",
            "symbol":      symbol,
            "issuer":      position.get("issuer", ""),
            "entry_time":  position.get("entry_time", time.time()),
            "logged_at":   time.time(),
            "phase":       "entry",

            # Scoring
            "total_score":         score,
            "score_band":          _get_score_band(score),
            "tvl_velocity_score":  float(tvl_vel_score),
            "dna_bonus":           float(dna_bonus),
            "trustline_score":     float(trustline_score),
            "momentum_score":      float(momentum_score),
            "chart_state":         position.get("chart_state", "unknown"),
            "wallet_cluster_boost": int(cluster_boost),
            "alpha_recycler_boost": int(recycler_boost),

            # Market context
            "entry_tvl_xrp":  float(position.get("entry_tvl", 0)),
            "regime":          bot_state.get("regime", "neutral"),
            "hour_utc":        now_dt.hour,
            "day_of_week":     now_dt.weekday(),

            # Token characteristics
            "entry_price":       float(position.get("entry_price", 0)),
            "smart_wallet_count": len(smart_wallets),
            "cluster_active":    bool(cluster_active),
            "alpha_signal_active": bool(alpha_active),

            # Dynamic TP context (best effort at entry)
            "momentum_score_at_entry": float(momentum_score),
            "momentum_direction":       "stable",  # updated by dynamic_tp if available

            # Outcome placeholders — filled at exit
            "pnl_xrp":      None,
            "pnl_pct":      None,
            "exit_reason":  None,
            "hold_time_min": None,
            "won":          None,
            "multiple":     None,
        }

        _append_jsonl(FEATURES_JSONL, record)
        logger.debug(f"[ml_features] entry logged: {symbol} score={score}")

    except Exception as e:
        logger.debug(f"[ml_features] log_entry_features error: {e}")


# ── Exit Feature Logging ───────────────────────────────────────────────────────

def log_exit_features(position: dict, trade_result: dict) -> None:
    """
    Called at trade exit. Completes the feature vector with outcome data.
    Appends to JSONL and updates the clean dataset for training.

    position: the position dict (as stored in bot_state['positions'])
    trade_result: the trade dict written to trade_history
    """
    try:
        symbol     = trade_result.get("symbol", position.get("symbol", "?"))
        entry_time = trade_result.get("entry_time", position.get("entry_time", 0))
        exit_time  = trade_result.get("exit_time", time.time())
        trade_id   = f"{symbol}_{int(entry_time)}"

        hold_min = (exit_time - entry_time) / 60.0 if entry_time else 0.0
        pnl_xrp  = float(trade_result.get("pnl_xrp", 0))
        pnl_pct  = float(trade_result.get("pnl_pct", 0))
        entry_p  = float(trade_result.get("entry_price", position.get("entry_price", 0)))
        exit_p   = float(trade_result.get("exit_price", 0))
        multiple = (exit_p / entry_p) if entry_p > 0 else 1.0

        outcome = {
            "pnl_xrp":      pnl_xrp,
            "pnl_pct":      pnl_pct,
            "exit_reason":  trade_result.get("exit_reason", "unknown"),
            "hold_time_min": hold_min,
            "won":          pnl_xrp > 0,
            "multiple":     multiple,
        }

        # Append exit record to JSONL
        exit_record = {"trade_id": trade_id, "phase": "exit", "logged_at": time.time()}
        exit_record.update(outcome)
        _append_jsonl(FEATURES_JSONL, exit_record)

        # Build complete feature dict for the dataset
        # First, try to find entry record in JSONL
        entry_record = _find_entry_record(trade_id)

        if entry_record:
            complete = dict(entry_record)
            complete.update(outcome)
            complete["phase"] = "complete"
        else:
            # Reconstruct from trade_result (best effort for backfilled trades)
            now_dt = datetime.fromtimestamp(entry_time, tz=timezone.utc)
            score  = int(trade_result.get("score", 0))
            complete = {
                "trade_id":    trade_id,
                "symbol":      symbol,
                "issuer":      trade_result.get("issuer", ""),
                "entry_time":  entry_time,
                "logged_at":   time.time(),
                "phase":       "complete",
                "total_score": score,
                "score_band":  _get_score_band(score),
                "tvl_velocity_score": 0.0,
                "dna_bonus":   0.0,
                "trustline_score": 0.0,
                "momentum_score": 0.0,
                "chart_state": trade_result.get("chart_state", "unknown"),
                "wallet_cluster_boost": 0,
                "alpha_recycler_boost": 0,
                "entry_tvl_xrp": float(trade_result.get("entry_tvl", 0)),
                "regime":      "neutral",
                "hour_utc":    now_dt.hour,
                "day_of_week": now_dt.weekday(),
                "entry_price": float(trade_result.get("entry_price", 0)),
                "smart_wallet_count": len(trade_result.get("smart_wallets", [])),
                "cluster_active":      False,
                "alpha_signal_active": False,
                "momentum_score_at_entry": 0.0,
                "momentum_direction":   "stable",
            }
            complete.update(outcome)

        # Append to dataset
        dataset = _load_dataset()
        # Remove any existing entry with same trade_id (idempotent)
        dataset = [d for d in dataset if d.get("trade_id") != trade_id]
        dataset.append(complete)
        _save_dataset(dataset)

        logger.debug(f"[ml_features] exit logged: {symbol} won={complete['won']} pnl={pnl_xrp:+.4f} XRP")

    except Exception as e:
        logger.debug(f"[ml_features] log_exit_features error: {e}")


def _find_entry_record(trade_id: str) -> Optional[dict]:
    """Search JSONL for the entry record matching trade_id."""
    if not os.path.exists(FEATURES_JSONL):
        return None
    try:
        result = None
        with open(FEATURES_JSONL) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if rec.get("trade_id") == trade_id and rec.get("phase") == "entry":
                        result = rec  # keep last entry record if duplicates
                except Exception:
                    continue
        return result
    except Exception:
        return None


# ── Backfill Existing Trades ───────────────────────────────────────────────────

def backfill_from_state(state_path: str = None) -> int:
    """
    Backfill feature records for existing trades in state.json.
    Best-effort: reconstructs features from available trade_history data.
    Returns number of trades backfilled.
    """
    if state_path is None:
        state_path = os.path.join(STATE_DIR, "state.json")
    if not os.path.exists(state_path):
        logger.warning(f"[ml_features] state.json not found at {state_path}")
        return 0

    try:
        with open(state_path) as f:
            state = json.load(f)
    except Exception as e:
        logger.warning(f"[ml_features] Could not load state.json: {e}")
        return 0

    trade_history = state.get("trade_history", [])
    if not trade_history:
        logger.info("[ml_features] No trade history to backfill")
        return 0

    dataset = _load_dataset()
    existing_ids = {d.get("trade_id") for d in dataset}

    backfilled = 0
    for trade in trade_history:
        symbol     = trade.get("symbol", "?")
        entry_time = trade.get("entry_time", 0)
        trade_id   = f"{symbol}_{int(entry_time)}"

        if trade_id in existing_ids:
            continue  # already have it

        # Reconstruct entry datetime
        try:
            now_dt = datetime.fromtimestamp(entry_time, tz=timezone.utc)
        except Exception:
            now_dt = datetime.now(timezone.utc)

        score     = int(trade.get("score", 0))
        entry_p   = float(trade.get("entry_price", 0))
        exit_p    = float(trade.get("exit_price", 0))
        pnl_xrp   = float(trade.get("pnl_xrp", 0))
        pnl_pct   = float(trade.get("pnl_pct", 0))
        exit_time = trade.get("exit_time", entry_time)
        hold_min  = (exit_time - entry_time) / 60.0 if entry_time and exit_time else 0.0
        multiple  = (exit_p / entry_p) if entry_p > 0 else 1.0

        record = {
            "trade_id":    trade_id,
            "symbol":      symbol,
            "issuer":      trade.get("issuer", ""),
            "entry_time":  entry_time,
            "logged_at":   time.time(),
            "phase":       "complete",
            "backfilled":  True,

            # Scoring (reconstructed)
            "total_score":         score,
            "score_band":          _get_score_band(score),
            "tvl_velocity_score":  0.0,
            "dna_bonus":           0.0,
            "trustline_score":     0.0,
            "momentum_score":      0.0,
            "chart_state":         trade.get("chart_state", "unknown"),
            "wallet_cluster_boost": 0,
            "alpha_recycler_boost": 0,

            # Market context
            "entry_tvl_xrp":  float(trade.get("entry_tvl", 0)),
            "regime":          "neutral",  # unknown at backfill
            "hour_utc":        now_dt.hour,
            "day_of_week":     now_dt.weekday(),

            # Token
            "entry_price":         entry_p,
            "smart_wallet_count":  len(trade.get("smart_wallets", [])),
            "cluster_active":      False,
            "alpha_signal_active": False,

            # Dynamic TP
            "momentum_score_at_entry": 0.0,
            "momentum_direction":      "stable",

            # Outcome
            "pnl_xrp":      pnl_xrp,
            "pnl_pct":      pnl_pct,
            "exit_reason":  trade.get("exit_reason", "unknown"),
            "hold_time_min": hold_min,
            "won":          pnl_xrp > 0,
            "multiple":     multiple,
        }

        # Append to JSONL log
        _append_jsonl(FEATURES_JSONL, record)
        dataset.append(record)
        existing_ids.add(trade_id)
        backfilled += 1
        logger.info(f"[ml_features] backfilled: {symbol} won={record['won']} pnl={pnl_xrp:+.4f} XRP")

    if backfilled > 0:
        _save_dataset(dataset)

    logger.info(f"[ml_features] Backfill complete: {backfilled} trades added, {len(dataset)} total in dataset")
    return backfilled


# ── Dataset Utilities ──────────────────────────────────────────────────────────

def get_complete_dataset() -> list:
    """Return all complete feature records (have outcome data)."""
    dataset = _load_dataset()
    return [d for d in dataset if d.get("won") is not None]


def get_dataset_count() -> int:
    return len(get_complete_dataset())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    n = backfill_from_state()
    print(f"Backfilled {n} trades. Dataset now has {get_dataset_count()} complete records.")
