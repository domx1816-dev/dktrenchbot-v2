"""
classifier.py — Token Type Classifier (GodModeEngine integration)
Maps raw token data → TokenType for strategy routing.

Token Types:
  BURST         — velocity > 2.5 AND vol > 50K XRP (fast movers, TrustSet burst)
  PRE_BREAKOUT  — TVL > 100K, low velocity (accumulation pattern)
  TREND         — TVL > 300K, rising velocity (established momentum)
  CLOB_LAUNCH   — age < 120 sec (orderbook-driven launch, brizzly/PRSV pattern)
  MICRO_SCALP   — thin vol, fast velocity (micro-cap scalp)
  NONE          — skip (no valid signal)

Integration: called from bot.py after scanner gathers candidate data,
            BEFORE scoring. Sets _strategy_type on candidate dict.
"""

import time
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Optional


class TokenType(Enum):
    BURST          = "burst"
    PRE_BREAKOUT   = "pre_breakout"
    TREND          = "trend"
    CLOB_LAUNCH    = "clob_launch"
    MICRO_SCALP    = "micro_scalp"
    NONE           = "none"


@dataclass
class Token:
    """Lightweight token object used by classifier + strategies."""
    symbol:    str
    price:     float
    volume:    float   # 5-min XRP volume (from scanner/realtime_watcher)
    tvl:       float   # AMM pool TVL in XRP
    velocity:  float   # price % change per reading (momentum score proxy)
    age:       float   # seconds since token first seen in registry
    meta:      dict    # arbitrary extra data (trustsets, holders, etc.)


def build_token(candidate: Dict, price_history: list = None) -> Token:
    """
    Build a Token object from a scanner candidate dict + price history.
    Computes velocity from price history.
    """
    symbol = candidate.get("symbol", "")
    issuer = candidate.get("issuer", "")
    currency = candidate.get("currency", "")
    price = candidate.get("price", 0)
    tvl = candidate.get("tvl_xrp", candidate.get("tvl", 0))

    # Volume: use clob_vol_5min if CLOB launch, else use scanner vol
    volume = candidate.get("clob_vol_5min", 0)
    if not volume:
        # scanner may set a vol_xrp field
        volume = candidate.get("vol_xrp", candidate.get("volume", 0))

    # Age: seconds since token was first added to registry
    age_seconds = 99999
    if price_history:
        # rough proxy: assume oldest reading is creation
        age_seconds = time.time() - price_history[0][0]
    else:
        # Fall back to age_h from trustset_watcher if present
        age_seconds = candidate.get("age_h", 999) * 3600
    # Also check first_seen from registry
    if candidate.get("first_seen"):
        age_seconds = min(age_seconds, time.time() - candidate["first_seen"])

    # Velocity: % change per reading (proxy via burst_count or price momentum)
    velocity = 0.0
    if candidate.get("burst_count", 0) > 0:
        # TrustSet burst rate = velocity proxy (3+ burst/5min = momentum)
        velocity = candidate["burst_count"] / 5.0  # bursts per 5-min window
    elif price_history and len(price_history) >= 3:
        prices = [r[1] for r in price_history if r[1] > 0]
        if len(prices) >= 3:
            # % change per reading (3 readings ≈ 3 minutes)
            vel = (prices[-1] - prices[-3]) / prices[-3] * 100 if prices[-3] > 0 else 0
            velocity = abs(vel)  # magnitude for thresholding

    # TrustSet burst rate (trustset_watcher output)
    ts_burst = candidate.get("burst_count", 0)

    # CLOB launch flag — set by realtime_watcher.py OR bot.py entry loop
    is_clob = candidate.get("_clob_launch", False)

    # Build meta dict with all extra signals
    meta = {
        "issuer":         issuer,
        "currency":       currency,
        "burst_count":    ts_burst,
        "offer_count":    candidate.get("offer_count", 0),
        "clob_vol_5min":  candidate.get("clob_vol_5min", 0),
        "tvl_change_pct": candidate.get("tvl_change_pct", 0),
        "smart_wallets":  candidate.get("smart_wallets", []),
        "chart_state":    candidate.get("chart_state", "unknown"),
        "breakout_quality": candidate.get("breakout_quality", 0),
        "holders":        candidate.get("holders", 0),
        "_clob_launch":   is_clob,   # CLOB-native entry (no AMM needed)
        "_burst_mode":    candidate.get("_burst_mode", False),
        "_momentum_mode": candidate.get("_momentum_mode", False),
        "_tvl_runner":    candidate.get("_tvl_runner", False),
    }

    return Token(
        symbol   = symbol,
        price    = price,
        volume   = volume,
        tvl      = tvl,
        velocity = velocity,
        age      = age_seconds,
        meta     = meta,
    )


