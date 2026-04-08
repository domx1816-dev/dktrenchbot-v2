"""
dynamic_tp.py — Dynamic Take-Profit Module (3-Layer Exit System)

Replaces/supplements current TP logic with:
  Layer 1: Profit Lock (non-negotiable scale-out at 2x, 3x, 5x)
  Layer 2: Momentum Tracker (adjust exit timing based on momentum)
  Layer 3: Danger Detection (emergency exits on smart wallet sells, liquidity drops, etc.)
  Trailing Stop: Enhanced 30% drawdown from peak

Integration:
  - Exports should_exit(position, bot_state) → {'action': 'hold'|'exit'|'emergency', 'pct': float, 'reason': str}
  - bot.py calls this in position management loop AFTER scoring, BEFORE execution
  - Existing TP system is FALLBACK — if dynamic_tp returns 'hold', existing TPs still apply
  - Config flag: DYNAMIC_TP_ENABLED = True
"""

import json
import os
import time
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("dynamic_tp")

STATE_DIR = os.path.join(os.path.dirname(__file__), "state")
MOMENTUM_FILE = os.path.join(STATE_DIR, "momentum_tracker.json")
DANGER_FILE = os.path.join(STATE_DIR, "danger_signals.json")

# ── Layer 1: Profit Lock thresholds ───────────────────────────────────────────
TP_2X_SELL_PCT = 0.50   # Sell 50% at 2x
TP_3X_SELL_PCT = 0.20   # Sell 20% at 3x
TP_5X_SELL_PCT = 0.15   # Sell 15% at 5x

# ── Layer 2: Momentum tracking ────────────────────────────────────────────────
MOMENTUM_INCREASE_THRESHOLD = 0.2   # Score change to detect trend
MOMENTUM_DECREASE_THRESHOLD = 0.2
MAX_HOLD_CYCLES_STRONG = 5          # Don't hold more than 5 cycles on strong momentum

# ── Layer 3: Danger detection thresholds ──────────────────────────────────────
SMART_WALLET_SELL_COUNT = 2         # 2+ smart wallets selling = emergency
LIQUIDITY_DROP_THRESHOLD = 0.75     # Liquidity < 75% of peak = emergency
PARABOLIC_SPIKE_MULT = 1.80         # Price > 1.8x peak 5min ago = spike
VOLUME_COLLAPSE_THRESHOLD = 0.50    # Volume < 50% of peak + held > 15 min
TIME_EXPIRED_MIN = 120              # Exit after 2 hours if momentum < 0.8

# ── Trailing Stop ─────────────────────────────────────────────────────────────
TRAILING_STOP_DRAWDOWN = 0.30       # 30% drawdown from peak = sell all


def _load_momentum_tracker() -> Dict:
    """Load momentum tracking state."""
    if os.path.exists(MOMENTUM_FILE):
        try:
            with open(MOMENTUM_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_momentum_tracker(data: Dict) -> None:
    """Save momentum tracking state."""
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = MOMENTUM_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, MOMENTUM_FILE)
    except Exception:
        with open(MOMENTUM_FILE, "w") as f:
            json.dump(data, f, indent=2)


def _compute_momentum_score(
    token_key: str,
    price_history: List[float],
    tvl_history: List[float] = None,
    new_buyers_5min: int = 0,
    baseline_buyer_rate: float = 1.0,
    trustlines_added_5min: int = 0,
) -> Tuple[float, str]:
    """
    Compute momentum score for a token.
    Returns (score, direction) where:
      score: 0.0 = bearish, 1.0 = neutral, 2.0+ = strong momentum
      direction: "increasing", "decreasing", or "stable"
    """
    if tvl_history is None:
        tvl_history = []

    # Wallet inflow (normalized)
    wallet_inflow = new_buyers_5min / max(baseline_buyer_rate, 0.1)

    # Volume growth (using TVL as proxy)
    if len(tvl_history) >= 2:
        volume_growth = (tvl_history[-1] - tvl_history[0]) / max(tvl_history[0], 1)
    else:
        volume_growth = 0.0

    # New trustlines
    new_tl_normalized = min(trustlines_added_5min, 10) / 10

    # Composite momentum score
    momentum_score = (
        min(wallet_inflow, 3.0) * 0.4 +
        min(volume_growth, 2.0) * 0.3 +
        new_tl_normalized * 0.3
    )

    # Track trend
    tracker = _load_momentum_tracker()
    prev_score = tracker.get(token_key, {}).get("last_score", momentum_score)

    if momentum_score > prev_score + MOMENTUM_INCREASE_THRESHOLD:
        direction = "increasing"
    elif momentum_score < prev_score - MOMENTUM_DECREASE_THRESHOLD:
        direction = "decreasing"
    else:
        direction = "stable"

    # Update tracker
    tracker[token_key] = {
        "last_score": momentum_score,
        "direction": direction,
        "updated": time.time(),
    }
    _save_momentum_tracker(tracker)

    return momentum_score, direction


