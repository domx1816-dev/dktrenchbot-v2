"""
ml_model.py — ML model trainer and predictor.

Phases:
  logging   (< 50 trades)  — silent data collection only
  logistic  (50-199 trades) — logistic regression
  xgboost   (200+ trades)   — XGBoost or Random Forest fallback

Key functions:
  predict_win_probability(features) → float 0.0-1.0
  get_ml_score_adjustment(features) → int (score pts)
  get_ml_size_multiplier(features)  → float (size mult)
  maybe_retrain()                   — retrains if needed
"""

import os
import json
import time
import pickle
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("ml_model")

STATE_DIR   = os.path.join(os.path.dirname(__file__), "state")
MODEL_PATH  = os.path.join(STATE_DIR, "ml_model.pkl")
SCALER_PATH = os.path.join(STATE_DIR, "ml_scaler.pkl")
META_PATH   = os.path.join(STATE_DIR, "ml_meta.json")

os.makedirs(STATE_DIR, exist_ok=True)

# Features used for prediction
FEATURE_COLS = [
    "total_score",
    "entry_tvl_xrp",
    "hour_utc",
    "wallet_cluster_boost",
    "alpha_recycler_boost",
    "smart_wallet_count",
    "cluster_active",
    "alpha_signal_active",
    "momentum_score_at_entry",
]

# Thresholds
RETRAIN_EVERY_HOURS  = 24
RETRAIN_NEW_TRADES   = 20
MIN_LOGGING_TRADES   = 50
MIN_XGBOOST_TRADES   = 200

# ── Phase Detection ────────────────────────────────────────────────────────────

def get_phase(n_trades: int) -> str:
    if n_trades < MIN_LOGGING_TRADES:
        return "logging"
    elif n_trades < MIN_XGBOOST_TRADES:
        return "logistic"
    else:
        return "xgboost"


# ── Model Persistence ──────────────────────────────────────────────────────────

def _save_model(model: Any, scaler: Any, meta: dict) -> None:
    tmp_m = MODEL_PATH  + ".tmp"
    tmp_s = SCALER_PATH + ".tmp"
    tmp_t = META_PATH   + ".tmp"
    with open(tmp_m, "wb") as f:
        pickle.dump(model, f)
    os.replace(tmp_m, MODEL_PATH)
    with open(tmp_s, "wb") as f:
        pickle.dump(scaler, f)
    os.replace(tmp_s, SCALER_PATH)
    with open(tmp_t, "w") as f:
        json.dump(meta, f, indent=2)
    os.replace(tmp_t, META_PATH)


def _load_model():
    """Returns (model, scaler, meta) or (None, None, {}) on failure."""
    try:
        if not os.path.exists(MODEL_PATH) or not os.path.exists(SCALER_PATH):
            return None, None, {}
        with open(MODEL_PATH, "rb") as f:
            model = pickle.load(f)
        with open(SCALER_PATH, "rb") as f:
            scaler = pickle.load(f)
        meta = {}
        if os.path.exists(META_PATH):
            with open(META_PATH) as f:
                meta = json.load(f)
        return model, scaler, meta
    except Exception as e:
        logger.debug(f"[ml_model] load_model error: {e}")
        return None, None, {}


# ── Feature Preparation ────────────────────────────────────────────────────────

def _prepare_features(records: list) -> tuple:
    """Convert list of feature dicts → (X numpy array, y numpy array)."""
    import numpy as np
    X_rows, y_rows = [], []
    for r in records:
        if r.get("won") is None:
            continue
        row = []
        for col in FEATURE_COLS:
            val = r.get(col, 0)
            if isinstance(val, bool):
                val = int(val)
            try:
                val = float(val)
            except (TypeError, ValueError):
                val = 0.0
            row.append(val)
        X_rows.append(row)
        y_rows.append(1 if r.get("won") else 0)
    if not X_rows:
        return None, None
    return np.array(X_rows, dtype=float), np.array(y_rows, dtype=int)


def _feature_dict_to_row(features: dict) -> list:
    row = []
    for col in FEATURE_COLS:
        val = features.get(col, 0)
        if isinstance(val, bool):
            val = int(val)
        try:
            val = float(val)
        except (TypeError, ValueError):
            val = 0.0
        row.append(val)
    return row


# ── Training ───────────────────────────────────────────────────────────────────

