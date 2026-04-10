"""
config.py — DKTrenchBot Configuration

DATA-DRIVEN REBUILD 2026-04-06 21:49 UTC
Based on 53 real trades analysis:
  - Score 0-49: 47% WR (BEST)
  - Score 50-59: 50% WR (SOLID)
  - Score 60-79: 12-22% WR (BAD — mostly stales)
  - Score 80-100: 0% WR (WORST — all stales, mature pools)
  - Hour 04-07 UTC: 6-17% WR (DEAD — no activity)
  - Hour 13-22 UTC: 44-100% WR (PEAK — trade here only)
  - Stales = 40% of all trades → cut stale timer hard
  - Winners cluster in low-TVL micro tokens, not established pools
"""

import os
from typing import List

# ── Core Infrastructure ────────────────────────────────────────────────────────
CLIO_URL         = os.environ.get("CLIO_URL", "https://rpc.xrplclaw.com")
WS_URL           = os.environ.get("WS_URL",   "wss://rpc.xrplclaw.com/ws")
BOT_WALLET_ADDRESS = "rKQACag8Td9TrMxBwYJPGRMDV8cxGfKsmF"
STATE_DIR        = os.path.join(os.path.dirname(__file__), "state")
POLL_INTERVAL_SEC = 1

# ── Score Thresholds ───────────────────────────────────────────────────────────
# DATA: Score 0-49 = 47% WR, 50-59 = 50% WR, 60-79 = 12-22% WR, 80-100 = 0% WR
# The scoring system is inversely correlated at high values — high TVL pools
# score well but are already discovered and don't move.
# Strategy: accept lower-scoring tokens (real runners), reject high-score stales.
SCORE_ELITE        = 50    # 50+ → elite size — DATA shows this is the real sweet spot
SCORE_TRADEABLE    = 42    # 42+ → normal entry — backtest showed 42-44 band has 60% WR (best performing)
SCORE_SMALL        = 999   # DISABLED — no small band, use scalp mode instead
PREFERRED_CHART_STATES = {"pre_breakout"}  # only state with runners — data confirmed

# ── Position Sizing ────────────────────────────────────────────────────────────
XRP_PER_TRADE_BASE = 8.0    # Normal entry (42-49) — moderate
XRP_ELITE_BASE     = 12.0   # Elite entry (50+) — confident
XRP_SMALL_BASE     = 4.0    # Scalp / micro entries
XRP_SNIPER_BASE    = 5.0    # Sniper entries
XRP_MICRO_BASE     = 5.0    # Micro-cap new token
MAX_POSITIONS = 999  # no limit - master build in full release mode

# ── TVL Thresholds ─────────────────────────────────────────────────────────────
# DATA: Winners cluster in micro TVL (under 3K XRP). Established pools (5K-20K)
# score high but produce 0% WR. Flip the model.
MIN_TVL_XRP        = 100    # ~$200 MC floor at $2/XRP — catches full $400-$5K MC sweet spot.
TVL_MICRO_CAP_XRP  = 2500   # 2.5K XRP TVL ≈ $5K MC ceiling. Above this is stale/discovered.
MIN_TVL_DROP_EXIT  = 0.40   # exit if TVL drops >40% in one cycle (pool draining)

# ── Exit System — 4-tier TP + Tight Stale ─────────────────────────────────────
# DATA: Stale exits = 40% of trades, all losses. Cut timer in half.
STALE_EXIT_HOURS   = 3.0    # raised from 0.97hr — stale exits at 1hr were killing flat-but-valid positions
MAX_HOLD_HOURS     = 12.0   # extended — PHX-type runners need 8-12hr to fully develop

HARD_STOP_PCT = 15   # warden tightened: loss > win
HARD_STOP_ABSOLUTE_PCT = 15  # absolute per-trade hard stop at -15% (QuantX patch Apr 10)
MAX_SLIPPAGE_PCT = 0.15  # Increased to 15% to catch thinner pools in $400-$5K MC range
HARD_STOP_EARLY_PCT = 0.15  # raised from 10% — was firing too early, matching main hard stop
HARD_STOP_GRACE_SEC = 1800  # 30 min early stop window