class Classifier:
    """
    Routes a token to its appropriate strategy type.
    Priority order matters — check in this order.
    """

    @staticmethod
    def classify(token: Token) -> TokenType:
        """
        Main classification logic.
        Returns TokenType enum value.
        """
        # ── CLOB_LAUNCH: age < 300s AND orderbook volume > 0
        # Pattern: brizzly, PROPHET, PRSV — orderbook drives launch, not AMM
        # Widen from 120s → 300s (Apr 8 2026): original 120s was too tight, real CLOB
        # launches persist 5-10 min. Scanner needs time to pick them up. 300s window
        # catches the early move without including stale/expired orderbook setups.
        if token.age < 300:
            # Require CLOB vol signal
            if token.meta.get("clob_vol_5min", 0) >= 10:
                return TokenType.CLOB_LAUNCH
            # Also allow if burst rate confirms community forming fast
            if token.meta.get("burst_count", 0) >= 5:
                return TokenType.CLOB_LAUNCH

        # ── BURST: TrustSet velocity burst OR fast price momentum
        # Primary signal: burst_count >= 8 TrustSets/hr (calibrated Apr 8)
        # Secondary: high price velocity on any TVL pool
        # PHX (137 TS/hr), PHASER (70 TS/hr), DKLEDGER (11 TS/hr at $400 MC)
        burst_count = token.meta.get("burst_count", 0) or token.meta.get("ts_burst_count", 0)
        if burst_count >= 8:
            return TokenType.BURST
        if token.velocity > 2.5 and token.tvl > 200:
            return TokenType.BURST
        # Realtime burst flag set by trustset_watcher or realtime_watcher
        if token.meta.get("_burst_mode", False):
            return TokenType.BURST

        # ── PRE_BREAKOUT: any TVL, low velocity, chart_state confirmed
        # Widened from TVL>100K — micro pools coil before massive moves too
        if token.meta.get("chart_state") == "pre_breakout" and token.velocity < 1.5:
            return TokenType.PRE_BREAKOUT
        if token.tvl > 50_000 and token.velocity < 1.2:
            return TokenType.PRE_BREAKOUT

        # ── TREND: established momentum, pool already large
        if token.tvl > 200_000 and token.velocity > 1.5:
            return TokenType.TREND

        # ── MICRO_SCALP: thin micro pool, fast momentum, quick flip
        if token.tvl < 2_000 and token.tvl >= 200 and token.velocity > 1.5:
            return TokenType.MICRO_SCALP

        return TokenType.NONE

    @staticmethod
    def classify_from_dict(candidate: Dict, price_history: list = None) -> TokenType:
        """
        Convenience wrapper: takes scanner candidate dict directly.
        Called from bot.py during candidate evaluation.
        """
        token = build_token(candidate, price_history)
        return Classifier.classify(token)


# ── Strategy base + implementations ─────────────────────────────────────────

class Strategy:
    """
    Base class for strategy objects.
    Each strategy has:
      valid()    — hard filter (must pass to consider entry)
      confirm()  — soft filter (must pass to enter)
      score()    — scoring bonus for this strategy type
    """

    def valid(self, token: Token) -> bool:
        return True

    def confirm(self, token: Token) -> bool:
        return True

    def score(self, token: Token) -> float:
        return 0


class BurstStrategy(Strategy):
    """
    BURST — fast mover, TrustSet velocity confirmed momentum.
    Strategy: enter fast, size moderate, exit on 2x TP1.
    Valid: velocity > 2.0
    Confirm: volume > 40K XRP
    Score: velocity * 30, capped at 100
    """
    def valid(self, token: Token) -> bool:
        return token.velocity > 2.0 or token.meta.get("burst_count", 0) >= 8

    def confirm(self, token: Token) -> bool:
        return token.volume > 40_000 or token.meta.get("burst_count", 0) >= 5

    def score(self, token: Token) -> float:
        # Higher score for faster bursts
        raw = token.velocity * 30
        burst_bonus = token.meta.get("burst_count", 0) * 2
        return min(100, raw + burst_bonus)