def train(dataset: list) -> Optional[dict]:
    """
    Train model on complete dataset. Returns meta dict or None on failure.
    """
    try:
        import numpy as np
        from sklearn.preprocessing import StandardScaler

        complete = [d for d in dataset if d.get("won") is not None]
        n = len(complete)
        phase = get_phase(n)

        if phase == "logging":
            logger.debug(f"[ml_model] logging phase ({n}/{MIN_LOGGING_TRADES}) — no training")
            return None

        X, y = _prepare_features(complete)
        if X is None or len(X) < MIN_LOGGING_TRADES:
            return None

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # Choose model
        if phase == "xgboost":
            try:
                from xgboost import XGBClassifier
                model = XGBClassifier(
                    n_estimators=100,
                    max_depth=4,
                    learning_rate=0.1,
                    eval_metric="logloss",
                    verbosity=0,
                )
                model_type = "xgboost"
            except ImportError:
                from sklearn.ensemble import RandomForestClassifier
                model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
                model_type = "random_forest"
        else:
            from sklearn.linear_model import LogisticRegression
            model = LogisticRegression(max_iter=1000, C=1.0, random_state=42)
            model_type = "logistic"

        model.fit(X_scaled, y)

        # Accuracy (in-sample — small dataset)
        preds = model.predict(X_scaled)
        accuracy = float(np.mean(preds == y))

        # Feature importance
        feature_importance = {}
        try:
            if hasattr(model, "coef_"):
                import numpy as np
                coefs = np.abs(model.coef_[0])
                coefs = coefs / coefs.sum() if coefs.sum() > 0 else coefs
                feature_importance = {FEATURE_COLS[i]: float(coefs[i]) for i in range(len(FEATURE_COLS))}
            elif hasattr(model, "feature_importances_"):
                fi = model.feature_importances_
                feature_importance = {FEATURE_COLS[i]: float(fi[i]) for i in range(len(FEATURE_COLS))}
        except Exception:
            pass

        meta = {
            "phase":              phase,
            "model_type":         model_type,
            "n_trades":           n,
            "trained_at":         time.time(),
            "accuracy":           accuracy,
            "feature_importance": feature_importance,
        }

        _save_model(model, scaler, meta)
        logger.info(f"[ml_model] trained {model_type}: n={n} accuracy={accuracy:.2%} phase={phase}")
        return meta

    except Exception as e:
        logger.debug(f"[ml_model] train error: {e}")
        return None


# ── Retrain Scheduler ──────────────────────────────────────────────────────────

def maybe_retrain() -> bool:
    """
    Retrain if:
    - 24h have passed since last training, OR
    - 20 new trades since last training
    Returns True if retrained.
    """
    try:
        import ml_features as _mf
        dataset = _mf.get_complete_dataset()
        n = len(dataset)
        phase = get_phase(n)

        if phase == "logging":
            return False  # silent

        _, _, meta = _load_model()
        last_trained_at = meta.get("trained_at", 0)
        last_n          = meta.get("n_trades", 0)

        hours_since = (time.time() - last_trained_at) / 3600
        new_trades  = n - last_n

        should_retrain = (
            hours_since >= RETRAIN_EVERY_HOURS
            or new_trades >= RETRAIN_NEW_TRADES
            or (meta == {} and n >= MIN_LOGGING_TRADES)
        )

        if should_retrain:
            logger.info(f"[ml_model] Retraining: n={n} hours_since={hours_since:.1f}h new_trades={new_trades}")
            train(dataset)
            return True

        return False
    except Exception as e:
        logger.debug(f"[ml_model] maybe_retrain error: {e}")
        return False


# ── Prediction ─────────────────────────────────────────────────────────────────

def predict_win_probability(features: dict) -> float:
    """
    Returns win probability 0.0-1.0.
    Returns 0.5 (neutral) if in logging phase or model not ready.
    """
    try:
        import ml_features as _mf
        n = _mf.get_dataset_count()
        phase = get_phase(n)

        if phase == "logging":
            return 0.5  # silent — no predictions yet

        model, scaler, meta = _load_model()
        if model is None or scaler is None:
            return 0.5

        import numpy as np
        row = _feature_dict_to_row(features)
        X = np.array([row], dtype=float)
        X_scaled = scaler.transform(X)

        proba = model.predict_proba(X_scaled)[0]
        # proba[1] = probability of class 1 (win)
        return float(proba[1])

    except Exception as e:
        logger.debug(f"[ml_model] predict error: {e}")
        return 0.5


# ── Score Adjustment ───────────────────────────────────────────────────────────

def get_ml_score_adjustment(features: dict) -> int:
    """
    Convert win probability to score adjustment.
    Returns 0 if in logging phase.
    """
    try:
        import ml_features as _mf
        n = _mf.get_dataset_count()
        if get_phase(n) == "logging":
            return 0

        prob = predict_win_probability(features)

        if prob >= 0.75:
            return 20
        elif prob >= 0.65:
            return 10
        elif prob >= 0.55:
            return 5
        elif prob <= 0.25:
            return -25
        elif prob <= 0.35:
            return -15
        else:
            return 0  # 0.35-0.55 neutral band

    except Exception as e:
        logger.debug(f"[ml_model] score_adj error: {e}")
        return 0


# ── Size Multiplier ────────────────────────────────────────────────────────────

def get_ml_size_multiplier(features: dict) -> float:
    """
    High confidence = bigger position, low confidence = smaller.
    Returns 1.0 if in logging phase.
    """
    try:
        import ml_features as _mf
        n = _mf.get_dataset_count()
        if get_phase(n) == "logging":
            return 1.0

        prob = predict_win_probability(features)

        if prob >= 0.75:
            return 1.3
        elif prob >= 0.65:
            return 1.15
        elif prob <= 0.25:
            return 0.5
        elif prob <= 0.35:
            return 0.7
        else:
            return 1.0  # 0.35-0.65 no change

    except Exception as e:
        logger.debug(f"[ml_model] size_mult error: {e}")
        return 1.0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import ml_features as mf
    dataset = mf.get_complete_dataset()
    print(f"Dataset: {len(dataset)} complete records")
    print(f"Phase: {get_phase(len(dataset))}")
    result = train(dataset)
    if result:
        print(f"Trained: {result}")
    else:
        print("No training (logging phase or insufficient data)")