def _check_danger_signals(
    position: Dict,
    bot_state: Dict,
    current_price: float,
    current_tvl: float,
) -> Optional[Dict]:
    """
    Check Layer 3 danger signals. Returns emergency exit signal if any triggered.
    """
    symbol = position.get("symbol", "")
    issuer = position.get("issuer", "")
    token_key = f"{symbol}:{issuer}"
    entry_time = position.get("entry_time", time.time())
    time_in_trade_min = (time.time() - entry_time) / 60

    # Signal 1: Smart wallet exits
    # Check if tracked smart wallets sold this token recently
    smart_selling = 0
    try:
        from config import TRACKED_WALLETS
        tracked = list(TRACKED_WALLETS) if hasattr(__import__('config'), 'TRACKED_WALLETS') else []
    except ImportError:
        tracked = []

    # Also check discovered wallets
    discovered_file = os.path.join(STATE_DIR, "discovered_wallets.json")
    if os.path.exists(discovered_file):
        try:
            with open(discovered_file) as f:
                disc = json.load(f)
            tracked.extend(disc.get("tracked", []))
        except Exception:
            pass

    # Check recent trade history for smart wallet sells on this token
    trade_history = bot_state.get("trade_history", [])
    now = time.time()
    for trade in trade_history[-50:]:  # Last 50 trades
        if trade.get("symbol") == symbol and trade.get("exit_reason", "").startswith("tp"):
            # This was our exit — check if smart wallets were also selling
            smart_wallets = trade.get("smart_wallets", [])
            if smart_wallets:
                smart_selling += len(smart_wallets)

    if smart_selling >= SMART_WALLET_SELL_COUNT:
        return {
            "action": "emergency",
            "pct": 0.75,
            "reason": f"smart_wallet_exit ({smart_selling} wallets)",
        }

    # Signal 2: Liquidity drop
    peak_tvl = position.get("peak_tvl", current_tvl)
    if peak_tvl > 0 and current_tvl < peak_tvl * LIQUIDITY_DROP_THRESHOLD:
        drop_pct = (peak_tvl - current_tvl) / peak_tvl
        return {
            "action": "emergency",
            "pct": 1.0,
            "reason": f"liquidity_drop_{drop_pct:.0%}",
        }

    # Signal 3: Parabolic spike
    # Compare current price to peak 5 minutes ago (approximate via price history)
    price_history = position.get("price_history_5min", [])
    if price_history:
        peak_5min_ago = max(price_history[-5:]) if len(price_history) >= 5 else price_history[0]
        if peak_5min_ago > 0 and current_price > peak_5min_ago * PARABOLIC_SPIKE_MULT:
            spike_mult = current_price / peak_5min_ago
            return {
                "action": "emergency",
                "pct": 0.40,
                "reason": f"parabolic_spike_{spike_mult:.2f}x",
            }

    # Signal 4: Volume collapse
    # Using TVL as volume proxy
    peak_tvl_recent = position.get("peak_tvl_15min", peak_tvl)
    if (peak_tvl_recent > 0 and
        current_tvl < peak_tvl_recent * VOLUME_COLLAPSE_THRESHOLD and
        time_in_trade_min > 15):
        return {
            "action": "emergency",
            "pct": 1.0,
            "reason": "volume_collapse",
        }

    return None