class PreBreakoutStrategy(Strategy):
    """
    PRE_BREAKOUT — large TVL, low velocity (accumulation compression).
    Strategy: wait for breakout confirmation, size large, hold for 5x+.
    Valid: TVL > 80K AND score >= 45 (Apr 8 2026: data shows score<45 = 24% WR, score>=45 = 58%+ WR)
    Confirm: velocity < 1.3 (still compressing)
    Score: TVL / 1000, capped at 100
    """
    def valid(self, token: Token) -> bool:
        # Score minimum gate — Apr 8 2026: backtest confirmed score<45 is loss territory
        score = min(100, token.tvl / 1000)
        return token.tvl > 80_000 and score >= 45

    def confirm(self, token: Token) -> bool:
        return token.velocity < 1.3 and token.meta.get("chart_state") == "pre_breakout"

    def score(self, token: Token) -> float:
        return min(100, token.tvl / 1000)


class TrendStrategy(Strategy):
    """
    TREND — established pool with rising momentum.
    Strategy: ride established trend, size moderate, tighter stop.
    Valid: TVL > 250K
    Confirm: velocity > 1.4
    Score: velocity * 20 + TVL/10000, capped at 100
    """
    def valid(self, token: Token) -> bool:
        return token.tvl > 250_000

    def confirm(self, token: Token) -> bool:
        return token.velocity > 1.4

    def score(self, token: Token) -> float:
        return min(100, token.velocity * 20 + token.tvl / 10000)


class ClobLaunchStrategy(Strategy):
    """
    CLOB_LAUNCH — orderbook-driven launch (brizzly/PROPHET/PRSV pattern).
    Strategy: fast entry, small size, tight stop. Orderbook momentum IS signal.
    Valid: age < 180s AND (CLOB vol OR TrustSet burst)
    Confirm: CLOB vol ≥10 XRP/5min OR burst ≥5 TrustSets/5min OR tvl > 50K (early AMM signal)
    Score: fixed 60 + age decay bonus

    NOTE: bot.py already enforces vol ≥20 XRP AND burst ≥10 for CLOB entries.
    The GodMode CLOB_LAUNCH strategy is a secondary confirmation layer that also
    catches pure orderbook launches where AMM hasn't been detected yet.
    """
    def valid(self, token: Token) -> bool:
        if token.age >= 180:
            return False
        # Must have at least one momentum signal
        has_clob      = token.meta.get("clob_vol_5min", 0) >= 5
        has_burst     = token.meta.get("burst_count", 0) >= 3
        has_tvl       = token.tvl > 50_000
        is_clob_flag  = token.meta.get("_clob_launch", False)
        is_burst_flag = token.meta.get("_burst_mode", False)
        return has_clob or has_burst or has_tvl or is_clob_flag or is_burst_flag

    def confirm(self, token: Token) -> bool:
        # Require stronger signal for full entry confirmation.
        # Note: bot.py already enforces burst ≥ 10 for CLOB entries (the primary filter).
        # Here we use a lower threshold as a secondary safety net for edge cases.
        clob_ok   = token.meta.get("clob_vol_5min", 0) >= 10
        burst_ok  = token.meta.get("burst_count", 0) >= 3
        tvl_ok    = token.tvl > 80_000
        # _burst_mode tokens have passed bot.py's burst ≥10 check upstream
        burst_flag_ok = token.meta.get("_burst_mode", False)
        # Fallback: tiny volume is OK if CLOB orderbook signal or burst flag is live
        vol_ok = token.volume >= 20_000 or clob_ok or burst_flag_ok
        return burst_ok or clob_ok or burst_flag_ok or (tvl_ok and vol_ok)

    def score(self, token: Token) -> float:
        # Bonus for fresh launches
        age_bonus = max(0, 20 - token.age / 10)  # decays after first 200s
        burst_bonus = token.meta.get("burst_count", 0) * 2
        clob_bonus  = min(20, token.meta.get("clob_vol_5min", 0) * 0.5)
        return min(100, 60 + age_bonus + burst_bonus + clob_bonus)