TRAIL_STOP_PCT     = 0.25   # widened from 20% — micro-caps swing 20% normally, was noise-tripping

# 4-tier TP — let real runners go to 600%+
TP1_PCT            = 0.20   # +20% → sell 30%
TP1_SELL_FRAC      = 0.30
TP2_PCT            = 0.50   # +50% → sell 30% of remainder
TP2_SELL_FRAC      = 0.30
TP3_PCT            = 3.00   # +300% → sell 30% of remainder
TP3_SELL_FRAC      = 0.30
TP4_PCT            = 6.00   # +600% → full exit

# ── Trading Hours ──────────────────────────────────────────────────────────────
# DATA: 04-07 UTC = 6-17% WR (dead market). 13-22 UTC = 44-100% WR.
# Only enter NEW positions during peak hours. Exit management runs 24/7.
TRADING_HOURS_UTC  = list(range(0, 24))  # 24/7 — operator preference: trade all hours

# ── Scoring Module Flags ───────────────────────────────────────────────────────
CONTINUATION_MIN_SCORE = 999   # DISABLED — 17% WR avg -1.4 XRP
ORPHAN_MIN_SCORE       = 999   # DISABLED — 14% WR, rugpull magnet

# ── Scalp Mode ─────────────────────────────────────────────────────────────────
# Quick 10% target for borderline tokens. Tight stop, time-limited.
# ── Micro Scalp (ghost pool hunter) — FIXED Apr 8 2026 ─────────────────────────────────
# Old SCALP was broken: 1.1x TP with 8% slippage = +2% net = guaranteed loser
# New targets ghost pools that run 4-10x on strong TrustSet bursts
SCALP_MIN_SCORE    = 42     # raised from 40 — filter out 35-41 zero-WR band; data shows 42+ catches all quality entries
SCALP_MAX_SCORE    = 52     # upper bound — 53+ starts hitting stale discovered pools, data shows diminishing WR
SCALP_SIZE_XRP     = 5.0    # keep small — ghost tokens are high risk
SCALP_TP_PCT       = 1.50   # +150% → TP1 at 2.5x, TP2 at 4.0x (TP ladder in dynamic_tp.py)
SCALP_STOP_PCT     = 0.08   # -8% hard stop — ghost rug risk is real
SCALP_MAX_HOLD_MIN = 60     # extended from 45 → 60 min — give runs room to develop

# ── Regime ────────────────────────────────────────────────────────────────────
REGIME_HOT_THRESHOLD    = 0.55   # WR above this = hot
REGIME_COLD_THRESHOLD   = 0.35   # WR below this = cold
REGIME_DANGER_THRESHOLD = 0.20   # WR below this = danger (pause entries)

# ── Reentry / Blacklist ────────────────────────────────────────────────────────
SKIP_REENTRY_SYMBOLS = {"Teddy", "ZERPS", "JEET", "NOX", "XRPB", "XRPH"}
COOLDOWN_AFTER_STOP_MIN = 120  # don't re-enter a stopped token for 2 hours

# ── Proven Token System ────────────────────────────────────────────────────────
# Tokens that have demonstrated TP1+ exits get priority reload on dip recovery.
# No cooldown applies to proven tokens. Bigger sizing allowed.
# Updated dynamically from trade_history at runtime.
PROVEN_TOKEN_MIN_WINS   = 2      # need 2+ TP exits to qualify as proven
PROVEN_TOKEN_RELOAD_XRP = 15.0   # bigger size for proven tokens (vs 8 base)
PROVEN_TOKEN_SCORE_GATE = 38     # lower score gate for proven tokens (they've earned trust)