def _get_strategy_exits(position: Dict) -> Dict:
    """
    Returns per-strategy TP targets and hard stop from GodMode classifier.
    Falls back to config defaults if no strategy stored on position.

    Strategy TP format: list of (multiple, sell_fraction) tuples
    e.g. [(2.0, 0.50), (3.0, 0.20), (5.0, 0.15), (7.0, 1.0)]
    """
    # Read strategy type stored at entry time by classifier.py
    strategy = position.get("_godmode_type", "unknown")

    STRATEGIES = {
        # BURST — fast momentum. Take profits quickly, trail tight.
        # PHX/PHASER type. Goal: lock 50% at 2x, ride remainder to 3x, trail stop.
        "burst": {
            "tps": [(2.0, 0.50), (3.0, 0.30), (6.0, 1.0)],
            "trail_stop": 0.20,   # tight — burst can reverse fast
            "hard_stop":  0.10,
            "stale_hours": 1.0,   # cut fast if not moving
        },
        # CLOB_LAUNCH — orderbook-driven fresh listing. Very fast, high risk.
        # Goal: quick 40% then trail. Dump full if momentum dies.
        "clob_launch": {
            "tps": [(1.4, 0.40), (2.0, 0.30), (3.0, 1.0)],
            "trail_stop": 0.15,   # tightest trail — CLOB dumps dump HARD
            "hard_stop":  0.08,
            "stale_hours": 0.5,
        },
        # PRE_BREAKOUT — coiled spring, hold for the big move.
        # DKLEDGER-type. Goal: let it breathe, target 5–10x.
        "pre_breakout": {
            "tps": [(1.3, 0.20), (2.0, 0.20), (5.0, 0.30), (10.0, 1.0)],
            "trail_stop": 0.25,   # wider — needs room to develop
            "hard_stop":  0.12,
            "stale_hours": 3.0,
        },
        # TREND — established momentum, already running.
        # Ride it but don't overstay.
        "trend": {
            "tps": [(1.2, 0.20), (1.5, 0.20), (2.0, 0.30), (4.0, 1.0)],
            "trail_stop": 0.18,
            "hard_stop":  0.08,
            "stale_hours": 2.0,
        },
        # MICRO_SCALP — ghost pool hunter, optimized Apr 8 2026
        # Ghost pools run HARD — 4x target gives room to catch the big moves
        # Old: (1.1x→60%, 1.2x→100%) was broken — +2% net after slippage = guaranteed loser
        # New: 2.5x→50% locks real profit, 4.0x→100% lets big runs pay off
        "micro_scalp": {
            "tps": [(2.50, 0.50), (4.00, 1.0)],
            "trail_stop": 0.20,   # widened from 8% — ghost pools swing 10-20% intraday, 8% was stopping out on noise
            "hard_stop":  0.08,   # keep at 8% — ghost rug risk is real, need the hard exit
            "stale_hours": 1.00,   # extended from 45min → 1hr — gives tokens room to develop
        },
    }

    # Default (no strategy classified or unknown)
    DEFAULT = {
        "tps": [(1.20, 0.30), (1.50, 0.30), (3.00, 0.30), (6.00, 1.0)],
        "trail_stop": 0.20,
        "hard_stop":  0.15,
        "stale_hours": 2.0,
    }

    return STRATEGIES.get(strategy, DEFAULT)


def _check_layer1_profit_lock(
    position: Dict,
    current_price: float,
) -> Optional[Dict]:
    """
    Check Layer 1 profit lock targets — reads per-strategy TP levels.
    Each strategy has its own TP ladder stored at entry via _godmode_type.
    """
    entry_price = position.get("entry_price", 0)
    if entry_price <= 0:
        return None

    multiple = current_price / entry_price
    exits = _get_strategy_exits(position)
    tps = exits["tps"]  # list of (multiple, sell_fraction)

    for i, (tp_mult, sell_frac) in enumerate(tps):
        flag = f"dynamic_tp_exited_tp{i}"
        if multiple >= tp_mult and not position.get(flag, False):
            action = "exit" if i < len(tps) - 1 else "exit"  # full exit on last TP
            return {
                "action": action,
                "pct": sell_frac,
                "reason": f"tp{i+1}_{tp_mult}x_profit_lock",
                "_tp_flag": flag,
                "_strategy": position.get("_godmode_type", "default"),
            }

    return None