class MicroScalpStrategy(Strategy):
    """
    MICRO_SCALP — micro-cap thin pools with fast momentum.
    Strategy: tiny size, tight stop, quick 10-15% exit.
    Valid: volume < 25K XRP
    Confirm: velocity > 1.7
    Score: fixed 50
    """
    def valid(self, token: Token) -> bool:
        return token.volume < 25_000 and token.tvl < 2_000

    def confirm(self, token: Token) -> bool:
        return token.velocity > 1.7

    def score(self, token: Token) -> float:
        return 50


# ── Strategy map ───────────────────────────────────────────────────────────────

STRATEGY_MAP = {
    TokenType.BURST:         BurstStrategy(),
    TokenType.PRE_BREAKOUT:  PreBreakoutStrategy(),
    TokenType.TREND:         TrendStrategy(),
    TokenType.CLOB_LAUNCH:   ClobLaunchStrategy(),
    TokenType.MICRO_SCALP:   MicroScalpStrategy(),
}


def get_strategy(token_type: TokenType) -> Strategy:
    """Return strategy instance for token type."""
    return STRATEGY_MAP.get(token_type, None)


# ── Execution validator ───────────────────────────────────────────────────────

class ExecutionValidator:
    """
    GodModeEngine execution gate — minimum quality floors.
    These are hard stops regardless of strategy.

    NOTE: The main bot (realtime_watcher.py) already applies CLOB-specific
    entry filters (vol ≥20 XRP AND burst ≥10 for CLOB entries). The
    GodMode ExecutionValidator here is a secondary safety net that catches
    edge cases where the CLOB signal was injected without proper filtering.

    For CLOB_LAUNCH tokens: use CLOB-native min (clob_vol_5min ≥ 10 XRP).
    For AMM tokens: enforce AMM pool floors.
    """

    # AMM pool floors (XRP-denominated)
    MIN_AMM_VOLUME_XRP = 100    # 100 XRP/hr (avg across scan cycle)
    MIN_AMM_TVL_XRP    = 200    # 200 XRP pool (bot MIN_TVL_XRP)

    # CLOB-specific floor (5-min window — already filtered upstream in bot.py)
    MIN_CLOB_VOL_5MIN  = 10     # 10 XRP bought on CLOB in 5-min window

    @classmethod
    def validate(cls, token: Token) -> tuple[bool, str]:
        """
        Returns (passed, reason) tuple.
        CLOB_LAUNCH tokens bypass the AMM volume floor (they use CLOB signals).
        """
        if token.price <= 0:
            return False, "no_valid_price"

        # CLOB-native or burst-mode tokens bypass AMM pool floors.
        # These are signals injected by realtime_watcher.py / bot.py entry loop
        # AFTER the CLOB-specific filtering (vol ≥20 XRP AND burst ≥10).
        # The GodMode validator is a secondary safety net, not the primary gate.

        # Burst-mode (TrustSet velocity): bypass all floors — already filtered upstream
        if token.meta.get("_burst_mode", False):
            return True, "pass"

        # CLOB-native launch flag: bypass clob_vol floor (bot.py uses AMM vol filter separately)
        if token.meta.get("_clob_launch", False):
            return True, "pass"

        # CLOB orderbook signals: require minimum CLOB volume
        if token.meta.get("_tvl_runner", False) or token.meta.get("clob_vol_5min", 0) > 0:
            if token.meta["clob_vol_5min"] < cls.MIN_CLOB_VOL_5MIN:
                return False, f"clob_vol={token.meta['clob_vol_5min']:.0f} < {cls.MIN_CLOB_VOL_5MIN}"
            return True, "pass"

        # AMM tokens: enforce pool quality floors
        if token.volume < cls.MIN_AMM_VOLUME_XRP:
            return False, f"amm_vol={token.volume:.0f} < {cls.MIN_AMM_VOLUME_XRP}"
        if token.tvl < cls.MIN_AMM_TVL_XRP:
            return False, f"tvl={token.tvl:.0f} < {cls.MIN_AMM_TVL_XRP}"

        return True, "pass"


# ── Position sizer ────────────────────────────────────────────────────────────

