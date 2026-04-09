"""
ml_trainer.py — Train XGBoost model on completed trades.
Auto-trains when 50+ trades available. Saves model to state/ml_model.json.

Features used:
- score: token score (0-100)
- tvl_xrp: AMM TVL in XRP
- strategy: burst/pre_breakout/micro_scalp/etc (one-hot encoded)
- momentum_score: price momentum indicator
- ts_burst_1h: TrustSet velocity (1hr window)
- concentration_pct: top holder concentration %

Target: pnl_xrp > 0 (binary classification: win/loss)
"""

import json
import os
import logging
from typing import Dict, List, Optional

logger = logging.getLogger("ml_trainer")

STATE_DIR = os.path.join(os.path.dirname(__file__), "state")
MODEL_FILE = os.path.join(STATE_DIR, "ml_model.json")
EXEC_LOG_FILE = os.path.join(STATE_DIR, "execution_log.json")

MIN_TRADES_FOR_TRAINING = 50


def load_completed_trades() -> List[Dict]:
    """Load completed trades from execution log."""
    if not os.path.exists(EXEC_LOG_FILE):
        return []
    try:
        with open(EXEC_LOG_FILE) as f:
            data = json.load(f)
        trades = data.get("trades", [])
        # Only use completed trades (have exit info)
        completed = [t for t in trades if t.get("exit_price") is not None and t.get("pnl_xrp") is not None]
        return completed
    except Exception as e:
        logger.error(f"Failed to load trades: {e}")
        return []


def extract_features(trade: Dict) -> Optional[Dict]:
    """Extract ML features from a completed trade."""
    try:
        features = {
            "score": float(trade.get("entry_score", trade.get("score", 50))),
            "tvl_xrp": float(trade.get("entry_tvl", trade.get("tvl_xrp", 0))),
            "momentum": float(trade.get("momentum_score", 0)),
            "ts_burst_1h": int(trade.get("ts_burst_1h", 0)),
            "concentration_pct": float(trade.get("concentration_pct", 0)),
            "strategy_burst": 1 if trade.get("strategy") == "burst" else 0,
            "strategy_pre_breakout": 1 if trade.get("strategy") == "pre_breakout" else 0,
            "strategy_micro_scalp": 1 if trade.get("strategy") == "micro_scalp" else 0,
            "strategy_clob_launch": 1 if trade.get("strategy") == "clob_launch" else 0,
            "strategy_trend": 1 if trade.get("strategy") == "trend" else 0,
        }
        return features
    except Exception as e:
        logger.debug(f"Feature extraction failed: {e}")
        return None


def train_simple_model(trades: List[Dict]) -> Optional[Dict]:
    """
    Train a simple weighted logistic regression-like model.
    Since we can't use sklearn/xgboost without pip install,
    we use a simple feature-weighted scoring model.
    
    Returns model dict with feature weights learned from data.
    """
    if len(trades) < MIN_TRADES_FOR_TRAINING:
        logger.info(f"Not enough trades for training: {len(trades)} < {MIN_TRADES_FOR_TRAINING}")
        return None
    
    # Extract features and labels
    X = []
    y = []
    for trade in trades:
        features = extract_features(trade)
        if features:
            X.append(features)
            y.append(1 if trade.get("pnl_xrp", 0) > 0 else 0)
    
    if len(X) < MIN_TRADES_FOR_TRAINING:
        logger.info(f"Not enough valid features: {len(X)} < {MIN_TRADES_FOR_TRAINING}")
        return None
    
    # Simple weight learning: correlate each feature with outcome
    feature_names = list(X[0].keys())
    weights = {}
    
    for fname in feature_names:
        # Calculate correlation between feature and outcome
        wins_with_high = sum(1 for x, label in zip(X, y) if x[fname] > 0.5 and label == 1)
        total_with_high = sum(1 for x in X if x[fname] > 0.5)
        wins_with_low = sum(1 for x, label in zip(X, y) if x[fname] <= 0.5 and label == 1)
        total_with_low = sum(1 for x in X if x[fname] <= 0.5)
        
        # Weight = difference in win rates
        wr_high = wins_with_high / max(total_with_high, 1)
        wr_low = wins_with_low / max(total_with_low, 1)
        weights[fname] = wr_high - wr_low
    
    # Calculate base win rate
    base_wr = sum(y) / len(y)
    
    model = {
        "feature_weights": weights,
        "base_win_rate": base_wr,
        "num_trades": len(trades),
        "trained_at": __import__('time').time(),
        "feature_names": feature_names,
    }
    
    logger.info(f"Model trained on {len(trades)} trades, base WR: {base_wr:.1%}")
    return model


def predict_win_probability(model: Dict, features: Dict) -> float:
    """Predict win probability for a candidate using trained model."""
    if not model or not features:
        return 0.5  # default uncertainty
    
    base_wr = model.get("base_win_rate", 0.5)
    weights = model.get("feature_weights", {})
    
    # Start with base win rate
    prob = base_wr
    
    # Adjust based on feature weights
    for fname, weight in weights.items():
        if fname in features:
            prob += weight * features[fname] * 0.1  # scale factor
    
    # Clamp to [0.1, 0.95]
    return max(0.1, min(0.95, prob))


def save_model(model: Dict) -> bool:
    """Save model to disk."""
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = MODEL_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(model, f, indent=2)
        os.replace(tmp, MODEL_FILE)
        logger.info(f"Model saved to {MODEL_FILE}")
        return True
    except Exception as e:
        logger.error(f"Failed to save model: {e}")
        return False


def load_model() -> Optional[Dict]:
    """Load model from disk."""
    if not os.path.exists(MODEL_FILE):
        return None
    try:
        with open(MODEL_FILE) as f:
            return json.load(f)
    except Exception:
        return None


def check_and_train() -> Optional[Dict]:
    """Check if we have enough trades, train if so."""
    trades = load_completed_trades()
    logger.info(f"Completed trades available: {len(trades)}")
    
    if len(trades) < MIN_TRADES_FOR_TRAINING:
        logger.info(f"Need {MIN_TRADES_FOR_TRAINING - len(trades)} more trades before training")
        return None
    
    model = train_simple_model(trades)
    if model:
        save_model(model)
    
    return model


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    model = check_and_train()
    if model:
        print(f"Model trained successfully!")
        print(f"  Trades: {model['num_trades']}")
        print(f"  Base WR: {model['base_win_rate']:.1%}")
        print(f"  Top features: {sorted(model['feature_weights'].items(), key=lambda x: abs(x[1]), reverse=True)[:5]}")
    else:
        print("No model trained (insufficient data)")