def _check_trailing_stop(
    position: Dict,
    current_price: float,
) -> Optional[Dict]:
    """
    Strategy-aware trailing stop.
    Each strategy has its own trail and hard stop pct from _get_strategy_exits().
    """
    exits = _get_strategy_exits(position)
    trail_pct = exits["trail_stop"]
    hard_stop_pct = exits["hard_stop"]

    entry_price = position.get("entry_price", 0)
    peak_price  = position.get("peak_price", entry_price)

    if peak_price <= 0 or entry_price <= 0:
        return None

    # Update peak
    if current_price > peak_price:
        position["peak_price"] = current_price
        peak_price = current_price

    drawdown_from_peak  = (peak_price - current_price) / peak_price
    drawdown_from_entry = (entry_price - current_price) / entry_price

    strategy = position.get("_godmode_type", "default")

    # Hard stop from entry (catches early dumps before peak is established)
    if drawdown_from_entry >= hard_stop_pct:
        return {
            "action": "exit",
            "pct": 1.0,
            "reason": f"hard_stop_{drawdown_from_entry:.0%}_{strategy}",
        }

    # Trailing stop from peak
    if drawdown_from_peak >= trail_pct:
        return {
            "action": "exit",
            "pct": 1.0,
            "reason": f"trail_stop_{drawdown_from_peak:.0%}_{strategy}",
        }

    return None


def _check_decision_engine(
    position: Dict,
    bot_state: Dict,
    current_price: float,
    current_tvl: float,
    momentum_score: float,
    momentum_direction: str,
) -> Optional[Dict]:
    """
    Run the decision engine logic.
    Priority order:
      1. Danger signal active → emergency exit
      2. Layer 1 targets hit → scale out
      3. Momentum strong AND increasing → hold (max 5 cycles)
      4. Momentum weakening → reduce position
      5. Time expired (>120 min) AND momentum < 0.8 → exit
    """
    symbol = position.get("symbol", "")
    issuer = position.get("issuer", "")
    token_key = f"{symbol}:{issuer}"
    entry_time = position.get("entry_time", time.time())
    time_in_trade_min = (time.time() - entry_time) / 60
    cycles_held = position.get("dynamic_tp_cycles_held", 0)

    # Check danger first
    danger = _check_danger_signals(position, bot_state, current_price, current_tvl)
    if danger:
        return danger

    # Check Layer 1 profit lock
    layer1 = _check_layer1_profit_lock(position, current_price)
    if layer1:
        return layer1

    # Momentum-based decisions
    if momentum_score >= 1.5 and momentum_direction == "increasing":
        # Strong momentum increasing — hold but cap cycles
        if cycles_held >= MAX_HOLD_CYCLES_STRONG:
            return {
                "action": "exit",
                "pct": 0.50,
                "reason": "max_hold_strong_momentum",
            }
        return {"action": "hold"}

    if momentum_direction == "decreasing" and momentum_score < 0.8:
        # Weakening momentum — reduce position
        return {
            "action": "exit",
            "pct": 0.25,
            "reason": "momentum_weakening",
        }

    # Time-based exit
    if time_in_trade_min > TIME_EXPIRED_MIN and momentum_score < 0.8:
        return {
            "action": "exit",
            "pct": 1.0,
            "reason": "time_expired",
        }

    return {"action": "hold"}