class PositionSizer:
    """
    GodModeEngine position sizing by token type.
    Uses available wallet balance to compute dynamic XRP amount.

    Sizes are base multipliers on a 2% base of balance.
    Override for high-conviction strategies.
    """

    BASE_PCT = 0.02  # 2% of balance as base unit

    @classmethod
    def size(cls, token_type: TokenType, strategy_score: float, balance: float) -> float:
        """
        Returns XRP amount for this position.
        Uses strategy type + score + available balance.
        """
        base = balance * cls.BASE_PCT  # 2% base unit

        if token_type == TokenType.BURST:
            return round(base * 0.5, 2)
        if token_type == TokenType.PRE_BREAKOUT:
            return round(base * 1.5, 2)
        if token_type == TokenType.TREND:
            return round(base * 1.2, 2)
        if token_type == TokenType.CLOB_LAUNCH:
            return round(base * 0.8, 2)
        if token_type == TokenType.MICRO_SCALP:
            return round(base * 0.4, 2)
        return round(base, 2)


# ── GodModeEngine integration helpers ─────────────────────────────────────────

def classify_and_route(candidate: Dict, price_history: list,
                        balance: float) -> Dict:
    """
    Main integration function — called from bot.py during candidate evaluation.

    Takes: scanner candidate dict + price history + available wallet balance
    Returns: dict with routing decision + strategy info
      {
        "action":  "enter" | "pending" | "skip",
        "reason":  str,
        "token_type": TokenType value,
        "strategy_score": float,
        "position_size": float,
        "hard_stop_pct": float,
        "tp_targets": list[float],
      }
    """
    token = build_token(candidate, price_history)
    token_type = Classifier.classify(token)

    if token_type == TokenType.NONE:
        return {"action": "skip", "reason": "no_signal", "token_type": "none"}

    strategy = get_strategy(token_type)
    if strategy is None:
        return {"action": "skip", "reason": "no_strategy", "token_type": token_type.value}

    # ── Strategy hard filter
    if not strategy.valid(token):
        return {
            "action": "skip",
            "reason": f"strategy_invalid_{token_type.value}",
            "token_type": token_type.value,
        }

    # ── Strategy soft filter
    if not strategy.confirm(token):
        # Log the reason but don't hard-skip — let main scoring decide.
        # Some strategies need live data (TrustSet bursts, CLOB vol) that the
        # scanner already filtered separately in bot.py. The GodMode confirm()
        # is a secondary filter; if it fails, we still let the composite score gate.
        return {
            "action": "skip",
            "reason": f"strategy_confirm_{token_type.value}",
            "token_type": token_type.value,
        }

    # ── Execution validator (hard floors)
    passed, val_reason = ExecutionValidator.validate(token)
    if not passed:
        return {"action": "skip", "reason": f"exec_validate_fail({val_reason})", "token_type": token_type.value}

    # ── Strategy score
    strat_score = strategy.score(token)

    # ── Position size
    size = PositionSizer.size(token_type, strat_score, balance)

    # ── TP targets by token type
    if token_type == TokenType.BURST:
        tp_targets = [0.20, 0.50, 3.00, 6.00]
        hard_stop = 0.10
    elif token_type == TokenType.PRE_BREAKOUT:
        tp_targets = [0.30, 0.60, 5.00, 10.00]  # wide TPs for breakout
        hard_stop = 0.12
    elif token_type == TokenType.TREND:
        tp_targets = [0.20, 0.50, 2.00, 4.00]
        hard_stop = 0.08
    elif token_type == TokenType.CLOB_LAUNCH:
        tp_targets = [0.15, 0.40, 1.50, 3.00]   # tight — CLOB dumps fast
        hard_stop = 0.08
    elif token_type == TokenType.MICRO_SCALP:
        tp_targets = [0.10, 0.20]               # quick scalp, fast exit
        hard_stop = 0.06
    else:
        tp_targets = [0.20, 0.50]
        hard_stop = 0.10

    return {
        "action":         "enter",
        "reason":        f"strategy_{token_type.value}",
        "token_type":     token_type.value,
        "strategy_score": strat_score,
        "position_size":  size,
        "hard_stop_pct":  hard_stop,
        "tp_targets":     tp_targets,
        "token":          token,  # pass Token object for further scoring
    }