# ── Hold vs Scalp Decision Logic ──────────────────────────────────────────────
# TVL tier determines strategy: micro = scalp, early-stage = hold for 300%+
# This is the single biggest lever for catching PHX-type runners vs wasting on stales
TVL_SCALP_MAX         = 1_000    # under 1K XRP TVL = quick scalp (ghost/unproven)
TVL_HOLD_MIN          = 1_000    # 1K-10K XRP TVL = hold for big moves
TVL_HOLD_MAX          = 10_000   # over 10K XRP = stale, skip or micro entry
TVL_VELOCITY_RUNNER   = 0.20     # TVL growing 20%+ = runner starting, hold mode (unified with inline threshold in bot.py)

# ── Token Registry & Currency Utils ───────────────────────────────────────────
# Default fallback registry (overridden at runtime by active_registry.json)
TOKEN_REGISTRY = {}

def get_currency(symbol: str) -> str:
    """Convert ticker symbol to XRPL currency code."""
    s = symbol.upper()
    if len(s) <= 3:
        return s.ljust(3)
    # If already a 40-char hex string, return as-is (avoid double-encoding)
    if len(s) == 40 and all(c in "0123456789ABCDEF" for c in s):
        return s
    # Hex-encode to 40-char currency code
    encoded = s.encode("utf-8").hex().upper()
    return encoded.ljust(40, "0")[:40]

# ── Safety / Execution Constants ──────────────────────────────────────────────
MIN_LP_BURN_PCT   = 0.80   # 80%+ LP burned = safe (issuer can't rug liquidity)
SECRETS_FILE      = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory", "secrets.md")

# Known XRPL blackhole addresses (issuer sent keys to these = tokens can't be rugged)
BLACK_HOLES = {
    "rrrrrrrrrrrrrrrrrrrrrhoLvTp",
    "rrrrrrrrrrrrrrrrrrrrBZbvji",
    "rBurnAddress1111111111111111",
    "rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh",
}

# ── Smart Money / Wallet Intelligence ─────────────────────────────────────────
WHALE_XRP_THRESHOLD = 10_000   # wallets holding 10K+ XRP equivalent = whale


# ── Stablecoin / Non-Meme Skip List (centralized) ─────────────────────────────
STABLECOIN_SKIP = frozenset({
    "USD","USDC","USDT","RLUSD","XUSD","AUDD","XSGD","XCHF","GYEN",
    "EUR","EURO","EUROP","GBP","JPY","CNY","AUD","CAD","MXRP",
    "SGB","FLR","XAH","BTC","ETH","SOL","XDC","SOLO","CSC","CORE","EVR",
})
FIAT_PREFIXES = ("USD","EUR","GBP","JPY","CNY","AUD","CAD","STABLE","PEGGED")

# ── Smart Wallet Tracking ─────────────────────────────────────────────────────
# Pre-seeded tracked wallets (auto-populated by new_wallet_discovery.py over time)
TRACKED_WALLETS: List[str] = []

# ── Dynamic TP Module ─────────────────────────────────────────────────────────
DYNAMIC_TP_ENABLED = True  # Enable 3-layer dynamic take-profit system

# ── Confidence-Based Position Sizing ─────────────────────────────────────────
MAX_POSITION_XRP = 10.0  # Hard ceiling per trade — cut from 15 to protect capital (QuantX patch Apr 10)

# ── ML Pipeline ───────────────────────────────────────────────────────────────
ML_ENABLED = True  # Enable ML feature logging and (when ready) predictions


# ── Strategy Allowlist (operator directive Apr 9 2026) ────────────────────────
# 14-day backtest on current 682-token universe:
#   burst:        67% WR | +1200 XRP | avg_win +5.3  ✅
#   pre_breakout: 36% WR | +1463 XRP | avg_win +13.1 ✅
#   micro_scalp:  71% WR |  +158 XRP                 ✅ keep
#   clob_launch:  36% WR |   +71 XRP  → reclassify as burst if burst-backed
#   trend:        18% WR |   -0.9 XRP ❌ BLOCKED (TVL > 200K = outside MC sweet spot)
BLOCKED_STRATEGIES = {"trend"}       # hard block
PREFERRED_STRATEGIES = {"burst", "pre_breakout"}  # primary signal sources