def should_exit(
    position: Dict,
    bot_state: Dict,
    current_price: float,
    current_tvl: float = 0.0,
    price_history: List[float] = None,
    tvl_history: List[float] = None,
    new_buyers_5min: int = 0,
    baseline_buyer_rate: float = 1.0,
    trustlines_added_5min: int = 0,
) -> Dict:
    """
    Main entry point. Determines if a position should exit based on dynamic TP rules.

    Returns:
      {'action': 'hold'} — no action needed
      {'action': 'exit', 'pct': float, 'reason': str} — partial or full exit
      {'action': 'emergency', 'pct': float, 'reason': str} — urgent exit

    Integration: bot.py calls this AFTER scoring, BEFORE sending to execution.
    If it returns 'hold', existing TP system still applies as fallback.
    """
    if price_history is None:
        price_history = []
    if tvl_history is None:
        tvl_history = []

    symbol = position.get("symbol", "")
    issuer = position.get("issuer", "")
    token_key = f"{symbol}:{issuer}"
    entry_price = position.get("entry_price", 0)

    # Increment cycle counter
    cycles_held = position.get("dynamic_tp_cycles_held", 0) + 1
    position["dynamic_tp_cycles_held"] = cycles_held

    # Update price history for parabolic spike detection
    hist_5min = position.get("price_history_5min", [])
    hist_5min.append(current_price)
    position["price_history_5min"] = hist_5min[-10:]  # Keep last 10 readings

    # Update peak TVL tracking
    peak_tvl = position.get("peak_tvl", current_tvl)
    if current_tvl > peak_tvl:
        position["peak_tvl"] = current_tvl

    # ── Step 1: Check trailing stop first (always active) ─────────────────────
    trailing = _check_trailing_stop(position, current_price)
    if trailing:
        logger.warning(
            f"🛑 DYNAMIC-TP {symbol}: {trailing['reason']} — "
            f"sell {trailing['pct']:.0%}"
        )
        return trailing

    # ── Step 2: Compute momentum score ────────────────────────────────────────
    momentum_score, momentum_direction = _compute_momentum_score(
        token_key=token_key,
        price_history=price_history,
        tvl_history=tvl_history,
        new_buyers_5min=new_buyers_5min,
        baseline_buyer_rate=baseline_buyer_rate,
        trustlines_added_5min=trustlines_added_5min,
    )

    # ── Step 3: Run decision engine ───────────────────────────────────────────
    decision = _check_decision_engine(
        position=position,
        bot_state=bot_state,
        current_price=current_price,
        current_tvl=current_tvl,
        momentum_score=momentum_score,
        momentum_direction=momentum_direction,
    )

    if decision["action"] != "hold":
        reason = decision.get("reason", "unknown")
        pct = decision.get("pct", 1.0)
        action_type = decision["action"]
        emoji = "🚨" if action_type == "emergency" else "📤"
        logger.info(
            f"{emoji} DYNAMIC-TP {symbol}: {reason} — "
            f"{action_type} {pct:.0%} (momentum={momentum_score:.2f} {momentum_direction})"
        )
        return decision

    # ── Step 4: Hold — log momentum state ─────────────────────────────────────
    logger.debug(
        f"  DYNAMIC-TP {symbol}: HOLD (momentum={momentum_score:.2f} "
        f"{momentum_direction}, cycles={cycles_held})"
    )

    return {"action": "hold"}


def mark_profit_lock_exit(position: Dict, reason: str, tp_flag: str = None) -> None:
    """Mark a profit lock level as exited so it won't trigger again."""
    # New flag-based system (strategy-aware)
    if tp_flag:
        position[tp_flag] = True
        return
    # Legacy fallback
    if "2x" in reason:
        position["dynamic_tp_exited_2x"] = True
    elif "3x" in reason:
        position["dynamic_tp_exited_3x"] = True
    elif "5x" in reason:
        position["dynamic_tp_exited_5x"] = True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("Dynamic TP Module — test mode")

    # Simulate a position
    test_position = {
        "symbol": "TEST",
        "issuer": "rTestIssuer123",
        "entry_price": 0.001,
        "peak_price": 0.001,
        "entry_time": time.time() - 3600,  # 1 hour ago
        "tokens_held": 10000,
        "xrp_spent": 10.0,
    }

    test_bot_state = {"trade_history": [], "positions": {}}

    # Test at various multiples
    for mult in [1.5, 2.0, 3.0, 5.0, 6.0]:
        current = test_position["entry_price"] * mult
        result = should_exit(
            position=test_position.copy(),
            bot_state=test_bot_state,
            current_price=current,
            current_tvl=5000,
        )
        print(f"  {mult}x: {result}")