#!/usr/bin/env python3
# "*"* coding: utf-8 -*-")
"""
DKTrenchBot v2 — ALL-IN-ONE SOURCE
Generated: 2026-04-09 | Total modules: 35
======================================================================
WALLET: rKQACag8Td9TrMxBwYJPGRMDV8cxGfKsmF
======================================================================
"""


======================================================================
# CONFIGURATION — config.py
======================================================================

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
SCORE_TRADEABLE    = 45    # 45+ → normal entry — GodMode audit: classifier layer guards quality now
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
MIN_TVL_XRP        = 200    # lower floor — catch the PHX-type early launchers
TVL_MICRO_CAP_XRP  = 5000   # under 5K XRP TVL = micro sizing (was 2K, too tight)
MIN_TVL_DROP_EXIT  = 0.40   # exit if TVL drops >40% in one cycle (pool draining)

# ── Exit System — 4-tier TP + Tight Stale ─────────────────────────────────────
# DATA: Stale exits = 40% of trades, all losses. Cut timer in half.
STALE_EXIT_HOURS   = 3.0    # raised from 0.97hr — stale exits at 1hr were killing flat-but-valid positions
MAX_HOLD_HOURS     = 12.0   # extended — PHX-type runners need 8-12hr to fully develop

HARD_STOP_PCT = 15   # warden tightened: loss > win
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
MAX_POSITION_XRP = 15.0  # Hard ceiling per trade — reduced from 40 to protect capital

# ── ML Pipeline ───────────────────────────────────────────────────────────────
ML_ENABLED = True  # Enable ML feature logging and (when ready) predictions


======================================================================
# STATE_MANAGEMENT — state.py
======================================================================

"""
state.py — Single source of truth for positions, trade history, and performance.
Always persists to disk. Thread-safe via file locking pattern.
"""

import json
import os
import time
from typing import Any, Dict, List, Optional
from config import STATE_DIR

os.makedirs(STATE_DIR, exist_ok=True)

STATE_FILE = os.path.join(STATE_DIR, "state.json")


def _default_state() -> Dict:
    return {
        "positions": {},           # token_key -> position dict
        "trade_history": [],       # list of completed trades
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
        "score_overrides": {},     # from improve.py
        "last_reconcile": 0,
        "last_improve": 0,
        "last_hygiene": 0,
    }


def load() -> Dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
            # Merge any missing keys from default
            default = _default_state()
            for k, v in default.items():
                if k not in data:
                    data[k] = v
            return data
        except Exception:
            pass
    return _default_state()


def save(state: Dict) -> None:
    state["performance"]["last_updated"] = time.time()
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        # Fallback: write directly if atomic rename fails
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)


def add_position(state: Dict, token_key: str, position: Dict) -> None:
    """Add or update a position."""
    state["positions"][token_key] = position
    save(state)


def remove_position(state: Dict, token_key: str) -> Optional[Dict]:
    """Remove and return a position."""
    pos = state["positions"].pop(token_key, None)
    if pos:
        save(state)
    return pos


def record_trade(state: Dict, trade: Dict) -> None:
    """Record a completed trade and update performance metrics."""
    state["trade_history"].append(trade)
    # Keep last 500 trades
    if len(state["trade_history"]) > 500:
        state["trade_history"] = state["trade_history"][-500:]

    perf = state["performance"]
    perf["total_trades"] += 1
    pnl_xrp    = float(trade.get("pnl_xrp", 0.0) or 0.0)
    pnl_pct    = float(trade.get("pnl_pct",  0.0) or 0.0)
    exit_reason = trade.get("exit_reason", "")
    perf["total_pnl_xrp"] += pnl_xrp

    # Skip dust trades from performance metrics
    # FIX: use pnl_xrp (real money) not pnl_pct (can be positive % on reduced position)
    if abs(pnl_xrp) < 0.1:
        perf["total_trades"] -= 1  # don't count dust exits
        return

    # FIX: Win/Loss determined by pnl_xrp (actual XRP profit), NOT pnl_pct.
    # pnl_pct can be positive (price went up) while pnl_xrp is negative
    # because partial sells (TP1/TP2) reduced the position size.
    if pnl_xrp > 0.1:
        perf["wins"] += 1
        perf["consecutive_losses"] = 0
        # best_trade_pct: use pnl_pct only when it agrees with pnl_xrp direction
        if pnl_pct > 0 and pnl_pct > perf["best_trade_pct"]:
            perf["best_trade_pct"] = pnl_pct
    elif pnl_xrp < -0.1:
        perf["losses"] += 1
        # Orphan cleanups / forced timeouts are NOT real signal losses
        # Don't let cleanup operations trigger danger regime
        forced_exits = {"orphan_timeout_1hr", "orphan_profit_take", "dead_token"}
        if exit_reason not in forced_exits:
            perf["consecutive_losses"] += 1
        else:
            perf["consecutive_losses"] = 0  # cleanup exits reset the streak
        if pnl_pct < 0 and pnl_pct < perf["worst_trade_pct"]:
            perf["worst_trade_pct"] = pnl_pct
    else:
        perf["consecutive_losses"] = 0  # near-zero scratch

    # FIX: Rolling win rate uses pnl_xrp not pnl_pct
    recent = [t for t in state["trade_history"][-30:] if abs(float(t.get("pnl_xrp", 0) or 0)) >= 0.1]
    if len(recent) >= 5:
        recent_wins = sum(1 for t in recent if float(t.get("pnl_xrp", 0) or 0) > 0.1)
        perf["win_rate"] = recent_wins / len(recent)
    else:
        total = perf["wins"] + perf["losses"]
        perf["win_rate"] = perf["wins"] / total if total > 0 else 0.5
    save(state)


def get_recent_trades(state: Dict, n: int = 20) -> List[Dict]:
    return state["trade_history"][-n:]


def position_key(symbol: str, issuer: str) -> str:
    return f"{symbol}:{issuer}"


if __name__ == "__main__":
    s = load()
    print(f"Positions: {len(s['positions'])}")
    print(f"Trades: {len(s['trade_history'])}")
    print(f"Win rate: {s['performance']['win_rate']:.1%}")
    print(f"PnL: {s['performance']['total_pnl_xrp']:.4f} XRP")

======================================================================
# RECONCILE — reconcile.py
======================================================================

"""
reconcile.py — On startup and every 30 min: sync chain state with local state.
Rebuilds positions if discrepancy. Cancels stale offers.
Writes: state/reconcile.log
"""

import json
import os
import time
import logging
import requests
from typing import Dict, List, Optional
from config import CLIO_URL, STATE_DIR, BOT_WALLET_ADDRESS, WS_URL, get_currency
import state as state_mod

os.makedirs(STATE_DIR, exist_ok=True)
RECONCILE_LOG = os.path.join(STATE_DIR, "reconcile.log")

logger = logging.getLogger("reconcile")


def _rpc(method: str, params: dict) -> Optional[dict]:
    for attempt in range(3):
        try:
            resp = requests.post(CLIO_URL, json={"method": method, "params": [params]}, timeout=15)
            data = resp.json()
            result = data.get("result")
            if isinstance(result, dict) and result.get("error") == "slowDown":
                time.sleep(1.0 * (attempt + 1))
                continue
            return result
        except Exception:
            time.sleep(0.5)
    return None


def _log(msg: str) -> None:
    ts  = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    with open(RECONCILE_LOG, "a") as f:
        f.write(line)
    logger.info(msg)


def get_chain_balances() -> Dict:
    """Get XRP balance and all token balances from chain."""
    result = _rpc("account_info", {
        "account":      BOT_WALLET_ADDRESS,
        "ledger_index": "validated",
    })
    xrp_balance = 0.0
    if result and result.get("status") == "success":
        xrp_balance = int(result["account_data"]["Balance"]) / 1e6

    # Token balances
    lines_result = _rpc("account_lines", {
        "account":      BOT_WALLET_ADDRESS,
        "ledger_index": "validated",
    })
    token_balances = {}
    if lines_result and lines_result.get("status") == "success":
        for line in lines_result.get("lines", []):
            bal = float(line.get("balance", 0))
            if bal > 0:
                key = f"{line['currency']}:{line['account']}"
                token_balances[key] = bal

    return {"xrp": xrp_balance, "tokens": token_balances}


def get_open_offers() -> List[Dict]:
    """Get all open DEX offers for bot wallet."""
    result = _rpc("account_offers", {
        "account":      BOT_WALLET_ADDRESS,
        "ledger_index": "validated",
    })
    if result and result.get("status") == "success":
        return result.get("offers", [])
    return []


def cancel_offer(sequence: int) -> bool:
    """Cancel a specific offer by sequence number."""
    try:
        from xrpl.clients import WebsocketClient
        from xrpl.models.transactions import OfferCancel
        from xrpl.transaction import submit_and_wait
        from execution import _get_wallet

        wallet = _get_wallet()
        tx = OfferCancel(
            account          = wallet.address,
            offer_sequence   = sequence,
        )
        with WebsocketClient(WS_URL) as ws:
            response = submit_and_wait(tx, ws, wallet)
            return response.is_successful()
    except Exception as e:
        _log(f"ERROR cancel_offer seq={sequence}: {e}")
        return False


def reconcile(bot_state: Dict, cancel_stale_hours: float = 2.0) -> Dict:
    """
    Full reconciliation run.
    Returns summary dict.
    """
    _log("=== Reconcile start ===")
    start_ts = time.time()

    chain = get_chain_balances()
    _log(f"Chain XRP balance: {chain['xrp']:.4f}")
    _log(f"Chain tokens: {list(chain['tokens'].keys())}")

    # SAFETY: if chain returned no data at all (RPC slowDown/failure), abort — don't wipe positions
    n_local_positions = len(bot_state.get("positions", {}))
    if chain["xrp"] == 0.0 and len(chain["tokens"]) == 0 and n_local_positions > 0:
        _log(f"⚠️  Chain returned empty data but we have {n_local_positions} local positions — RPC likely slowDown. Aborting reconcile to protect positions.")
        return {"ts": time.time(), "xrp_balance": 0, "chain_tokens": 0, "discrepancies": 0, "offers_cancelled": 0, "duration_ms": 0, "aborted": True}

    # Check for position discrepancies
    positions = bot_state.get("positions", {})
    discrepancies = []

    for pos_key, pos in list(positions.items()):
        symbol = pos.get("symbol", "")
        issuer = pos.get("issuer", "")
        currency = get_currency(symbol)
        chain_key_hex  = f"{currency}:{issuer}"
        chain_key_raw  = f"{symbol}:{issuer}"

        chain_bal = chain["tokens"].get(chain_key_hex) or chain["tokens"].get(chain_key_raw, 0)
        local_bal = pos.get("tokens_held", 0)

        if chain_bal <= 0 and local_bal > 0:
            _log(f"DISCREPANCY: {symbol} has local={local_bal} but chain=0 — removing position")
            discrepancies.append(pos_key)
            state_mod.remove_position(bot_state, pos_key)
        elif abs(chain_bal - local_bal) / max(local_bal, 1) > 0.05:
            _log(f"DISCREPANCY: {symbol} local={local_bal:.4f} chain={chain_bal:.4f} — updating")
            bot_state["positions"][pos_key]["tokens_held"] = chain_bal
            discrepancies.append(pos_key)

    # Check for tokens on chain not in positions (orphaned positions)
    # DATA AUDIT 2026-04-06: orphan adoption = 14% WR, -8.5 XRP avg loss. Don't ADOPT, but DO sell.
    KEEP_TOKENS = {"PHX"}  # tokens to never auto-sell
    for chain_key, balance in chain["tokens"].items():
        if balance <= 0.001:
            continue
        # Skip if already tracked as a position
        if any(chain_key.startswith(pos.get("symbol","")) or chain_key.endswith(pos.get("issuer","")) for pos in positions.values()):
            continue
        if chain_key in positions:
            continue
        currency, _, issuer = chain_key.partition(":")
        # Skip known KEEP tokens
        symbol_short = currency.strip("0")[:6] if len(currency) > 6 else currency.strip()
        if any(k in chain_key.upper() for k in KEEP_TOKENS):
            _log(f"ORPHAN token on chain: {chain_key} balance={balance:.6f} — KEEPING (KEEP_TOKENS)")
            continue
        _log(f"ORPHAN token on chain: {chain_key} balance={balance:.6f} — attempting sell to recover XRP")
        try:
            from execution import sell_token
            import scanner as _sc
            _live_price, _, _, _ = _sc.get_token_price_and_tvl(currency, issuer)
            if not _live_price:
                _log(f"⚠️  Cannot fetch live price for {chain_key} — skipping orphan sell")
                continue
            sell_result = sell_token(
                symbol         = currency,
                issuer         = issuer,
                token_amount   = balance,
                expected_price = _live_price,
                slippage_tolerance = 0.15,
            )
            if sell_result.get("success"):
                _log(f"✅ Orphan sell succeeded: {chain_key} → {sell_result.get('xrp_received', 0):.4f} XRP")
            else:
                _log(f"❌ Orphan sell failed: {chain_key}: {sell_result.get('error','unknown')}")
                orphans = bot_state.setdefault("orphan_positions", {})
                orphans[currency] = {"tokens": balance, "issuer": issuer, "currency": currency, "ts": time.time()}
        except Exception as _oe:
            _log(f"❌ Orphan sell exception: {chain_key}: {_oe}")

    # Cancel stale offers
    offers = get_open_offers()
    cancelled = 0
    for offer in offers:
        _log(f"Open offer seq={offer.get('seq')} — cancelling stale offer")
        if cancel_offer(offer.get("seq", 0)):
            cancelled += 1

    # Update state
    bot_state["last_reconcile"] = start_ts
    state_mod.save(bot_state)

    summary = {
        "ts":              start_ts,
        "xrp_balance":     chain["xrp"],
        "chain_tokens":    len(chain["tokens"]),
        "discrepancies":   len(discrepancies),
        "offers_cancelled": cancelled,
        "duration_ms":     int((time.time() - start_ts) * 1000),
    }
    _log(f"Reconcile done: {summary}")
    return summary


if __name__ == "__main__":
    s = state_mod.load()
    result = reconcile(s)
    print(result)

======================================================================
# WALLET_HYGIENE — wallet_hygiene.py
======================================================================

"""
wallet_hygiene.py — On startup + daily:
  - Liquidate dust positions (< 0.5 XRP value)
  - Close zero-balance trustlines
  - Cancel old/orphaned offers
Writes: state/hygiene.log
"""

import json
import os
import time
import logging
import requests
from typing import Dict, List, Optional
from config import CLIO_URL, STATE_DIR, BOT_WALLET_ADDRESS, WS_URL, get_currency
import state as state_mod

os.makedirs(STATE_DIR, exist_ok=True)
HYGIENE_LOG = os.path.join(STATE_DIR, "hygiene.log")

logger = logging.getLogger("wallet_hygiene")
DUST_XRP_VALUE = 2.0  # anything under 2 XRP value = dust, not worth keeping trustline reserve


def _rpc(method: str, params: dict) -> Optional[dict]:
    try:
        resp = requests.post(CLIO_URL, json={"method": method, "params": [params]}, timeout=15)
        return resp.json().get("result")
    except Exception:
        return None


def _log(msg: str) -> None:
    ts   = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    with open(HYGIENE_LOG, "a") as f:
        f.write(line)
    logger.info(msg)


def _get_wallet():
    from execution import _get_wallet as _gw
    return _gw()


def get_all_trustlines() -> List[Dict]:
    result = _rpc("account_lines", {
        "account":      BOT_WALLET_ADDRESS,
        "ledger_index": "validated",
    })
    if result and result.get("status") == "success":
        return result.get("lines", [])
    return []


def get_token_price_xrp(currency: str, issuer: str) -> float:
    """Estimate token price in XRP via AMM."""
    result = _rpc("amm_info", {
        "asset":  {"currency": "XRP"},
        "asset2": {"currency": currency, "issuer": issuer},
    })
    if result and result.get("status") == "success":
        amm = result.get("amm", {})
        try:
            xrp   = int(amm["amount"]) / 1e6
            token = float(amm["amount2"]["value"])
            return xrp / token if token > 0 else 0.0
        except Exception:
            pass
    return 0.0


def close_trustline(currency: str, issuer: str) -> bool:
    """
    Close a zero-balance trustline by setting limit to 0.
    """
    try:
        from xrpl.clients import WebsocketClient
        from xrpl.models.transactions import TrustSet
        from xrpl.models.amounts import IssuedCurrencyAmount
        from xrpl.transaction import submit_and_wait

        wallet = _get_wallet()
        tx = TrustSet(
            account    = wallet.address,
            limit_amount = IssuedCurrencyAmount(
                currency = currency,
                issuer   = issuer,
                value    = "0",
            ),
        )
        with WebsocketClient(WS_URL) as ws:
            response = submit_and_wait(tx, ws, wallet)
            return response.is_successful()
    except Exception as e:
        _log(f"ERROR close_trustline {currency}:{issuer}: {e}")
        return False


def sell_dust(currency: str, issuer: str, balance: float,
              price_xrp: float) -> bool:
    """Sell dust token balance."""
    try:
        from execution import sell_token
        result = sell_token(
            symbol         = currency if len(currency) <= 3 else currency,
            issuer         = issuer,
            token_amount   = balance,
            expected_price = price_xrp,
            slippage_tolerance = 0.10,  # wider tolerance for dust
        )
        return result.get("success", False)
    except Exception as e:
        _log(f"ERROR sell_dust {currency}: {e}")
        return False


def cancel_old_offers() -> int:
    """Cancel all open offers."""
    from reconcile import get_open_offers, cancel_offer
    offers    = get_open_offers()
    cancelled = 0
    for offer in offers:
        seq = offer.get("seq", 0)
        _log(f"Cancelling offer seq={seq}")
        if cancel_offer(seq):
            cancelled += 1
    return cancelled


def run_hygiene(bot_state: Dict, force: bool = False) -> Dict:
    """
    Run wallet hygiene. Skip if run in last 23 hours (unless force=True).
    """
    last = bot_state.get("last_hygiene", 0)
    if not force and (time.time() - last) < 4 * 3600:  # run every 4hr (was 23hr)
        return {"skipped": True, "reason": "ran_recently"}

    _log("=== Hygiene start ===")
    start_ts = time.time()

    lines         = get_all_trustlines()
    dust_sold     = 0
    lines_closed  = 0
    cancelled     = 0

    for line in lines:
        currency = line.get("currency", "")
        issuer   = line.get("account", "")
        balance  = float(line.get("balance", 0))

        if balance <= 0:
            # Zero balance — close trustline
            _log(f"Closing zero-balance trustline: {currency}:{issuer}")
            if close_trustline(currency, issuer):
                lines_closed += 1
            continue

        # Check if dust
        price_xrp = get_token_price_xrp(currency, issuer)
        value_xrp = balance * price_xrp

        if 0 < value_xrp < DUST_XRP_VALUE:
            if value_xrp < 0.5:
                # Gas cost > proceeds — abandon without selling, just close line
                _log(f"Abandoning micro-dust: {currency} = {value_xrp:.4f} XRP (gas > value)")
                time.sleep(1)
                if close_trustline(currency, issuer):
                    lines_closed += 1
            else:
                _log(f"Selling dust: {balance:.4f} {currency} = {value_xrp:.4f} XRP")
                sold = sell_dust(currency, issuer, balance, price_xrp)
                if sold:
                    dust_sold += 1
                    time.sleep(1)
                    if close_trustline(currency, issuer):
                        lines_closed += 1

    # Cancel any stale offers
    cancelled = cancel_old_offers()

    bot_state["last_hygiene"] = start_ts
    state_mod.save(bot_state)

    summary = {
        "ts":           start_ts,
        "dust_sold":    dust_sold,
        "lines_closed": lines_closed,
        "offers_cancelled": cancelled,
        "duration_ms":  int((time.time() - start_ts) * 1000),
    }
    _log(f"Hygiene done: {summary}")
    return summary


if __name__ == "__main__":
    s = state_mod.load()
    result = run_hygiene(s, force=True)
    print(result)

======================================================================
# SCANNER — scanner.py
======================================================================

"""
scanner.py — Token discovery, AMM data collection, and momentum bucketing.
Fetches AMM pool data for all registry tokens and ranks by momentum.
Writes: state/scan_results.json
"""

import json
import logging
import os
import time
import requests
from typing import Dict, List, Optional, Tuple
from config import CLIO_URL, STATE_DIR, TOKEN_REGISTRY, MIN_TVL_XRP, get_currency

os.makedirs(STATE_DIR, exist_ok=True)

SCAN_HISTORY_FILE  = os.path.join(STATE_DIR, "scan_history.json")
SCAN_RESULTS_FILE  = os.path.join(STATE_DIR, "scan_results.json")
ACTIVE_REGISTRY_FILE = os.path.join(STATE_DIR, "active_registry.json")


def _load_active_registry():
    """
    Load the dynamic registry from discovery.py if available.
    Falls back to backup, then static TOKEN_REGISTRY from config.py.
    """
    for path in [ACTIVE_REGISTRY_FILE, ACTIVE_REGISTRY_FILE.replace(".json", "_backup.json")]:
        try:
            with open(path) as f:
                data = json.load(f)
            tokens = data.get("tokens", [])
            if len(tokens) >= 10:
                return tokens
        except:
            pass
    return TOKEN_REGISTRY

# In-memory price history: token_key -> list of (timestamp, price, tvl)
_price_history: Dict[str, List] = {}


def _rpc(method: str, params: dict) -> Optional[dict]:
    for attempt in range(3):
        try:
            resp = requests.post(CLIO_URL, json={"method": method, "params": [params]}, timeout=15)
            data = resp.json()
            result = data.get("result")
            # Retry on slowDown
            if isinstance(result, dict) and result.get("error") == "slowDown":
                time.sleep(1.0 * (attempt + 1))
                continue
            return result
        except Exception:
            time.sleep(0.5)
    return None


def get_amm_info(symbol: str, issuer: str, currency: str = None) -> Optional[Dict]:
    """Fetch AMM pool info for a token/XRP pair.
    Pass currency directly if known (avoids get_currency() recomputation errors)."""
    if not currency:
        currency = get_currency(symbol)
    result = _rpc("amm_info", {
        "asset":  {"currency": "XRP"},
        "asset2": {"currency": currency, "issuer": issuer},
    })
    if result and result.get("status") == "success":
        return result.get("amm")
    return None


def calc_price(amm: Dict) -> Optional[float]:
    """AMM price: XRP per token. amount=XRP drops, amount2=token."""
    try:
        xrp_drops = int(amm["amount"])
        token_val  = float(amm["amount2"]["value"])
        if token_val == 0:
            return None
        return (xrp_drops / 1e6) / token_val
    except Exception:
        return None


def calc_tvl_xrp(amm: Dict) -> float:
    """TVL in XRP = 2x the XRP side of the pool."""
    try:
        return (int(amm["amount"]) / 1e6) * 2
    except Exception:
        return 0.0


def get_clob_price(symbol: str, issuer: str, currency: str = None) -> Optional[float]:
    """Get best CLOB offer price (XRP per token) for tokens without AMM."""
    if not currency:
        currency = get_currency(symbol)
    result = _rpc("book_offers", {
        "taker_pays": {"currency": "XRP"},
        "taker_gets": {"currency": currency, "issuer": issuer},
        "limit": 5,
    })
    if not result:
        return None
    offers = result.get("offers", [])
    if not offers:
        return None
    try:
        best = offers[0]
        xrp_pays = int(best["TakerPays"]) / 1e6
        tok_gets  = float(best["TakerGets"]["value"])
        if tok_gets == 0:
            return None
        return xrp_pays / tok_gets
    except Exception:
        return None


def get_clob_tvl(symbol: str, issuer: str, currency: str = None) -> float:
    """Estimate CLOB depth (XRP) from top 10 offers."""
    if not currency:
        currency = get_currency(symbol)
    result = _rpc("book_offers", {
        "taker_pays": {"currency": "XRP"},
        "taker_gets": {"currency": currency, "issuer": issuer},
        "limit": 10,
    })
    if not result:
        return 0.0
    offers = result.get("offers", [])
    total = 0.0
    for o in offers:
        try:
            total += int(o["TakerPays"]) / 1e6
        except Exception:
            pass
    return total


def get_token_price_and_tvl(symbol: str, issuer: str, currency: str = None):
    """Unified price+TVL: tries AMM first, falls back to CLOB. Returns (price, tvl, source, amm).
    Pass currency from registry to avoid get_currency() recomputation errors."""
    amm = get_amm_info(symbol, issuer, currency=currency)
    if amm:
        price = calc_price(amm)
        tvl   = calc_tvl_xrp(amm)
        if price:
            return price, tvl, "amm", amm
    # Fallback: CLOB
    price = get_clob_price(symbol, issuer, currency=currency)
    tvl   = get_clob_tvl(symbol, issuer, currency=currency) if price else 0.0
    return price, tvl, "clob", None


def token_key(symbol: str, issuer: str) -> str:
    return f"{symbol}:{issuer}"


def _load_history() -> Dict:
    if os.path.exists(SCAN_HISTORY_FILE):
        try:
            with open(SCAN_HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_history(history: Dict) -> None:
    # Keep max 20 readings per token
    for k in history:
        if len(history[k]) > 20:
            history[k] = history[k][-20:]
    with open(SCAN_HISTORY_FILE, "w") as f:
        json.dump(history, f)


def _momentum_bucket(readings: List) -> str:
    """
    Classify token momentum from price history.
    readings: list of {ts, price, tvl}
    """
    if len(readings) < 2:
        return "fresh_momentum"

    prices = [r["price"] for r in readings if r.get("price")]
    if not prices or len(prices) < 2:
        return "dead"

    tvls = [r["tvl"] for r in readings if r.get("tvl", 0) > 0]
    avg_tvl = sum(tvls) / len(tvls) if tvls else 0

    if avg_tvl < MIN_TVL_XRP:
        return "thin_liquidity_trap"

    first_price = prices[0]
    last_price  = prices[-1]
    if first_price <= 0:
        return "dead"

    pct_change = (last_price - first_price) / first_price

    # Check if price is going up or mostly flat/down
    if pct_change <= -0.10:
        return "dead"

    # Count higher lows
    lows = []
    for i in range(1, len(prices)):
        if prices[i] < prices[i - 1]:
            lows.append(prices[i])

    n = len(readings)

    # SPIKE: check last 2 readings for sudden explosive move (2k→45k type)
    if len(prices) >= 2:
        recent_move = (prices[-1] - prices[-2]) / max(prices[-2], 1e-12)
        if recent_move > 0.15:   # 15%+ in single scan interval = SPIKE
            return "fresh_momentum"

    # Late extension: big move already happened
    if pct_change > 0.25 and n > 8:
        return "late_extension"
    # Fresh: strong early move
    if pct_change > 0.08 and n <= 8:
        return "fresh_momentum"
    # Sustained: still moving after many readings
    if pct_change > 0.05 and n > 8:
        return "sustained_momentum"
    # Weak fresh: any positive move >= 0.5%
    if pct_change > 0.005:
        return "fresh_momentum"
    else:
        return "dead"


def _momentum_score(readings: List, bucket: str) -> float:
    """Score 0-100 for ranking within bucket. Higher = stronger momentum."""
    if bucket in ("dead", "thin_liquidity_trap"):
        return 0.0

    if len(readings) < 2:
        return 10.0

    prices = [r["price"] for r in readings if r.get("price")]
    tvls   = [r["tvl"] for r in readings if r.get("tvl", 0) > 0]
    if not prices or prices[0] <= 0:
        return 0.0

    pct_change = (prices[-1] - prices[0]) / prices[0]
    avg_tvl    = sum(tvls) / len(tvls) if tvls else 0

    # SPIKE bonus: sudden move in last interval
    spike_bonus = 0
    if len(prices) >= 2:
        last_move = (prices[-1] - prices[-2]) / max(prices[-2], 1e-12)
        if last_move > 0.30:   # 30%+ spike
            spike_bonus = 25
        elif last_move > 0.15:
            spike_bonus = 12

    # Base score from price move (0-60 pts)
    move_score = min(pct_change * 200, 60)  # 30% move = 60pts

    # TVL score: sweet spot 2K-100K XRP (0-25 pts)
    if 2_000 <= avg_tvl <= 100_000:
        tvl_score = 25
    elif 500 <= avg_tvl < 2_000:
        tvl_score = 15
    elif avg_tvl > 100_000:
        tvl_score = 10  # too big, slow mover
    else:
        tvl_score = 5

    # Recency bonus: is the move recent? (last 3 readings vs earlier)
    recency_score = 0
    if len(prices) >= 4:
        early_chg = (prices[len(prices)//2] - prices[0]) / prices[0]
        late_chg  = (prices[-1] - prices[len(prices)//2]) / prices[len(prices)//2] if prices[len(prices)//2] > 0 else 0
        if late_chg > early_chg:  # accelerating
            recency_score = 15
        elif late_chg > 0:
            recency_score = 8

    total = move_score + tvl_score + recency_score + spike_bonus
    return min(total, 100.0)


def scan() -> Dict:
    """
    Scan all registry tokens. Returns structured results.
    """
    history = _load_history()
    now = time.time()

    results = {
        "fresh_momentum": [],
        "sustained_momentum": [],
        "late_extension": [],
        "thin_liquidity_trap": [],
        "dead": [],
        "scan_time": now,
        "token_data": {},
    }

    active_registry = _load_active_registry()
    for token in active_registry:
        symbol = token["symbol"]
        issuer = token["issuer"]
        key    = token_key(symbol, issuer)

        # Pass registry currency directly — avoids get_currency() recomputation errors
        reg_currency = token.get("currency")
        price, tvl, source, amm = get_token_price_and_tvl(symbol, issuer, currency=reg_currency)
        time.sleep(0.15)  # rate limit protection for CLIO
        if not price:
            # No price from AMM or CLOB — mark dead
            results["dead"].append({"symbol": symbol, "issuer": issuer, "reason": "no_price"})
            continue

        entry = {"ts": now, "price": price, "tvl": tvl}

        if key not in history:
            history[key] = []
        history[key].append(entry)

        readings = history[key]
        bucket   = _momentum_bucket(readings)
        score    = _momentum_score(readings, bucket)

        # TVL change vs 5 readings ago (momentum signal even for thin pools)
        tvl_change_pct = 0.0
        if len(readings) >= 5:
            prev_tvl = readings[-5].get("tvl", 0)
            if prev_tvl > 0 and tvl > 0:
                tvl_change_pct = (tvl - prev_tvl) / prev_tvl
        elif len(readings) >= 2:
            prev_tvl = readings[0].get("tvl", 0)
            if prev_tvl > 0 and tvl > 0:
                tvl_change_pct = (tvl - prev_tvl) / prev_tvl

        # Apply smart wallet score bonus if token was discovered via tracked wallet
        sw_bonus = token.get("score_bonus", 0)
        if sw_bonus > 0:
            score = min(score + sw_bonus, 100)

        # ── Token Intelligence (Lite Haus-style enrichment) ──────────────────
        # holders, top10%, RSI, p5m/1h/24h, buyer pressure, volume, launch age
        intel = {}
        intel_bonus = 0
        try:
            import token_intel as ti
            # Fetch xpmarket index once per scan (cached 4min)
            if not hasattr(scan, "_xpm_index"):
                scan._xpm_index = {}
                scan._xpm_ts = 0
            if time.time() - scan._xpm_ts > 240:
                scan._xpm_index = ti.fetch_xpmarket_index()
                scan._xpm_ts = time.time()

            price_hist = [(ts, p, t) for ts, p, t in readings]
            intel = ti.enrich_token(symbol, issuer, reg_currency or "",
                                    price_hist, scan._xpm_index)
            intel_bonus = ti.score_from_intel(intel)
            if intel:
                logging.getLogger("scanner").debug(
                    ti.format_intel_log(intel) + f" intel_bonus={intel_bonus:+d}")
        except Exception as _ie:
            logging.getLogger("scanner").debug(f"intel error {symbol}: {_ie}")

        # Apply intel bonus to score
        if intel_bonus != 0:
            score = max(0, min(100, score + intel_bonus))

        token_data = {
            "symbol":        symbol,
            "issuer":        issuer,
            "currency":      reg_currency,
            "price":         price,
            "tvl_xrp":       tvl,
            "tvl_change_pct": tvl_change_pct,
            "bucket":        bucket,
            "score":         score,
            "score_bonus":   sw_bonus,
            "intel_bonus":   intel_bonus,
            "intel":         intel,
            "readings":      len(readings),
            "amm":           amm,
            "source":        token.get("source", "registry"),
        }

        results["token_data"][key] = token_data
        results[bucket].append(token_data)

    # Sort each bucket by score desc
    for bucket in ["fresh_momentum", "sustained_momentum", "late_extension", "thin_liquidity_trap"]:
        results[bucket].sort(key=lambda x: x.get("score", 0), reverse=True)

    _save_history(history)

    with open(SCAN_RESULTS_FILE, "w") as f:
        # Don't write full AMM data to keep file small
        slim = {k: v for k, v in results.items() if k != "token_data"}
        slim["token_data"] = {
            k: {fk: fv for fk, fv in v.items() if fk != "amm"}
            for k, v in results["token_data"].items()
        }
        json.dump(slim, f, indent=2)

    return results


def get_candidates(results: Dict, min_bucket_score: float = 0.0) -> List[Dict]:
    """Return tradeable candidates from scan results, sorted by score."""
    candidates = []
    for bucket in ["fresh_momentum", "sustained_momentum"]:
        for t in results.get(bucket, []):
            if t.get("score", 0) >= min_bucket_score:
                candidates.append(t)
    candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
    return candidates


if __name__ == "__main__":
    print("Running scanner...")
    results = scan()
    print(f"Fresh momentum:     {len(results['fresh_momentum'])}")
    print(f"Sustained momentum: {len(results['sustained_momentum'])}")
    print(f"Late extension:     {len(results['late_extension'])}")
    print(f"Thin liquidity:     {len(results['thin_liquidity_trap'])}")
    print(f"Dead:               {len(results['dead'])}")
    candidates = get_candidates(results)
    print(f"Candidates: {[c['symbol'] for c in candidates]}")

======================================================================
# PRE_MOVE_DETECTOR — pre_move_detector.py
======================================================================

"""
pre_move_detector.py — DKTrenchBot v2
Optimized: Scans every cycle, fast-path on existing TrustSet signals, no registry lag.

Framework:
- Registry scan: all known tokens, every cycle
- Fast-path: reads from trustset_watcher + realtime_signals signals — every 30s
- Signal: PRE_ACCUMULATION → WHALE_BUILDING → CONFIRMED_MOVE → SCALING
- Size: 5 XRP initial (pre-explosion entry)
- Scale up on TS confirmation

Config:
- TVL window: $400-$5k AMM pool (est. MC $800-$10k)
- LP supply min: 100k (meaningful liquidity)
- TS burst: >15/hr confirms move started
"""

import json
import time
import logging
import requests
from datetime import datetime, timezone
from collections import defaultdict

CLIO_URL = "https://rpc.xrplclaw.com"
STATE_PATH = "/home/agent/workspace/trading-bot-v2/state/pre_move_state.json"
FAST_PATH_STATE = "/home/agent/workspace/trading-bot-v2/state/pre_move_fastpath.json"

# ── Config ──────────────────────────────────────────────────────────────────────
MIN_TVL_XRP = 400
MAX_TVL_XRP = 5000          # early entry ceiling
MIN_TVL_CHANGE_PCT = 50    # TVL surge = whale accumulating
MAX_POSITION_XRP = 5.0      # small initial — pre-explosion
SCALE_UP_XRP = 10.0        # add to position on TS confirmation
TS_BURST_THRESHOLD = 15    # TS/hr to confirm move
LP_SUPPLY_MIN = 100000      # meaningful LP commitment
FAST_PATH_INTERVAL = 30     # seconds between fast-path runs

XRPL_EPOCH = 946684800

# ── State ──────────────────────────────────────────────────────────────────────
_state = None

def _load_state():
    global _state
    if _state is None:
        try:
            with open(STATE_PATH) as f:
                _state = json.load(f)
        except:
            _state = {"tracked_tokens": {}, "signals": [], "entries": []}
    return _state

def _save_state(state):
    global _state
    state["signals"] = state.get("signals", [])[-100:]
    state["entries"] = state.get("entries", [])[-50:]
    _state = state
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def _rpc(method, params, timeout=15):
    try:
        r = requests.post(CLIO_URL, json={"method": method, "params": [params]}, timeout=timeout)
        return r.json().get("result", {})
    except Exception as e:
        return {"error": str(e)}


def _decode_currency(cur):
    if not cur:
        return ""
    if len(cur) == 40:
        try:
            return bytes.fromhex(cur[:20]).decode("utf-8", "replace").strip("\x00 ")
        except:
            return cur[:10]
    return cur


def _get_amm_state(addr, currency_hex):
    if not currency_hex or not addr:
        return None
    amm = _rpc("amm_info", {
        "asset": {"currency": "XRP"},
        "asset2": {"currency": currency_hex, "issuer": addr},
        "ledger_index": "validated"
    })
    a = amm.get("amm", {})
    if not a:
        return None
    xrp_pool = int(a.get("amount", 0)) / 1e6
    tok_pool = float(a.get("amount2", {}).get("value", 0))
    price = xrp_pool / tok_pool if tok_pool > 0 else 0
    lp_supply = float(a.get("lp_token", {}).get("value", 0))
    fee = int(a.get("trading_fee", 0)) / 10
    return {
        "xrp_pool": xrp_pool, "token_pool": tok_pool, "price": price,
        "lp_supply": lp_supply, "trading_fee": fee, "tvl": xrp_pool * 2
    }


def _get_ts_rate(addr, lookback_hours=2):
    cutoff_ts = int(time.time()) - (lookback_hours * 3600)
    txs = _rpc("account_tx", {
        "account": addr, "limit": 200,
        "forward": True,
        "ledger_index_min": -1, "ledger_index_max": -1
    })
    ts_count = 0
    for tx in txs.get("transactions", []):
        d = tx.get("tx", {})
        date = d.get("date", 0)
        if date and date > 0:
            if (date + XRPL_EPOCH) >= cutoff_ts and d.get("TransactionType") == "TrustSet":
                ts_count += 1
    return ts_count / lookback_hours


def _evaluate_token(addr, currency_hex, prev_state):
    curr = _get_amm_state(addr, currency_hex)
    if not curr:
        return None, None
    
    ts_rate = _get_ts_rate(addr, lookback_hours=2)
    
    # TVL change detection
    tvl_change_pct = 0
    whale_accumulating = False
    price_change_pct = 0
    if prev_state:
        prev_tvl = prev_state.get("xrp_pool", 0) * 2
        curr_tvl = curr["tvl"]
        if prev_tvl > 0:
            tvl_change_pct = (curr_tvl - prev_tvl) / prev_tvl * 100
            if prev_state.get("price", 0) > 0:
                price_change_pct = (curr["price"] - prev_state["price"]) / prev_state["price"] * 100
            whale_accumulating = tvl_change_pct >= MIN_TVL_CHANGE_PCT and abs(price_change_pct) < 10
    
    symbol = _decode_currency(currency_hex) if currency_hex else ""
    
    # SIGNAL 1: PRE-ACCUMULATION
    if (MIN_TVL_XRP <= curr["tvl"] <= MAX_TVL_XRP and
        curr["lp_supply"] > LP_SUPPLY_MIN and
        ts_rate < TS_BURST_THRESHOLD):
        return {
            "symbol": symbol, "addr": addr, "currency": currency_hex,
            "signal": "pre_accumulation", "confidence": 80,
            "reason": f"TVL={curr['tvl']:.0f} XRP (${curr['tvl']*2:.0f} MC) | LP={curr['lp_supply']:.0f} | fee={curr['trading_fee']:.1f}% | TS/hr={ts_rate:.0f}",
            "recommendation": "enter_5x",
            "tvl": curr["tvl"], "price": curr["price"],
            "lp_supply": curr["lp_supply"], "fee": curr["trading_fee"],
            "ts_rate": ts_rate, "tvl_change_pct": tvl_change_pct
        }, curr
    
    # SIGNAL 2: WHALE BUILDING — TVL surged 50%+ but price stable
    if whale_accumulating:
        return {
            "symbol": symbol, "addr": addr, "currency": currency_hex,
            "signal": "whale_building", "confidence": 82,
            "reason": f"TVL +{tvl_change_pct:.0f}% | price stable ({price_change_pct:.1f}%) — whale accumulating",
            "recommendation": "enter_5x",
            "tvl": curr["tvl"], "price": curr["price"],
            "lp_supply": curr["lp_supply"], "fee": curr["trading_fee"],
            "ts_rate": ts_rate, "tvl_change_pct": tvl_change_pct
        }, curr
    
    # SIGNAL 3: CONFIRMED MOVE
    if ts_rate >= TS_BURST_THRESHOLD and MIN_TVL_XRP * 0.5 <= curr["tvl"] <= MAX_TVL_XRP * 3:
        return {
            "symbol": symbol, "addr": addr, "currency": currency_hex,
            "signal": "confirmed_move", "confidence": 85,
            "reason": f"TS burst {ts_rate:.0f}/hr — move confirmed | TVL={curr['tvl']:.0f} XRP",
            "recommendation": "scale_up",
            "tvl": curr["tvl"], "price": curr["price"],
            "lp_supply": curr["lp_supply"], "fee": curr["trading_fee"],
            "ts_rate": ts_rate, "tvl_change_pct": tvl_change_pct
        }, curr
    
    # SIGNAL 4: MID-TVL SCALING
    if (curr["tvl"] > MAX_TVL_XRP and curr["tvl"] <= 15000 and
        curr["lp_supply"] > LP_SUPPLY_MIN and
        ts_rate >= TS_BURST_THRESHOLD / 2):
        return {
            "symbol": symbol, "addr": addr, "currency": currency_hex,
            "signal": "scaling", "confidence": 70,
            "reason": f"Post-launch TVL={curr['tvl']:.0f} XRP | TS={ts_rate:.0f}/hr — scaling phase",
            "recommendation": "scale_up",
            "tvl": curr["tvl"], "price": curr["price"],
            "lp_supply": curr["lp_supply"], "fee": curr["trading_fee"],
            "ts_rate": ts_rate, "tvl_change_pct": tvl_change_pct
        }, curr
    
    return None, curr


def _scan_registry():
    try:
        with open("/home/agent/workspace/trading-bot-v2/state/active_registry.json") as f:
            raw = json.load(f)
        return raw.get("tokens", [])
    except:
        return []


def _scan_fast_path():
    """
    FAST PATH: Uses existing signals from trustset_watcher and realtime_watcher.
    These already run every cycle and catch TrustSet burst activity.
    We check the AMM state for their issuers directly.
    Throttled to every 30 seconds.
    """
    try:
        with open(FAST_PATH_STATE) as f:
            fp_state = json.load(f)
    except:
        fp_state = {"last_run": 0, "hot_issuers": {}}
    
    if time.time() - fp_state.get("last_run", 0) < FAST_PATH_INTERVAL:
        return []
    
    fp_state["last_run"] = int(time.time())
    new_signals = []
    state = _load_state()
    tracked = state.get("tracked_tokens", {})
    
    # Collect issuers from trustset_signals.json
    hot_issuers = {}
    
    # From trustset_signals.json
    try:
        with open("/home/agent/workspace/trading-bot-v2/state/trustset_signals.json") as f:
            content = f.read().strip()
            if content:
                ts_data = json.loads(content)
                if isinstance(ts_data, list):
                    for sig in ts_data:
                        if isinstance(sig, dict) and sig.get("issuer"):
                            iss = sig["issuer"]
                            hot_issuers[iss] = max(hot_issuers.get(iss, 0), sig.get("burst_count", 0))
    except Exception:
        pass
    
    # From realtime_signals.json
    try:
        with open("/home/agent/workspace/trading-bot-v2/state/realtime_signals.json") as f:
            content = f.read().strip()
            if content:
                rt_data = json.loads(content)
                if isinstance(rt_data, dict):
                    va = rt_data.get("velocity_alerts", {})
                    if isinstance(va, dict):
                        for iss, sig in va.items():
                            if isinstance(sig, dict):
                                hot_issuers[iss] = max(hot_issuers.get(iss, 0), sig.get("burst_count", 0))
    except Exception:
        pass
    
    for addr, ts_count in hot_issuers.items():
        # Get currency from account_lines
        lines = _rpc("account_lines", {"account": addr, "limit": 5})
        currency = None
        for line in lines.get("lines", []):
            cur = line.get("currency", "")
            if cur and cur not in ("XRP", ""):
                currency = cur
                break
        if not currency:
            continue
        
        prev = tracked.get(addr, {}).get("last_state")
        sig, curr_state = _evaluate_token(addr, currency, prev)
        
        if sig:
            sig["fast_path"] = True
            sig["ts_count_recent"] = ts_count
            new_signals.append(sig)
            
            if addr not in tracked:
                tracked[addr] = {"signals": [], "entries": [], "last_state": None}
            tracked[addr]["last_state"] = curr_state
    
    fp_state["hot_issuers"] = hot_issuers
    with open(FAST_PATH_STATE, "w") as f:
        json.dump(fp_state, f)
    
    return new_signals


def run_scan():
    state = _load_state()
    tracked = state.get("tracked_tokens", {})
    signals = state.get("signals", [])
    entries = state.get("entries", [])
    
    new_signals = []
    new_entries = []
    
    # ── 1. Registry scan ────────────────────────────────────────────────────────
    registry = _scan_registry()
    tokens_checked = 0
    tokens_in_range = 0
    
    for data in registry:
        tvl = data.get("tvl_xrp", 0)
        if tvl < MIN_TVL_XRP:
            continue
        
        tokens_checked += 1
        currency = data.get("currency", "")
        addr = data.get("issuer", "")
        if not currency or not addr:
            continue
        
        if not (MIN_TVL_XRP <= tvl <= MAX_TVL_XRP * 10):
            continue
        
        tokens_in_range += 1
        prev = tracked.get(addr, {}).get("last_state")
        sig, curr_state = _evaluate_token(addr, currency, prev)
        
        if sig and not sig.get("fast_path"):
            sig["fast_path"] = False
            new_signals.append(sig)
            if sig["recommendation"] in ["enter_5x", "enter_3x", "scale_up"]:
                new_entries.append({
                    "ts": time.time(),
                    "symbol": sig["symbol"],
                    "addr": sig["addr"],
                    "currency": sig["currency"],
                    "signal": sig["signal"],
                    "confidence": sig["confidence"],
                    "reason": sig["reason"],
                    "recommendation": sig["recommendation"],
                    "tvl": sig["tvl"],
                    "price": sig["price"],
                    "size_xrp": 5.0 if sig["recommendation"] == "enter_5x" else 3.0,
                    "fast_path": False,
                    "injected": False
                })
            
            if addr not in tracked:
                tracked[addr] = {"signals": [], "entries": [], "last_state": None}
            tracked[addr]["last_state"] = curr_state
    
    # ── 2. Fast-path scan ──────────────────────────────────────────────────────
    fp_signals = _scan_fast_path()
    for sig in fp_signals:
        sig["fast_path"] = True
        new_signals.append(sig)
        if sig["recommendation"] in ["enter_5x", "enter_3x", "scale_up"]:
            if not any(e.get("addr") == sig["addr"] and e.get("currency") == sig["currency"] for e in new_entries):
                new_entries.append({
                    "ts": time.time(),
                    "symbol": sig["symbol"],
                    "addr": sig["addr"],
                    "currency": sig["currency"],
                    "signal": sig["signal"],
                    "confidence": sig["confidence"],
                    "reason": sig["reason"] + f" | [FAST-PATH {sig.get('ts_count_recent', 0)} TS]",
                    "recommendation": sig["recommendation"],
                    "tvl": sig["tvl"],
                    "price": sig["price"],
                    "size_xrp": 5.0,
                    "fast_path": True,
                    "injected": False
                })
    
    for sig in fp_signals:
        addr = sig["addr"]
        currency = sig["currency"]
        if addr not in tracked:
            tracked[addr] = {"signals": [], "entries": [], "last_state": None}
        curr = _get_amm_state(addr, currency)
        if curr:
            tracked[addr]["last_state"] = curr
    
    # ── Cap signals ───────────────────────────────────────────────────────────
    cutoff = time.time() - 3600
    signals = [s for s in signals if s.get("ts", 0) > cutoff] + new_signals
    entries = [e for e in entries if e.get("ts", 0) > time.time() - 300] + new_entries
    signals = signals[-100:]
    entries = entries[-50:]
    
    state["tracked_tokens"] = tracked
    state["signals"] = signals
    state["entries"] = entries
    _save_state(state)
    
    pre_acc = [s for s in new_signals if s.get("signal") == "pre_accumulation"]
    confirmed = [s for s in new_signals if s.get("signal") == "confirmed_move"]
    whales = [s for s in new_signals if s.get("signal") == "whale_building"]
    fast_path_hits = [s for s in new_signals if s.get("fast_path")]
    
    return {
        "tokens_checked": tokens_checked,
        "tokens_in_range": tokens_in_range,
        "new_signals": len(new_signals),
        "pre_accumulation": len(pre_acc),
        "confirmed_move": len(confirmed),
        "whale_building": len(whales),
        "fast_path_hits": len(fast_path_hits),
        "entries_ready": new_entries
    }


if __name__ == "__main__":
    result = run_scan()
    print(json.dumps(result, indent=2))


def inject_to_bot():
    """
    Called each cycle from bot.py.
    Writes pre_move_signals.json for bot.py to inject as candidates.
    """
    result = run_scan()
    
    inject_file = "/home/agent/workspace/trading-bot-v2/state/pre_move_signals.json"
    if result["entries_ready"]:
        with open(inject_file, "w") as f:
            json.dump({
                "ts": time.time(),
                "signals": result["entries_ready"]
            }, f, indent=2)
        try:
            logger = logging.getLogger("pre_move_detector")
            fp = result.get("fast_path_hits", 0)
            fp_tag = f" [⚡ {fp} fast-path]" if fp else ""
            for e in result["entries_ready"][:5]:
                logger.info(f"📡 PRE-MOVE: {e['symbol']} | {e['reason'][:60]}{fp_tag}")
        except Exception:
            pass
    
    return result
======================================================================
# CLASSIFIER — classifier.py
======================================================================

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

======================================================================
# DISAGREEMENT_ENGINE — disagreement.py
======================================================================

"""
disagreement.py — Disagreement Engine for DKTrenchBot v2

A second-opinion layer that challenges every entry signal before execution.
When the classifier says "enter", the disagreement engine asks hard questions.
A veto from any critical check kills the trade — no overrides.

Architecture:
    Signal Layer  → "BURST — enter PHASER"
    Disagree Layer→ checks 6 independent signals
    If ≥1 VETO   → skip, log reason
    If 0 VETO    → proceed, log confidence

Checks (in order):
    1. Rug fingerprint    — issuer wallet age, supply concentration
    2. Fake burst         — TrustSets from same wallet cluster (wash)
    3. Liquidity trap     — TVL added by one wallet only
    4. Smart money veto   — smart wallets SELLING when we want to BUY
    5. Hard blacklist     — known rug/dump patterns
    6. Regime veto        — market in danger mode, skip lower-quality signals

Each check returns: ("pass"|"veto"|"warn", reason, confidence_adj)
confidence_adj: float added to/subtracted from entry confidence score
"""

import json, os, time, logging, requests
from typing import Dict, Tuple, Optional

logger = logging.getLogger("disagreement")

CLIO = os.environ.get("CLIO_URL", "https://rpc.xrplclaw.com")
XRPL_EPOCH = 946684800
STATE_DIR = os.path.join(os.path.dirname(__file__), "state")
VETO_LOG  = os.path.join(STATE_DIR, "disagreement_log.json")

# ── Thresholds ─────────────────────────────────────────────────────────────────
ISSUER_AGE_MIN_HOURS  = 0.5    # issuer wallet must exist ≥30 min (fresh = rug risk)
CONCENTRATION_VETO    = 0.90   # top holder > 90% supply = almost certainly a rug
CONCENTRATION_WARN    = 0.70   # top holder > 70% = warn, reduce size
FAKE_BURST_VETO_PCT   = 0.80   # if 80%+ of TrustSets from <3 wallets = wash
MIN_UNIQUE_TRUSTSETS  = 3      # need at least 3 unique wallets setting trust
LIQUIDITY_SINGLE_WALLET = 0.95 # if 95%+ of TVL from one LP provider = trap
SMART_SELL_VETO       = 3      # if 3+ smart wallets SELLING = veto

def _rpc(method: str, params: dict) -> dict:
    try:
        r = requests.post(CLIO, json={"method": method, "params": [params]}, timeout=10)
        return r.json().get("result", {})
    except Exception as e:
        logger.debug(f"[disagree] rpc error: {e}")
        return {}

def _load_veto_log() -> list:
    try:
        with open(VETO_LOG) as f:
            return json.load(f)
    except:
        return []

def _save_veto(symbol: str, reason: str, check: str):
    log = _load_veto_log()
    log.append({"ts": time.time(), "symbol": symbol, "check": check, "reason": reason})
    log = log[-500:]  # keep last 500
    os.makedirs(STATE_DIR, exist_ok=True)
    try:
        with open(VETO_LOG, "w") as f:
            json.dump(log, f, indent=2)
    except:
        pass

# ── Check 1: Rug Fingerprint ──────────────────────────────────────────────────
def check_rug_fingerprint(candidate: Dict) -> Tuple[str, str, float]:
    """
    Checks issuer wallet age and known rug patterns.
    Fresh wallets (< 30 min) with no history = rug risk.
    """
    issuer = candidate.get("issuer", "")
    symbol = candidate.get("symbol", "")

    if not issuer:
        return ("warn", "no_issuer", -0.10)

    info = _rpc("account_info", {"account": issuer, "ledger_index": "validated"})
    acct = info.get("account_data", {})

    if not acct:
        return ("warn", "issuer_not_found", -0.15)

    # Check issuer age via sequence number proxy
    # Low sequence = new wallet
    seq = acct.get("Sequence", 0)
    if seq < 5:
        return ("veto", f"issuer_wallet_fresh_seq={seq} — likely new rug wallet", -1.0)

    # Check if issuer has a known blackhole (burned keys = safe)
    regular_key = acct.get("RegularKey", "")
    BLACK_HOLES = {
        "rrrrrrrrrrrrrrrrrrrrrhoLvTp",
        "rrrrrrrrrrrrrrrrrrrrBZbvji",
        "rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh",
    }
    if regular_key in BLACK_HOLES:
        return ("pass", "issuer_keys_burned", +0.15)  # bonus — safe issuer

    # Domain check — verified issuers are NOT memes (we want anon memes)
    domain = acct.get("Domain", "")
    if domain:
        try:
            decoded = bytes.fromhex(domain).decode("utf-8", errors="ignore")
            # If it's a real company domain, this isn't a meme
            UTILITY_DOMAINS = ("bitstamp", "gatehub", "xrptoolkit", "ripple.com", "xumm")
            if any(d in decoded.lower() for d in UTILITY_DOMAINS):
                return ("veto", f"verified_utility_issuer domain={decoded}", -1.0)
        except:
            pass

    return ("pass", "issuer_ok", 0.0)


# ── Check 2: Fake Burst Detection ─────────────────────────────────────────────
def check_fake_burst(candidate: Dict) -> Tuple[str, str, float]:
    """
    Validates that TrustSet burst is from multiple unique wallets.
    Coordinated wash: same 1-2 wallets adding/removing trustlines repeatedly.
    """
    issuer = candidate.get("issuer", "")
    burst_count = int(candidate.get("burst_count", 0) or candidate.get("ts_burst_count", 0))

    if burst_count < 8 or not issuer:
        return ("pass", "no_burst_to_validate", 0.0)

    result = _rpc("account_tx", {
        "account": issuer,
        "limit": 50,
        "forward": False,
        "ledger_index_min": -1,
        "ledger_index_max": -1,
    })

    txs = result.get("transactions", [])
    now = time.time()
    cutoff = now - 3600  # last hour

    trust_wallets = []
    for t in txs:
        tx = t.get("tx", t.get("tx_json", {}))
        if tx.get("TransactionType") != "TrustSet":
            continue
        ts = tx.get("date", 0) + XRPL_EPOCH
        if ts < cutoff:
            continue
        trust_wallets.append(tx.get("Account", ""))

    if not trust_wallets:
        return ("warn", "no_recent_trustsets_found", -0.05)

    unique = len(set(trust_wallets))
    total  = len(trust_wallets)

    if unique < MIN_UNIQUE_TRUSTSETS:
        return ("veto", f"fake_burst: only {unique} unique wallets in {total} TrustSets — wash activity", -1.0)

    concentration = 1 - (unique / total) if total > 0 else 0
    if concentration >= FAKE_BURST_VETO_PCT:
        return ("veto", f"wash_burst: {concentration:.0%} of TrustSets from same wallets", -1.0)

    # Good signal: many unique wallets
    diversity_bonus = min(0.20, unique / 50)
    return ("pass", f"burst_authentic: {unique}/{total} unique wallets", +diversity_bonus)


# ── Check 3: Liquidity Trap ────────────────────────────────────────────────────
def check_liquidity_trap(candidate: Dict) -> Tuple[str, str, float]:
    """
    Checks if a single wallet controls most of the AMM liquidity.
    One-wallet TVL = issuer can drain pool instantly = trap.
    """
    amm = candidate.get("amm_data", {})
    if not amm:
        return ("pass", "no_amm_data", 0.0)

    vote_slots = amm.get("vote_slots", [])
    lp_token   = amm.get("lp_token", {})

    if not vote_slots:
        return ("warn", "no_vote_slots", -0.05)

    # Check vote weight concentration (proxy for LP concentration)
    total_weight = sum(v.get("vote_weight", 0) for v in vote_slots)
    if total_weight > 0:
        top_weight = max(v.get("vote_weight", 0) for v in vote_slots)
        concentration = top_weight / total_weight
        if concentration >= LIQUIDITY_SINGLE_WALLET:
            return ("veto", f"liquidity_trap: {concentration:.0%} LP from one wallet — can drain instantly", -1.0)
        if concentration >= 0.80:
            return ("warn", f"liquidity_concentration: {concentration:.0%} from top LP", -0.15)

    return ("pass", "liquidity_distributed", +0.05)


# ── Check 4: Smart Money Veto ─────────────────────────────────────────────────
def check_smart_money(candidate: Dict, bot_state: Dict) -> Tuple[str, str, float]:
    """
    If smart wallets are SELLING this token, don't buy.
    If smart wallets are BUYING, boost confidence.
    """
    symbol  = candidate.get("symbol", "")
    sm_sells = candidate.get("smart_wallet_sells", 0)
    sm_buys  = candidate.get("smart_money_boost", 0)

    # Smart wallet sells from wallet_cluster monitor
    if sm_sells >= SMART_SELL_VETO:
        return ("veto", f"smart_money_selling: {sm_sells} tracked wallets exiting", -1.0)

    if sm_sells > 0:
        return ("warn", f"smart_money_1_sell: {sm_sells} wallet(s) exiting", -0.10)

    if sm_buys >= 2:
        return ("pass", f"smart_money_buying: {sm_buys} wallets entered", +0.20)

    return ("pass", "smart_money_neutral", 0.0)


# ── Check 5: Hard Blacklist ────────────────────────────────────────────────────
def check_blacklist(candidate: Dict, bot_state: Dict) -> Tuple[str, str, float]:
    """
    Checks known bad actors: tokens that rugged before, serial dumpers.
    Also checks if this token has triggered 3+ hard stops historically.
    """
    symbol = candidate.get("symbol", "")
    issuer = candidate.get("issuer", "")

    # Known rug issuers (add as discovered)
    KNOWN_RUG_ISSUERS = set()  # populated from state/rug_registry.json if exists
    try:
        rug_path = os.path.join(STATE_DIR, "rug_registry.json")
        if os.path.exists(rug_path):
            with open(rug_path) as f:
                KNOWN_RUG_ISSUERS = set(json.load(f).get("issuers", []))
    except:
        pass

    if issuer in KNOWN_RUG_ISSUERS:
        return ("veto", f"known_rug_issuer: {issuer[:16]}", -1.0)

    # Check hard stop history for this token
    history = bot_state.get("trade_history", [])
    hard_stops = [t for t in history if t.get("symbol") == symbol and "hard_stop" in t.get("exit_reason", "")]
    if len(hard_stops) >= 3:
        return ("veto", f"serial_hard_stopper: {len(hard_stops)} hard stops on {symbol}", -1.0)
    if len(hard_stops) >= 2:
        return ("warn", f"repeat_hard_stop: {len(hard_stops)} stops on {symbol}", -0.20)

    return ("pass", "blacklist_clear", 0.0)


# ── Check 6: Regime Veto ──────────────────────────────────────────────────────
def check_regime(candidate: Dict, regime: str, score: int) -> Tuple[str, str, float]:
    """
    In danger regime (WR < 20%), only allow highest-conviction signals.
    In cold regime, raise the bar slightly.
    """
    strategy = candidate.get("_godmode_type", "unknown")
    burst_count = int(candidate.get("burst_count", 0) or 0)

    if regime == "danger":
        # Only PHX-level bursts (50+ TS/hr) allowed in danger
        if burst_count < 50 and score < 75:
            return ("veto", f"regime_danger: score={score} burst={burst_count} — below danger threshold", -1.0)
        return ("pass", "regime_danger_exception_high_conviction", 0.0)

    if regime == "cold":
        if score < 55 and burst_count < 15:
            return ("warn", "regime_cold_borderline", -0.10)

    return ("pass", f"regime_{regime}_ok", 0.0)


# ── Main Entry Point ───────────────────────────────────────────────────────────
def evaluate(
    candidate: Dict,
    bot_state: Dict,
    regime: str = "neutral",
    score: int = 0,
) -> Dict:
    """
    Run all disagreement checks on a candidate.

    Returns:
        {
            "verdict":    "proceed" | "veto" | "warn",
            "reason":     str,
            "confidence_adj": float,   # add to score
            "checks":     dict,        # full check results
        }
    """
    symbol = candidate.get("symbol", "?")
    checks = {}
    confidence_adj = 0.0
    veto_reasons = []
    warn_reasons  = []

    # Run all checks
    check_fns = [
        ("rug_fingerprint",  lambda: check_rug_fingerprint(candidate)),
        ("fake_burst",       lambda: check_fake_burst(candidate)),
        ("liquidity_trap",   lambda: check_liquidity_trap(candidate)),
        ("smart_money",      lambda: check_smart_money(candidate, bot_state)),
        ("blacklist",        lambda: check_blacklist(candidate, bot_state)),
        ("regime",           lambda: check_regime(candidate, regime, score)),
    ]

    for check_name, fn in check_fns:
        try:
            verdict, reason, adj = fn()
            checks[check_name] = {"verdict": verdict, "reason": reason, "adj": adj}
            confidence_adj += adj
            if verdict == "veto":
                veto_reasons.append(f"{check_name}: {reason}")
            elif verdict == "warn":
                warn_reasons.append(f"{check_name}: {reason}")
        except Exception as e:
            logger.debug(f"[disagree] check {check_name} error: {e}")
            checks[check_name] = {"verdict": "pass", "reason": f"error:{e}", "adj": 0}

    if veto_reasons:
        reason_str = " | ".join(veto_reasons)
        _save_veto(symbol, reason_str, "multi")
        logger.info(f"🚫 DISAGREE VETO {symbol}: {reason_str}")
        return {
            "verdict":        "veto",
            "reason":         reason_str,
            "confidence_adj": confidence_adj,
            "checks":         checks,
        }

    if warn_reasons:
        logger.info(f"⚠️  DISAGREE WARN {symbol}: {' | '.join(warn_reasons)} (adj={confidence_adj:+.2f})")
        return {
            "verdict":        "warn",
            "reason":         " | ".join(warn_reasons),
            "confidence_adj": confidence_adj,
            "checks":         checks,
        }

    logger.debug(f"✅ DISAGREE PASS {symbol}: all checks clear (adj={confidence_adj:+.2f})")
    return {
        "verdict":        "proceed",
        "reason":         "all_checks_passed",
        "confidence_adj": confidence_adj,
        "checks":         checks,
    }

======================================================================
# DYNAMIC_TP — dynamic_tp.py
======================================================================

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
======================================================================
# SIZING — sizing.py
======================================================================

"""
sizing.py — Dynamic capital-based position sizing for DKTrenchBot v2.
Scales position size based on available wallet balance and confidence signals.

Usage:
    from sizing import calculate_position_size
    size = calculate_position_size(score=65, wallet_balance=150, confidence_inputs={...})
"""

import logging
from typing import Dict

logger = logging.getLogger("sizing")

# Position sizing as % of available balance
# Reduced from 20/12/6/3% — avg 9.5 XRP on 200 XRP wallet was 4.75%
# but stale exits at -1.29 XRP avg mean each loss = 13.5% of intended size
# Target: max 5% per trade on standard, 8% on elite burst signals
BASE_PCT_ELITE = 0.08   # 8% of balance for elite (score≥65) — was 20%
BASE_PCT_NORMAL = 0.05  # 5% of balance for normal (score≥50) — was 12%
BASE_PCT_SMALL = 0.03   # 3% of balance for small (score≥40) — was 6%
BASE_PCT_SCALP = 0.02   # 2% of balance for scalp/micro — was 3%

# Hard limits per position (safety ceiling)
MAX_POSITION_XRP = 15.0   # Hard cap per trade — was 100, protect capital
MIN_POSITION_XRP = 3.0    # Minimum viable position


def calculate_position_size(score: int, wallet_balance: float, confidence_inputs: Dict) -> float:
    """
    Dynamic position sizing based on wallet balance and confidence.

    Args:
        score: Composite token score (0-100)
        wallet_balance: Available XRP balance in wallet
        confidence_inputs: Dict with keys:
            wallet_cluster_active (bool)
            alpha_signal_active (bool)
            ml_probability (float, 0-1)
            regime (str: 'bull'|'bear'|'neutral')
            smart_wallet_count (int)
            tvl_xrp (float)

    Returns:
        Position size in XRP, scaled to balance.
    """
    if wallet_balance <= 0:
        return 0.0

    # ── 1. Base size as % of balance ─────────────────────────────────────────
    if score >= 65:
        base_pct = BASE_PCT_ELITE
    elif score >= 50:
        base_pct = BASE_PCT_NORMAL
    elif score >= 40:
        base_pct = BASE_PCT_SMALL
    else:
        base_pct = BASE_PCT_SCALP

    base_xrp = wallet_balance * base_pct

    # ── 2. Confidence multiplier (additive bonuses) ──────────────────────────
    multiplier = 1.0

    if confidence_inputs.get("wallet_cluster_active", False):
        multiplier += 0.20

    if confidence_inputs.get("alpha_signal_active", False):
        multiplier += 0.15

    # TrustSet burst signal — explosive early launch, max aggression
    if confidence_inputs.get("ts_burst_active", False):
        ts_count = int(confidence_inputs.get("ts_burst_count", 0))
        if ts_count >= 50:
            multiplier += 0.50   # PHX-level burst — all in
        elif ts_count >= 25:
            multiplier += 0.35   # strong burst
        elif ts_count >= 8:
            multiplier += 0.20   # early burst signal

    ml_prob = float(confidence_inputs.get("ml_probability", 0.5))
    if ml_prob >= 0.75:
        multiplier += 0.15
    elif ml_prob <= 0.25:
        multiplier -= 0.20

    regime = confidence_inputs.get("regime", "neutral")
    if regime == "bull":
        multiplier += 0.10
    elif regime == "bear":
        multiplier -= 0.20

    sw_count = int(confidence_inputs.get("smart_wallet_count", 0))
    sw_bonus = min(sw_count * 0.05, 0.25)
    if sw_bonus > 0:
        multiplier += sw_bonus

    # Clamp multiplier to [0.5x, 2.5x]
    multiplier = max(0.5, min(2.5, multiplier))

    # ── 3. Liquidity factor (TVL-based, 0.5–1.5) ─────────────────────────────
    tvl = float(confidence_inputs.get("tvl_xrp", 2000))

    # TrustSet burst entries: size is slippage-constrained by TVL.
    # A thin pool (50-200 XRP) will move 20-40% against you if you throw 20+ XRP in.
    # Cap aggressively on micro pools, open up once pool can absorb the position.
    if confidence_inputs.get("ts_burst_active", False):
        if tvl < 200:
            # Ghost-thin pool — toe in only, 7 XRP max regardless of score
            liquidity_factor = 0.0   # overridden below by hard cap
            raw_size = 7.0
            final_size = max(MIN_POSITION_XRP, min(7.0, raw_size))
            logger.info(
                f"sizing: BURST micro-pool TVL={tvl:.0f} XRP → hard cap 7 XRP (slippage protection)"
            )
            return round(final_size, 2)
        elif tvl < 500:
            # Sub-$1000 MC zone — scale 7–15 XRP proportionally to TVL
            # At TVL=200 → 7 XRP, at TVL=500 → 15 XRP
            capped_size = 7.0 + (tvl - 200) / 300 * 8.0   # linear 7→15 over 200-500 XRP TVL
            raw_size = base_xrp * multiplier
            final_size = max(MIN_POSITION_XRP, min(capped_size, raw_size))
            logger.info(
                f"sizing: BURST thin-pool TVL={tvl:.0f} XRP → slippage cap {capped_size:.1f} XRP → {final_size:.1f} XRP"
            )
            return round(final_size, 2)
        else:
            # TVL ≥ 500 XRP — pool can absorb it, 1.0x flat
            liquidity_factor = 1.0
    else:
        liquidity_factor = max(0.5, min(1.5, tvl / 2000.0))

    # ── 4. Final size with safety caps ────────────────────────────────────────
    raw_size = base_xrp * multiplier * liquidity_factor
    final_size = max(MIN_POSITION_XRP, min(raw_size, MAX_POSITION_XRP))

    logger.info(
        f"sizing: score={score} bal={wallet_balance:.0f} base={base_xrp:.1f} "
        f"mult={multiplier:.2f} liq={liquidity_factor:.2f} → {final_size:.1f} XRP"
    )
    return round(final_size, 2)


if __name__ == "__main__":
    examples = [
        {"label": "150 XRP, score=65, cluster=True, ml=0.75", "bal": 150, "score": 65,
         "inputs": {"wallet_cluster_active": True, "ml_probability": 0.75, "tvl_xrp": 2000}},
        {"label": "225 XRP, score=65, all signals+", "bal": 225, "score": 65,
         "inputs": {"wallet_cluster_active": True, "alpha_signal_active": True,
                    "ml_probability": 0.75, "regime": "bull", "smart_wallet_count": 2, "tvl_xrp": 3000}},
        {"label": "150 XRP, score=50, neutral", "bal": 150, "score": 50,
         "inputs": {"ml_probability": 0.5, "tvl_xrp": 1500}},
    ]
    print("=== Dynamic Position Sizing ===\n")
    for ex in examples:
        size = calculate_position_size(ex["score"], ex["bal"], ex["inputs"])
        print(f"  {ex['label']}")
        print(f"  → {size:.2f} XRP ({size/ex['bal']*100:.1f}% of balance)\n")

======================================================================
# TRUSTSET_WATCHER — trustset_watcher.py
======================================================================

"""
trustset_watcher.py — TrustSet Velocity Detector

Watches newly launched XRPL tokens for rapid TrustSet accumulation.
This is the PHX signal: 137 holders in the first hour on a token seeded
with only 51 XRP → 2200x move over 4 days.

Signal: NEW AMM (< 6h old, TVL < 500 XRP) with 15+ TrustSets in last hour
        = coordinated community launch, enter BEFORE price moves.

Entry: 5 XRP (micro-cap sizing). Stop: -20%. Hold for the wave.
"""

import json, time, os, logging, requests
from typing import Dict, List

logger = logging.getLogger("trustset_watcher")

CLIO = os.environ.get("CLIO_URL", "https://rpc.xrplclaw.com")
STATE_FILE = os.path.join(os.path.dirname(__file__), "state", "trustset_watchlist.json")

# Signal thresholds
MIN_TRUSTSETS_1H  = 8      # min TrustSets in last hour to flag (was 15 — lowered to catch DKLEDGER-type early launches)
MIN_TRUSTSETS_ABS = 15     # min total TrustSets on the token (was 25)
MAX_AMM_AGE_H     = 24     # only watch tokens launched in last 24h
MAX_SEED_XRP      = 1000   # seed XRP < this = micro-launch (PHX was 51)
MAX_ENTRY_TVL     = 3000   # don't enter if TVL already > 3000 XRP (missed it)
MIN_ENTRY_TVL     = 30     # need at least 30 XRP TVL to have a working AMM

XRPL_EPOCH = 946684800

def _rpc(method, params, timeout=10):
    try:
        r = requests.post(CLIO, json={"method": method, "params": [params]}, timeout=timeout)
        return r.json().get("result", {})
    except Exception as e:
        logger.debug(f"RPC error {method}: {e}")
        return {}

def _load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except:
        return {"watchlist": {}, "alerted": [], "last_scan": 0}

def _save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def _get_trustset_velocity(issuer: str) -> dict:
    """Count TrustSets in last 1h and total for a token issuer."""
    now = time.time()
    cutoff_1h = now - 3600
    cutoff_6h = now - 21600

    txs = _rpc("account_tx", {"account": issuer, "limit": 400, "forward": False})
    transactions = txs.get("transactions", [])

    total_trustsets = 0
    last_1h = 0
    last_6h = 0
    unique_wallets = set()
    oldest_ts = now

    for t in transactions:
        tx = t.get("tx", t.get("transaction", {}))
        if tx.get("TransactionType") != "TrustSet":
            continue
        ts = tx.get("date", 0) + XRPL_EPOCH
        acct = tx.get("Account", "")
        total_trustsets += 1
        unique_wallets.add(acct)
        if ts < oldest_ts:
            oldest_ts = ts
        if ts >= cutoff_1h:
            last_1h += 1
        if ts >= cutoff_6h:
            last_6h += 1

    age_h = (now - oldest_ts) / 3600 if oldest_ts < now else 0

    return {
        "total": total_trustsets,
        "last_1h": last_1h,
        "last_6h": last_6h,
        "unique_wallets": len(unique_wallets),
        "age_h": age_h,
    }

def _get_amm_info(issuer: str, currency: str) -> dict:
    """Get current AMM state."""
    r = _rpc("amm_info", {"asset": {"currency": "XRP"}, "asset2": {"currency": currency, "issuer": issuer}})
    if not r.get("amm"):
        return {}
    amm = r["amm"]
    xrp = int(amm.get("amount", 0)) / 1e6
    tok = float(amm.get("amount2", {}).get("value", 1))
    price = xrp / tok if tok > 0 else 0
    return {
        "tvl_xrp": xrp,
        "price": price,
        "fee": amm.get("trading_fee", 0) / 1000,
        "lp_tokens": float(amm.get("lp_token", {}).get("value", 0)),
    }

def scan(registry: dict) -> List[dict]:
    """
    Scan registry tokens for TrustSet velocity signals.
    Returns list of high-conviction launch candidates.
    
    Called from main bot loop every 4 cycles (~20 min).
    """
    state = _load_state()
    signals = []
    now = time.time()

    # Only check tokens that appear new (low TVL, recently added to registry)
    candidates = []
    for key, token in registry.items():
        tvl = token.get("tvl_xrp", 0)
        if MIN_ENTRY_TVL <= tvl <= MAX_ENTRY_TVL:
            candidates.append((key, token))

    if not candidates:
        return []

    logger.info(f"TrustSet scan: checking {len(candidates)} micro-TVL tokens")

    for key, token in candidates:
        symbol = token.get("symbol", key)
        issuer = token.get("issuer", "")
        currency = token.get("currency", symbol)

        if not issuer:
            continue

        # Skip already alerted tokens
        if key in state.get("alerted", []):
            continue

        # Get TrustSet velocity
        vel = _get_trustset_velocity(issuer)

        # Must be relatively new AND accumulating holders fast
        if vel["age_h"] > MAX_AMM_AGE_H:
            continue
        if vel["total"] < MIN_TRUSTSETS_ABS:
            continue
        if vel["last_1h"] < MIN_TRUSTSETS_1H:
            continue

        # Get AMM state
        amm = _get_amm_info(issuer, currency)
        if not amm:
            continue

        tvl = amm["tvl_xrp"]
        if tvl > MAX_ENTRY_TVL or tvl < MIN_ENTRY_TVL:
            continue

        # Score the signal
        score = 0
        score += min(30, vel["last_1h"] * 2)       # up to 30pts for 1h velocity
        score += min(20, vel["total"] // 5)          # up to 20pts for total holders
        score += min(20, vel["unique_wallets"] // 5) # up to 20pts for unique wallets
        if tvl < 200:
            score += 15   # ultra-early bonus
        elif tvl < 500:
            score += 10   # early entry bonus

        signal = {
            "key": key,
            "symbol": symbol,
            "issuer": issuer,
            "currency": currency,
            "score": score,
            "trustsets_1h": vel["last_1h"],
            "trustsets_total": vel["total"],
            "unique_wallets": vel["unique_wallets"],
            "age_h": round(vel["age_h"], 1),
            "tvl_xrp": tvl,
            "price": amm["price"],
            "signal_type": "trustset_velocity",
            "ts": now,
        }

        signals.append(signal)
        logger.info(
            f"🔥 TRUSTSET SIGNAL {symbol}: {vel['last_1h']} TrustSets/1h "
            f"| total={vel['total']} | TVL={tvl:.0f} XRP | age={vel['age_h']:.1f}h | score={score}"
        )

        # Mark as alerted so we don't re-signal
        state.setdefault("alerted", []).append(key)
        # Trim alerted list to last 200
        state["alerted"] = state["alerted"][-200:]

    state["last_scan"] = now
    _save_state(state)

    return sorted(signals, key=lambda x: x["score"], reverse=True)


if __name__ == "__main__":
    # Test mode
    logging.basicConfig(level=logging.INFO)
    test_registry = {
        "PHX:rskkPc3Eea3phZmzYqdoRFXeHg1GF7oVzG": {
            "symbol": "PHX", "issuer": "rskkPc3Eea3phZmzYqdoRFXeHg1GF7oVzG",
            "currency": "PHX", "tvl_xrp": 4940
        }
    }
    # PHX has 4940 XRP TVL now — too high for entry, but test velocity
    issuer = "rskkPc3Eea3phZmzYqdoRFXeHg1GF7oVzG"
    vel = _get_trustset_velocity(issuer)
    print(f"\nPHX TrustSet profile:")
    print(f"  Total TrustSets:  {vel['total']}")
    print(f"  Last 1h:          {vel['last_1h']}")
    print(f"  Last 6h:          {vel['last_6h']}")
    print(f"  Unique wallets:   {vel['unique_wallets']}")
    print(f"  Token age:        {vel['age_h']:.1f}h")
    print(f"\n  At launch, PHX had 137 TrustSets in first 1h")
    print(f"  Seed XRP: 51.14 | Move: +2208x over 4 days")
    print(f"  Entry at 5 XRP → potential ~11,000 XRP return")

======================================================================
# SCORING — scoring.py
======================================================================

"""
scoring.py — Composite token score (0-100).
Components:
  breakout_quality:   0-25 pts
  chart_state:        0-20 pts
  liquidity_depth:    0-15 pts
  issuer_safety:      0-10 pts
  route_quality:      0-10 pts
  smart_money:        0-10 pts
  extension_penalty: -20-0 pts
  regime_bonus:      -10-+5 pts

Thresholds: 85+=elite, 70-84=tradeable, 60-69=small_size, <60=skip
"""

from typing import Dict, Optional
from config import SCORE_ELITE, SCORE_TRADEABLE, SCORE_SMALL


def compute_score(
    breakout_quality:  int   = 0,
    chart_state:       str   = "dead",
    chart_confidence:  float = 0.5,
    tvl_xrp:          float = 0.0,
    issuer_safe:       bool  = False,
    issuer_warnings:   int   = 0,
    route_slippage:    float = 0.05,
    route_exit_ok:     bool  = True,
    smart_money_boost: int   = 0,     # 0, 10, or 20
    extension_pct:     float = 0.0,   # total price move from entry
    tvl_change_pct:    float = 0.0,   # TVL % change vs last reading (momentum signal)
    regime:            str   = "neutral",
    regime_override:   bool  = False,
    symbol:            str   = "",    # for TG signal lookup
) -> Dict:
    """
    Compute composite score. Returns dict with total and breakdown.
    """
    breakdown = {}

    # 1. Breakout quality: 0-35 pts (primary signal — learned 2026-04-03)
    # Linear up to BQ=60, then bonus acceleration for high conviction
    if breakout_quality >= 80:
        bq_pts = 35
    elif breakout_quality >= 60:
        bq_pts = 25 + int((breakout_quality - 60) * 0.5)   # 25-35 pts
    else:
        bq_pts = int(breakout_quality * 0.42)               # 0-25 pts
    breakdown["breakout_quality"] = bq_pts

    # 2. Chart state quality: 0-20 pts
    from chart_intelligence import get_chart_state_score
    cs_pts = get_chart_state_score(chart_state)
    # Scale by confidence
    cs_pts = int(cs_pts * chart_confidence)
    breakdown["chart_state"] = cs_pts

    # 3. Liquidity depth: 0-30 pts
    # DATA REBUILD 2026-04-06: Score 80-100 (high TVL, established pools) = 0% WR, all stales.
    # Winners cluster in MICRO TVL (under 3K XRP) — fresh launches, not discovered yet.
    # INVERTED from previous: reward fresh/micro, penalise large/established.
    if 500 <= tvl_xrp < 2_000:
        liq_pts = 30   # ⭐ sweet spot — fresh launch, not yet discovered
    elif 200 <= tvl_xrp < 500:
        liq_pts = 25   # very early, high volatility, PHX-type launch window
    elif 2_000 <= tvl_xrp < 5_000:
        liq_pts = 20   # early stage — still moveable
    elif 5_000 <= tvl_xrp < 15_000:
        liq_pts = 10   # mid — already partially discovered
    elif 15_000 <= tvl_xrp < 40_000:
        liq_pts = 5    # large — slow mover, stale risk
    elif tvl_xrp >= 40_000:
        liq_pts = 0    # very large — won't move meaningfully, skip
    else:
        liq_pts = 0    # too thin (<200 XRP) — ghost pool

    # TVL momentum bonus: rapidly growing pool = community piling in (+0 to +10 pts)
    if tvl_change_pct >= 0.50:
        liq_pts = min(liq_pts + 10, 30)  # TVL up 50%+ — live launch happening
    elif tvl_change_pct >= 0.25:
        liq_pts = min(liq_pts + 6, 30)
    elif tvl_change_pct >= 0.10:
        liq_pts = min(liq_pts + 3, 30)

    breakdown["liquidity_depth"] = liq_pts

    # 4. Issuer safety: 0-10 pts
    if issuer_safe:
        issuer_pts = 10
    elif issuer_warnings == 0:
        issuer_pts = 6
    else:
        issuer_pts = max(0, 6 - issuer_warnings * 2)
    breakdown["issuer_safety"] = issuer_pts

    # 5. Route quality: 0-10 pts
    if route_slippage <= 0.005:
        route_pts = 10
    elif route_slippage <= 0.01:
        route_pts = 8
    elif route_slippage <= 0.02:
        route_pts = 5
    elif route_slippage <= 0.03:
        route_pts = 2
    else:
        route_pts = 0
    if not route_exit_ok:
        route_pts = max(0, route_pts - 5)
    breakdown["route_quality"] = route_pts

    # 6. Smart money: 0-10 pts
    sm_pts = min(10, smart_money_boost)
    breakdown["smart_money"] = sm_pts

    # 6b. Wallet Cluster boost (Audit #2): +30 if 2+ smart wallets entering same token
    cluster_boost = 0
    try:
        import wallet_cluster as _wc
        cluster_boost = _wc.get_cluster_boost(symbol, issuer) if symbol and issuer else 0
    except Exception:
        pass
    breakdown["wallet_cluster"] = cluster_boost

    # 6d. Alpha Recycler boost (Audit #3): +25 if a tracked wallet just recycled into this token
    recycler_boost = 0
    try:
        import alpha_recycler as _ar
        recycler_boost = _ar.get_alpha_recycler_boost(symbol, issuer) if symbol and issuer else 0
    except Exception:
        pass
    breakdown["alpha_recycler"] = recycler_boost

    # 7. Extension penalty: -20 to 0
    if extension_pct >= 0.50:
        ext_penalty = -20
    elif extension_pct >= 0.35:
        ext_penalty = -15
    elif extension_pct >= 0.25:
        ext_penalty = -10
    elif extension_pct >= 0.15:
        ext_penalty = -5
    else:
        ext_penalty = 0
    breakdown["extension_penalty"] = ext_penalty

    # 8. Regime bonus: -10 to +5
    regime_bonus = {
        "hot":     5,
        "neutral": 0,
        "cold":   -5,
        "danger": -10,
    }.get(regime, 0)
    breakdown["regime_bonus"] = regime_bonus

    # 9. ML score adjustment (active only after 50+ trades; silent in logging phase)
    ml_adj = 0
    try:
        from config import ML_ENABLED
        if ML_ENABLED:
            import ml_model as _ml
            from datetime import datetime
            _ml_features = {
                "total_score":              sum(breakdown.values()),
                "entry_tvl_xrp":            tvl_xrp,
                "hour_utc":                 datetime.utcnow().hour,
                "wallet_cluster_boost":     cluster_boost,
                "alpha_recycler_boost":     recycler_boost,
                "smart_wallet_count":       0,   # unknown at scoring time
                "cluster_active":           cluster_boost > 0,
                "alpha_signal_active":      recycler_boost > 0,
                "momentum_score_at_entry":  float(cs_pts),
            }
            ml_adj = _ml.get_ml_score_adjustment(_ml_features)
    except Exception:
        pass
    breakdown["ml_adjustment"] = ml_adj

    total = sum(breakdown.values())
    total = max(0, min(100, total))

    band = "skip"
    if total >= SCORE_ELITE:
        band = "elite"
    elif total >= SCORE_TRADEABLE:
        band = "tradeable"
    elif total >= SCORE_SMALL:
        band = "small_size"

    return {
        "total":     total,
        "band":      band,
        "breakdown": breakdown,
    }


def position_size(score: int, regime: str, base_xrp: float = 5.0,
                  elite_xrp: float = 7.5, small_xrp: float = 2.5,
                  bq: int = 50, wallet_xrp: float = 0.0) -> float:
    """
    Score-band primary sizing with BQ and regime multipliers.
    Kelly was giving negative edge on low BQ tokens — unreliable as primary.
    Band is the anchor, BQ and regime are modifiers.
    """
    if regime == "danger":
        # Danger doesn't return 0 — half size, stay in the game
        return max(small_xrp, base_xrp * 0.5)

    regime_mult = {"hot": 1.2, "neutral": 1.0, "cold": 0.85}.get(regime, 1.0)

    # ── Capital-aware sizing ─────────────────────────────────────────────────
    # Scale base sizes proportionally to available capital.
    # Target: 8-10% of spendable per hold trade, 3% per scalp.
    # At 90 XRP spendable: base=9, elite=13.5
    # At 180 XRP spendable: base=14, elite=20
    if wallet_xrp > 50:
        capital_scalar = min(wallet_xrp / 90.0, 1.8)  # cap at 1.8x base
        base_xrp  = round(base_xrp  * capital_scalar, 1)
        elite_xrp = round(elite_xrp * capital_scalar, 1)
        small_xrp = round(small_xrp * capital_scalar, 1)

    # Primary size from score band
    if score >= SCORE_ELITE:
        base = elite_xrp
    elif score >= SCORE_TRADEABLE:
        base = base_xrp
    else:
        base = small_xrp

    # BQ conviction multiplier
    if bq >= 80:   bq_mult = 1.3
    elif bq >= 65: bq_mult = 1.15
    elif bq >= 50: bq_mult = 1.0
    else:          bq_mult = 0.9

    # Score conviction bonus
    if score >= SCORE_ELITE:
        score_mult = min(1.0 + (score - SCORE_ELITE) * 0.01, 1.3)
    else:
        score_mult = 1.0

    size = base * regime_mult * bq_mult * score_mult

    # Hard cap: never more than 20% of wallet in one trade
    if wallet_xrp > 0:
        size = min(size, wallet_xrp * 0.20)

    # Floor
    size = max(size, small_xrp)

    return round(size, 2)


def size_multiplier(score: int, regime: str) -> float:
    """Legacy multiplier — kept for compatibility."""
    if regime == "danger":
        return 0.0
    base = {"hot": 1.2, "neutral": 1.0, "cold": 0.5}.get(regime, 1.0)
    if score >= SCORE_ELITE:
        return base * 1.5
    elif score >= SCORE_TRADEABLE:
        return base * 1.0
    elif score >= SCORE_SMALL:
        return base * 0.5
    else:
        return 0.0


if __name__ == "__main__":
    result = compute_score(
        breakout_quality=75,
        chart_state="pre_breakout",
        chart_confidence=0.8,
        tvl_xrp=15000,
        issuer_safe=True,
        route_slippage=0.015,
        route_exit_ok=True,
        smart_money_boost=10,
        extension_pct=0.08,
        regime="neutral",
    )
    print(f"Score: {result['total']} ({result['band']})")
    print(f"Breakdown: {result['breakdown']}")

======================================================================
# ROUTE_ENGINE — route_engine.py
======================================================================

"""
route_engine.py — Compare AMM vs DEX order book. Calculate slippage and exit feasibility.
Rejects if entry slippage > 3% or exit liquidity < 2x position.
Writes: state/route_log.json
"""

import json
import os
import time
import requests
from typing import Dict, Optional, Tuple
from config import CLIO_URL, STATE_DIR, get_currency

os.makedirs(STATE_DIR, exist_ok=True)
ROUTE_LOG_FILE = os.path.join(STATE_DIR, "route_log.json")


def _rpc(method: str, params: dict) -> Optional[dict]:
    for attempt in range(3):
        try:
            resp = requests.post(CLIO_URL, json={"method": method, "params": [params]}, timeout=15)
            data = resp.json()
            result = data.get("result")
            if isinstance(result, dict) and result.get("error") == "slowDown":
                time.sleep(1.0 * (attempt + 1))
                continue
            return result
        except Exception:
            time.sleep(0.5)
    return None


def get_amm_price(amm: Dict) -> Optional[float]:
    """Get AMM mid-price (XRP per token)."""
    try:
        xrp_drops  = int(amm["amount"])
        token_val  = float(amm["amount2"]["value"])
        if token_val == 0:
            return None
        return (xrp_drops / 1e6) / token_val
    except Exception:
        return None


def estimate_amm_slippage(amm: Dict, xrp_in: float) -> float:
    """
    Estimate AMM slippage for buying `xrp_in` XRP worth of token.
    Uses constant product formula: dy = y * dx / (x + dx)
    """
    try:
        x = int(amm["amount"]) / 1e6      # XRP in pool
        y = float(amm["amount2"]["value"]) # token in pool
        if x <= 0 or y <= 0:
            return 1.0
        # With trading fee (typically 0.3% on XRPL AMMs)
        fee = float(amm.get("trading_fee", 500)) / 1_000_000  # fee in bips → fraction
        dx  = xrp_in
        # Tokens out: standard AMM formula with fee
        dy  = y * dx * (1 - fee) / (x + dx * (1 - fee))
        # Ideal (no slippage): dx * (y / x)
        ideal = dx * (y / x)
        if ideal <= 0:
            return 1.0
        slippage = abs(ideal - dy) / ideal
        return slippage
    except Exception:
        return 1.0


def get_book_depth(symbol: str, issuer: str, limit: int = 20) -> Dict:
    """Get DEX order book depth for token/XRP."""
    currency = get_currency(symbol)
    # Buy side: offers to sell XRP for token (taker_gets=token, taker_pays=XRP)
    buy_result = _rpc("book_offers", {
        "taker_gets": {"currency": currency, "issuer": issuer},
        "taker_pays": {"currency": "XRP"},
        "limit":      limit,
    })
    # Sell side: offers to sell token for XRP
    sell_result = _rpc("book_offers", {
        "taker_gets": {"currency": "XRP"},
        "taker_pays": {"currency": currency, "issuer": issuer},
        "limit":      limit,
    })

    buy_offers  = buy_result.get("offers", [])  if buy_result  else []
    sell_offers = sell_result.get("offers", []) if sell_result else []

    return {"buy": buy_offers, "sell": sell_offers}


def estimate_book_slippage(book: Dict, xrp_in: float) -> float:
    """Estimate slippage from order book for buying xrp_in XRP worth."""
    offers = book.get("buy", [])
    if not offers:
        return 1.0  # No liquidity

    filled = 0.0
    total_xrp_cost = 0.0

    for offer in offers:
        try:
            # offer taker_pays = XRP, taker_gets = token
            tp = offer.get("taker_pays", {})
            tg = offer.get("taker_gets", {})
            if isinstance(tp, str):
                offer_xrp   = int(tp) / 1e6
                offer_token = float(tg.get("value", 0))
            else:
                continue
            if offer_xrp <= 0 or offer_token <= 0:
                continue
            can_take = min(xrp_in - total_xrp_cost, offer_xrp)
            filled         += (offer_token * can_take / offer_xrp)
            total_xrp_cost += can_take
            if total_xrp_cost >= xrp_in:
                break
        except Exception:
            continue

    if filled <= 0:
        return 1.0

    # Compare to AMM-equivalent rate (first offer rate)
    try:
        first_tp = offers[0].get("taker_pays", {})
        first_tg = offers[0].get("taker_gets", {})
        best_xrp   = int(first_tp) / 1e6   if isinstance(first_tp, str) else 0
        best_token = float(first_tg.get("value", 0))
        if best_xrp > 0:
            ideal = xrp_in * (best_token / best_xrp)
            slippage = abs(ideal - filled) / ideal if ideal > 0 else 1.0
            return slippage
    except Exception:
        pass

    return 0.01  # minimal slippage if filled


def check_exit_liquidity(amm: Dict, position_xrp: float) -> Tuple[bool, float]:
    """
    Check if exit liquidity is >= 2x position size.
    Returns (ok, available_xrp).
    """
    try:
        xrp_in_pool = int(amm["amount"]) / 1e6
        available   = xrp_in_pool  # can always exit into AMM, limited by pool size
        threshold   = position_xrp * 2
        return available >= threshold, available
    except Exception:
        return False, 0.0


def evaluate_route(symbol: str, issuer: str, amm: Dict, xrp_in: float) -> Dict:
    """
    Full route evaluation. Returns recommendation and slippage estimates.
    """
    ts = time.time()
    currency = get_currency(symbol)

    # Always route through AMM — no CLOB
    amm_slippage = estimate_amm_slippage(amm, xrp_in)
    best_route   = "amm"
    best_slippage = amm_slippage

    exit_ok, exit_liq = check_exit_liquidity(amm, xrp_in)

    # Hard filters
    entry_ok = best_slippage <= 0.12  # Raised from 5% → 12% per operator request
    trade_ok = entry_ok and exit_ok

    result = {
        "ts":             ts,
        "symbol":         symbol,
        "issuer":         issuer,
        "xrp_in":         xrp_in,
        "amm_slippage":   round(amm_slippage, 5),
        "best_route":     best_route,
        "best_slippage":  round(best_slippage, 5),
        "exit_ok":        exit_ok,
        "exit_liquidity": round(exit_liq, 2),
        "entry_ok":       entry_ok,
        "trade_ok":       trade_ok,
        "reject_reason":  None,
    }

    if not entry_ok:
        result["reject_reason"] = f"slippage_too_high:{best_slippage:.2%}"
    elif not exit_ok:
        result["reject_reason"] = f"insufficient_exit_liq:{exit_liq:.0f}<{xrp_in*2:.0f}"

    # Append to route log
    _append_log(result)
    return result


def _append_log(entry: Dict) -> None:
    log = []
    if os.path.exists(ROUTE_LOG_FILE):
        try:
            with open(ROUTE_LOG_FILE) as f:
                log = json.load(f)
        except Exception:
            pass
    log.append(entry)
    log = log[-200:]  # keep last 200
    with open(ROUTE_LOG_FILE, "w") as f:
        json.dump(log, f, indent=2)


if __name__ == "__main__":
    from scanner import get_amm_info
    token = {"symbol": "SOLO", "issuer": "rsoLo2S1kiGeCcn6hCUXVrCpGMWLrRrLZz"}
    amm = get_amm_info(token["symbol"], token["issuer"])
    if amm:
        result = evaluate_route(token["symbol"], token["issuer"], amm, xrp_in=5.0)
        print(json.dumps(result, indent=2))
    else:
        print("No AMM for SOLO")

======================================================================
# EXECUTION_CORE — execution_core.py
======================================================================

"""
execution_core.py — DKTrenchBot Trade Execution
==============================================
Pure execution layer. All intelligence lives in brain.py.
This module only submits transactions and manages split entries.

bot.py → brain.py (decisions) → execution_core.py (execution)
"""

import logging
import time
from typing import Dict, Optional

from config import BOT_WALLET_ADDRESS
import brain  # all sizing/safety decisions

logger = logging.getLogger("execution_core")

# ═══════════════════════════════════════════════════════════════
# Re-export brain functions so callers don't need a second import
# ═══════════════════════════════════════════════════════════════

estimate_slippage   = brain.predict_slippage  # renamed for backward compat
get_safe_entry_size = brain._get_safe_entry_size
pre_trade_validator = brain.pre_trade_validator
position_sizer      = brain.position_sizer

# Safety constants (mirror brain so execution_core consumers don't break)
MAX_SLIPPAGE     = brain.MAX_SLIPPAGE
MIN_CONFIDENCE   = brain.MIN_CONFIDENCE
MIN_POSITION_XRP = brain.MIN_POSITION_XRP
MIN_LIQUIDITY_USD = brain.MIN_LIQUIDITY_USD

# ═══════════════════════════════════════════════════════════════
# Execution Guards — derived from brain's pre_trade_validator
# ═══════════════════════════════════════════════════════════════

def pre_trade_validator(token: Dict, route_quality: str = "GOOD") -> bool:
    """
    Wrapper for brain.pre_trade_validator.
    Kept for backward compatibility with any direct callers.
    """
    size, confidence = _emergency_size_confidence(token)
    ok, reason = brain.pre_trade_validator(token, size, confidence, route_quality)
    if not ok:
        logger.info(f"[execution_core] {token.get('symbol','?')}: {reason}")
    return ok


def _emergency_size_confidence(token: Dict):
    """Fallback size/confidence when not available from caller context."""
    return token.get("last_size", 10.0), token.get("confidence", 0.5)


# ═══════════════════════════════════════════════════════════════
# Split Execution
# ═══════════════════════════════════════════════════════════════

def split_execute(token: Dict, size: float, side: str = "buy") -> Dict:
    """
    Split entry: 40% then 60% after 2s stability wait.
    Reduces price impact on larger positions.
    """
    import execution as exec_mod

    leg1 = size * 0.40
    leg2 = size * 0.60

    if side == "buy":
        result1 = exec_mod.buy_token(
            symbol=token["symbol"], issuer=token["issuer"],
            xrp_amount=leg1, expected_price=token.get("price", 0),
            slippage_tolerance=0.10,
        )
    else:
        result1 = exec_mod.sell_token(
            symbol=token["symbol"], issuer=token["issuer"],
            token_amount=token.get("balance", 0),
            expected_price=token.get("price", 0),
            slippage_tolerance=0.10,
        )

    if not result1.get("success"):
        return {"first": result1, "second": None, "split": False}

    time.sleep(2.0)

    if side == "buy":
        result2 = exec_mod.buy_token(
            symbol=token["symbol"], issuer=token["issuer"],
            xrp_amount=leg2, expected_price=token.get("price", 0),
            slippage_tolerance=0.10,
        )
    else:
        result2 = exec_mod.sell_token(
            symbol=token["symbol"], issuer=token["issuer"],
            token_amount=token.get("balance", 0),
            expected_price=token.get("price", 0),
            slippage_tolerance=0.10,
        )

    return {"first": result1, "second": result2, "split": True, "size": size}


# ═══════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════

def execute_trade(
    token: Dict,
    classification: Dict,
    strategy,
    wallet_state: Dict,
    route_quality: str = "GOOD",
    side: str = "buy",
) -> Optional[Dict]:
    """
    Centralized execution pipeline. All intelligence gates are in brain.pre_trade_validator.
    This function only handles transaction submission and split entries.
    """
    symbol = token.get("symbol", "?")

    # Brain-based validation
    size = brain.position_sizer(token, classification, wallet_state)
    if size <= 0:
        logger.info(f"[execution_core] {symbol}: position_sizer returned 0")
        return None

    ok, reason = brain.pre_trade_validator(
        token, size,
        classification.get("confidence", 0.5),
        route_quality
    )
    if not ok:
        logger.info(f"[execution_core] {symbol}: {reason}")
        return None

    # Strategy confirm gate
    try:
        if not strategy.valid(token):
            logger.info(f"[execution_core] {symbol}: strategy.valid()=False")
            return None
        if not strategy.confirm(token):
            logger.info(f"[execution_core] {symbol}: strategy.confirm()=False")
            return None
    except Exception as e:
        logger.warning(f"[execution_core] {symbol}: strategy check exception: {e}")
        return None

    # Execute
    logger.info(f"[execution_core] EXECUTE {symbol}: {size:.2f} XRP ({side})")
    result = split_execute(token, size, side=side)
    return result


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("execution_core.py — decisions delegated to brain.py")
    print(f"  MAX_SLIPPAGE     : {MAX_SLIPPAGE:.1%}")
    print(f"  MIN_CONFIDENCE   : {MIN_CONFIDENCE}")
    print(f"  MIN_POSITION_XRP : {MIN_POSITION_XRP}")
    print(f"  MIN_LIQUIDITY_USD: ${MIN_LIQUIDITY_USD}")

======================================================================
# EXECUTION_HARDENER — execution_hardener.py
======================================================================

"""
execution_hardener.py — Resilient execution wrapper for DKTrenchBot v2

Sits in front of execution.py to add:
  - 3-attempt retry with exponential backoff
  - Fail-fast on unrecoverable XRPL errors
  - Ghost fill detection (buy succeeds but 0 tokens received)
  - Orphan position tracking on partial failures
  - State save on any failure
  - Unified buy/sell surface (safe_buy / safe_sell)

All function names match the actual codebase (execution.buy_token, brain.pre_trade_validator, etc.)
"""

import time
import logging
import traceback
from typing import Dict, Optional, Any, Tuple

log = logging.getLogger("execution_hardener")

# ── Config ─────────────────────────────────────────────────────────────────
MAX_RETRIES           = 3
RETRY_BASE_SLEEP      = 0.6   # seconds (doubles each retry)
SELL_RETRY_BASE_SLEEP = 0.8
MIN_SUCCESS_TOKENS    = 1e-12  # ghost fill threshold
DEFAULT_BUY_SLIP      = 0.12
DEFAULT_SELL_SLIP     = 0.12

# XRPL result codes that will NEVER succeed on retry — bail immediately
FAIL_FAST_ERRORS = {
    "tecINSUF_FUND", "tecUNFUNDED_OFFER", "tecPATH_DRY",
    "tecNO_AUTH", "temBAD_AMOUNT", "temBAD_OFFER", "tecNO_LINE",
    "tecNO_PERMISSION", "temDISABLED",
}


# ── Helpers ─────────────────────────────────────────────────────────────────

def _safe_get(d: Optional[Dict], key: str, default=None):
    if not isinstance(d, dict):
        return default
    return d.get(key, default)


def _sleep_backoff(base: float, attempt: int):
    time.sleep(base * (2 ** attempt))


def _normalize_result(result: Any, side: str) -> Dict:
    if isinstance(result, dict):
        return result
    return {
        "success": False,
        "error": f"invalid_result_type:{type(result).__name__}",
        "side": side,
    }


def _is_fail_fast(err: str) -> bool:
    e = (err or "").upper().replace("-", "_").replace(" ", "_")
    return any(k in e for k in FAIL_FAST_ERRORS)


def _call_brain_pretrade(brain, token: Dict, size: float,
                         confidence: float, route_quality: str) -> Tuple[bool, str]:
    """Call brain.pre_trade_validator safely."""
    try:
        return brain.pre_trade_validator(token, size, confidence, route_quality)
    except Exception as e:
        return False, f"pretrade_exception:{e}"


def _call_buy(execution, token: Dict, size: float,
              expected_price: float, slippage: float) -> Dict:
    return execution.buy_token(
        symbol            = _safe_get(token, "symbol"),
        issuer            = _safe_get(token, "issuer"),
        xrp_amount        = size,
        expected_price    = expected_price,
        slippage_tolerance = slippage,
    )


def _call_sell(execution, token: Dict, size: float,
               expected_price: float, slippage: float) -> Dict:
    token_amount = (
        _safe_get(token, "tokens_held", 0)
        or _safe_get(token, "balance", 0)
        or size
    )
    return execution.sell_token(
        symbol            = _safe_get(token, "symbol"),
        issuer            = _safe_get(token, "issuer"),
        token_amount      = token_amount,
        expected_price    = expected_price,
        slippage_tolerance = slippage,
    )


# ── Core ────────────────────────────────────────────────────────────────────

def robust_execute(
    *,
    brain,
    execution,
    token: Dict,
    classification: Dict,
    wallet_state: Dict,
    route_quality: str    = "GOOD",
    side: str             = "buy",
    expected_price: Optional[float] = None,
    size: Optional[float] = None,
    max_retries: int      = MAX_RETRIES,
    buy_slippage: float   = DEFAULT_BUY_SLIP,
    sell_slippage: float  = DEFAULT_SELL_SLIP,
    # Hooks (all optional)
    update_orphan_fn      = None,
    save_state_fn         = None,
    on_success_fn         = None,
    on_failure_fn         = None,
) -> Dict:
    token          = token or {}
    classification = classification or {}
    wallet_state   = wallet_state or {}

    symbol     = _safe_get(token, "symbol", "?")
    confidence = _safe_get(classification, "confidence", 0.5)

    # ── Sizing ─────────────────────────────────────────────────────────────
    if size is None:
        size = _safe_get(token, "size", None)
    if size is None:
        try:
            size = brain.position_sizer(token, classification, wallet_state)
        except Exception as e:
            return {"success": False, "error": f"sizer_exception:{e}", "symbol": symbol}

    if not size or size <= 0:
        return {"success": False, "error": "size_zero", "symbol": symbol}

    # ── Pre-trade gate ──────────────────────────────────────────────────────
    ok, reason = _call_brain_pretrade(brain, token, size, confidence, route_quality)
    if not ok:
        log.info("pretrade_reject symbol=%s reason=%s", symbol, reason)
        return {"success": False, "error": f"pretrade_reject:{reason}",
                "symbol": symbol, "size": size}

    # ── Execution with retry ────────────────────────────────────────────────
    slip     = buy_slippage if side == "buy" else sell_slippage
    px       = expected_price if expected_price is not None else _safe_get(token, "price", 0) or 0
    last_err = None

    for attempt in range(max_retries):
        try:
            if side == "buy":
                raw = _call_buy(execution, token, size, px, slip)
            else:
                raw = _call_sell(execution, token, size, px, slip)

            result = _normalize_result(raw, side)

            if result.get("success"):
                # Ghost fill check
                if side == "buy":
                    tokens_rx = float(result.get("tokens_received", 0) or 0)
                    if tokens_rx < MIN_SUCCESS_TOKENS:
                        last_err = f"ghost_fill:{tokens_rx}"
                        log.warning("ghost_fill symbol=%s tokens_received=%s", symbol, tokens_rx)
                        result = {"success": False, "error": last_err}
                    else:
                        if on_success_fn:
                            try:
                                on_success_fn(result, token, classification, wallet_state)
                            except Exception as hook_err:
                                log.warning("success_hook_failed:%s", hook_err)
                        return result
                else:
                    if on_success_fn:
                        try:
                            on_success_fn(result, token, classification, wallet_state)
                        except Exception as hook_err:
                            log.warning("success_hook_failed:%s", hook_err)
                    return result
            else:
                last_err = str(result.get("error") or "unknown")
                log.warning("exec_failed symbol=%s side=%s attempt=%d err=%s",
                            symbol, side, attempt + 1, last_err)

                # Fail fast on unrecoverable XRPL errors
                if _is_fail_fast(last_err):
                    log.info("fail_fast symbol=%s err=%s", symbol, last_err)
                    break

                # Sell: try wider slippage once on UNFUNDED
                if side == "sell" and "UNFUNDED" in last_err.upper():
                    try:
                        alt = _normalize_result(
                            _call_sell(execution, token, size, px, min(0.30, slip * 2.0)),
                            "sell"
                        )
                        if alt.get("success"):
                            log.info("alt_sell_succeeded symbol=%s", symbol)
                            return alt
                    except Exception as alt_err:
                        last_err = f"alt_sell:{alt_err}"

        except Exception as e:
            last_err = f"exception:{traceback.format_exc(limit=2)}"
            log.error("exec_exception symbol=%s side=%s: %s", symbol, side, e)

        if attempt < max_retries - 1:
            _sleep_backoff(SELL_RETRY_BASE_SLEEP if side == "sell" else RETRY_BASE_SLEEP, attempt)

    # ── All attempts exhausted ──────────────────────────────────────────────
    failure = {
        "success":      False,
        "error":        last_err or "execution_failed",
        "symbol":       symbol,
        "side":         side,
        "size":         size,
        "route_quality": route_quality,
    }

    if side == "buy" and update_orphan_fn:
        try:
            update_orphan_fn(token, size, failure)
        except Exception as e:
            log.warning("orphan_fn_failed:%s", e)

    if save_state_fn:
        try:
            save_state_fn()
        except Exception as e:
            log.warning("save_state_failed:%s", e)

    if on_failure_fn:
        try:
            on_failure_fn(failure, token, classification, wallet_state)
        except Exception as e:
            log.warning("failure_fn_failed:%s", e)

    return failure


# ── Public API ──────────────────────────────────────────────────────────────

def safe_buy(*, brain, execution, token, classification,
             wallet_state, route_quality="GOOD",
             expected_price=None, **kwargs) -> Dict:
    """Resilient buy with retry, ghost fill detection, orphan tracking."""
    return robust_execute(
        brain=brain, execution=execution, token=token,
        classification=classification, wallet_state=wallet_state,
        route_quality=route_quality, side="buy",
        expected_price=expected_price, **kwargs,
    )


def safe_sell(*, brain, execution, token, classification,
              wallet_state, route_quality="GOOD",
              expected_price=None, **kwargs) -> Dict:
    """Resilient sell with retry and wider-slippage fallback."""
    return robust_execute(
        brain=brain, execution=execution, token=token,
        classification=classification, wallet_state=wallet_state,
        route_quality=route_quality, side="sell",
        expected_price=expected_price, **kwargs,
    )

======================================================================
# DYNAMIC_EXIT — dynamic_exit.py
======================================================================

"""
dynamic_exit.py — Dynamic exit logic for open positions.

Philosophy: Let winners run. Cut losers fast. Protect profits.

Key rules:
  - Break-even protection: once up 5%, trail stop floor = entry (never lose on a winner)
  - Tiered trailing: tighter trail as profit grows (lock in more as it moons)
  - Dynamic exits only trigger at meaningful losses (-5%+), not tiny dips
  - Stale exit is generous (6hr) — meme tokens need time
"""

import time
from typing import Dict, List, Optional
from config import (HARD_STOP_PCT, HARD_STOP_EARLY_PCT, HARD_STOP_GRACE_SEC,
                    TRAIL_STOP_PCT, TP1_PCT, TP1_SELL_FRAC,
                    TP2_PCT, TP2_SELL_FRAC, TP3_PCT, TP3_SELL_FRAC,
                    TP4_PCT, STALE_EXIT_HOURS, MAX_HOLD_HOURS,
                    SCALP_TP_PCT, SCALP_STOP_PCT, SCALP_MAX_HOLD_MIN)


def check_exit(position: Dict, current_price: float,
               current_tvl: float = 0.0,
               breakout_quality: int = 50,
               price_history: List[float] = None) -> Dict:
    """
    Check all exit conditions for a position.
    Returns: { exit, partial, reason, fraction }
    """
    if price_history is None:
        price_history = []

    entry_price  = position["entry_price"]
    entry_time   = position["entry_time"]
    peak_price   = position.get("peak_price", entry_price)
    entry_tvl    = position.get("entry_tvl", current_tvl)
    tp1_hit      = position.get("tp1_hit", False)
    tp2_hit      = position.get("tp2_hit", False)
    tp3_hit      = position.get("tp3_hit", False)
    is_orphan    = position.get("orphan", False)
    now          = time.time()
    hold_secs    = now - entry_time
    hold_hours   = hold_secs / 3600

    if entry_price <= 0:
        return _exit_signal("invalid_entry_price", 1.0)

    # FIX: Use XRP-value based P&L not price-based.
    # After partial TP sells, tokens_held is reduced. Real P&L =
    # (tokens_held * current_price) vs xrp_spent (remaining cost basis).
    # Price-based pnl_pct was showing +300% on trades that actually lost XRP.
    tokens_held = float(position.get("tokens_held", 0) or 0)
    xrp_spent   = float(position.get("xrp_spent", 0) or 0)

    if tokens_held > 0 and xrp_spent > 0:
        current_value = tokens_held * current_price
        pnl_pct       = (current_value - xrp_spent) / xrp_spent
    else:
        # Fallback to price-based if no token count
        pnl_pct = (current_price - entry_price) / entry_price

    # Peak pnl still price-based (for trailing stop calculation)
    peak_pnl_pct = (peak_price - entry_price) / entry_price

    # ── Scalp Mode: tight TP/stop/time exits ─────────────────────────────────
    if position.get("scalp_mode"):
        hold_min = hold_secs / 60
        if pnl_pct >= SCALP_TP_PCT:
            return _exit_signal("scalp_tp", 1.0)
        if pnl_pct <= -SCALP_STOP_PCT:
            return _exit_signal("scalp_stop", 1.0)
        if hold_min >= SCALP_MAX_HOLD_MIN:
            return _exit_signal(f"scalp_timeout_{hold_min:.0f}m", 1.0)
        return {"exit": False, "partial": False, "reason": "hold_scalp", "fraction": 0.0}

    # ── Orphan Fast Exit ─────────────────────────────────────────────────
    # DATA: orphan = 0% WR, -18.5 XRP total — worst performing category
    # Any orphan with fast_exit=True: sell at first profit, or cut at 1h
    if position.get("fast_exit") and is_orphan:
        if pnl_pct >= 0.005:  # any tiny profit → take it immediately
            return _exit_signal("orphan_profit_take", 1.0)
        if hold_hours >= 1.0:  # held 1h with no profit → cut it
            return _exit_signal("orphan_timeout_1hr", 1.0)

    # ── Hard Stop ────────────────────────────────────────────────────────
    # Unified stop — no tight early filter (meme tokens get stop hunted in first 30min)
    # Require 2 consecutive readings below stop before exiting (avoids single bad tick)
    consecutive_below_stop = position.get("consecutive_below_stop", 0)
    if pnl_pct <= -HARD_STOP_PCT:
        position["consecutive_below_stop"] = consecutive_below_stop + 1
        if consecutive_below_stop >= 1:  # 2nd consecutive reading = real stop
            position["consecutive_below_stop"] = 0
            return _exit_signal("hard_stop", 1.0)
        # First reading below stop — warn but hold one more cycle
    else:
        position["consecutive_below_stop"] = 0  # reset on any recovery

    # ── Break-even Protection ─────────────────────────────────────────────
    # DATA: breakeven_protection = 28.6% WR, -0.82 avg — triggering too early.
    # Raised from 5% to 8% so trades get more room before floor locks in.
    # We NEVER turn an 8%+ winner into a loser.
    if peak_pnl_pct >= 0.08:
        # Floor: never exit below entry
        if pnl_pct < 0.0:
            return _exit_signal("breakeven_protection", 1.0)

    # ── Tiered Trailing Stop ──────────────────────────────────────────────
    # Tighter trails as profit grows — lock in more of the gain as it moons.
    # Only applies once peak is above entry.
    if peak_price > entry_price:
        trail_drawdown = (peak_price - current_price) / peak_price
        # Peak >100%: trail at 15% (2x — lock in moonshot gains)
        if peak_pnl_pct >= 1.00 and trail_drawdown >= 0.15:
            return _exit_signal(f"trail_tight_{trail_drawdown:.1%}", 1.0)
        # Peak >50%: trail at 20%
        elif peak_pnl_pct >= 0.50 and trail_drawdown >= 0.20:
            return _exit_signal(f"trail_mid_{trail_drawdown:.1%}", 1.0)
        # Peak >25%: trail at 22%
        elif peak_pnl_pct >= 0.25 and trail_drawdown >= 0.22:
            return _exit_signal(f"trail_wide_{trail_drawdown:.1%}", 1.0)
        # Default: trail at 25% (TRAIL_STOP_PCT config)
        elif trail_drawdown >= TRAIL_STOP_PCT:
            return _exit_signal(f"trailing_stop_{trail_drawdown:.1%}", 1.0)

    # ── Take Profit Levels ────────────────────────────────────────────────
    # 4-tier TP system — designed to let real runners go to 600%+
    # After each TP, trailing stop protects remaining position
    # Must be genuinely profitable (pnl_pct > 0) to prevent stale price false exits

    # TP4: +600% → full exit — M1N/moonshot tier
    if pnl_pct >= TP4_PCT and pnl_pct > 0:
        return _exit_signal("tp4_moon", 1.0)

    # TP3: +300% → sell 30% of remainder (~34% of original still running free)
    if not tp3_hit and tp2_hit and pnl_pct >= TP3_PCT and pnl_pct > 0:
        return _partial_signal("tp3_runner", TP3_SELL_FRAC)

    # TP2: +50% → sell 30% of remainder (~49% of original still running)
    if not tp2_hit and tp1_hit and pnl_pct >= TP2_PCT:
        return _partial_signal("tp2_remainder", TP2_SELL_FRAC)

    # TP1: +20% → sell 30% (keep 70% running)
    if not tp1_hit and pnl_pct >= TP1_PCT:
        return _partial_signal("tp1_partial", TP1_SELL_FRAC)

    # ── Dynamic Stale Exit ────────────────────────────────────────────────
    # DATA: BXE -6.65 XRP, 589 -2.74 XRP, AMEN -1.71 XRP all bled on 3hr stale
    #       gei +5.73 XRP, TABS +5.25 XRP both won via longer hold
    # Fix: timer scales with position health — cut losers fast, let winners run
    xrp_spent    = float(position.get("xrp_spent", 0) or 0)
    pnl_xrp_est  = xrp_spent * pnl_pct  # rough XRP P&L estimate

    if pnl_xrp_est < -3.0:
        dynamic_stale = 2.0            # deep bleed (-3+ XRP) — cut at 2h
    elif pnl_xrp_est < -1.5:
        dynamic_stale = STALE_EXIT_HOURS  # moderate loss — normal timer
    elif pnl_xrp_est > 3.0:
        dynamic_stale = MAX_HOLD_HOURS # strong winner — max hold (12hr)
    elif pnl_xrp_est > 0.5:
        dynamic_stale = 10.0           # positive — let it breathe
    else:
        dynamic_stale = STALE_EXIT_HOURS  # flat — normal 3hr timer

    if hold_hours >= dynamic_stale and pnl_pct < -0.02:  # only stale-exit losers, not flat/small-gain positions
        return _exit_signal(f"stale_{hold_hours:.1f}hr", 1.0)

    # Max hold: absolute time limit
    if hold_hours >= MAX_HOLD_HOURS:
        return _exit_signal(f"max_hold_{hold_hours:.1f}hr", 1.0)

    # ── Dynamic Exit Signals ──────────────────────────────────────────────
    # Only apply after position has had time to develop (30min+)
    # And only trigger on meaningful losses (-5%+), not tiny dips
    # Skip entirely for orphans in first 2hr (no real price history)
    can_dynamic = not (is_orphan and hold_hours < 2.0) and hold_hours >= 0.5

    if can_dynamic:
        # Profit giveback: peaked well, now giving it all back
        # Only exit if we had significant peak AND are now deeply in red
        if peak_pnl_pct >= 0.20 and pnl_pct < -0.05:
            return _exit_signal("profit_giveback", 1.0)

        # Liquidity deterioration: TVL dropped >30% (much more tolerant — meme pools swing)
        if entry_tvl > 0 and current_tvl > 0:
            tvl_drop = (entry_tvl - current_tvl) / entry_tvl
            if tvl_drop > 0.30 and pnl_pct < -0.05:
                return _exit_signal(f"liquidity_drop_{tvl_drop:.1%}", 1.0)

        # Rapid price dump: dropped >8% in last 5 readings AND losing
        if len(price_history) >= 5 and pnl_pct < -0.05:
            recent_drop = (price_history[-5] - current_price) / price_history[-5]
            if recent_drop > 0.08:
                return _exit_signal("rapid_dump", 1.0)

        # Momentum stall: completely flat + losing + held >1hr
        # Requires 5 readings flat (tighter window = fewer false triggers)
        if len(price_history) >= 5 and hold_hours > 1.0 and pnl_pct < -0.05:
            recent = price_history[-5:]
            high, low = max(recent), min(recent)
            if high > 0 and (high - low) / high < 0.003:
                return _exit_signal("momentum_stall", 1.0)

    return {"exit": False, "partial": False, "reason": "hold", "fraction": 0.0}


def _exit_signal(reason: str, fraction: float) -> Dict:
    return {"exit": True, "partial": False, "reason": reason, "fraction": fraction}


def _partial_signal(reason: str, fraction: float) -> Dict:
    return {"exit": True, "partial": True, "reason": reason, "fraction": fraction}


def _has_lower_highs(prices: List[float]) -> bool:
    highs = []
    for i in range(1, len(prices) - 1):
        if prices[i] >= prices[i - 1] and prices[i] >= prices[i + 1]:
            highs.append(prices[i])
    if len(highs) < 2:
        return False
    return highs[-1] < highs[-2]


def update_peak(position: Dict, current_price: float) -> Dict:
    if current_price > position.get("peak_price", 0):
        position["peak_price"] = current_price
    return position

======================================================================
# SMART_MONEY — smart_money.py
======================================================================

"""
smart_money.py — Track profitable wallets and detect coordinated buying.
Boost score +10 (single wallet) or +20 (multiple wallets) when they buy
the same token within 5 minutes.
Writes: state/smart_money.json
"""

import json
import os
import time
import requests
from typing import Dict, List, Set, Optional
from config import CLIO_URL, STATE_DIR, WHALE_XRP_THRESHOLD, get_currency

os.makedirs(STATE_DIR, exist_ok=True)
SM_FILE = os.path.join(STATE_DIR, "smart_money.json")

# Wallets considered "smart money" — populated from trade history winners
SMART_MONEY_WALLETS: Set[str] = set()


def _rpc(method: str, params: dict) -> Optional[dict]:
    try:
        resp = requests.post(CLIO_URL, json={"method": method, "params": [params]}, timeout=15)
        return resp.json().get("result")
    except Exception:
        return None


def _load_sm() -> Dict:
    if os.path.exists(SM_FILE):
        try:
            with open(SM_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"wallets": [], "recent_buys": {}, "signals": {}}


def _save_sm(data: Dict) -> None:
    with open(SM_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_recent_token_buys(symbol: str, issuer: str,
                          lookback_seconds: int = 300) -> List[Dict]:
    """
    Get recent AMM/DEX buys for a token in the last `lookback_seconds`.
    Returns list of {wallet, amount_xrp, ts}.
    """
    currency = get_currency(symbol)
    result   = _rpc("account_tx", {
        "account":         issuer,
        "limit":           50,
        "ledger_index_min": -1,
        "ledger_index_max": -1,
    })
    if not result or result.get("status") != "success":
        return []

    cutoff  = time.time() - lookback_seconds
    buys    = []

    for tx_wrapper in result.get("transactions", []):
        tx   = tx_wrapper.get("tx", {})
        meta = tx_wrapper.get("meta", {})

        # Look for OfferCreate or Payment involving this token
        tx_type  = tx.get("TransactionType", "")
        tx_time  = tx.get("date", 0) + 946684800  # Ripple epoch

        if tx_time < cutoff:
            continue

        sender = tx.get("Account", "")

        if tx_type == "OfferCreate":
            tp = tx.get("TakerPays", {})
            tg = tx.get("TakerGets", {})
            # Buying token: TakerPays=token, TakerGets=XRP
            if (isinstance(tp, dict) and tp.get("currency") == currency and
                    tp.get("issuer") == issuer and isinstance(tg, str)):
                xrp_val = int(tg) / 1e6
                buys.append({"wallet": sender, "amount_xrp": xrp_val, "ts": tx_time})

    return buys


def check_smart_money_signal(symbol: str, issuer: str,
                              known_wallets: Set[str] = None) -> Dict:
    """
    Check if smart money wallets are buying this token.
    Returns {boost: int, wallets: list, signal: str}
    """
    sm_data = _load_sm()
    tracked = set(sm_data.get("wallets", [])) | (known_wallets or SMART_MONEY_WALLETS)

    if not tracked:
        return {"boost": 0, "wallets": [], "signal": "no_tracked_wallets"}

    recent_buys = get_recent_token_buys(symbol, issuer, lookback_seconds=300)
    smart_buyers = [b for b in recent_buys if b["wallet"] in tracked]

    key    = f"{symbol}:{issuer}"
    ts_now = time.time()

    # Record signal
    sm_data.setdefault("signals", {})[key] = {
        "ts":           ts_now,
        "smart_buyers": len(smart_buyers),
        "all_buyers":   len(recent_buys),
    }

    if len(smart_buyers) >= 2:
        _save_sm(sm_data)
        return {"boost": 20, "wallets": [b["wallet"] for b in smart_buyers],
                "signal": "multiple_smart_money"}
    elif len(smart_buyers) == 1:
        _save_sm(sm_data)
        return {"boost": 10, "wallets": [b["wallet"] for b in smart_buyers],
                "signal": "single_smart_money"}
    else:
        _save_sm(sm_data)
        return {"boost": 0, "wallets": [], "signal": "no_signal"}


def update_smart_wallets_from_trades(trade_history: List[Dict]) -> None:
    """
    Identify consistently profitable wallets from trade history.
    Wallets that appeared in our winning trades' concurrent buys.
    """
    sm_data = _load_sm()
    # Simple: store wallets seen in smart_money signals on winning trades
    wallet_wins: Dict[str, int] = {}
    for trade in trade_history:
        if trade.get("pnl_pct", 0) > 0.05:
            for w in trade.get("smart_wallets", []):
                wallet_wins[w] = wallet_wins.get(w, 0) + 1

    # Wallets with 2+ wins = smart money
    sm_wallets = [w for w, wins in wallet_wins.items() if wins >= 2]
    sm_data["wallets"] = sm_wallets[:50]  # cap at 50
    _save_sm(sm_data)


if __name__ == "__main__":
    result = check_smart_money_signal("SOLO", "rsoLo2S1kiGeCcn6hCUXVrCpGMWLrRrLZz")
    print(json.dumps(result, indent=2))

======================================================================
# WALLET_INTELLIGENCE — wallet_intelligence.py
======================================================================

"""
wallet_intelligence.py — On-chain wallet scoring & clustering for DKTrenchBot

Replicates HorizonXRPL's Starmaps / wallet analysis features using pure XRPL RPC.

For each candidate token, this module:
1. Pulls all current holders (excluding AMM pool)
2. For each significant holder, scores them by:
   - Realized PnL across recent trades (profitable trader signal)
   - Number of tokens held (diversification / serial buyer)
   - Entry timing on past tokens (early mover score)
   - Wallet age & activity (established vs fresh burner)
   - Cluster detection (wallets that co-hold multiple same tokens = coordinated group)
3. Returns an intelligence summary:
   - smart_money_score: 0-100 (how much smart money is in this token)
   - cluster_count: # of detected wallet clusters
   - early_movers: wallets that got in early with profitable history
   - risk_flags: coordinated dump risk, new wallets, etc.

Called from bot.py for any token that passes initial score threshold.
Result injected as score modifier before final entry decision.
"""

import json, os, time, requests, logging
from typing import Dict, List, Tuple
from collections import defaultdict

logger = logging.getLogger("wallet_intel")

CLIO = os.environ.get("CLIO_URL", "https://rpc.xrplclaw.com")
XRPL_EPOCH = 946684800
STATE_FILE = os.path.join(os.path.dirname(__file__), "state", "wallet_intel_cache.json")

# Cache wallet scores for 30 min to avoid re-fetching
CACHE_TTL = 1800
# How many top holders to analyze deeply (balance cost vs depth)
MAX_HOLDERS_DEEP = 15
# Min token balance % to be considered a "significant holder"
MIN_HOLDER_PCT = 0.5

def _rpc(method, params, timeout=10):
    try:
        r = requests.post(CLIO, json={"method": method, "params": [params]}, timeout=timeout)
        return r.json().get("result", {})
    except Exception as e:
        logger.debug(f"RPC error {method}: {e}")
        return {}

def _load_cache() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except:
        return {}

def _save_cache(cache: dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(cache, f)

def _decode_currency(cur: str) -> str:
    if not cur or len(cur) <= 3:
        return cur or ""
    try:
        padded = cur.ljust(40, "0")[:40]
        raw = bytes.fromhex(padded).decode("ascii", errors="ignore")
        name = raw.rstrip("\x00").strip()
        return name if name and name.isprintable() else cur[:8]
    except:
        return cur[:8]

# ─────────────────────────────────────────────────────────────────────────────
# WALLET SCORING
# ─────────────────────────────────────────────────────────────────────────────

def score_wallet(address: str, cache: dict) -> dict:
    """
    Score a single wallet. Returns a score dict with components.
    Cached for CACHE_TTL seconds.
    """
    now = time.time()
    cached = cache.get(address, {})
    if cached and now - cached.get("ts", 0) < CACHE_TTL:
        return cached

    score = 0
    flags = []
    details = {}

    # ── 1. Wallet age & basic info ────────────────────────────────────────
    ai = _rpc("account_info", {"account": address, "ledger_index": "validated"})
    if not ai.get("account_data"):
        return {"score": 0, "flags": ["wallet_not_found"], "ts": now}

    ad = ai["account_data"]
    xrp_bal = int(ad.get("Balance", 0)) / 1e6
    seq = ad.get("Sequence", 0)
    owner_count = ad.get("OwnerCount", 0)

    # Age proxy: lower sequence = older wallet
    if seq < 1_000_000:
        score += 15  # very old wallet
        details["age"] = "veteran"
    elif seq < 5_000_000:
        score += 10
        details["age"] = "established"
    elif seq < 20_000_000:
        score += 5
        details["age"] = "active"
    else:
        score += 0
        details["age"] = "new"
        flags.append("new_wallet")

    # XRP balance = skin in the game
    if xrp_bal >= 500:
        score += 15
        details["xrp"] = "whale"
    elif xrp_bal >= 100:
        score += 10
        details["xrp"] = "strong"
    elif xrp_bal >= 20:
        score += 5
        details["xrp"] = "active"
    elif xrp_bal < 5:
        flags.append("low_xrp")
        details["xrp"] = "low"

    # ── 2. Token portfolio diversity ──────────────────────────────────────
    lines = _rpc("account_lines", {"account": address, "limit": 400})
    holdings = lines.get("lines", [])
    nonzero = [h for h in holdings if abs(float(h.get("balance", 0))) > 0]
    token_count = len(nonzero)
    details["token_count"] = token_count

    if token_count >= 10:
        score += 12  # serial meme buyer — knows the game
        details["portfolio"] = "serial_buyer"
    elif token_count >= 5:
        score += 8
        details["portfolio"] = "diversified"
    elif token_count >= 2:
        score += 4
        details["portfolio"] = "selective"
    else:
        details["portfolio"] = "concentrated"

    # ── 3. Trading activity & PnL (last 50 txs) ──────────────────────────
    txs = _rpc("account_tx", {"account": address, "limit": 50, "forward": False})
    transactions = txs.get("transactions", [])

    offers_created = 0
    offers_filled = 0
    payments_out = 0
    xrp_flows = []

    for t in transactions:
        tx = t.get("tx", t.get("transaction", {}))
        meta = t.get("meta", t.get("metadata", {}))
        tt = tx.get("TransactionType", "")

        if tt == "OfferCreate":
            offers_created += 1
            result = meta.get("TransactionResult", "")
            if result == "tesSUCCESS":
                # Check if offer was filled (taker_gets delivered)
                for node in meta.get("AffectedNodes", []):
                    mn = node.get("DeletedNode", node.get("ModifiedNode", {}))
                    if mn.get("LedgerEntryType") == "Offer":
                        offers_filled += 1
                        break

        elif tt == "Payment":
            payments_out += 1

    details["offers_created"] = offers_created
    details["offers_filled"] = offers_filled
    fill_rate = offers_filled / offers_created if offers_created > 0 else 0

    if fill_rate >= 0.7 and offers_created >= 5:
        score += 15  # active trader with high fill rate = skilled
        details["trading"] = "skilled_trader"
        flags.append("active_trader")
    elif offers_created >= 3:
        score += 8
        details["trading"] = "active"
    elif offers_created == 0:
        details["trading"] = "passive_holder"

    # ── 4. Early mover detection ──────────────────────────────────────────
    # Check if this wallet was in the first 20 holders of any token
    # (proxy: has very old TrustSets relative to token age)
    early_score = 0
    for h in nonzero[:10]:  # check first 10 holdings
        cur = h.get("currency", "")
        peer = h.get("account", "")
        # Check when they set this trustline
        limit_ts = None
        for t in transactions:
            tx = t.get("tx", t.get("transaction", {}))
            if tx.get("TransactionType") == "TrustSet":
                lim = tx.get("LimitAmount", {})
                if isinstance(lim, dict) and lim.get("currency") == cur and lim.get("issuer") == peer:
                    limit_ts = tx.get("date", 0) + XRPL_EPOCH
                    break
        # We can't fully measure early entry here without token creation time
        # But if they have many TrustSets in history = active meme hunter
        if limit_ts:
            early_score += 1

    if early_score >= 5:
        score += 10
        details["early_mover"] = True
        flags.append("early_mover")
    elif early_score >= 2:
        score += 5

    # Clamp score
    score = min(100, max(0, score))

    result = {
        "score":        score,
        "xrp_balance":  xrp_bal,
        "token_count":  token_count,
        "age":          details.get("age", "unknown"),
        "trading":      details.get("trading", "unknown"),
        "portfolio":    details.get("portfolio", "unknown"),
        "flags":        flags,
        "details":      details,
        "ts":           now,
    }
    cache[address] = result
    return result


# ─────────────────────────────────────────────────────────────────────────────
# CLUSTER DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def detect_clusters(holders: List[dict], amm_pool: str) -> dict:
    """
    Detect wallet clusters — groups that co-hold the same tokens.
    Wallets that appear together across multiple tokens = coordinated group.
    
    High cluster count = community is organised (bullish for coordinated pumps)
    Single large cluster = potential coordinated dump risk
    """
    # For each holder, get their other token holdings
    wallet_tokens = {}  # address -> set of token issuers held
    
    significant = [
        h for h in holders
        if h.get("account") != amm_pool and abs(float(h.get("balance", 0))) > 0
    ][:20]  # limit to top 20 for speed

    for h in significant:
        addr = h["account"]
        lines = _rpc("account_lines", {"account": addr, "limit": 100})
        held = frozenset(
            l.get("account", "")
            for l in lines.get("lines", [])
            if abs(float(l.get("balance", 0))) > 0
        )
        wallet_tokens[addr] = held

    # Find wallets that share ≥2 common token issuers = cluster
    clusters = defaultdict(set)
    addrs = list(wallet_tokens.keys())

    for i in range(len(addrs)):
        for j in range(i+1, len(addrs)):
            a, b = addrs[i], addrs[j]
            shared = wallet_tokens[a] & wallet_tokens[b]
            if len(shared) >= 2:
                # They're in the same cluster
                cluster_key = min(a, b)
                clusters[cluster_key].add(a)
                clusters[cluster_key].add(b)

    # Merge overlapping clusters
    merged = []
    assigned = set()
    for key, members in clusters.items():
        if key not in assigned:
            group = set(members)
            for other_key, other_members in clusters.items():
                if other_key != key and group & other_members:
                    group |= other_members
            merged.append(group)
            assigned |= group

    # Singletons (no cluster)
    singletons = [a for a in addrs if a not in assigned]

    return {
        "cluster_count":   len(merged),
        "clusters":        [list(c) for c in merged],
        "singleton_count": len(singletons),
        "total_analyzed":  len(significant),
        "largest_cluster": max((len(c) for c in merged), default=0),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ANALYSIS FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def analyze_token(symbol: str, currency: str, issuer: str) -> dict:
    """
    Full wallet intelligence analysis for a candidate token.
    
    Returns:
        smart_money_score: 0-100 composite score
        score_modifier:    how much to adjust bot entry score (+/-)
        summary:           human-readable summary
        flags:             list of risk/opportunity flags
        top_holders:       scored holder list
        clusters:          cluster analysis
    """
    now = time.time()
    cache = _load_cache()
    token_key = f"{currency}:{issuer}"

    # Check token-level cache
    token_cache = cache.get(f"token:{token_key}", {})
    if token_cache and now - token_cache.get("ts", 0) < CACHE_TTL:
        logger.debug(f"[wallet_intel] {symbol}: cached result")
        return token_cache

    logger.info(f"[wallet_intel] Analyzing {symbol} holders...")

    # ── Get AMM pool account ──────────────────────────────────────────────
    amm_pool = ""
    amm_res = _rpc("amm_info", {"asset": {"currency": "XRP"}, "asset2": {"currency": currency, "issuer": issuer}})
    if amm_res.get("amm"):
        amm_pool = amm_res["amm"].get("account", "")

    # ── Get all holders ───────────────────────────────────────────────────
    lines_res = _rpc("account_lines", {"account": issuer, "limit": 400})
    all_lines = lines_res.get("lines", [])

    # Filter: exclude AMM pool, zero balances, get real holders
    holders = [
        l for l in all_lines
        if l.get("account") != amm_pool
        and abs(float(l.get("balance", 0))) > 0
    ]

    if not holders:
        return {"smart_money_score": 50, "score_modifier": 0, "summary": "no holders found",
                "flags": [], "top_holders": [], "clusters": {}, "ts": now}

    # Calculate total supply ex-AMM
    total_supply = sum(abs(float(h.get("balance", 0))) for h in holders)

    # Sort by balance
    holders_sorted = sorted(holders, key=lambda x: abs(float(x.get("balance", 0))), reverse=True)

    # ── Score top holders ─────────────────────────────────────────────────
    top_holders_scored = []
    wallet_scores = []

    for h in holders_sorted[:MAX_HOLDERS_DEEP]:
        addr = h["account"]
        bal = abs(float(h.get("balance", 0)))
        pct = bal / total_supply * 100 if total_supply > 0 else 0

        ws = score_wallet(addr, cache)
        wallet_scores.append(ws["score"])

        top_holders_scored.append({
            "address":      addr,
            "balance":      bal,
            "pct":          round(pct, 2),
            "wallet_score": ws["score"],
            "age":          ws.get("age", "?"),
            "token_count":  ws.get("token_count", 0),
            "trading":      ws.get("trading", "?"),
            "flags":        ws.get("flags", []),
            "xrp_balance":  ws.get("xrp_balance", 0),
        })

    _save_cache(cache)

    # ── Cluster analysis ──────────────────────────────────────────────────
    cluster_data = detect_clusters(holders_sorted[:20], amm_pool)

    # ── Composite smart money score ───────────────────────────────────────
    avg_wallet_score = sum(wallet_scores) / len(wallet_scores) if wallet_scores else 50

    # Count high-quality holders
    high_quality = len([s for s in wallet_scores if s >= 60])
    medium_quality = len([s for s in wallet_scores if 40 <= s < 60])

    smart_money_score = int(avg_wallet_score)

    # Bonus for multiple high-quality holders
    if high_quality >= 5:
        smart_money_score = min(100, smart_money_score + 15)
    elif high_quality >= 3:
        smart_money_score = min(100, smart_money_score + 10)
    elif high_quality >= 1:
        smart_money_score = min(100, smart_money_score + 5)

    # Cluster bonus: organised community = coordinated buying
    cluster_bonus = 0
    if cluster_data["cluster_count"] >= 3:
        cluster_bonus = 8
    elif cluster_data["cluster_count"] >= 2:
        cluster_bonus = 5
    elif cluster_data["cluster_count"] == 1 and cluster_data["largest_cluster"] >= 5:
        cluster_bonus = 10  # one tight group = PHX-style community

    smart_money_score = min(100, smart_money_score + cluster_bonus)

    # ── Score modifier for bot entry ──────────────────────────────────────
    # Translate smart money score into +/- on bot's total score
    if smart_money_score >= 75:
        score_modifier = +10   # strong smart money = boost
    elif smart_money_score >= 60:
        score_modifier = +6
    elif smart_money_score >= 45:
        score_modifier = +2
    elif smart_money_score >= 30:
        score_modifier = 0
    else:
        score_modifier = -5   # weak holder base = mild penalty

    # ── Flags ─────────────────────────────────────────────────────────────
    flags = []
    all_wallet_flags = [f for h in top_holders_scored for f in h["flags"]]

    if all_wallet_flags.count("early_mover") >= 3:
        flags.append("multiple_early_movers")
        score_modifier += 5

    if all_wallet_flags.count("active_trader") >= 3:
        flags.append("trader_heavy_holder_base")
        score_modifier += 3

    if all_wallet_flags.count("new_wallet") >= 5:
        flags.append("many_new_wallets")   # fresh burners = potential coordinated buy/dump
        score_modifier -= 3

    if cluster_data["largest_cluster"] >= 8:
        flags.append("large_coordinated_cluster")  # could go either way
        
    serial_buyers = len([h for h in top_holders_scored if h["token_count"] >= 8])
    if serial_buyers >= 3:
        flags.append("serial_meme_buyers")
        score_modifier += 4

    # Clamp modifier
    score_modifier = max(-15, min(+15, score_modifier))

    # ── Summary ───────────────────────────────────────────────────────────
    top3 = top_holders_scored[:3]
    summary_parts = []
    summary_parts.append(f"{len(holders)} real holders (ex-AMM)")
    summary_parts.append(f"smart_money={smart_money_score}/100")
    summary_parts.append(f"avg_holder_score={avg_wallet_score:.0f}")
    summary_parts.append(f"clusters={cluster_data['cluster_count']}")
    if flags:
        summary_parts.append(f"flags={flags}")

    result = {
        "symbol":            symbol,
        "smart_money_score": smart_money_score,
        "score_modifier":    score_modifier,
        "avg_holder_score":  round(avg_wallet_score, 1),
        "high_quality_holders": high_quality,
        "total_holders":     len(holders),
        "summary":           " | ".join(summary_parts),
        "flags":             flags,
        "top_holders":       top_holders_scored,
        "clusters":          cluster_data,
        "ts":                now,
    }

    # Cache at token level
    cache[f"token:{token_key}"] = result
    _save_cache(cache)

    return result


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # Test on RUGRATS
    result = analyze_token(
        "RUGRATS",
        "5255475241545300000000000000000000000000",
        "r3owcAEjUpT7eJsr99FRXDaRq9EUkM4jUF"
    )
    print(f"\n{'='*55}")
    print(f"  RUGRATS Wallet Intelligence")
    print(f"{'='*55}")
    print(f"  Smart money score: {result['smart_money_score']}/100")
    print(f"  Score modifier:    {result['score_modifier']:+d}")
    print(f"  Total holders:     {result['total_holders']}")
    print(f"  High-quality:      {result['high_quality_holders']}")
    print(f"  Flags:             {result['flags']}")
    print(f"  Clusters:          {result['clusters']['cluster_count']} detected | largest={result['clusters']['largest_cluster']}")
    print(f"\n  Top Holders:")
    for h in result["top_holders"][:8]:
        flag_str = ",".join(h["flags"]) if h["flags"] else "-"
        print(f"    {h['address'][:18]}  {h['pct']:5.1f}%  score={h['wallet_score']:3d}  "
              f"age={h['age']:12}  tokens={h['token_count']:3d}  xrp={h['xrp_balance']:8.1f}  [{flag_str}]")

======================================================================
# WALLET_CLUSTER — wallet_cluster.py
======================================================================

"""
wallet_cluster.py — Wallet Clustering on Realtime Stream (Audit #2)

Goal: Alert when 2+ known smart wallets enter the same token on the live stream.

Algorithm:
1. Load known_wallets = list(config.TRACKED_WALLETS) + discovered_wallets from state/discovered_wallets.json
2. Subscribe to XRPL websocket stream: wss://rpc.xrplclaw.com/ (CLIO supports account subscriptions)
3. For each known wallet, watch for incoming Payments (TrustSet doesn't help — watch Payments to token issuers)
4. Maintain in-memory dict: token_wallet_map[token] = set of wallets seen in last 10 min
5. If token_wallet_map[token] has >= 2 distinct known wallets entering within 10 min → CLUSTER_ALERT
6. Emit cluster_alert to bot_state["signals"]["wallet_cluster"] and log it prominently
7. The scoring module (scoring.py) should read this signal and boost the token's score significantly (+30 points)
8. Clean up old entries (10 min TTL on each wallet entry per token)
9. Graceful reconnect on disconnect

Note on XRPL websocket: CLIO supports `subscribe` with `accounts` field.
Send: {"command":"subscribe","accounts":[wallet1, wallet2, ...]}
"""

import json
import os
import time
import logging
import threading
import websocket
from typing import Dict, List, Set, Optional, Callable
from collections import defaultdict

logger = logging.getLogger("wallet_cluster")

STATE_DIR = os.path.join(os.path.dirname(__file__), "state")
SIGNALS_FILE = os.path.join(STATE_DIR, "cluster_signals.json")
WS_URL = "wss://rpc.xrplclaw.com/"

# Time-to-live for wallet entries per token (seconds)
ENTRY_TTL_SEC = 600  # 10 minutes

# Minimum wallets to trigger cluster alert
CLUSTER_THRESHOLD = 2

# Reconnect delay (seconds)
RECONNECT_DELAY = 5


class WalletClusterMonitor:
    """Monitors known wallets for coordinated token entries."""

    def __init__(self):
        self._ws: Optional[websocket.WebSocketApp] = None
        self._running = False
        self._token_wallet_map: Dict[str, Dict[str, float]] = {}  # token -> {wallet: ts}
        self._cluster_alerts: List[Dict] = []
        self._known_wallets: Set[str] = set()
        self._lock = threading.Lock()
        self._bot_state_ref: Optional[dict] = None  # Reference to bot_state for signal injection
        self._on_alert_callback: Optional[Callable] = None

    def load_known_wallets(self) -> Set[str]:
        """Load tracked wallets from config and discovered_wallets.json."""
        wallets = set()

        # From config TRACKED_WALLETS
        try:
            from config import TRACKED_WALLETS
            if isinstance(TRACKED_WALLETS, (list, tuple)):
                wallets.update(TRACKED_WALLETS)
        except (ImportError, AttributeError):
            pass

        # From discovered_wallets.json
        discovered_file = os.path.join(STATE_DIR, "discovered_wallets.json")
        if os.path.exists(discovered_file):
            try:
                with open(discovered_file) as f:
                    data = json.load(f)
                wallets.update(data.get("tracked", []))
                wallets.update(data.get("candidates", {}).keys())
            except Exception as e:
                logger.debug(f"Error loading discovered wallets: {e}")

        self._known_wallets = wallets
        return wallets

    def _cleanup_expired(self):
        """Remove expired wallet entries (older than ENTRY_TTL_SEC)."""
        now = time.time()
        with self._lock:
            for token in list(self._token_wallet_map.keys()):
                self._token_wallet_map[token] = {
                    w: ts for w, ts in self._token_wallet_map[token].items()
                    if now - ts < ENTRY_TTL_SEC
                }
                # Remove empty tokens
                if not self._token_wallet_map[token]:
                    del self._token_wallet_map[token]

    def _record_wallet_entry(self, wallet: str, token_key: str):
        """Record a wallet entering a token."""
        now = time.time()
        with self._lock:
            if token_key not in self._token_wallet_map:
                self._token_wallet_map[token_key] = {}
            self._token_wallet_map[token_key][wallet] = now

        # Check for cluster
        self._check_cluster(token_key)

    def _check_cluster(self, token_key: str):
        """Check if token has enough wallets to trigger cluster alert."""
        now = time.time()
        with self._lock:
            wallets_in_window = self._token_wallet_map.get(token_key, {})
            active_wallets = {
                w for w, ts in wallets_in_window.items()
                if now - ts < ENTRY_TTL_SEC
            }

        if len(active_wallets) >= CLUSTER_THRESHOLD:
            # Parse token key: "SYMBOL:issuer" or "currency:issuer"
            parts = token_key.split(":")
            symbol = parts[0] if parts else token_key

            alert = {
                "token": token_key,
                "symbol": symbol,
                "wallets": list(active_wallets),
                "count": len(active_wallets),
                "ts": now,
                "signal_type": "wallet_cluster",
            }

            # Dedup: don't re-alert same token within 5 minutes
            recent_same = [
                a for a in self._cluster_alerts
                if a["token"] == token_key and now - a["ts"] < 300
            ]
            if not recent_same:
                self._cluster_alerts.append(alert)
                # Keep last 50 alerts
                if len(self._cluster_alerts) > 50:
                    self._cluster_alerts = self._cluster_alerts[-50:]

                logger.warning(
                    f"🚨 CLUSTER ALERT: {symbol} — {len(active_wallets)} smart wallets entered! "
                    f"Wallets: {[w[:10]+'...' for w in active_wallets]}"
                )

                # Save to signals file
                self._save_signals()

                # Inject into bot_state if reference available
                if self._bot_state_ref is not None:
                    if "signals" not in self._bot_state_ref:
                        self._bot_state_ref["signals"] = {}
                    self._bot_state_ref["signals"]["wallet_cluster"] = alert

                # Call callback if registered
                if self._on_alert_callback:
                    try:
                        self._on_alert_callback(alert)
                    except Exception as e:
                        logger.error(f"Cluster alert callback error: {e}")

    def _save_signals(self):
        """Save cluster signals to file."""
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = SIGNALS_FILE + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump({
                    "alerts": self._cluster_alerts[-20:],  # Last 20
                    "last_updated": time.time(),
                }, f, indent=2)
            os.replace(tmp, SIGNALS_FILE)
        except Exception as e:
            logger.error(f"Error saving cluster signals: {e}")

    def _handle_message(self, ws, message: str):
        """Process incoming websocket messages."""
        try:
            data = json.loads(message)

            # Transaction notification
            if data.get("type") == "transaction":
                tx_data = data.get("transaction", {})
                meta = data.get("meta", {})
                tx_type = tx_data.get("TransactionType", "")
                account = tx_data.get("Account", "")

                # Only process transactions from our known wallets
                if account not in self._known_wallets:
                    return

                # Detect token purchases via Payment or OfferCreate
                if tx_type == "Payment":
                    amount = tx_data.get("Amount", {})
                    destination = tx_data.get("Destination", "")

                    # If the payment is a token (not XRP), record it
                    if isinstance(amount, dict):
                        currency = amount.get("currency", "")
                        issuer = amount.get("issuer", "")
                        if currency and issuer:
                            token_key = f"{currency}:{issuer}"
                            self._record_wallet_entry(account, token_key)
                            logger.info(
                                f"  📥 {account[:10]}... bought {currency[:8]} via Payment"
                            )

                elif tx_type == "OfferCreate":
                    # Detect buy offers: TakerPays=XRP, TakerGets=token
                    tp = tx_data.get("TakerPays", {})
                    tg = tx_data.get("TakerGets", {})

                    # Buying token: paying XRP (string), getting token (dict)
                    if isinstance(tp, str) and isinstance(tg, dict):
                        currency = tg.get("currency", "")
                        issuer = tg.get("issuer", "")
                        if currency and issuer:
                            token_key = f"{currency}:{issuer}"
                            self._record_wallet_entry(account, token_key)
                            logger.info(
                                f"  📥 {account[:10]}... bought {currency[:8]} via OfferCreate"
                            )

            elif data.get("type") == "ledgerClosed":
                # Periodic cleanup on ledger close
                self._cleanup_expired()

        except Exception as e:
            logger.debug(f"Message handling error: {e}")

    def _handle_error(self, ws, error):
        logger.error(f"WebSocket error: {error}")

    def _handle_close(self, ws, close_status_code, close_msg):
        logger.info(f"WebSocket closed: {close_status_code} {close_msg}")
        if self._running:
            logger.info(f"Reconnecting in {RECONNECT_DELAY}s...")
            time.sleep(RECONNECT_DELAY)
            self._connect()

    def _handle_open(self, ws):
        logger.info("WebSocket connected — subscribing to accounts...")
        self._subscribe_accounts(ws)

    def _subscribe_accounts(self, ws):
        """Subscribe to account transactions."""
        if not self._known_wallets:
            self.load_known_wallets()

        if not self._known_wallets:
            logger.warning("No known wallets to subscribe to")
            return

        # XRPL has limits on subscription size — batch if needed
        wallet_list = list(self._known_wallets)
        logger.info(f"Subscribing to {len(wallet_list)} wallets...")

        subscribe_msg = {
            "command": "subscribe",
            "accounts": wallet_list,
            "streams": ["ledger"],
        }

        try:
            ws.send(json.dumps(subscribe_msg))
            logger.info("Subscription sent")
        except Exception as e:
            logger.error(f"Subscription error: {e}")

    def _connect(self):
        """Establish WebSocket connection."""
        self._ws = websocket.WebSocketApp(
            WS_URL,
            on_open=self._handle_open,
            on_message=self._handle_message,
            on_error=self._handle_error,
            on_close=self._handle_close,
        )

        try:
            self._ws.run_forever()
        except Exception as e:
            logger.error(f"WebSocket run error: {e}")

    def start(self, bot_state: Optional[dict] = None, on_alert: Optional[Callable] = None):
        """Start the cluster monitor in a background thread."""
        if self._running:
            logger.warning("Cluster monitor already running")
            return

        self._running = True
        self._bot_state_ref = bot_state
        self._on_alert_callback = on_alert
        self.load_known_wallets()

        logger.info(f"Starting wallet cluster monitor ({len(self._known_wallets)} wallets)")

        self._thread = threading.Thread(target=self._connect, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the cluster monitor."""
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        logger.info("Wallet cluster monitor stopped")

    def get_active_clusters(self) -> List[Dict]:
        """Get current active cluster signals."""
        now = time.time()
        clusters = []
        with self._lock:
            for token, wallets_ts in self._token_wallet_map.items():
                active = {w for w, ts in wallets_ts.items() if now - ts < ENTRY_TTL_SEC}
                if len(active) >= CLUSTER_THRESHOLD:
                    clusters.append({
                        "token": token,
                        "wallets": list(active),
                        "count": len(active),
                    })
        return clusters

    def get_cluster_score_boost(self, symbol: str, issuer: str) -> int:
        """
        Get score boost for a token based on cluster activity.
        Returns +30 if cluster detected, 0 otherwise.
        Called by scoring.py.
        """
        token_key = f"{symbol}:{issuer}"
        now = time.time()

        with self._lock:
            wallets_ts = self._token_wallet_map.get(token_key, {})
            active_count = sum(1 for ts in wallets_ts.values() if now - ts < ENTRY_TTL_SEC)

        if active_count >= CLUSTER_THRESHOLD:
            return 30  # Significant boost
        return 0


# Global instance for integration with bot
_monitor: Optional[WalletClusterMonitor] = None


def start_cluster_monitor(bot_state: Optional[dict] = None, on_alert: Optional[Callable] = None):
    """Start the global cluster monitor."""
    global _monitor
    if _monitor is None:
        _monitor = WalletClusterMonitor()
    _monitor.start(bot_state=bot_state, on_alert=on_alert)


def stop_cluster_monitor():
    """Stop the global cluster monitor."""
    global _monitor
    if _monitor:
        _monitor.stop()
        _monitor = None


def get_cluster_boost(symbol: str, issuer: str) -> int:
    """Get cluster score boost for a token (called by scoring.py)."""
    global _monitor
    if _monitor:
        return _monitor.get_cluster_score_boost(symbol, issuer)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("Wallet Cluster Monitor — test mode")
    print("This module runs as a background thread in the main bot.")
    monitor = WalletClusterMonitor()
    wallets = monitor.load_known_wallets()
    print(f"Known wallets: {len(wallets)}")
    for w in list(wallets)[:5]:
        print(f"  - {w}")

======================================================================
# CHART_INTELLIGENCE — chart_intelligence.py
======================================================================

"""
chart_intelligence.py — Classify token market structure.
States: accumulation, pre_breakout, expansion, continuation, exhaustion, reversal_risk, dead
Tradeable states: pre_breakout, expansion, continuation
"""

import os
import json
from typing import Dict, List, Optional
from config import STATE_DIR

os.makedirs(STATE_DIR, exist_ok=True)

TRADEABLE_STATES = {"pre_breakout", "expansion", "continuation"}

CHART_STATES = [
    "accumulation",
    "pre_breakout",
    "expansion",
    "continuation",
    "exhaustion",
    "reversal_risk",
    "dead",
]


def classify(token_key: str, prices: List[float], tvl_readings: List[float],
             breakout_quality: int = 0) -> Dict:
    """
    Classify market structure from price and TVL history.

    Returns dict with: state, confidence, tradeable, details
    """
    if not prices or len(prices) < 2:
        return _result("dead", 0.5, "insufficient_data")

    n = len(prices)
    first = prices[0]
    last  = prices[-1]

    if first <= 0:
        return _result("dead", 0.9, "zero_price")

    pct_change   = (last - first) / first
    recent_3     = prices[-3:] if n >= 3 else prices
    recent_5     = prices[-5:] if n >= 5 else prices

    # Dead: price declining significantly
    if pct_change < -0.20:
        return _result("dead", 0.9, f"price_down_{pct_change:.1%}")

    # TVL trend
    tvl_trend = 0.0
    if len(tvl_readings) >= 2:
        tvl_trend = (tvl_readings[-1] - tvl_readings[0]) / tvl_readings[0] if tvl_readings[0] > 0 else 0

    # Reversal risk: was rising, now dropping, TVL also dropping
    if n >= 5:
        peak_idx  = prices.index(max(prices))
        is_peaked = peak_idx < n - 2
        if is_peaked and last < prices[peak_idx] * 0.90 and tvl_trend < -0.05:
            return _result("reversal_risk", 0.8, "peaked_and_declining")

    # Exhaustion: extreme extension + slowing momentum
    total_move = pct_change
    if total_move > 0.40 and _is_slowing(prices):
        return _result("exhaustion", 0.75, f"extended_{total_move:.1%}_slowing")

    # Expansion: strong uptrend, high breakout quality
    if breakout_quality >= 65 and pct_change > 0.05 and _is_trending_up(recent_5):
        confidence = min(1.0, breakout_quality / 100 + 0.1)
        return _result("expansion", confidence, f"bq={breakout_quality}")

    # Pre-breakout: compression with higher lows
    if breakout_quality >= 40 and abs(pct_change) < 0.08 and _has_higher_lows(prices):
        return _result("pre_breakout", 0.7, "compressed_higher_lows")

    # Continuation: uptrend with pullback-to-support pattern
    if pct_change > 0.03 and _is_continuation(prices):
        return _result("continuation", 0.65, "pullback_continuation")

    # Accumulation: tight range, low volatility, slight upward bias
    if abs(pct_change) < 0.05 and _is_tight_range(prices):
        return _result("accumulation", 0.6, "tight_range")

    # Default based on price direction
    if pct_change > 0.0:
        return _result("continuation", 0.4, "mild_uptrend")
    elif pct_change > -0.10:
        return _result("accumulation", 0.4, "mild_drift")
    else:
        return _result("dead", 0.6, f"declining_{pct_change:.1%}")


def _result(state: str, confidence: float, reason: str) -> Dict:
    return {
        "state":      state,
        "confidence": round(confidence, 3),
        "tradeable":  state in TRADEABLE_STATES,
        "reason":     reason,
    }


def _is_trending_up(prices: List[float]) -> bool:
    if len(prices) < 3:
        return False
    up = sum(1 for i in range(1, len(prices)) if prices[i] > prices[i - 1])
    return up / (len(prices) - 1) >= 0.6


def _is_slowing(prices: List[float]) -> bool:
    """Check if momentum is decelerating."""
    if len(prices) < 4:
        return False
    moves = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    first_half = moves[:len(moves) // 2]
    second_half = moves[len(moves) // 2:]
    avg_first  = sum(first_half) / len(first_half) if first_half else 0
    avg_second = sum(second_half) / len(second_half) if second_half else 0
    return avg_second < avg_first * 0.5


def _has_higher_lows(prices: List[float]) -> bool:
    """Detect higher low pattern."""
    lows = []
    for i in range(1, len(prices) - 1):
        if prices[i] <= prices[i - 1] and prices[i] <= prices[i + 1]:
            lows.append(prices[i])
    if len(lows) < 2:
        return False
    return lows[-1] > lows[0]


def _is_continuation(prices: List[float]) -> bool:
    """Detect pullback-and-resume pattern."""
    if len(prices) < 5:
        return False
    # Was higher, dipped, now recovering
    peak = max(prices[:-2])
    trough = min(prices[-3:])
    last = prices[-1]
    return peak > 0 and trough < peak and last > trough * 1.02


def _is_tight_range(prices: List[float]) -> bool:
    if not prices:
        return False
    high = max(prices)
    low  = min(prices)
    if low <= 0:
        return False
    return (high - low) / low < 0.05


def get_chart_state_score(state: str) -> int:
    """Return scoring points for chart state (used in scoring.py)."""
    return {
        "pre_breakout": 20,
        "accumulation": 12,
        "expansion":     4,   # DATA: 0% WR — keep low until proven otherwise
        "continuation":  6,   # DATA: 17% WR avg -1.4 XRP — real signal only via burst override
    }.get(state, 0)


if __name__ == "__main__":
    # Test with simulated price series
    prices_breakout = [1.0, 1.01, 0.99, 1.00, 1.02, 1.01, 1.02, 1.05, 1.09, 1.15]
    tvls = [5000] * len(prices_breakout)
    result = classify("test", prices_breakout, tvls, breakout_quality=72)
    print(f"Breakout series: {result}")

    prices_dead = [1.0, 0.95, 0.88, 0.80, 0.72, 0.65]
    result2 = classify("test2", prices_dead, [4000] * 6, breakout_quality=10)
    print(f"Dead series: {result2}")

======================================================================
# REGIME — regime.py
======================================================================

"""
regime.py — Market regime detection.
Regimes: hot, neutral, cold, danger
Writes: state/regime.json
"""

import json
import os
import time
from typing import Dict, List
import state as state_mod
from config import STATE_DIR

os.makedirs(STATE_DIR, exist_ok=True)
REGIME_FILE = os.path.join(STATE_DIR, "regime.json")


def detect_regime(bot_state: Dict, candidates_above_70: int = 0) -> str:
    """
    Regime detection — DISABLED for live trading (Apr 9 2026).
    Set REGIME_ENABLED = True to re-enable the cold/danger logic.
    When disabled: always returns neutral — bot trades at full signal quality.
    """
    REGIME_ENABLED = False  # ← True to re-enable

    if not REGIME_ENABLED:
        return "neutral"

    perf = bot_state.get("performance", {})
    cons_loss  = perf.get("consecutive_losses", 0)
    total      = perf.get("total_trades", 0)

    history = bot_state.get("trade_history", [])
    recent  = history[-15:] if len(history) >= 15 else history
    if len(recent) >= 5:
        recent_wins = sum(1 for t in recent if "tp" in t.get("exit_reason",""))
        win_rate = recent_wins / len(recent)
    else:
        win_rate = perf.get("win_rate", 0.5)

    if total < 15:
        return "neutral"
    if cons_loss >= 10:
        return "danger"
    if win_rate < 0.35:
        return "cold"
    if win_rate > 0.60 and candidates_above_70 >= 1:
        return "hot"

    return "neutral"


def get_regime_adjustments(regime: str) -> Dict:
    """Return behavior adjustments for the current regime."""
    return {
        "hot": {
            "size_mult":       1.0,
            "score_threshold": 0,   # no bonus threshold
            "max_positions":   5,
            "allow_entry":     True,
        },
        "neutral": {
            "size_mult":       1.0,
            "score_threshold": 0,
            "max_positions":   5,
            "allow_entry":     True,
        },
        "cold": {
            "size_mult":       0.75,  # was 0.5 — don't be too timid, miss winners
            "score_threshold": 3,     # GodMode: +3 in cold (was 5) — classifier guards quality
            "max_positions":   4,     # was 3
            "allow_entry":     True,
        },
        "danger": {
            "size_mult":       0.5,   # half size — stay in the game, don't ghost
            "score_threshold": 5,     # GodMode: +5 in danger (was 8) — classifier secondary gate
            "max_positions":   3,     # 3 max in danger
            "allow_entry":     True,
        },
    }.get(regime, {
        "size_mult":       1.0,
        "score_threshold": 0,
        "max_positions":   5,
        "allow_entry":     True,
    })


def load_regime() -> Dict:
    if os.path.exists(REGIME_FILE):
        try:
            with open(REGIME_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"regime": "neutral", "ts": 0, "details": {}}


def save_regime(regime: str, details: Dict = None) -> None:
    data = {
        "regime":      regime,
        "ts":          time.time(),
        "details":     details or {},
        "adjustments": get_regime_adjustments(regime),
    }
    with open(REGIME_FILE, "w") as f:
        json.dump(data, f, indent=2)


def update_and_get_regime(bot_state: Dict, candidates_above_70: int = 0) -> str:
    regime = detect_regime(bot_state, candidates_above_70)
    perf   = bot_state.get("performance", {})
    details = {
        "win_rate":           perf.get("win_rate", 0),
        "consecutive_losses": perf.get("consecutive_losses", 0),
        "total_trades":       perf.get("total_trades", 0),
        "candidates_above_70": candidates_above_70,
    }
    save_regime(regime, details)
    return regime


if __name__ == "__main__":
    s = state_mod.load()
    regime = update_and_get_regime(s, candidates_above_70=3)
    print(f"Regime: {regime}")
    print(json.dumps(get_regime_adjustments(regime), indent=2))

======================================================================
# LEARN — learn.py
======================================================================

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

======================================================================
# ALPHA_RECYCLER — alpha_recycler.py
======================================================================

"""
alpha_recycler.py — Alpha Recycling Tracker (Audit #6)

Goal: When a tracked smart wallet sells a winner, immediately look for their NEXT buy.
This is the best leading indicator.

Algorithm:
1. Maintain state/alpha_recycler.json: {wallet: {"last_sell": {token, time, pnl_pct}, "next_buy": None}}
2. Poll account_tx on known smart wallets every 5 minutes
3. Detect: wallet had a sell transaction (outgoing payment of a token they hold) on a winner
4. Then: watch for their NEXT incoming payment (buy) of ANY token within next 30 minutes
5. If that next buy is a token we don't already hold → add to bot_state["signals"]["alpha_recycler"]
6. Alpha recycler signals get a +25 score boost in scoring.py
7. Log: "🔁 ALPHA RECYCLE: @wallet sold XYZ at +Yx, just bought ABC"
"""

import json
import os
import time
import logging
import requests
from typing import Dict, List, Optional, Set
from collections import defaultdict

logger = logging.getLogger("alpha_recycler")

STATE_DIR = os.path.join(os.path.dirname(__file__), "state")
RECYCLER_FILE = os.path.join(STATE_DIR, "alpha_recycler.json")
SIGNALS_FILE = os.path.join(STATE_DIR, "alpha_recycler_signals.json")
CLIO_URL = "https://rpc.xrplclaw.com"

# Poll interval for checking wallet transactions (seconds)
POLL_INTERVAL_SEC = 300  # 5 minutes

# Window to watch for next buy after a sell (seconds)
BUY_WINDOW_SEC = 1800  # 30 minutes

# Minimum profit multiple to consider a "winner" sell
MIN_WIN_MULTIPLE = 1.5  # 1.5x+


def _rpc(method: str, params: dict, timeout: int = 15) -> Optional[dict]:
    """Send RPC request to CLIO."""
    try:
        resp = requests.post(CLIO_URL, json={"method": method, "params": [params]}, timeout=timeout)
        return resp.json().get("result", {})
    except Exception as e:
        logger.debug(f"RPC error {method}: {e}")
        return None


def _load_recycler_state() -> Dict:
    """Load alpha recycler state."""
    if os.path.exists(RECYCLER_FILE):
        try:
            with open(RECYCLER_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_recycler_state(data: Dict) -> None:
    """Save alpha recycler state."""
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = RECYCLER_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, RECYCLER_FILE)
    except Exception:
        with open(RECYCLER_FILE, "w") as f:
            json.dump(data, f, indent=2)


def _load_discovered_wallets() -> Set[str]:
    """Load tracked and candidate wallets from discovered_wallets.json."""
    wallets = set()

    # From config TRACKED_WALLETS
    try:
        from config import TRACKED_WALLETS
        if isinstance(TRACKED_WALLETS, (list, tuple)):
            wallets.update(TRACKED_WALLETS)
    except (ImportError, AttributeError):
        pass

    # From discovered_wallets.json
    discovered_file = os.path.join(STATE_DIR, "discovered_wallets.json")
    if os.path.exists(discovered_file):
        try:
            with open(discovered_file) as f:
                data = json.load(f)
            wallets.update(data.get("tracked", []))
            wallets.update(data.get("candidates", {}).keys())
        except Exception as e:
            logger.debug(f"Error loading discovered wallets: {e}")

    return wallets


def _get_currency_code(symbol: str) -> str:
    """Convert symbol to XRPL currency code."""
    s = symbol.upper()
    if len(s) <= 3:
        return s.ljust(3)
    if len(s) == 40 and all(c in "0123456789ABCDEF" for c in s):
        return s
    encoded = s.encode("utf-8").hex().upper()
    return encoded.ljust(40, "0")[:40]


def _get_token_symbol(currency: str, issuer: str) -> str:
    """Try to resolve currency code back to symbol."""
    # Check active registry
    registry_file = os.path.join(STATE_DIR, "active_registry.json")
    if os.path.exists(registry_file):
        try:
            with open(registry_file) as f:
                registry = json.load(f)
            for entry in registry.values() if isinstance(registry, dict) else registry:
                if isinstance(entry, dict):
                    if entry.get("currency") == currency and entry.get("issuer") == issuer:
                        return entry.get("symbol", currency[:8])
        except Exception:
            pass
    return currency[:8]  # Fallback to first 8 chars


def _check_wallet_transactions(wallet: str, lookback_ledgers: int = 50) -> List[Dict]:
    """
    Check recent transactions for a wallet.
    Returns list of {type, token, currency, issuer, amount, ts, direction} events.
    direction: 'in' (buy/receive) or 'out' (sell/send)
    """
    events = []

    result = _rpc("account_tx", {
        "account": wallet,
        "limit": lookback_ledgers,
        "ledger_index_min": -1,
        "ledger_index_max": -1,
    })

    if not result or result.get("status") != "success":
        return events

    for tx_wrapper in result.get("transactions", []):
        tx = tx_wrapper.get("tx", {})
        meta = tx_wrapper.get("meta", {})
        tx_type = tx.get("TransactionType", "")
        tx_date = tx.get("date", 0)
        tx_time_unix = tx_date + 946684800  # Convert Ripple epoch to Unix

        account = tx.get("Account", "")
        destination = tx.get("Destination", "")

        if tx_type == "OfferCreate":
            tp = tx.get("TakerPays", {})
            tg = tx.get("TakerGets", {})

            # Selling token: TakerPays=token, TakerGets=XRP
            if isinstance(tp, dict) and isinstance(tg, str):
                currency = tp.get("currency", "")
                issuer = tp.get("issuer", "")
                if currency and issuer:
                    events.append({
                        "type": "sell",
                        "direction": "out",
                        "currency": currency,
                        "issuer": issuer,
                        "ts": tx_time_unix,
                        "wallet": account,
                    })

            # Buying token: TakerPays=XRP, TakerGets=token
            elif isinstance(tp, str) and isinstance(tg, dict):
                currency = tg.get("currency", "")
                issuer = tg.get("issuer", "")
                if currency and issuer:
                    events.append({
                        "type": "buy",
                        "direction": "in",
                        "currency": currency,
                        "issuer": issuer,
                        "ts": tx_time_unix,
                        "wallet": account,
                    })

        elif tx_type == "Payment":
            amount = tx.get("Amount", {})
            if isinstance(amount, dict):
                currency = amount.get("currency", "")
                issuer = amount.get("issuer", "")
                if currency and issuer:
                    # Determine direction: did this wallet send or receive?
                    if account == wallet:
                        direction = "out"  # Wallet sent tokens (sell)
                    elif destination == wallet:
                        direction = "in"   # Wallet received tokens (buy)
                    else:
                        continue

                    events.append({
                        "type": "payment",
                        "direction": direction,
                        "currency": currency,
                        "issuer": issuer,
                        "ts": tx_time_unix,
                        "wallet": wallet,
                    })

    return events


def _is_token_held_by_bot(token_key: str, bot_state: Optional[Dict] = None) -> bool:
    """Check if the bot already holds this token."""
    if bot_state is None:
        return False

    positions = bot_state.get("positions", {})
    return token_key in positions


def scan_alpha_recycling(bot_state: Optional[Dict] = None) -> List[Dict]:
    """
    Main scan function. Checks all tracked wallets for sell→buy patterns.
    Returns list of new alpha recycle signals.
    """
    logger.info("🔄 Scanning alpha recycling...")

    recycler_state = _load_recycler_state()
    known_wallets = _load_discovered_wallets()
    now = time.time()
    new_signals = []

    for wallet in known_wallets:
        wallet_data = recycler_state.get(wallet, {})
        last_sell = wallet_data.get("last_sell")
        next_buy = wallet_data.get("next_buy")

        # Check recent transactions
        events = _check_wallet_transactions(wallet, lookback_ledgers=30)

        # Look for new sells (winner exits)
        for event in events:
            if event["direction"] == "out" and event["type"] in ("sell", "payment"):
                currency = event["currency"]
                issuer = event["issuer"]
                token_key = f"{currency}:{issuer}"
                symbol = _get_token_symbol(currency, issuer)

                # Record the sell if not already tracked
                if not last_sell or event["ts"] > last_sell.get("time", 0):
                    # We can't easily determine PnL without full position history
                    # Mark as potential winner — will be confirmed if they rebuy
                    recycler_state[wallet] = {
                        "last_sell": {
                            "token": symbol,
                            "currency": currency,
                            "issuer": issuer,
                            "token_key": token_key,
                            "time": event["ts"],
                            "pnl_pct": None,  # Unknown without entry price
                        },
                        "next_buy": None,
                        "updated": now,
                    }
                    logger.info(
                        f"  📤 {wallet[:10]}... sold {symbol} — watching for next buy"
                    )

        # Check if wallet has a pending "watching for buy" state
        if last_sell and not next_buy:
            sell_time = last_sell.get("time", 0)
            elapsed = now - sell_time

            # Still within the buy window?
            if elapsed < BUY_WINDOW_SEC:
                # Look for a new buy in recent events
                for event in events:
                    if event["direction"] == "in" and event["type"] in ("buy", "payment"):
                        if event["ts"] > sell_time:  # Buy happened after the sell
                            buy_currency = event["currency"]
                            buy_issuer = event["issuer"]
                            buy_token_key = f"{buy_currency}:{buy_issuer}"
                            buy_symbol = _get_token_symbol(buy_currency, buy_issuer)

                            # Check if bot already holds this token
                            if not _is_token_held_by_bot(buy_token_key, bot_state):
                                signal = {
                                    "wallet": wallet,
                                    "sold_token": last_sell.get("token", ""),
                                    "bought_token": buy_symbol,
                                    "bought_currency": buy_currency,
                                    "bought_issuer": buy_issuer,
                                    "bought_token_key": buy_token_key,
                                    "sell_time": sell_time,
                                    "buy_time": event["ts"],
                                    "delay_sec": event["ts"] - sell_time,
                                    "context": f"recycled_from_{last_sell.get('token', 'unknown')}",
                                    "ts": now,
                                    "signal_type": "alpha_recycler",
                                }

                                new_signals.append(signal)

                                # Update state
                                recycler_state[wallet]["next_buy"] = {
                                    "token": buy_symbol,
                                    "currency": buy_currency,
                                    "issuer": buy_issuer,
                                    "token_key": buy_token_key,
                                    "time": event["ts"],
                                }

                                logger.warning(
                                    f"🔁 ALPHA RECYCLE: {wallet[:10]}... sold "
                                    f"{last_sell.get('token', '?')} → just bought {buy_symbol}"
                                )

                                # Save signal to file
                                _save_signal_to_file(signal)

                                # Inject into bot_state if available
                                if bot_state is not None:
                                    if "signals" not in bot_state:
                                        bot_state["signals"] = {}
                                    bot_state["signals"]["alpha_recycler"] = signal

                            break  # Only track first buy after sell
            else:
                # Window expired — clear the watch
                if wallet in recycler_state:
                    recycler_state[wallet]["next_buy"] = None
                    recycler_state[wallet]["last_sell"] = None
                    logger.debug(f"  ⏰ Watch expired for {wallet[:10]}...")

    _save_recycler_state(recycler_state)

    if new_signals:
        logger.info(f"✅ Found {len(new_signals)} alpha recycle signal(s)")
    else:
        logger.debug("No new alpha recycle signals")

    return new_signals


def _save_signal_to_file(signal: Dict):
    """Append signal to alpha_recycler_signals.json."""
    os.makedirs(STATE_DIR, exist_ok=True)
    try:
        if os.path.exists(SIGNALS_FILE):
            with open(SIGNALS_FILE) as f:
                data = json.load(f)
        else:
            data = {"signals": [], "last_updated": 0}

        data["signals"].append(signal)
        # Keep last 50 signals
        data["signals"] = data["signals"][-50:]
        data["last_updated"] = time.time()

        tmp = SIGNALS_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, SIGNALS_FILE)
    except Exception as e:
        logger.error(f"Error saving alpha recycler signal: {e}")


def get_alpha_recycler_boost(symbol: str, issuer: str) -> int:
    """
    Get score boost for a token based on alpha recycler activity.
    Returns +25 if an alpha recycler signal matches this token, 0 otherwise.
    Called by scoring.py.
    """
    signals_file = SIGNALS_FILE
    if not os.path.exists(signals_file):
        return 0

    try:
        with open(signals_file) as f:
            data = json.load(f)

        now = time.time()
        token_key = f"{symbol}:{issuer}"

        # Check recent signals (within 30 min)
        for sig in data.get("signals", []):
            if sig.get("bought_token_key") == token_key:
                age = now - sig.get("ts", 0)
                if age < 1800:  # 30 min TTL
                    return 25
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("Alpha Recycler — test mode")
    signals = scan_alpha_recycling()
    print(f"New signals: {len(signals)}")
    for sig in signals:
        print(f"  🔁 {sig['wallet'][:10]}... : {sig['sold_token']} → {sig['bought_token']}")

======================================================================
# REALTIME_WATCHER — realtime_watcher.py
======================================================================

"""
realtime_watcher.py — Real-time XRPL transaction stream watcher.

Connects to XRPL via WebSocket and watches the live ledger stream.
Catches AMMCreate and TrustSet transactions the MOMENT they happen
— no polling delay, no missed launches.

What it catches:
  1. AMMCreate → new token launched, immediately adds to registry
  2. TrustSet bursts → existing token gaining holders fast → velocity alert
  3. OfferCreate clusters → coordinated buying on a token → momentum alert

Output: writes to state/realtime_signals.json — bot.py reads this
        and injects signals directly into the scan cycle.

Run alongside bot.py — launched as a background thread from bot.py.
"""

import json, os, time, logging, threading
import asyncio
import websockets

logger = logging.getLogger("realtime")

WS_URL       = "wss://rpc.xrplclaw.com/ws"
STATE_DIR    = os.path.join(os.path.dirname(__file__), "state")
SIGNALS_FILE = os.path.join(STATE_DIR, "realtime_signals.json")
REGISTRY_FILE = os.path.join(STATE_DIR, "active_registry.json")

XRPL_EPOCH   = 946684800
MIN_AMM_XRP  = 50      # ignore dust pools < 50 XRP
MAX_AMM_XRP  = 10000   # ignore already-large pools at launch (not a new launch)
BURST_WINDOW = 300     # 5 min window to count TrustSet bursts
BURST_MIN    = 8       # 8 TrustSets in 5 min = burst signal (lowered from 10 — missed PROPHET at early stage)

# Offer volume tracking for price momentum detection
OFFER_WINDOW   = 120   # 2 min window for offer clustering
OFFER_MIN      = 5     # 5 OfferCreates in 2 min = buy pressure signal

# Per-issuer TrustSet timestamps for burst detection
_trustset_times: dict = {}
# Per-token offer timestamps for momentum detection
_offer_times: dict = {}
_lock = threading.Lock()

# Throttle signal file writes — max once every 5s
_last_signals_flush = 0.0

def _save_signals_throttled(signals: dict):
    global _last_signals_flush
    now = time.time()
    if now - _last_signals_flush >= 5:
        _save_signals(signals)
        _last_signals_flush = now


def _load_signals() -> dict:
    try:
        with open(SIGNALS_FILE) as f:
            return json.load(f)
    except:
        return {"new_tokens": {}, "velocity_alerts": {}, "last_updated": 0}


def _save_signals(signals: dict):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(SIGNALS_FILE, "w") as f:
        json.dump(signals, f, indent=2)


def _hex_to_sym(h: str) -> str:
    if not h or len(h) <= 3:
        return h or ""
    try:
        padded = h.ljust(40, "0")[:40]
        raw = bytes.fromhex(padded).decode("ascii", errors="ignore")
        name = raw.rstrip("\x00").strip()
        return name if name and name.isprintable() and len(name) >= 2 else h[:8]
    except:
        return h[:8]


def _add_to_registry(symbol: str, currency: str, issuer: str, tvl_xrp: float, source: str):
    """Inject a new token into the active registry immediately."""
    try:
        with open(REGISTRY_FILE) as f:
            reg = json.load(f)
    except:
        reg = {"tokens": [], "updated": ""}

    tokens = reg.get("tokens", [])
    key = f"{currency}:{issuer}"

    # Check not already in registry
    for t in tokens:
        if t.get("currency") == currency and t.get("issuer") == issuer:
            return  # already tracked

    tokens.append({
        "symbol":   symbol,
        "currency": currency,
        "issuer":   issuer,
        "tvl_xrp":  round(tvl_xrp, 2),
        "source":   source,
    })
    reg["tokens"] = tokens
    reg["updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    with open(REGISTRY_FILE, "w") as f:
        json.dump(reg, f, indent=2)

    logger.info(f"🆕 REALTIME: Added {symbol} to registry ({source}) TVL={tvl_xrp:.0f} XRP")


def _handle_amm_create(tx: dict):
    """New AMM pool created — add token to registry immediately."""
    amount  = tx.get("Amount", 0)
    amount2 = tx.get("Amount2", {})

    # We want XRP/Token pairs
    if isinstance(amount, str) and isinstance(amount2, dict):
        xrp_drops = int(amount)
        xrp = xrp_drops / 1e6
        currency = amount2.get("currency", "")
        issuer   = amount2.get("issuer", "")
        value    = float(amount2.get("value", 0))
    elif isinstance(amount, dict) and isinstance(amount2, str):
        xrp_drops = int(amount2)
        xrp = xrp_drops / 1e6
        currency = amount.get("currency", "")
        issuer   = amount.get("issuer", "")
        value    = float(amount.get("value", 0))
    else:
        return  # token/token pair, skip

    if not currency or not issuer:
        return
    if xrp < MIN_AMM_XRP:
        return
    if xrp > MAX_AMM_XRP:
        logger.debug(f"AMMCreate: {currency[:8]} TVL {xrp:.0f} XRP too large, skipping")
        return

    symbol = _hex_to_sym(currency)
    logger.info(f"🚀 NEW AMM: {symbol} | TVL={xrp:.1f} XRP | issuer={issuer[:12]}")

    # Add to registry immediately
    _add_to_registry(symbol, currency, issuer, xrp, "realtime_ammcreate")

    # Add to signals file
    signals = _load_signals()
    signals["new_tokens"][f"{currency}:{issuer}"] = {
        "symbol":      symbol,
        "currency":    currency,
        "issuer":      issuer,
        "tvl_xrp":     xrp,
        "detected_at": time.time(),
        "source":      "ammcreate",
    }
    signals["last_updated"] = time.time()
    _save_signals_throttled(signals)


def _handle_trustset(tx: dict):
    """TrustSet transaction — track bursts per issuer."""
    limit = tx.get("LimitAmount", {})
    if not isinstance(limit, dict):
        return

    currency = limit.get("currency", "")
    issuer   = limit.get("issuer", "")
    if not currency or not issuer:
        return

    key = f"{currency}:{issuer}"
    now = time.time()

    with _lock:
        if key not in _trustset_times:
            _trustset_times[key] = []
        _trustset_times[key].append(now)

        # Keep only last BURST_WINDOW seconds
        _trustset_times[key] = [t for t in _trustset_times[key] if now - t <= BURST_WINDOW]
        burst_count = len(_trustset_times[key])

    # Check if burst threshold hit
    if burst_count >= BURST_MIN and burst_count % 5 == 0:  # alert every 5 new ones after threshold
        symbol = _hex_to_sym(currency)
        logger.info(f"⚡ BURST: {symbol} — {burst_count} TrustSets in last {BURST_WINDOW//60}m")

        signals = _load_signals()
        alert_key = key
        prev = signals["velocity_alerts"].get(alert_key, {})
        prev_count = prev.get("burst_count", 0)

        # Only update if meaningfully new
        if burst_count > prev_count:
            signals["velocity_alerts"][alert_key] = {
                "symbol":      symbol,
                "currency":    currency,
                "issuer":      issuer,
                "burst_count": burst_count,
                "window_min":  BURST_WINDOW // 60,
                "updated_at":  now,
            }
            signals["last_updated"] = now
            _save_signals_throttled(signals)

            # Also inject into registry if not there
            _add_to_registry(symbol, currency, issuer, 0, "realtime_trustset_burst")


def _handle_offer_create(tx: dict):
    """
    OfferCreate — track buy-side clusters AND CLOB price/volume.

    Two signals:
    1. Buy cluster: 5+ buys in 2 min = coordinated buying
    2. CLOB launch: 60+ TrustSets + 25+ XRP/5min = runner launching on orderbook
       (catches brizzly/PROPHET/PRSV which moved on CLOB not AMM)
    """
    taker_gets = tx.get("TakerGets", {})
    if not isinstance(taker_gets, dict):
        return  # XRP offer, not a token buy

    currency = taker_gets.get("currency", "")
    issuer   = taker_gets.get("issuer", "")
    taker_pays = tx.get("TakerPays", 0)

    # Must be buying a token WITH XRP (TakerPays = XRP drops)
    if not currency or not issuer or not isinstance(taker_pays, (int, str)):
        return

    try:
        xrp_spent = int(taker_pays) / 1_000_000
    except (ValueError, TypeError):
        return

    if xrp_spent < 0.5:  # ignore dust orders
        return

    # Skip stablecoins and fiat-pegged tokens — no meme upside
    sym = _hex_to_sym(currency).upper()
    try:
        from config import STABLECOIN_SKIP as _SC_SKIP
    except Exception:
        _SC_SKIP = {"USD","USDC","USDT","RLUSD","EUR","GBP","JPY","CNY","SGB","FLR","XAH","BTC","ETH","SOL"}
    if sym in _SC_SKIP:
        return

    symbol   = _hex_to_sym(currency)
    tok_amt  = float(taker_gets.get("value", 0))
    key      = f"{currency}:{issuer}"
    now      = time.time()

    # ── CLOB price/volume tracking (the brizzly fix) ──────────────────────
    # Get current TrustSet burst count for this token
    with _lock:
        ts_burst = len(_trustset_times.get(key, []))

    try:
        import clob_tracker
        clob_tracker.on_offer_create(
            currency    = currency,
            issuer      = issuer,
            symbol      = symbol,
            xrp_amount  = xrp_spent,
            token_amount= tok_amt,
            side        = "BUY",
            ts_burst_count = ts_burst,
        )
    except Exception as _cte:
        logger.debug(f"clob_tracker error: {_cte}")

    # ── Buy cluster tracking (count-based, existing logic) ────────────────
    with _lock:
        if key not in _offer_times:
            _offer_times[key] = []
        _offer_times[key].append({"ts": now, "xrp": xrp_spent})
        # Keep only last OFFER_WINDOW seconds
        _offer_times[key] = [o for o in _offer_times[key] if now - o["ts"] <= OFFER_WINDOW]
        offer_count = len(_offer_times[key])
        total_xrp   = sum(o["xrp"] for o in _offer_times[key])

    if offer_count >= OFFER_MIN and offer_count % 3 == 0:
        logger.info(f"📈 BUY CLUSTER: {symbol} — {offer_count} buys / {OFFER_WINDOW}s | {total_xrp:.1f} XRP volume")

        signals = _load_signals()
        if "momentum_alerts" not in signals:
            signals["momentum_alerts"] = {}

        prev = signals["momentum_alerts"].get(key, {})
        prev_count = prev.get("offer_count", 0)

        if offer_count > prev_count:
            signals["momentum_alerts"][key] = {
                "symbol":      symbol,
                "currency":    currency,
                "issuer":      issuer,
                "offer_count": offer_count,
                "total_xrp":   round(total_xrp, 2),
                "window_sec":  OFFER_WINDOW,
                "updated_at":  now,
            }
            signals["last_updated"] = now
            _save_signals_throttled(signals)

            # Inject into registry so bot can score it
            _add_to_registry(symbol, currency, issuer, 0, "realtime_buy_cluster")


async def _stream():
    """Main WebSocket stream loop."""
    subscribe_msg = {
        "command": "subscribe",
        "streams": ["transactions"]
    }

    logger.info("📡 Realtime watcher connecting to XRPL stream...")

    while True:
        try:
            async with websockets.connect(WS_URL, ping_interval=30, ping_timeout=10) as ws:
                await ws.send(json.dumps(subscribe_msg))
                resp = await ws.recv()
                logger.info("📡 Realtime watcher connected — watching live ledger")

                while True:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=60)
                        data = json.loads(msg)

                        if data.get("type") != "transaction":
                            continue

                        tx = data.get("transaction", {})
                        meta = data.get("meta", {})
                        result = meta.get("TransactionResult", "")

                        # Only process successful txs
                        if result != "tesSUCCESS":
                            continue

                        tt = tx.get("TransactionType", "")

                        if tt == "AMMCreate":
                            _handle_amm_create(tx)
                        elif tt == "TrustSet":
                            _handle_trustset(tx)
                        elif tt == "OfferCreate":
                            _handle_offer_create(tx)

                    except asyncio.TimeoutError:
                        # Send ping to keep alive
                        await ws.ping()

        except Exception as e:
            logger.warning(f"📡 Stream disconnected: {e} — reconnecting in 5s")
            await asyncio.sleep(5)


def _run_loop():
    """Run the async stream in a dedicated event loop (for threading)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_stream())
    except Exception as e:
        logger.error(f"Realtime watcher fatal: {e}")
    finally:
        loop.close()


def start_background():
    """Start the realtime watcher as a daemon thread. Call from bot.py."""
    t = threading.Thread(target=_run_loop, name="realtime-watcher", daemon=True)
    t.start()
    logger.info("📡 Realtime watcher thread started")
    return t


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s"
    )
    logger.info("Starting realtime watcher standalone...")
    asyncio.run(_stream())

======================================================================
# AMM_LAUNCH_WATCHER — amm_launch_watcher.py
======================================================================

#!/usr/bin/env python3
"""
amm_launch_watcher.py — Real-time XRPL AMM launch detector.

Subscribes to the XRPL ledger via WebSocket and watches for:
  1. AMMCreate transactions → brand new AMM pools launching
  2. Large OfferCreate bursts → early buy signals (whale accumulation)

When a new launch is detected:
  - Scores it with winner_dna.py immediately
  - Injects into active_registry.json so scanner picks it up
  - Writes a hot signal to state/hot_launches.json with score + DNA flags
  - Notifies via TG if score is strong enough

Latency: ~1-3 seconds from on-chain to registry. vs 15-60min via xpmarket API.
"""

import asyncio
import json
import os
import sys
import time
import requests
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from warden_security_patch import rpc_call

# ── Paths ─────────────────────────────────────────────────────────────────────
BOT_DIR    = Path(__file__).parent
STATE_DIR  = BOT_DIR / "state"
REGISTRY_F = STATE_DIR / "active_registry.json"
HOT_FILE   = STATE_DIR / "hot_launches.json"
LOG_FILE   = STATE_DIR / "amm_watcher.log"

WS_URL     = "wss://rpc.xrplclaw.com"

# Minimum XRP TVL to care about a new launch
MIN_LAUNCH_TVL = 500   # XRP — even very thin launches are worth watching

os.makedirs(STATE_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("amm_watcher")


def load_hot_launches() -> dict:
    try:
        if HOT_FILE.exists():
            return json.loads(HOT_FILE.read_text())
    except:
        pass
    return {"launches": {}}


def save_hot_launches(data: dict):
    tmp = str(HOT_FILE) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, str(HOT_FILE))


def load_registry() -> list:
    try:
        if REGISTRY_F.exists():
            data = json.loads(REGISTRY_F.read_text())
            return data.get("tokens", data) if isinstance(data, dict) else data
    except:
        pass
    return []


def save_registry(tokens: list):
    tmp = str(REGISTRY_F) + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"tokens": tokens, "updated": time.time()}, f, indent=2)
    os.replace(tmp, str(REGISTRY_F))


def hex_to_symbol(hex_str: str) -> str:
    """Convert XRPL hex currency code to ASCII symbol."""
    try:
        if len(hex_str) == 3:
            return hex_str
        b = bytes.fromhex(hex_str)
        s = b.decode("ascii").strip("\x00").strip()
        return s if s.isprintable() and s.strip() else hex_str[:6]
    except:
        return hex_str[:8]


def get_amm_info(asset1: dict, asset2: dict) -> Optional[dict]:
    """Fetch AMM pool info for a token pair."""
    r = rpc_call("amm_info", {"asset": asset1, "asset2": asset2})
    return r.get("amm")


def analyze_launch(currency: str, issuer: str, amm_data: dict) -> dict:
    """
    Full analysis of a newly launched AMM pool.
    Returns enriched token data with DNA score.
    """
    symbol = hex_to_symbol(currency) if len(currency) > 3 else currency

    # Extract TVL from AMM data
    amount1 = amm_data.get("amount", "0")
    tvl_xrp = int(amount1) / 1e6 if isinstance(amount1, str) else 0

    log.info(f"Analyzing launch: {symbol} | TVL={tvl_xrp:.0f} XRP | issuer={issuer[:16]}...")

    # Score with winner DNA
    dna_score = 0
    dna_flags = []
    dna_details = {}
    try:
        sys.path.insert(0, str(BOT_DIR))
        import winner_dna as wdna
        result = wdna.get_winner_dna_score(symbol, issuer, currency, tvl_xrp)
        dna_score   = result.get("bonus", 0)
        dna_flags   = result.get("flags", [])
        dna_details = result.get("details", {})
    except Exception as e:
        log.warning(f"DNA score error for {symbol}: {e}")

    # Calculate price
    amount2 = amm_data.get("amount2", {})
    token_amount = float(amount2.get("value", 0)) if isinstance(amount2, dict) else 0
    price_xrp = tvl_xrp / token_amount if token_amount > 0 else 0

    return {
        "symbol":      symbol,
        "currency":    currency,
        "issuer":      issuer,
        "tvl_xrp":     tvl_xrp,
        "price_xrp":   price_xrp,
        "dna_score":   dna_score,
        "dna_flags":   dna_flags,
        "dna_details": dna_details,
        "launch_time": time.time(),
        "source":      "amm_watcher",
    }


def inject_to_registry(token_data: dict):
    """Add new token to active_registry so scanner picks it up immediately."""
    tokens = load_registry()
    issuer = token_data["issuer"]
    currency = token_data["currency"]

    # Check if already tracked
    for t in tokens:
        if t.get("issuer") == issuer and t.get("currency") == currency:
            log.info(f"Already in registry: {token_data['symbol']}")
            return False

    tokens.append({
        "symbol":    token_data["symbol"],
        "issuer":    issuer,
        "currency":  currency,
        "last_tvl":  token_data["tvl_xrp"],
        "source":    "amm_watcher",
        "added_at":  time.time(),
    })
    save_registry(tokens)
    log.info(f"✅ Injected {token_data['symbol']} into registry ({len(tokens)} total)")
    return True


def write_hot_signal(token_data: dict):
    """Write to hot_launches.json — bot reads this for immediate score boost."""
    hot = load_hot_launches()
    key = f"{token_data['currency']}:{token_data['issuer']}"

    hot["launches"][key] = {
        "symbol":      token_data["symbol"],
        "dna_score":   token_data["dna_score"],
        "dna_flags":   token_data["dna_flags"],
        "tvl_xrp":     token_data["tvl_xrp"],
        "launch_time": token_data["launch_time"],
        "expires":     time.time() + 3600,  # signal valid for 1h
        "notified":    False,
    }
    save_hot_launches(hot)


def notify_if_strong(token_data: dict):
    """Send TG alert if this launch looks like a winner."""
    score = token_data["dna_score"]
    sym   = token_data["symbol"]
    tvl   = token_data["tvl_xrp"]
    flags = token_data["dna_flags"]
    details = token_data["dna_details"]

    if score < 20:
        return  # not interesting enough

    stars = "🔥🔥🔥" if score >= 50 else ("🔥🔥" if score >= 35 else "🔥")
    flag_str = " | ".join(flags[:4]) if flags else "none"
    holders = details.get("holder_count", "?")
    age_h = details.get("age_hours", "?")
    if isinstance(age_h, float):
        age_h = f"{age_h:.1f}h"

    msg = (
        f"{stars} *NEW LAUNCH DETECTED*\n"
        f"Token: `{sym}`\n"
        f"DNA Score: `+{score} pts`\n"
        f"TVL: `{tvl:.0f} XRP`\n"
        f"Holders: `{holders}` | Age: `{age_h}`\n"
        f"Signals: `{flag_str}`\n"
        f"_Bot will auto-scan next cycle_"
    )
    log.info(f"Launch alert logged for {sym} (DNA={score})")


async def watch_ledger():
    """Subscribe to XRPL WebSocket and watch for AMMCreate transactions."""
    import websockets

    log.info(f"Connecting to {WS_URL}...")
    reconnect_delay = 5

    while True:
        try:
            async with websockets.connect(WS_URL, ping_interval=20, ping_timeout=10) as ws:
                # Subscribe to all validated transactions
                await ws.send(json.dumps({
                    "command": "subscribe",
                    "streams": ["transactions"]
                }))

                resp = await ws.recv()
                sub = json.loads(resp)
                log.info(f"Subscribed: {sub.get('status', 'unknown')}")
                reconnect_delay = 5  # reset on success

                while True:
                    raw = await ws.recv()
                    msg = json.loads(raw)

                    # Only care about validated transactions
                    if msg.get("type") != "transaction":
                        continue
                    if msg.get("status") != "closed" and msg.get("validated") is not True:
                        # Some nodes send engine_result instead
                        meta = msg.get("meta", {})
                        if meta.get("TransactionResult") != "tesSUCCESS":
                            continue

                    tx = msg.get("transaction", msg.get("tx_json", {}))
                    if not tx:
                        continue

                    tx_type = tx.get("TransactionType", "")

                    # ── AMMCreate: brand new pool ──────────────────────────────
                    if tx_type == "AMMCreate":
                        await handle_amm_create(tx, msg.get("meta", {}))

                    # ── Large OfferCreate burst: whale accumulation ────────────
                    elif tx_type == "OfferCreate":
                        await handle_offer_burst(tx, msg.get("meta", {}))

        except Exception as e:
            log.warning(f"WS error: {e} — reconnecting in {reconnect_delay}s")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 60)


async def handle_amm_create(tx: dict, meta: dict):
    """Handle a new AMMCreate transaction."""
    # Extract token info from the transaction
    a1 = tx.get("Amount", {})
    a2 = tx.get("Amount2", {})

    # Figure out which side is XRP and which is the token
    if isinstance(a1, str) and isinstance(a2, dict):
        xrp_drops = int(a1)
        token = a2
    elif isinstance(a2, str) and isinstance(a1, dict):
        xrp_drops = int(a2)
        token = a1
    else:
        return  # token/token pair, not XRP/token

    tvl_xrp = xrp_drops / 1e6
    if tvl_xrp < MIN_LAUNCH_TVL:
        log.debug(f"AMMCreate too thin: {tvl_xrp:.0f} XRP — skipping")
        return

    currency = token.get("currency", "")
    issuer   = token.get("issuer", "")
    if not currency or not issuer:
        return

    symbol = hex_to_symbol(currency)
    log.info(f"🚀 NEW AMM LAUNCH: {symbol} | {tvl_xrp:.0f} XRP | creator={tx.get('Account','?')[:16]}")

    # Small delay to let ledger settle then fetch full AMM data
    await asyncio.sleep(2)
    amm = get_amm_info({"currency": "XRP"}, {"currency": currency, "issuer": issuer})
    if not amm:
        # Build minimal AMM data from tx itself
        amm = {"amount": str(xrp_drops), "amount2": token}

    token_data = analyze_launch(currency, issuer, amm)
    write_hot_signal(token_data)
    inject_to_registry(token_data)
    notify_if_strong(token_data)

    log.info(f"  {symbol}: DNA={token_data['dna_score']} flags={token_data['dna_flags']}")


# Track recent OfferCreate activity per issuer to detect accumulation bursts
_offer_tracker: Dict[str, list] = {}

async def handle_offer_burst(tx: dict, meta: dict):
    """
    Detect whale accumulation: 3+ large buy offers on the same token
    within 60 seconds = early signal even before price moves.
    """
    # Check if this is a token buy (taker_pays=XRP, taker_gets=token)
    pays = tx.get("TakerPays", {})
    gets = tx.get("TakerGets", {})

    if not (isinstance(pays, str) and isinstance(gets, dict)):
        return  # not a buy

    xrp_amount = int(pays) / 1e6
    if xrp_amount < 50:  # only care about 50+ XRP orders
        return

    currency = gets.get("currency", "")
    issuer   = gets.get("issuer", "")
    if not currency or not issuer:
        return

    # Skip stablecoins and known large-volume non-meme tokens
    symbol_check = hex_to_symbol(currency).upper()
    SKIP_SYMBOLS = {"USD", "USDC", "USDT", "RLUSD", "BTC", "ETH", "XLM",
                    "EUR", "EURO", "EUROP", "GBP", "JPY", "CNY", "AUD", "CAD",
                    "SOLO", "CSC", "SGB", "FLR", "XAH", "CORE", "EVR",
                    "XUSD", "MXRP", "AUDD", "XSGD", "XCHF", "GYEN"}
    # Also skip anything that looks like a fiat peg by name
    FIAT_PATTERNS = ("USD", "EUR", "GBP", "JPY", "CNY", "AUD", "CAD", "STABLE", "PEGGED")
    if symbol_check in SKIP_SYMBOLS:
        return
    if any(symbol_check.startswith(p) or symbol_check.endswith(p) for p in FIAT_PATTERNS):
        return

    # Track this buy
    key = f"{currency}:{issuer}"
    now = time.time()
    if key not in _offer_tracker:
        _offer_tracker[key] = []
    _offer_tracker[key].append({"time": now, "xrp": xrp_amount})

    # Clean old entries (>60s)
    _offer_tracker[key] = [e for e in _offer_tracker[key] if now - e["time"] < 60]

    buys = _offer_tracker[key]
    total_xrp = sum(e["xrp"] for e in buys)
    count = len(buys)

    # 3+ buys totaling 200+ XRP in 60s = accumulation burst
    if count >= 3 and total_xrp >= 200:
        symbol = hex_to_symbol(currency)
        log.info(f"⚡ ACCUMULATION BURST: {symbol} — {count} buys, {total_xrp:.0f} XRP in 60s")

        # Check if already in registry
        registry = load_registry()
        already = any(t.get("issuer") == issuer for t in registry)

        if not already:
            # New token — fetch AMM and add
            amm = get_amm_info({"currency": "XRP"}, {"currency": currency, "issuer": issuer})
            if amm:
                token_data = analyze_launch(currency, issuer, amm)
                token_data["dna_flags"].append(f"whale_burst_{count}buys_{total_xrp:.0f}xrp")
                token_data["dna_score"] = min(token_data["dna_score"] + 20, 60)  # burst bonus
                write_hot_signal(token_data)
                inject_to_registry(token_data)
                notify_if_strong(token_data)
        else:
            # Already tracked — boost its hot signal score
            hot = load_hot_launches()
            if key in hot.get("launches", {}):
                hot["launches"][key]["dna_score"] = min(
                    hot["launches"][key].get("dna_score", 0) + 15, 60
                )
                hot["launches"][key]["dna_flags"].append(f"burst_{count}x_{total_xrp:.0f}xrp")
                hot["launches"][key]["expires"] = time.time() + 1800
                save_hot_launches(hot)
                log.info(f"  Boosted hot signal for {symbol}")

        # Reset tracker so we don't spam
        _offer_tracker[key] = []


def main():
    log.info("AMM Launch Watcher starting...")
    log.info(f"Registry: {REGISTRY_F}")
    log.info(f"Hot signals: {HOT_FILE}")
    log.info(f"Min TVL: {MIN_LAUNCH_TVL} XRP")

    try:
        import websockets
    except ImportError:
        log.info("Installing websockets...")
        os.system("pip install websockets -q")
        import websockets

    asyncio.run(watch_ledger())


if __name__ == "__main__":
    main()

======================================================================
# SAFETY — safety.py
======================================================================

"""
safety.py — Hard safety filter. ALL checks must pass before entry.
Checks: AMM TVL, LP burn, issuer blackhole, freeze risk, concentration, liquidity stability.
Writes: state/safety_cache.json
"""

import json
import os
import time
import requests
from typing import Dict, List, Optional, Tuple
from config import (CLIO_URL, STATE_DIR, MIN_TVL_XRP, MIN_LP_BURN_PCT,
                    BLACK_HOLES, get_currency)

os.makedirs(STATE_DIR, exist_ok=True)
SAFETY_CACHE_FILE = os.path.join(STATE_DIR, "safety_cache.json")

# lsfNoFreeze = 0x00200000, lsfGlobalFreeze = 0x00400000
LSF_NO_FREEZE     = 0x00200000
LSF_GLOBAL_FREEZE = 0x00400000
LSF_DISABLE_MASTER = 0x00100000


def _rpc(method: str, params: dict) -> Optional[dict]:
    time.sleep(0.12)  # rate limit protection between calls
    for attempt in range(3):
        try:
            resp = requests.post(CLIO_URL, json={"method": method, "params": [params]}, timeout=15)
            data = resp.json()
            result = data.get("result")
            if isinstance(result, dict) and result.get("error") == "slowDown":
                time.sleep(1.5 * (attempt + 1))
                continue
            return result
        except Exception:
            time.sleep(0.5)
    return None


def _load_cache() -> Dict:
    if os.path.exists(SAFETY_CACHE_FILE):
        try:
            with open(SAFETY_CACHE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_cache(cache: Dict) -> None:
    with open(SAFETY_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def check_amm_tvl(amm: Dict) -> Tuple[bool, float, str]:
    """Returns (pass, tvl_xrp, reason)."""
    try:
        tvl = (int(amm["amount"]) / 1e6) * 2
        if tvl >= MIN_TVL_XRP:
            return True, tvl, "ok"
        return False, tvl, f"tvl_too_low:{tvl:.0f}<{MIN_TVL_XRP}"
    except Exception as e:
        return False, 0.0, f"tvl_parse_error:{e}"


def check_lp_burn(amm: Dict) -> Tuple[str, str]:
    """
    Check if LP tokens are burned to blackhole accounts.
    Returns (status, reason) where status: 'safe'|'unsafe'|'unknown'
    """
    lp_token = amm.get("lp_token")
    if not lp_token:
        return "unknown", "no_lp_token_in_amm"

    lp_currency = lp_token.get("currency")
    lp_issuer   = lp_token.get("issuer")
    if not lp_currency or not lp_issuer:
        return "unknown", "no_lp_currency_issuer"

    # Get total LP supply
    result = _rpc("gateway_balances", {"account": lp_issuer, "ledger_index": "validated"})
    total_supply = 0.0
    if result and result.get("status") == "success":
        obligations = result.get("obligations", {})
        total_supply = float(obligations.get(lp_currency, 0))

    if total_supply <= 0:
        return "unknown", "cannot_determine_supply"

    # Check burned amount in blackholes
    burned = 0.0
    for bh in BLACK_HOLES:
        result = _rpc("account_lines", {
            "account": bh,
            "ledger_index": "validated",
            "limit": 400,
        })
        if result and result.get("status") == "success":
            for line in result.get("lines", []):
                if (line.get("currency") == lp_currency and
                        line.get("account") == lp_issuer):
                    burned += abs(float(line.get("balance", 0)))

    if total_supply > 0:
        burn_pct = (burned / total_supply) * 100
        if burn_pct >= MIN_LP_BURN_PCT:
            return "safe", f"burn_pct:{burn_pct:.1f}%"
        else:
            return "unsafe", f"burn_pct:{burn_pct:.1f}%<{MIN_LP_BURN_PCT}%"

    return "unknown", "zero_total_supply"


def check_issuer_blackhole(issuer: str) -> Tuple[bool, str]:
    """
    Returns (is_safe, reason).
    Safe = disableMaster=True AND no regularKey.
    """
    result = _rpc("account_info", {"account": issuer, "ledger_index": "validated"})
    if not result or result.get("status") != "success":
        return False, "cannot_fetch_issuer"

    acct = result.get("account_data", {})
    flags = acct.get("Flags", 0)
    disable_master = bool(flags & LSF_DISABLE_MASTER)
    has_regular_key = bool(acct.get("RegularKey"))

    if disable_master and not has_regular_key:
        return True, "blackholed"
    return False, f"disable_master={disable_master},regular_key={has_regular_key}"


def check_freeze_risk(issuer: str) -> Tuple[bool, str]:
    """Returns (no_freeze_risk, reason). True = safe."""
    result = _rpc("account_info", {"account": issuer, "ledger_index": "validated"})
    if not result or result.get("status") != "success":
        return False, "cannot_fetch_issuer"

    acct  = result.get("account_data", {})
    flags = acct.get("Flags", 0)

    if flags & LSF_GLOBAL_FREEZE:
        return False, "global_freeze_active"
    if flags & LSF_NO_FREEZE:
        return True, "no_freeze_set"
    return True, "no_freeze_flags"  # neither set = can freeze but hasn't


def check_concentration(issuer: str, symbol: str) -> Tuple[bool, str]:
    """
    Rough concentration check. Returns (ok, reason).
    Checks gateway_balances to see largest single holder.
    """
    currency = get_currency(symbol)
    result = _rpc("gateway_balances", {
        "account": issuer,
        "ledger_index": "validated",
        "hotwallet": [],
    })
    if not result or result.get("status") != "success":
        return True, "cannot_check_skip"

    obligations = result.get("obligations", {})
    total = float(obligations.get(currency, 0))
    if total <= 0:
        return True, "no_supply"

    # Check top holders via account_lines on issuer
    result2 = _rpc("account_lines", {
        "account": issuer,
        "ledger_index": "validated",
        "limit": 400,
    })
    if not result2 or result2.get("status") != "success":
        return True, "cannot_check_holders"

    lines = result2.get("lines", [])

    # Get the AMM pool account so we can exclude it — it holds tokens as liquidity,
    # NOT as a whale. Counting it inflates concentration massively (often 40-70%).
    amm_pool_account = ""
    amm_res = _rpc("amm_info", {"asset": {"currency": "XRP"}, "asset2": {"currency": currency, "issuer": issuer}})
    if amm_res.get("amm"):
        amm_pool_account = amm_res["amm"].get("account", "")

    # Filter out AMM pool account and zero balances
    balances_filtered = [
        (abs(float(l.get("balance", 0))), l.get("account", ""))
        for l in lines
        if l.get("currency") == currency
        and l.get("account", "") != amm_pool_account
        and abs(float(l.get("balance", 0))) > 0
    ]
    if not balances_filtered:
        return True, "no_holders"

    # Recalculate total excluding AMM pool
    real_total = sum(b for b, _ in balances_filtered)
    if real_total <= 0:
        return True, "no_supply_ex_amm"

    max_bal = max(b for b, _ in balances_filtered)
    pct = (max_bal / real_total * 100)
    if pct > 30:
        return False, f"top_holder:{pct:.1f}%>30%"
    return True, f"top_holder:{pct:.1f}%"


# TVL history for stability check
_tvl_history: Dict[str, List] = {}


def check_liquidity_stability(token_key: str, current_tvl: float) -> Tuple[bool, str]:
    """Reject if TVL dropped > 20% in last 3 readings."""
    if token_key not in _tvl_history:
        _tvl_history[token_key] = []
    _tvl_history[token_key].append(current_tvl)
    readings = _tvl_history[token_key][-3:]

    if len(readings) < 2:
        return True, "insufficient_history"

    max_tvl = max(readings[:-1])
    if max_tvl > 0:
        drop_pct = (max_tvl - readings[-1]) / max_tvl
        if drop_pct > 0.20:
            return False, f"tvl_drop:{drop_pct:.1%}"
    return True, f"stable"


def safety_check(token: Dict, amm: Dict, cache: Optional[Dict] = None) -> Dict:
    """
    Run all safety checks on a token.
    Returns dict with pass/fail for each check and overall 'safe' bool.
    """
    symbol = token["symbol"]
    issuer = token["issuer"]
    key    = f"{symbol}:{issuer}"

    # Use cache if fresh (< 10 min)
    if cache and key in cache:
        cached = cache[key]
        if time.time() - cached.get("ts", 0) < 1800:  # 30 min cache
            return cached

    result = {"ts": time.time(), "symbol": symbol, "issuer": issuer}

    # 1. AMM TVL
    tvl_pass, tvl, tvl_reason = check_amm_tvl(amm)
    result["tvl_pass"]   = tvl_pass
    result["tvl_xrp"]    = tvl
    result["tvl_reason"] = tvl_reason

    # 2. LP Burn — DISABLED for XRPL AMMs
    # XRPL AMM LP tokens are never "burned" — they're held by LPs by design.
    # LP burn is an EVM/Uniswap concept and does not apply here.
    lp_status = "n/a"
    lp_reason = "xrpl_amm_lp_burn_not_applicable"
    result["lp_burn_status"] = lp_status
    result["lp_burn_reason"] = lp_reason
    lp_pass = True

    # 3. Issuer blackhole
    bh_pass, bh_reason = check_issuer_blackhole(issuer)
    result["issuer_blackhole"]        = bh_pass
    result["issuer_blackhole_reason"] = bh_reason

    # 4. Freeze risk
    freeze_pass, freeze_reason = check_freeze_risk(issuer)
    result["freeze_safe"]   = freeze_pass
    result["freeze_reason"] = freeze_reason

    # 5. Concentration
    conc_pass, conc_reason = check_concentration(issuer, symbol)
    result["concentration_ok"]     = conc_pass
    result["concentration_reason"] = conc_reason

    # 6. Liquidity stability
    stab_pass, stab_reason = check_liquidity_stability(key, tvl)
    result["liquidity_stable"]        = stab_pass
    result["liquidity_stable_reason"] = stab_reason

    # Overall safety logic:
    # Hard fails: TVL too low, liquidity actively collapsing
    # Warnings (allow with flag): cannot fetch issuer (RPC fail), LP unknown, not blackholed
    # True hard fail: freeze_reason is explicitly bad (not just cannot_fetch)
    rpc_fail = "cannot_fetch" in freeze_reason or "cannot_fetch" in bh_reason
    freeze_hard_fail = not freeze_pass and not rpc_fail

    hard_pass = tvl_pass and lp_pass and not freeze_hard_fail and stab_pass
    result["safe"]     = hard_pass
    result["warnings"] = []

    # issuer_not_blackholed removed — XRPL AMM issuers don't blackhole by design, not a risk signal
    if not conc_pass:
        result["warnings"].append(f"concentration_risk:{conc_reason}")
    if lp_status == "unknown":
        result["warnings"].append("lp_burn_unknown")
    if rpc_fail:
        result["warnings"].append("issuer_rpc_unavailable")

    return result


def run_safety(token: Dict, amm: Dict) -> Dict:
    """Run safety check with cache."""
    cache = _load_cache()
    result = safety_check(token, amm, cache)
    key = f"{token['symbol']}:{token['issuer']}"
    cache[key] = result
    _save_cache(cache)
    return result


if __name__ == "__main__":
    from scanner import get_amm_info
    test_token = {"symbol": "SOLO", "issuer": "rsoLo2S1kiGeCcn6hCUXVrCpGMWLrRrLZz"}
    amm = get_amm_info(test_token["symbol"], test_token["issuer"])
    if amm:
        result = run_safety(test_token, amm)
        print(json.dumps(result, indent=2))
    else:
        print("No AMM found for SOLO")

======================================================================
# SAFETY_CONTROLLER — safety_controller.py
======================================================================

"""
safety_controller.py — Emergency stop and pause system for DKTrenchBot v2.

File-based control: creating a file activates the state, deleting it clears it.
- state/PAUSED          → bot pauses new entries, manages exits only
- state/EMERGENCY_STOP  → bot halts all activity immediately

CLI:
    python3 safety_controller.py status
    python3 safety_controller.py pause
    python3 safety_controller.py resume
    python3 safety_controller.py emergency-stop
    python3 safety_controller.py reset
"""

import argparse
import json
import os
import sys
import time
from typing import Dict

from config import STATE_DIR

PAUSE_FILE = os.path.join(STATE_DIR, "PAUSED")
KILL_FILE = os.path.join(STATE_DIR, "EMERGENCY_STOP")
ALERT_LOG_FILE = os.path.join(STATE_DIR, "safety_alerts.json")

# Drawdown thresholds
MIN_BALANCE_XRP = 10.0       # emergency stop if balance falls below this
CONSEC_LOSS_PAUSE = 3        # pause after N consecutive losses all > this XRP
CONSEC_LOSS_THRESHOLD = 5.0  # each loss must exceed this XRP to count
SINGLE_LOSS_PAUSE = 10.0     # pause + alert if single loss exceeds this XRP


def _write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def _log_alert(event: str, reason: str) -> None:
    alerts = []
    if os.path.exists(ALERT_LOG_FILE):
        try:
            with open(ALERT_LOG_FILE) as f:
                alerts = json.load(f)
        except Exception:
            pass
    alerts.append({
        "ts": time.time(),
        "ts_human": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "event": event,
        "reason": reason,
    })
    alerts = alerts[-200:]  # keep last 200 alerts
    tmp = ALERT_LOG_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(alerts, f, indent=2)
    os.replace(tmp, ALERT_LOG_FILE)


class SafetyController:
    """
    Emergency stop and pause system.
    File-based: state survives process restarts.
    """

    PAUSE_FILE = PAUSE_FILE
    KILL_FILE = KILL_FILE

    def is_paused(self) -> bool:
        """Returns True if PAUSED file exists."""
        return os.path.exists(PAUSE_FILE)

    def is_emergency_stopped(self) -> bool:
        """Returns True if EMERGENCY_STOP file exists."""
        return os.path.exists(KILL_FILE)

    def pause(self, reason: str = "manual") -> None:
        """Create PAUSED file with reason."""
        content = json.dumps({
            "ts": time.time(),
            "ts_human": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "reason": reason,
        }, indent=2)
        _write_file(PAUSE_FILE, content)
        _log_alert("PAUSED", reason)
        print(f"⏸️  Bot PAUSED: {reason}")

    def resume(self) -> None:
        """Remove PAUSED file."""
        if os.path.exists(PAUSE_FILE):
            os.remove(PAUSE_FILE)
            _log_alert("RESUMED", "manual resume")
            print("▶️  Bot RESUMED — new entries re-enabled")
        else:
            print("ℹ️  Bot was not paused")

    def emergency_stop(self, reason: str = "manual") -> None:
        """Create EMERGENCY_STOP file. Bot will halt on next cycle check."""
        content = json.dumps({
            "ts": time.time(),
            "ts_human": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "reason": reason,
        }, indent=2)
        _write_file(KILL_FILE, content)
        _log_alert("EMERGENCY_STOP", reason)
        print(f"🛑 EMERGENCY STOP activated: {reason}")

    def reset_emergency(self) -> None:
        """Remove EMERGENCY_STOP file (requires explicit operator action)."""
        if os.path.exists(KILL_FILE):
            os.remove(KILL_FILE)
            _log_alert("EMERGENCY_CLEARED", "manual reset")
            print("✅ Emergency stop CLEARED — bot can resume on next restart")
        else:
            print("ℹ️  No emergency stop active")

    def check_drawdown_kill(self, bot_state: Dict) -> bool:
        """
        Check drawdown conditions and auto-trigger pause/stop as needed.

        Auto-triggers:
          - balance < MIN_BALANCE_XRP XRP → emergency stop
          - 3+ consecutive losses > CONSEC_LOSS_THRESHOLD XRP each → pause
          - single loss > SINGLE_LOSS_PAUSE XRP → pause + alert

        Returns True if any action was taken.
        """
        triggered = False
        perf = bot_state.get("performance", {})
        history = bot_state.get("trade_history", [])

        # --- Balance check ---
        balance_xrp = bot_state.get("_cycle_wallet_xrp", 0.0)
        if balance_xrp > 0 and balance_xrp < MIN_BALANCE_XRP:
            if not self.is_emergency_stopped():
                reason = f"balance_critical_{balance_xrp:.1f}XRP_below_{MIN_BALANCE_XRP}XRP"
                self.emergency_stop(reason)
                triggered = True

        # --- Consecutive losses ---
        consec = perf.get("consecutive_losses", 0)
        if consec >= CONSEC_LOSS_PAUSE:
            # Verify each loss was > threshold
            recent_losses = [
                t for t in history[-consec:]
                if float(t.get("pnl_xrp", 0) or 0) < -CONSEC_LOSS_THRESHOLD
            ]
            if len(recent_losses) >= CONSEC_LOSS_PAUSE and not self.is_paused():
                reason = f"{consec}_consecutive_losses_over_{CONSEC_LOSS_THRESHOLD}XRP_each"
                self.pause(reason)
                triggered = True

        # --- Single large loss ---
        if history:
            last_trade = history[-1]
            last_pnl = float(last_trade.get("pnl_xrp", 0) or 0)
            if last_pnl < -SINGLE_LOSS_PAUSE and not self.is_paused():
                reason = f"single_loss_{abs(last_pnl):.2f}XRP_exceeds_{SINGLE_LOSS_PAUSE}XRP_threshold"
                self.pause(reason)
                triggered = True

        return triggered

    def check_cycle(self, bot_state: Dict) -> str:
        """
        Called at the top of every run_cycle().
        Returns: 'ok', 'paused', 'stopped'

        Also auto-checks drawdown conditions.
        """
        # Run drawdown checks first (may activate pause/stop)
        self.check_drawdown_kill(bot_state)

        if self.is_emergency_stopped():
            return "stopped"
        if self.is_paused():
            return "paused"
        return "ok"

    def get_status(self) -> Dict:
        """Return current status dict."""
        paused = self.is_paused()
        stopped = self.is_emergency_stopped()

        pause_reason = ""
        stop_reason = ""

        if paused and os.path.exists(PAUSE_FILE):
            try:
                pause_reason = json.loads(open(PAUSE_FILE).read()).get("reason", "")
            except Exception:
                pause_reason = "unknown"

        if stopped and os.path.exists(KILL_FILE):
            try:
                stop_reason = json.loads(open(KILL_FILE).read()).get("reason", "")
            except Exception:
                stop_reason = "unknown"

        status = "ok"
        if stopped:
            status = "EMERGENCY_STOPPED"
        elif paused:
            status = "PAUSED"

        return {
            "status": status,
            "is_paused": paused,
            "is_emergency_stopped": stopped,
            "pause_reason": pause_reason,
            "stop_reason": stop_reason,
            "pause_file": PAUSE_FILE,
            "kill_file": KILL_FILE,
        }


# Module-level singleton
_controller: SafetyController = SafetyController()


def get_safety_controller() -> SafetyController:
    return _controller


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DKTrenchBot Safety Controller")
    parser.add_argument("action", nargs="?", default="status",
                        choices=["status", "pause", "resume", "emergency-stop", "reset"],
                        help="Action to perform")
    parser.add_argument("--reason", default="manual CLI command",
                        help="Reason for pause/stop")
    args = parser.parse_args()

    ctrl = SafetyController()

    if args.action == "status":
        s = ctrl.get_status()
        print(f"\n=== DKTrenchBot Safety Status ===")
        print(f"  Status:    {s['status']}")
        if s["is_paused"]:
            print(f"  Pause:     {s['pause_reason']}")
        if s["is_emergency_stopped"]:
            print(f"  Stop:      {s['stop_reason']}")
        print(f"  Pause file:  {PAUSE_FILE}  ({'EXISTS' if s['is_paused'] else 'absent'})")
        print(f"  Kill file:   {KILL_FILE}  ({'EXISTS' if s['is_emergency_stopped'] else 'absent'})")

        # Load recent alerts
        if os.path.exists(ALERT_LOG_FILE):
            try:
                alerts = json.load(open(ALERT_LOG_FILE))
                recent = alerts[-5:]
                if recent:
                    print(f"\n  Recent alerts:")
                    for a in recent:
                        print(f"    [{a['ts_human']}] {a['event']}: {a['reason']}")
            except Exception:
                pass
        print()

    elif args.action == "pause":
        ctrl.pause(args.reason)

    elif args.action == "resume":
        ctrl.resume()

    elif args.action == "emergency-stop":
        confirm = input("⚠️  Confirm EMERGENCY STOP? This halts all bot activity. [yes/N]: ")
        if confirm.strip().lower() == "yes":
            ctrl.emergency_stop(args.reason)
        else:
            print("Cancelled.")

    elif args.action == "reset":
        ctrl.reset_emergency()
        ctrl.resume()
        print("✅ All safety states cleared")

======================================================================
# IMPROVE — improve.py
======================================================================

"""
improve.py — Every 6 hours: analyze last 20+ trades, adjust parameters.
Only adjusts if >= 10 trades in a category.
Writes: state/improvements.json
"""

import json
import os
import time
from typing import Dict, List, Optional
from config import (STATE_DIR, SCORE_ELITE, SCORE_TRADEABLE, SCORE_SMALL,
                    STALE_EXIT_HOURS, MAX_POSITIONS)
import state as state_mod

os.makedirs(STATE_DIR, exist_ok=True)
IMPROVEMENTS_FILE = os.path.join(STATE_DIR, "improvements.json")


def _load_improvements() -> Dict:
    if os.path.exists(IMPROVEMENTS_FILE):
        try:
            with open(IMPROVEMENTS_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "score_threshold_adj": 0,      # added to SCORE_TRADEABLE
        "size_multiplier":     1.0,
        "stale_exit_hours":    STALE_EXIT_HOURS,
        "max_positions":       MAX_POSITIONS,
        "ts":                  0,
        "history":             [],
    }


def _save_improvements(imp: Dict) -> None:
    imp["ts"] = time.time()
    with open(IMPROVEMENTS_FILE, "w") as f:
        json.dump(imp, f, indent=2)


def _analyze_by_category(trades: List[Dict], key: str) -> Dict:
    """Group trades by a category key, compute win rate per group."""
    groups: Dict[str, List] = {}
    for t in trades:
        val = t.get(key, "unknown")
        groups.setdefault(str(val), []).append(t)
    result = {}
    for cat, cat_trades in groups.items():
        wins = sum(1 for t in cat_trades if t.get("pnl_pct", 0) > 0)
        total = len(cat_trades)
        result[cat] = {
            "count":    total,
            "wins":     wins,
            "win_rate": wins / total if total > 0 else 0.0,
            "avg_pnl":  sum(t.get("pnl_pct", 0) for t in cat_trades) / total if total > 0 else 0.0,
        }
    return result


def run_improve(bot_state: Dict, force: bool = False) -> Dict:
    """
    Analyze recent performance and adjust parameters.
    Only runs every 6 hours unless force=True.
    """
    last = bot_state.get("last_improve", 0)
    if not force and (time.time() - last) < 6 * 3600:
        return {"skipped": True, "reason": "ran_recently"}

    trades = state_mod.get_recent_trades(bot_state, n=50)
    imp    = _load_improvements()

    if len(trades) < 20:
        bot_state["last_improve"] = time.time()
        state_mod.save(bot_state)
        return {"skipped": True, "reason": f"insufficient_trades:{len(trades)}"}

    changes = []

    # 1. Analyze by chart state
    by_chart = _analyze_by_category(trades, "chart_state")
    for state_name, metrics in by_chart.items():
        if metrics["count"] >= 10:
            if metrics["win_rate"] < 0.30 and state_name in ("expansion", "continuation"):
                # This state performing poorly — note it
                changes.append(f"chart_state:{state_name} win_rate={metrics['win_rate']:.0%} (poor)")

    # 2. Analyze by score band
    by_band = _analyze_by_category(trades, "score_band")
    for band, metrics in by_band.items():
        if metrics["count"] >= 10:
            if band == "small_size" and metrics["win_rate"] < 0.35:
                # Small size trades losing — raise threshold
                new_adj = min(25, imp["score_threshold_adj"] + 5)
                if new_adj != imp["score_threshold_adj"]:
                    imp["score_threshold_adj"] = new_adj
                    changes.append(f"score_threshold +5 → {SCORE_TRADEABLE + new_adj}")
            elif band == "tradeable" and metrics["win_rate"] > 0.65:
                # Good performance — allow slightly more
                new_adj = max(0, imp["score_threshold_adj"] - 5)
                if new_adj != imp["score_threshold_adj"]:
                    imp["score_threshold_adj"] = new_adj
                    changes.append(f"score_threshold -5 → {SCORE_TRADEABLE + new_adj}")

    # 3. Analyze by liquidity band
    def liq_band(tvl: float) -> str:
        if tvl >= 50000:  return "high"
        elif tvl >= 10000: return "mid"
        else:              return "low"

    for t in trades:
        t["_liq_band"] = liq_band(t.get("entry_tvl", 0))

    by_liq = _analyze_by_category(trades, "_liq_band")
    for band, metrics in by_liq.items():
        if metrics["count"] >= 10:
            if band == "low" and metrics["win_rate"] < 0.35:
                changes.append("low_liquidity_trades performing poorly — consider raising MIN_TVL")

    # 4. Overall size multiplier
    overall_wr = bot_state["performance"].get("win_rate", 0.5)
    if overall_wr > 0.65:
        new_mult = min(1.5, imp["size_multiplier"] + 0.1)
        if new_mult != imp["size_multiplier"]:
            imp["size_multiplier"] = new_mult
            changes.append(f"size_multiplier +0.1 → {new_mult:.1f}")
    elif overall_wr < 0.35:
        new_mult = max(0.5, imp["size_multiplier"] - 0.1)
        if new_mult != imp["size_multiplier"]:
            imp["size_multiplier"] = new_mult
            changes.append(f"size_multiplier -0.1 → {new_mult:.1f}")

    # 5. Stale exit timing
    stale_exits = [t for t in trades if t.get("exit_reason", "").startswith("stale")]
    if len(stale_exits) >= 10:
        stale_pnl = sum(t.get("pnl_pct", 0) for t in stale_exits) / len(stale_exits)
        if stale_pnl < -0.02:
            # Stale exits losing — reduce stale time
            new_stale = max(1.0, imp["stale_exit_hours"] - 0.5)
            if new_stale != imp["stale_exit_hours"]:
                imp["stale_exit_hours"] = new_stale
                changes.append(f"stale_exit_hours → {new_stale}")

    # Record adjustment history
    imp.setdefault("history", []).append({
        "ts":      time.time(),
        "changes": changes,
        "trades_analyzed": len(trades),
        "win_rate": overall_wr,
    })
    imp["history"] = imp["history"][-20:]  # keep last 20

    _save_improvements(imp)
    bot_state["last_improve"]   = time.time()
    bot_state["score_overrides"] = {
        "score_threshold_adj": imp["score_threshold_adj"],
        "size_multiplier":     imp["size_multiplier"],
        "stale_exit_hours":    imp["stale_exit_hours"],
    }
    state_mod.save(bot_state)

    return {
        "changes":         changes,
        "improvements":    imp,
        "trades_analyzed": len(trades),
    }


def get_current_adjustments() -> Dict:
    imp = _load_improvements()
    return {
        "score_threshold_adj": imp.get("score_threshold_adj", 0),
        "size_multiplier":     imp.get("size_multiplier", 1.0),
        "stale_exit_hours":    imp.get("stale_exit_hours", STALE_EXIT_HOURS),
        "max_positions":       imp.get("max_positions", MAX_POSITIONS),
    }


if __name__ == "__main__":
    s = state_mod.load()
    result = run_improve(s, force=True)
    print(f"Changes: {result.get('changes', [])}")
    print(f"Trades analyzed: {result.get('trades_analyzed', 0)}")

======================================================================
# REPORT — report.py
======================================================================

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

======================================================================
# BRAIN — brain.py
======================================================================

"""
brain.py — DKTrenchBot Unified Decision Engine
==============================================
Single source of truth for ALL intelligence: sizing, slippage, routing,
pool safety, strategy weighting, and execution feedback.

Bot imports from here. Execution core is dumb — brain tells it what to do.

Architecture:
    bot.py → brain.py (decisions) → execution_core.py (execution only)
"""

from collections import defaultdict
import math
import logging

logger = logging.getLogger("brain")

# ═══════════════════════════════════════════════════════════════
# GLOBAL STATE — persisted across cycles via bot.py reload
# ═══════════════════════════════════════════════════════════════

# Per-strategy performance tracking
strategy_stats = defaultdict(lambda: {
    "wins": 0, "losses": 0, "pnl": 0.0, "trades": 0, "volatility": 0.0,
})

# Per-route slippage tracking
execution_stats = defaultdict(lambda: {
    "avg_slippage": 0.0, "route_score": 1.0, "samples": 0,
})

# Capital allocation weights per strategy
capital_allocation = defaultdict(lambda: 1.0)

# Per-pool behavior memory (rug signals + volatility)
pool_memory = defaultdict(lambda: {"volatility": 0.0, "rug_signals": 0})

# ═══════════════════════════════════════════════════════════════
# SAFETY CONSTANTS
# ═══════════════════════════════════════════════════════════════

MAX_SLIPPAGE      = 0.15   # hard cap — bot skips if predicted > 15%
MIN_CONFIDENCE    = 0.44   # minimum classifier confidence to proceed
MIN_POSITION_XRP  = 5.0   # absolute floor — no trades below this
MIN_LIQUIDITY_USD = 300    # micro-cap guard (USD)
POOL_RUG_THRESHOLD = 3     # 3 large losses = pool suspect
POOL_VOL_THRESHOLD = 0.5   # volatility > 0.5 = unsafe

# Strategy base risk (used in position_sizer)
STRATEGY_BASE_RISK = {
    # Reduced 40% from originals — protect capital until WR stabilizes
    # Avg position was 9.5 XRP on 200 XRP wallet = 4.75% per trade (correct target)
    "burst":        0.05,   # was 0.20 — BURST is high WR but micro-caps need small size
    "clob_launch":  0.05,   # was 0.20
    "pre_breakout": 0.04,   # was 0.15
    "trend":        0.04,   # was 0.12
    "micro_scalp":  0.03,   # was 0.06
    "none":         0.03,   # was 0.06
}

# ═══════════════════════════════════════════════════════════════
# FEEDBACK LOOP — called after every closed trade
# ═══════════════════════════════════════════════════════════════

def update_after_trade(trade: dict) -> None:
    """
    Called after every position close. Updates strategy weights,
    execution stats, and pool memory. All learning is cumulative.
    """
    strategy  = trade.get("strategy", "unknown")
    pnl       = trade.get("pnl_xrp", 0.0)
    win       = pnl > 0

    stats = strategy_stats[strategy]
    stats["trades"]  += 1
    stats["pnl"]     += pnl
    if win:
        stats["wins"]   += 1
    else:
        stats["losses"] += 1
    stats["volatility"] = _vol(stats["volatility"], pnl)

    # Execution quality tracking
    _update_execution_stats(trade)

    # Recompute strategy weight
    _recompute_strategy_weight(strategy)

    # Pool behavior tracking
    token = trade.get("token", {})
    if token:
        _update_pool_behavior(token, pnl)

    logger.debug(
        f"[brain] trade: {strategy} | pnl={pnl:+.4f} XRP | "
        f"wr={stats['wins']/max(1,stats['trades']):.1%} | "
        f"capital_weight={capital_allocation[strategy]:.2f}"
    )


# ═══════════════════════════════════════════════════════════════
# ADAPTIVE CAPITAL ALLOCATION
# ═══════════════════════════════════════════════════════════════

def _recompute_strategy_weight(strategy: str) -> None:
    stats = strategy_stats[strategy]
    if stats["trades"] < 5:
        capital_allocation[strategy] = 1.0
        return
    winrate = stats["wins"] / max(1, stats["trades"])
    score = (winrate * 0.5) + (_norm_pnl(stats["pnl"]) * 0.4) - (stats["volatility"] * 0.2)
    capital_allocation[strategy] = _clamp(score, 0.3, 1.5)


def adjust_size_for_strategy(size: float, strategy: str) -> float:
    """
    Scale position size by capital allocation weight for this strategy.
    Weights < 1.0 = underperforming strategy, reduce size.
    Weights > 1.0 = outperformers, increase size.
    Minimum weight: 0.3x | Maximum: 1.5x.
    """
    weight = capital_allocation.get(strategy, 1.0)
    return size * weight


# ═══════════════════════════════════════════════════════════════
# SLIPPAGE PREDICTION
# ═══════════════════════════════════════════════════════════════

def predict_slippage(token: dict, size: float) -> float:
    """
    Predict realized slippage based on pool depth, position size,
    and our rolling global average slippage.
    """
    liquidity = token.get("liquidity_usd", 0) or token.get("tvl_xrp", 0)
    if not liquidity:
        return 0.05
    base = size / liquidity
    global_avg = _global_avg_slippage()
    return _clamp(base * (1 + global_avg), 0.0, 0.5)


def _global_avg_slippage() -> float:
    vals = [v["avg_slippage"] for v in execution_stats.values() if v["samples"] > 0]
    return sum(vals) / len(vals) if vals else 0.05


# ═══════════════════════════════════════════════════════════════
# EXECUTION INTELLIGENCE
# ═══════════════════════════════════════════════════════════════

def update_execution_stats(trade: dict) -> None:
    route    = trade.get("route", "default")
    expected = trade.get("entry_price", 1.0)
    actual   = trade.get("exit_price", expected)
    if not expected:
        return
    slippage = abs(actual - expected) / expected
    stats    = execution_stats[route]
    n        = stats["samples"] + 1
    stats["samples"]      = n
    stats["avg_slippage"] = (stats["avg_slippage"] * (n - 1) + slippage) / n
    stats["route_score"]   = 1.0 / (1.0 + stats["avg_slippage"])


def select_best_route(routes: list) -> str:
    """
    Given a list of route names, return the best one based on
    rolling slippage performance.
    """
    if not routes:
        return "default"
    best_score = -1
    best_route = routes[0]
    for route in routes:
        score = execution_stats[route].get("route_score", 0)
        if score > best_score:
            best_score = score
            best_route = route
    return best_route


# ═══════════════════════════════════════════════════════════════
# POOL SAFETY
# ═══════════════════════════════════════════════════════════════

def update_pool_behavior(token: dict, trade: dict) -> None:
    """Track pool volatility and rug events for safety gating."""
    pool_id = token.get("pool_id") or token.get("key", "unknown")
    mem     = pool_memory[pool_id]
    pnl     = trade.get("pnl_xrp", 0)
    mem["volatility"] = _vol(mem["volatility"], pnl)
    if pnl < -0.3:
        mem["rug_signals"] += 1


def is_pool_safe(token: dict) -> bool:
    """
    Pool is UNSAFE and should be skipped if:
    - 3+ rug events (large losses), OR
    - Volatility exceeds 0.5 (50% drawdown per trade on avg)
    """
    pool_id = token.get("pool_id") or token.get("key", "unknown")
    mem     = pool_memory[pool_id]
    if mem["rug_signals"] >= POOL_RUG_THRESHOLD:
        logger.info(f"[brain] POOL_UNSAFE {pool_id}: rug_signals={mem['rug_signals']}")
        return False
    if mem["volatility"] > POOL_VOL_THRESHOLD:
        logger.info(f"[brain] POOL_UNSAFE {pool_id}: volatility={mem['volatility']:.3f}")
        return False
    return True


# ═══════════════════════════════════════════════════════════════
# PRE-TRADE VALIDATION GATES
# ═══════════════════════════════════════════════════════════════

def pre_trade_validator(token: dict, size: float, confidence: float, route_quality: str = "GOOD") -> tuple[bool, str]:
    """
    Non-bypassable safety gates. Returns (pass, reason).
    reason = "" if passed, else human-readable skip reason.
    """
    symbol = token.get("symbol", "?")

    # Gate 1: Confidence
    if confidence < MIN_CONFIDENCE:
        return False, f"confidence {confidence:.2f} < {MIN_CONFIDENCE}"

    # Gate 2: Predicted slippage (uses brain's learned slippage model)
    predicted = predict_slippage(token, size)
    if predicted > MAX_SLIPPAGE:
        return False, f"slippage {predicted:.1%} > {MAX_SLIPPAGE:.1%}"

    # Gate 3: Liquidity floor
    liquidity = token.get("liquidity_usd", 0)
    if liquidity < MIN_LIQUIDITY_USD:
        return False, f"liquidity ${liquidity} < ${MIN_LIQUIDITY_USD}"

    # Gate 4: Pool safety
    if not is_pool_safe(token):
        return False, "pool unsafe — volatility/rug signal"

    # Gate 5: Route quality
    if route_quality != "GOOD":
        return False, f"route={route_quality}"

    return True, ""


# ═══════════════════════════════════════════════════════════════
# POSITION SIZER
# ═══════════════════════════════════════════════════════════════

def position_sizer(
    token: dict,
    classification: dict,
    wallet_state: dict,
    strategy_name: str = "none",
) -> float:
    """
    Centralized position sizing:
    - Strategy base risk
    - Confidence multiplier (0.5x–1.5x)
    - Liquidity cap (never exceed safe pool depth)
    - Drawdown protection (halve if wallet down >20%)
    - Adaptive weight from capital_allocation
    """
    strat_name  = strategy_name or classification.get("primary", "none")
    base_risk   = STRATEGY_BASE_RISK.get(strat_name, 0.12)
    balance     = wallet_state.get("balance", 0)
    base_size   = balance * base_risk

    # Confidence multiplier: 0.5 + confidence → 0.94–1.5x for 0.44–1.0 confidence
    conf = classification.get("confidence", 0.5)
    base_size *= (0.5 + conf)

    # Liquidity cap (safe entry size based on pool depth)
    max_safe = _get_safe_entry_size(token)
    size     = min(base_size, max_safe)

    # Drawdown protection
    drawdown = wallet_state.get("drawdown", 0)
    if drawdown > 0.20:
        size *= 0.5

    # Apply capital allocation weight
    size *= capital_allocation.get(strat_name, 1.0)

    # Floor
    if size < MIN_POSITION_XRP:
        return 0.0

    return round(size, 2)


def _get_safe_entry_size(token: dict) -> float:
    """
    Maximum safe position size (XRP) based on pool depth.
    MC < $2k  → 1.5% of TVL
    MC < $10k → 2.5% of TVL
    MC > $10k → 3.0% of TVL
    """
    liquidity = token.get("liquidity_usd", 0)
    mcap      = token.get("market_cap", 0)
    if mcap < 2000:
        pct = 0.015
    elif mcap < 10000:
        pct = 0.025
    else:
        pct = 0.030
    return max(liquidity * pct, MIN_POSITION_XRP)


# ═══════════════════════════════════════════════════════════════
# INTELLIGENCE ACCESS — bot.py queries these
# ═══════════════════════════════════════════════════════════════

def get_strategy_weight(strategy: str) -> float:
    """Current capital allocation weight for a strategy."""
    return capital_allocation.get(strategy, 1.0)


def get_strategy_stats(strategy: str) -> dict:
    """Full stats for a strategy (for dashboards/reporting)."""
    return dict(strategy_stats.get(strategy, {}))


def get_pool_stats(pool_id: str) -> dict:
    """Pool memory (rug_signals, volatility)."""
    return dict(pool_memory.get(pool_id, {}))


def get_route_stats(route: str) -> dict:
    """Route execution quality (avg_slippage, route_score, samples)."""
    return dict(execution_stats.get(route, {}))


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _vol(current: float, new_pnl: float) -> float:
    """Exponentially weighted volatility tracking."""
    return current * 0.9 + abs(new_pnl) * 0.1

def _norm_pnl(pnl: float) -> float:
    """Bounded PnL normalization: maps to ~[-1, 1]"""
    return math.tanh(pnl / 10.0)

def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(value, hi))

======================================================================
# WALLET_DISCOVERY — new_wallet_discovery.py
======================================================================

"""
new_wallet_discovery.py — Smart Wallet Auto-Discovery (Audit #1)

Goal: Mine our own trade_history from state.json to auto-discover smart wallets
that bought alongside us on winners.

Algorithm:
1. Load state.json trade_history
2. For each trade where we profited (profit_xrp > 0), get entry_time, currency/issuer, entry_price
3. Query ledger txs around entry_time ± 10 min to find OTHER wallets that bought the same token
4. Score those wallets by how well they timed the entry vs ours
5. If they entered before or at the same time as us on a winner → add to candidate_wallets
6. Track candidate_wallet conviction over time: if they keep appearing on winners, promote to TRACKED_WALLET
7. Store discovered wallets in state/discovered_wallets.json
8. At startup, re-check all historical winners to continuously expand the list
9. Log discoveries clearly

Key constraint: XRPL has no "AMM history" — use account_tx on the AMM account address
(pool's account) filtering by currency, or scan ledger for Payment transactions to the
token issuer in that time window.
"""

import json
import os
import time
import logging
import requests
from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict

logger = logging.getLogger("wallet_discovery")

STATE_DIR = os.path.join(os.path.dirname(__file__), "state")
DISCOVERED_FILE = os.path.join(STATE_DIR, "discovered_wallets.json")
CLIO_URL = "https://rpc.xrplclaw.com"

# Minimum XRP profit to consider a trade a "winner" worth mining
MIN_PROFIT_XRP = 1.0

# Time window around our entry to look for co-buyers (seconds)
ENTRY_WINDOW_SEC = 600  # ±10 minutes

# Conviction threshold: wallet must appear on N winning trades to be promoted
CONVICTION_THRESHOLD = 3

# Maximum candidates to track
MAX_CANDIDATES = 100


def _rpc(method: str, params: dict, timeout: int = 15) -> Optional[dict]:
    """Send RPC request to CLIO."""
    try:
        resp = requests.post(CLIO_URL, json={"method": method, "params": [params]}, timeout=timeout)
        result = resp.json().get("result", {})
        return result
    except Exception as e:
        logger.debug(f"RPC error {method}: {e}")
        return None


def _load_state() -> Dict:
    """Load bot state.json."""
    state_file = os.path.join(STATE_DIR, "state.json")
    if os.path.exists(state_file):
        try:
            with open(state_file) as f:
                return json.load(f)
        except Exception:
            pass
    return {"trade_history": [], "positions": {}}


def _load_discovered() -> Dict:
    """Load discovered wallets file."""
    if os.path.exists(DISCOVERED_FILE):
        try:
            with open(DISCOVERED_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "candidates": {},   # wallet -> {appearances, tokens, first_seen, last_seen, conviction_score}
        "tracked": [],      # list of wallet addresses promoted to tracked
        "last_scan_ledger": 0,
    }


def _save_discovered(data: Dict) -> None:
    """Save discovered wallets."""
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = DISCOVERED_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, DISCOVERED_FILE)
    except Exception:
        with open(DISCOVERED_FILE, "w") as f:
            json.dump(data, f, indent=2)


def _get_currency_code(symbol: str) -> str:
    """Convert symbol to XRPL currency code (same logic as config.get_currency)."""
    s = symbol.upper()
    if len(s) <= 3:
        return s.ljust(3)
    if len(s) == 40 and all(c in "0123456789ABCDEF" for c in s):
        return s
    encoded = s.encode("utf-8").hex().upper()
    return encoded.ljust(40, "0")[:40]


def _find_amm_account(currency: str, issuer: str) -> Optional[str]:
    """
    Find the AMM pool account for a currency/issuer pair.
    The AMM account is deterministic but we need to query it.
    We search for accounts holding this token via account_lines on the issuer.
    """
    # Strategy: look for AMM-related accounts by checking who holds large amounts
    # of this token. The AMM pool will be the largest holder besides the issuer.
    result = _rpc("account_lines", {
        "account": issuer,
        "limit": 100,
    })
    if not result or result.get("status") != "success":
        return None

    lines = result.get("lines", [])
    # Sort by balance descending — AMM pool should be near top
    sorted_lines = sorted(lines, key=lambda x: float(x.get("balance", "0")), reverse=True)

    for line in sorted_lines[:5]:
        peer = line.get("account", "")
        # AMM accounts typically have very high balances
        bal = float(line.get("balance", "0"))
        if bal > 1000000:  # Large holder likely AMM
            return peer

    return None


def _scan_transactions_for_buyers(
    issuer: str,
    currency: str,
    entry_time: float,
    our_entry_time: float,
    window_sec: int = ENTRY_WINDOW_SEC,
) -> List[Dict]:
    """
    Scan transactions on the issuer account around entry_time to find buyers.
    Returns list of {wallet, ts, amount_xrp} for wallets that bought the token.
    """
    buyers = []
    cutoff_start = entry_time - window_sec
    cutoff_end = entry_time + window_sec

    # Convert to Ripple epoch for comparison
    ripple_cutoff_start = cutoff_start - 946684800
    ripple_cutoff_end = cutoff_end - 946684800

    result = _rpc("account_tx", {
        "account": issuer,
        "limit": 100,
        "ledger_index_min": -1,
        "ledger_index_max": -1,
    })

    if not result or result.get("status") != "success":
        return buyers

    for tx_wrapper in result.get("transactions", []):
        tx = tx_wrapper.get("tx", {})
        meta = tx_wrapper.get("meta", {})
        tx_type = tx.get("TransactionType", "")
        tx_date = tx.get("date", 0)  # Ripple epoch seconds

        # Convert to Unix epoch
        tx_time_unix = tx_date + 946684800

        # Check time window
        if tx_time_unix < cutoff_start or tx_time_unix > cutoff_end:
            continue

        sender = tx.get("Account", "")
        if not sender:
            continue

        # Skip our own wallet
        from config import BOT_WALLET_ADDRESS
        if sender == BOT_WALLET_ADDRESS:
            continue

        # Detect buys: OfferCreate where TakerPays=token, TakerGets=XRP
        if tx_type == "OfferCreate":
            tp = tx.get("TakerPays", {})
            tg = tx.get("TakerGets", {})

            # Buying token: paying token, getting XRP
            if (isinstance(tp, dict) and
                tp.get("currency") == currency and
                tp.get("issuer") == issuer and
                isinstance(tg, str)):

                try:
                    xrp_amount = int(tg) / 1e6
                    buyers.append({
                        "wallet": sender,
                        "ts": tx_time_unix,
                        "amount_xrp": xrp_amount,
                        "timing_offset": tx_time_unix - our_entry_time,
                    })
                except (ValueError, TypeError):
                    pass

        elif tx_type == "Payment":
            # Direct payment of token
            amt = tx.get("Amount", {})
            if isinstance(amt, dict) and amt.get("currency") == currency and amt.get("issuer") == issuer:
                dest = tx.get("Destination", "")
                if dest:
                    buyers.append({
                        "wallet": dest,
                        "ts": tx_time_unix,
                        "amount_xrp": 0,  # Can't determine XRP value easily
                        "timing_offset": tx_time_unix - our_entry_time,
                    })

    return buyers


def _score_wallet_timing(buyers: List[Dict], our_entry_time: float) -> Dict[str, float]:
    """
    Score wallets by how well they timed their entry relative to ours.
    Earlier entry = higher score. Same time = good. Later = lower.
    Returns {wallet: score} where score is 0-100.
    """
    scores = {}
    for buyer in buyers:
        offset = buyer["timing_offset"]  # negative = before us, positive = after us
        wallet = buyer["wallet"]

        # Scoring: entered before us = 80-100, same time = 70-80, within 5min after = 50-70
        if offset <= 0:
            # Entered before or at same time — best signal
            score = max(70, min(100, 80 + abs(offset) / 60))  # +1 per minute early
        elif offset <= 300:
            # Within 5 min after us — still good, they saw the same signal
            score = max(50, 70 - offset / 15)  # -1 per 15 sec late
        else:
            # More than 5 min late — weaker signal
            score = max(20, 50 - (offset - 300) / 30)

        # Accumulate if wallet appears multiple times
        scores[wallet] = scores.get(wallet, 0) + score

    return scores


def discover_smart_wallets(force_rescan: bool = False) -> Dict:
    """
    Main discovery function. Mines trade_history for winning trades and finds
    co-buying wallets. Returns updated discovered data.
    """
    logger.info("🔍 Starting smart wallet discovery...")

    state = _load_state()
    discovered = _load_discovered()
    trade_history = state.get("trade_history", [])

    # Filter to winning trades only
    winners = [
        t for t in trade_history
        if t.get("pnl_xrp", 0) > MIN_PROFIT_XRP
    ]

    if not winners:
        logger.info("No winning trades found to mine.")
        return discovered

    logger.info(f"Found {len(winners)} winning trades (pnl_xrp > {MIN_PROFIT_XRP})")

    new_candidates = defaultdict(lambda: {
        "appearances": 0,
        "tokens": set(),
        "total_score": 0.0,
        "first_seen": time.time(),
        "last_seen": 0,
        "win_details": [],
    })

    for trade in winners:
        symbol = trade.get("symbol", "")
        issuer = trade.get("issuer", "")
        entry_time = trade.get("entry_time", 0)
        pnl_xrp = trade.get("pnl_xrp", 0)
        exit_reason = trade.get("exit_reason", "")

        if not symbol or not issuer or not entry_time:
            continue

        currency = _get_currency_code(symbol)
        logger.info(f"  Mining winner: {symbol} (pnl={pnl_xrp:+.2f} XRP, reason={exit_reason})")

        # Scan for co-buyers around entry time
        buyers = _scan_transactions_for_buyers(
            issuer=issuer,
            currency=currency,
            entry_time=entry_time,
            our_entry_time=entry_time,
        )

        if not buyers:
            logger.debug(f"    No co-buyers found for {symbol}")
            continue

        # Score timing
        timing_scores = _score_wallet_timing(buyers, entry_time)

        for wallet, score in timing_scores.items():
            # Only consider wallets that entered before or close to our entry
            # (within 5 min after is acceptable — they may have seen the same signal)
            matching_buyers = [b for b in buyers if b["wallet"] == wallet]
            earliest_offset = min(b["timing_offset"] for b in matching_buyers)

            # Key criterion: they entered before or at roughly the same time as us
            if earliest_offset <= 300:  # within 5 min of our entry
                cand = new_candidates[wallet]
                cand["appearances"] += 1
                cand["tokens"].add(symbol)
                cand["total_score"] += score
                cand["last_seen"] = time.time()
                cand["win_details"].append({
                    "symbol": symbol,
                    "pnl_xrp": pnl_xrp,
                    "exit_reason": exit_reason,
                    "our_entry": entry_time,
                    "their_offset": earliest_offset,
                })
                logger.info(f"    🎯 Candidate: {wallet[:8]}... appeared on {symbol} "
                          f"(offset={earliest_offset:+.0f}s, score={score:.0f})")

    # Merge with existing candidates
    for wallet, data in new_candidates.items():
        existing = discovered["candidates"].get(wallet, {})
        existing["appearances"] = existing.get("appearances", 0) + data["appearances"]
        existing_tokens = set(existing.get("tokens", []))
        existing_tokens.update(data["tokens"])
        existing["tokens"] = list(existing_tokens)
        existing["total_score"] = existing.get("total_score", 0) + data["total_score"]
        existing["last_seen"] = max(existing.get("last_seen", 0), data["last_seen"])
        if "first_seen" not in existing:
            existing["first_seen"] = data["first_seen"]
        existing_wins = existing.get("win_details", [])
        existing_wins.extend(data["win_details"])
        # Keep last 20 win details
        existing["win_details"] = existing_wins[-20:]

        # Calculate conviction score: appearances * avg_score / 100
        avg_score = existing["total_score"] / max(existing["appearances"], 1)
        existing["conviction_score"] = round(avg_score * existing["appearances"] / 10, 2)

        discovered["candidates"][wallet] = existing

    # Promote high-conviction candidates to tracked
    newly_tracked = []
    for wallet, data in list(discovered["candidates"].items()):
        if (data["appearances"] >= CONVICTION_THRESHOLD and
            wallet not in discovered["tracked"]):
            discovered["tracked"].append(wallet)
            newly_tracked.append(wallet)
            logger.info(f"  ⭐ PROMOTED to tracked: {wallet} "
                       f"(appearances={data['appearances']}, conviction={data['conviction_score']})")

    # Prune low-quality candidates (keep top MAX_CANDIDATES by conviction)
    if len(discovered["candidates"]) > MAX_CANDIDATES:
        sorted_cands = sorted(
            discovered["candidates"].items(),
            key=lambda x: x[1].get("conviction_score", 0),
            reverse=True,
        )
        keep = dict(sorted_cands[:MAX_CANDIDATES])
        discovered["candidates"] = keep

    discovered["last_scan_ledger"] = int(time.time())
    _save_discovered(discovered)

    logger.info(f"✅ Discovery complete: {len(discovered['candidates'])} candidates, "
               f"{len(discovered['tracked'])} tracked wallets")
    if newly_tracked:
        logger.info(f"  Newly tracked: {len(newly_tracked)} wallets")

    return discovered


def get_discovered_wallets() -> List[str]:
    """Return list of all discovered wallet addresses (candidates + tracked)."""
    discovered = _load_discovered()
    wallets = set(discovered.get("tracked", []))
    wallets.update(discovered.get("candidates", {}).keys())
    return list(wallets)


def get_tracked_wallets() -> List[str]:
    """Return list of promoted tracked wallet addresses."""
    discovered = _load_discovered()
    return discovered.get("tracked", [])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    result = discover_smart_wallets(force_rescan=True)
    print(json.dumps({
        "candidates": len(result["candidates"]),
        "tracked": len(result["tracked"]),
        "tracked_addresses": result["tracked"][:10],
    }, indent=2))

======================================================================
# BREAKOUT — breakout.py
======================================================================

"""
breakout.py — Price breakout detection and quality scoring.
Tracks price over up to 20 readings, detects higher lows, compression,
breakout strength, wick quality, and extension.
Returns breakout_quality: 0-100
"""

import os
import json
from typing import Dict, List, Optional, Tuple
from config import STATE_DIR

os.makedirs(STATE_DIR, exist_ok=True)

BREAKOUT_FILE = os.path.join(STATE_DIR, "breakout_data.json")


def _load_data() -> Dict:
    if os.path.exists(BREAKOUT_FILE):
        try:
            with open(BREAKOUT_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_data(data: Dict) -> None:
    with open(BREAKOUT_FILE, "w") as f:
        json.dump(data, f)


def update_price(token_key: str, price: float, volume_proxy: float = 0.0) -> None:
    """Add a price reading to history (max 20 kept)."""
    data = _load_data()
    if token_key not in data:
        data[token_key] = []
    data[token_key].append({"price": price, "vol": volume_proxy})
    if len(data[token_key]) > 20:
        data[token_key] = data[token_key][-20:]
    _save_data(data)


def _higher_lows(prices: List[float]) -> float:
    """Score 0-1 based on proportion of higher lows."""
    if len(prices) < 3:
        return 0.5
    lows = []
    for i in range(1, len(prices) - 1):
        if prices[i] < prices[i - 1] and prices[i] < prices[i + 1]:
            lows.append(prices[i])
    if len(lows) < 2:
        return 0.5
    higher_low_count = sum(1 for i in range(1, len(lows)) if lows[i] > lows[i - 1])
    return higher_low_count / (len(lows) - 1)


def _compression_score(prices: List[float]) -> float:
    """
    Measure price compression (tight range before breakout).
    Score 0-1: 1.0 = very tight compression.
    """
    if len(prices) < 4:
        return 0.5
    # Look at the middle portion of history
    window = prices[max(0, len(prices) - 6):-1] if len(prices) > 6 else prices[:-1]
    if not window:
        return 0.5
    high = max(window)
    low  = min(window)
    if low <= 0:
        return 0.0
    range_pct = (high - low) / low
    # < 3% range = very compressed
    if range_pct < 0.03:
        return 1.0
    elif range_pct < 0.06:
        return 0.8
    elif range_pct < 0.10:
        return 0.6
    elif range_pct < 0.15:
        return 0.4
    else:
        return 0.2


def _breakout_strength(prices: List[float]) -> float:
    """
    Compare last price to the recent range high.
    Returns 0-1 score.
    """
    if len(prices) < 3:
        return 0.0
    recent = prices[-5:] if len(prices) >= 5 else prices
    prior  = prices[:-1]
    if not prior:
        return 0.0
    prior_high = max(prior[-5:]) if len(prior) >= 5 else max(prior)
    last = prices[-1]
    if prior_high <= 0:
        return 0.0
    strength = (last - prior_high) / prior_high
    # Score: 0%=0, 3%=0.5, 8%+=1.0
    if strength <= 0:
        return 0.0
    elif strength >= 0.08:
        return 1.0
    else:
        return strength / 0.08


def _wick_quality(prices: List[float]) -> float:
    """
    Estimate wick quality from price action.
    We don't have candle data, so proxy: steady uptrend = good wicks.
    Score 0-1.
    """
    if len(prices) < 3:
        return 0.5
    # Count how many periods closed above open (price higher than prior)
    bullish = sum(1 for i in range(1, len(prices)) if prices[i] > prices[i - 1])
    return bullish / (len(prices) - 1)


def _extension_check(prices: List[float]) -> float:
    """
    Penalty for being overextended. Returns 0-1 (1=not extended, 0=fully extended).
    """
    if len(prices) < 3:
        return 1.0
    start = prices[0]
    last  = prices[-1]
    if start <= 0:
        return 1.0
    total_move = (last - start) / start
    # > 50% move without pullback = extended
    if total_move > 0.50:
        return 0.0
    elif total_move > 0.30:
        return 0.3
    elif total_move > 0.20:
        return 0.6
    elif total_move > 0.10:
        return 0.85
    else:
        return 1.0


def compute_breakout_quality(token_key: str) -> Dict:
    """
    Compute breakout_quality (0-100) and component scores.
    """
    data = _load_data()
    readings = data.get(token_key, [])

    if len(readings) < 2:
        return {
            "breakout_quality": 0,
            "reason": "insufficient_data",
            "readings": len(readings),
        }

    prices = [r["price"] for r in readings if r.get("price", 0) > 0]
    if len(prices) < 2:
        return {"breakout_quality": 0, "reason": "no_prices"}

    hl_score      = _higher_lows(prices)
    comp_score    = _compression_score(prices)
    strength      = _breakout_strength(prices)
    wick_q        = _wick_quality(prices)
    extension     = _extension_check(prices)

    # Weighted composite → 0-100
    raw = (
        hl_score   * 25 +
        comp_score * 20 +
        strength   * 30 +
        wick_q     * 15 +
        extension  * 10
    )
    quality = min(100, max(0, int(raw)))

    return {
        "breakout_quality": quality,
        "higher_lows":      round(hl_score, 3),
        "compression":      round(comp_score, 3),
        "strength":         round(strength, 3),
        "wick_quality":     round(wick_q, 3),
        "extension":        round(extension, 3),
        "readings":         len(prices),
        "price_first":      prices[0],
        "price_last":       prices[-1],
        "pct_change":       round((prices[-1] - prices[0]) / prices[0] * 100, 2) if prices[0] > 0 else 0,
    }


def get_breakout_quality(token_key: str, current_price: float) -> int:
    """Update price history and return breakout_quality score."""
    update_price(token_key, current_price)
    result = compute_breakout_quality(token_key)
    return result.get("breakout_quality", 0)


if __name__ == "__main__":
    import time
    key = "TEST:rTest123"
    # Simulate accumulation then breakout
    prices = [1.0, 1.01, 0.99, 1.00, 1.02, 1.01, 1.03, 1.05, 1.08, 1.12]
    for p in prices:
        update_price(key, p)
        time.sleep(0.01)
    result = compute_breakout_quality(key)
    print(json.dumps(result, indent=2))

======================================================================
# TOKEN_INTEL — token_intel.py
======================================================================

#!/usr/bin/env python3
"""
token_intel.py — Lite Haus-style token intelligence for every scanned token.

Produces the same data as the Lite Haus Alerts Hub automatically:
  - Holders + top 10 concentration %
  - Price changes: 5m / 1h / 6h / 24h (from our own price history)
  - RSI (14-period, computed from price history)
  - Buyer pressure % (buy vol vs total vol)
  - Market cap + liquidity (from xpmarket)
  - Volume 24h, unique traders
  - Concentration risk flag
  - Launch age

Sources:
  - xpmarket AMM list (cached every 4min, already fetched by discovery.py)
  - XRPL account_lines (holder count + top 10%, rate-limited, cached 10min)
  - Scanner price history (in-memory, updated every 60s)

All data cached in state/token_intel_cache.json
"""

import json, os, time, math, requests, logging
from pathlib import Path
from typing import Dict, Optional, List
from collections import defaultdict

BOT_DIR   = Path(__file__).parent
STATE_DIR = BOT_DIR / "state"
CACHE_FILE = STATE_DIR / "token_intel_cache.json"
XPMARKET_CACHE = STATE_DIR / "xpmarket_cache.json"

CLIO_URL = "http://xrpl-rpc.goons.app:51233"

# Cache TTLs
HOLDER_CACHE_TTL  = 600   # 10 min — account_lines is slow
XPMARKET_CACHE_TTL = 240  # 4 min — matches discovery cycle

import logging
log = logging.getLogger("token_intel")

os.makedirs(STATE_DIR, exist_ok=True)


# ── Cache management ──────────────────────────────────────────────────────────

def load_cache() -> dict:
    try:
        if CACHE_FILE.exists():
            return json.loads(CACHE_FILE.read_text())
    except:
        pass
    return {}


def save_cache(c: dict):
    try:
        tmp = str(CACHE_FILE) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(c, f)
        os.replace(tmp, str(CACHE_FILE))
    except:
        pass


def load_xpmarket_cache() -> dict:
    try:
        if XPMARKET_CACHE.exists():
            d = json.loads(XPMARKET_CACHE.read_text())
            if time.time() - d.get("ts", 0) < XPMARKET_CACHE_TTL:
                return d.get("data", {})
    except:
        pass
    return {}


def save_xpmarket_cache(data: dict):
    try:
        with open(XPMARKET_CACHE, "w") as f:
            json.dump({"ts": time.time(), "data": data}, f)
    except:
        pass


# ── xpmarket enrichment ───────────────────────────────────────────────────────

def fetch_xpmarket_index() -> dict:
    """
    Fetch full xpmarket AMM list and index by issuer.
    Returns {issuer: {holders, volume_usd, liquidity_usd, txns, swaps,
                      created_at, plus2Depth, minus2Depth, price1Usd}}
    Cached 4 minutes.
    """
    cached = load_xpmarket_cache()
    if cached:
        return cached

    result = {}
    page = 1
    while True:
        try:
            r = requests.get(
                "https://api.xpmarket.com/api/amm/list",
                params={"sort": "liquidity", "order": "desc", "limit": 100, "page": page},
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
                timeout=12,
            )
            items = r.json().get("data", {}).get("items", [])
            if not items:
                break
            for item in items:
                # Symbol format: "XRP/RLUSD-rMxCKbEDwqr76QuheSUMdEGf4B9xJ8m5De"
                # or "FUZZY-rhCAT4hRdi2Y9puNdkpMzxrdKa5wkppR62/XRP"
                sym_full = item.get("symbol", "")

                # Extract token issuer — it's embedded after the "-" in the symbol
                token_issuer = ""
                if "-" in sym_full:
                    part = sym_full.split("-")[-1].split("/")[0]
                    if len(part) > 20 and part.startswith("r"):
                        token_issuer = part

                # Extract token symbol
                if "/" in sym_full:
                    parts = sym_full.split("/")
                    raw = parts[1] if parts[0] == "XRP" else parts[0]
                    sym = raw.split("-")[0]
                else:
                    sym = sym_full.split("-")[0]

                # Use token issuer for index key (not AMM pool issuer)
                iss = token_issuer if token_issuer else item.get("issuer", "")

                # XRP liquidity: for "XRP/TOKEN" pools, amount1=XRP side
                # for "TOKEN/XRP" pools, amount2=XRP side
                sym_parts = sym_full.split("/")
                if sym_parts[0].strip() == "XRP":
                    liq_xrp = float(item.get("amount1", 0) or 0)
                else:
                    liq_xrp = float(item.get("amount2", 0) or 0)

                result[iss] = {
                    "symbol_xpm":   sym,
                    "holders":      item.get("holders", 0),
                    "volume_usd":   float(item.get("volume_usd", 0) or 0),
                    "liquidity_usd": float(item.get("liquidity_usd", 0) or 0),
                    "liquidity_xrp": liq_xrp,
                    "txns":         item.get("txns", 0),
                    "swaps":        item.get("swaps", 0),
                    "created_at":   item.get("created_at", ""),
                    "plus2_depth":  float(item.get("plus2Depth", 0) or 0),
                    "minus2_depth": float(item.get("minus2Depth", 0) or 0),
                    "price_usd":    float(item.get("price2Usd", 0) or 0),
                    "trading_fee":  float(item.get("tradingFee", 0) or 0),
                    "apr":          float(item.get("apr", 0) or 0),
                    "level":        item.get("level", ""),
                }
            if len(items) < 100:
                break
            page += 1
            time.sleep(0.3)
        except Exception as e:
            log.debug(f"xpmarket fetch error page {page}: {e}")
            break

    save_xpmarket_cache(result)
    return result


# ── Holder analysis ───────────────────────────────────────────────────────────

def fetch_holder_data(issuer: str) -> dict:
    """
    Fetch holder count and top-10 concentration from XRPL account_lines.
    Cached 10 minutes per token.
    """
    cache = load_cache()
    key = f"holders:{issuer}"
    entry = cache.get(key, {})
    if entry and time.time() - entry.get("ts", 0) < HOLDER_CACHE_TTL:
        return entry.get("data", {})

    try:
        r = requests.post(CLIO_URL, json={
            "method": "account_lines",
            "params": [{"account": issuer, "limit": 400}]
        }, timeout=8)
        lines = r.json().get("result", {}).get("lines", [])
        time.sleep(0.15)

        holders = [(l["account"], abs(float(l.get("balance", 0))))
                   for l in lines if abs(float(l.get("balance", 0))) > 0]
        holders.sort(key=lambda x: -x[1])

        total = sum(b for _, b in holders)
        top10_pct = sum(b for _, b in holders[:10]) / total * 100 if total > 0 else 0
        top1_pct  = holders[0][1] / total * 100 if holders else 0

        data = {
            "holder_count": len(holders),
            "top10_pct":    round(top10_pct, 2),
            "top1_pct":     round(top1_pct, 2),
            "top_holders":  [{"addr": a[:8]+"...", "pct": round(b/total*100,2)} for a,b in holders[:10]] if total > 0 else [],
            "high_concentration": top1_pct > 30 or top10_pct > 70,
        }

        cache[key] = {"ts": time.time(), "data": data}
        save_cache(cache)
        return data

    except Exception as e:
        log.debug(f"holder fetch error {issuer[:16]}: {e}")
        return {}


# ── Price analytics from history ──────────────────────────────────────────────

def compute_price_analytics(price_history: list) -> dict:
    """
    Compute price changes and RSI from our in-memory price history.
    price_history: list of (timestamp, price, tvl) tuples
    Returns p5m, p1h, p6h, p24h, rsi14, buyer_pressure_estimate
    """
    if not price_history or len(price_history) < 2:
        return {}

    now = time.time()
    prices = sorted(price_history, key=lambda x: x[0])  # sort by time

    current_price = prices[-1][1]
    if current_price <= 0:
        return {}

    def price_n_ago(seconds: int) -> Optional[float]:
        target = now - seconds
        # Find closest price to target time
        best = None
        best_diff = float("inf")
        for ts, p, _ in prices:
            diff = abs(ts - target)
            if diff < best_diff:
                best_diff = diff
                best = p
        return best if best_diff < seconds * 0.5 else None  # must be within 50% of target window

    result = {}

    p5m  = price_n_ago(300)
    p1h  = price_n_ago(3600)
    p6h  = price_n_ago(21600)
    p24h = price_n_ago(86400)

    if p5m  and p5m > 0:  result["p5m"]  = round((current_price - p5m)  / p5m  * 100, 2)
    if p1h  and p1h > 0:  result["p1h"]  = round((current_price - p1h)  / p1h  * 100, 2)
    if p6h  and p6h > 0:  result["p6h"]  = round((current_price - p6h)  / p6h  * 100, 2)
    if p24h and p24h > 0: result["p24h"] = round((current_price - p24h) / p24h * 100, 2)

    # RSI-14 from price history
    if len(prices) >= 15:
        close_prices = [p for _, p, _ in prices[-15:]]
        gains, losses = [], []
        for i in range(1, len(close_prices)):
            change = close_prices[i] - close_prices[i-1]
            gains.append(max(change, 0))
            losses.append(max(-change, 0))
        avg_gain = sum(gains) / len(gains) if gains else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        if avg_loss == 0:
            rsi = 100
        elif avg_gain == 0:
            rsi = 0
        else:
            rs = avg_gain / avg_loss
            rsi = round(100 - (100 / (1 + rs)), 1)
        result["rsi"] = rsi

    # TVL momentum (is pool growing?)
    if len(prices) >= 3:
        recent_tvls = [tvl for _, _, tvl in prices[-3:] if tvl > 0]
        older_tvls  = [tvl for _, _, tvl in prices[:3]  if tvl > 0]
        if recent_tvls and older_tvls:
            tvl_change = (sum(recent_tvls)/len(recent_tvls) - sum(older_tvls)/len(older_tvls))
            tvl_change_pct = tvl_change / (sum(older_tvls)/len(older_tvls)) * 100 if older_tvls else 0
            result["tvl_change_pct"] = round(tvl_change_pct, 1)

    # Price trend: count up vs down moves
    if len(prices) >= 5:
        recent = [p for _, p, _ in prices[-10:]]
        ups   = sum(1 for i in range(1, len(recent)) if recent[i] > recent[i-1])
        downs = sum(1 for i in range(1, len(recent)) if recent[i] < recent[i-1])
        total_moves = ups + downs
        if total_moves > 0:
            result["buyer_pressure"] = round(ups / total_moves * 100, 1)

    return result


# ── Launch age ────────────────────────────────────────────────────────────────

def compute_launch_age(created_at: str) -> dict:
    """Convert xpmarket created_at ISO string to age in hours."""
    if not created_at:
        return {}
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        age_hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
        return {
            "launch_age_hours": round(age_hours, 1),
            "is_fresh": age_hours < 24,
            "is_very_fresh": age_hours < 6,
        }
    except:
        return {}


# ── Main enrichment function ──────────────────────────────────────────────────

def enrich_token(symbol: str, issuer: str, currency: str,
                 price_history: list = None,
                 xpmarket_index: dict = None) -> dict:
    """
    Full Lite Haus-style analysis for one token.
    Called from scanner.py during scan cycle.

    Returns enriched intel dict that gets logged + used for scoring.
    """
    intel = {
        "symbol":  symbol,
        "issuer":  issuer,
        "ts":      time.time(),
    }

    # ── xpmarket data (holders, volume, liquidity, slippage depth) ────────────
    xpm = xpmarket_index or {}
    # Try to match by issuer (xpmarket uses AMM pool issuer, not token issuer)
    # We index during discovery — try direct match first, then by symbol
    xpm_data = xpm.get(issuer, {})
    if not xpm_data:
        # Secondary: try matching by symbol in xpm values
        for iss, d in xpm.items():
            if d.get("symbol_xpm","").upper() == symbol.upper():
                xpm_data = d
                break

    if xpm_data:
        intel["holders"]       = xpm_data.get("holders", 0)
        intel["volume_usd_24h"] = xpm_data.get("volume_usd", 0)
        intel["liquidity_usd"] = xpm_data.get("liquidity_usd", 0)
        intel["txns_total"]    = xpm_data.get("txns", 0)
        intel["swaps_24h"]     = xpm_data.get("swaps", 0)
        intel["plus2_depth"]   = xpm_data.get("plus2_depth", 0)
        intel["minus2_depth"]  = xpm_data.get("minus2_depth", 0)
        intel["trading_fee"]   = xpm_data.get("trading_fee", 0)
        intel["pool_level"]    = xpm_data.get("level", "")
        intel.update(compute_launch_age(xpm_data.get("created_at", "")))

    # ── Holder concentration (rate-limited — uses cache) ─────────────────────
    holder_data = fetch_holder_data(issuer)
    if holder_data:
        # Prefer xpmarket holders if xrpl.to not available, but use CLIO if fresher
        if not intel.get("holders") or holder_data.get("holder_count", 0) > 0:
            intel["holders"]         = holder_data.get("holder_count", intel.get("holders", 0))
        intel["top10_pct"]           = holder_data.get("top10_pct", 0)
        intel["top1_pct"]            = holder_data.get("top1_pct", 0)
        intel["top_holders"]         = holder_data.get("top_holders", [])
        intel["high_concentration"]  = holder_data.get("high_concentration", False)

    # ── Price analytics from our own history ──────────────────────────────────
    if price_history:
        pa = compute_price_analytics(price_history)
        intel.update(pa)

    return intel


def format_intel_log(intel: dict) -> str:
    """Format intel as a single-line Lite Haus-style log entry."""
    sym    = intel.get("symbol","?")
    hold   = intel.get("holders", "?")
    top10  = intel.get("top10_pct")
    top10s = f"{top10:.1f}%" if top10 is not None else "?"
    p5m    = intel.get("p5m")
    p1h    = intel.get("p1h")
    p24h   = intel.get("p24h")
    rsi    = intel.get("rsi")
    bp     = intel.get("buyer_pressure")
    vol    = intel.get("volume_usd_24h", 0)
    liq    = intel.get("liquidity_usd", 0)
    age    = intel.get("launch_age_hours")
    hcr    = "⚠️HCR" if intel.get("high_concentration") else ""
    fresh  = "🔥NEW" if intel.get("is_very_fresh") else ("✨FRESH" if intel.get("is_fresh") else "")

    p5ms  = f"{p5m:+.1f}%" if p5m is not None else "?"
    p1hs  = f"{p1h:+.1f}%" if p1h is not None else "?"
    p24hs = f"{p24h:+.1f}%" if p24h is not None else "?"
    rsis  = f"{rsi:.0f}" if rsi is not None else "?"
    bps   = f"{bp:.0f}%" if bp is not None else "?"
    ages  = f"{age:.0f}h" if age is not None else "?"

    return (f"{sym}: holders={hold} top10={top10s} {hcr}{fresh} | "
            f"5m={p5ms} 1h={p1hs} 24h={p24hs} | "
            f"RSI={rsis} BP={bps} | "
            f"vol=${vol:.0f} liq=${liq:.0f} | age={ages}")


def score_from_intel(intel: dict) -> int:
    """
    Compute additional score bonus from full token intel.
    Max +30 pts. Applied on top of base momentum score.
    """
    pts = 0

    # Holder sweet spot (PHX=104, ROOS=115)
    holders = intel.get("holders", 0)
    if 50 <= holders <= 150:    pts += 12
    elif 150 < holders <= 300:  pts += 6
    elif holders > 500:         pts -= 5

    # Top10 concentration
    top10 = intel.get("top10_pct", 0)
    if 0 < top10 <= 25:   pts += 8
    elif top10 <= 40:     pts += 4
    elif top10 > 60:      pts -= 10

    # RSI: oversold = buy signal, overbought = avoid
    rsi = intel.get("rsi")
    if rsi is not None:
        if rsi < 35:      pts += 8   # oversold = bounce potential
        elif rsi < 50:    pts += 3
        elif rsi > 75:    pts -= 5   # overbought = extended

    # Multi-TF momentum alignment
    p5m  = intel.get("p5m", 0) or 0
    p1h  = intel.get("p1h", 0) or 0
    p24h = intel.get("p24h", 0) or 0
    green = sum(1 for p in [p5m, p1h, p24h] if p > 0)
    if green == 3:    pts += 8
    elif green == 2:  pts += 4

    # Strong recent momentum
    if p5m > 5:    pts += 5
    if p1h > 10:   pts += 5

    # Pullback entry: 24h up but 1h/5m slight dip = best entry timing
    if p24h > 5 and p1h < 0 and p5m < 2:
        pts += 6

    # Buyer pressure
    bp = intel.get("buyer_pressure", 50) or 50
    if bp > 65:   pts += 5
    elif bp < 35: pts -= 3

    # Fresh launch bonus
    if intel.get("is_very_fresh"):  pts += 8
    elif intel.get("is_fresh"):     pts += 4

    # High concentration risk
    if intel.get("high_concentration"):  pts -= 8

    # Slippage depth (exit safety) — plus2_depth/minus2_depth in XRP
    plus_depth = intel.get("plus2_depth", 0) or 0
    if plus_depth > 5000:   pts += 3   # deep = easy to exit
    elif plus_depth < 500:  pts -= 3   # shallow = slippage risk

    return max(-20, min(pts, 30))


if __name__ == "__main__":
    # Quick test on current registry
    import sys
    sys.path.insert(0, str(BOT_DIR))
    from scanner import price_history as ph

    with open(STATE_DIR / "active_registry.json") as f:
        reg = json.load(f)
    tokens = reg.get("tokens", reg) if isinstance(reg, dict) else reg

    print("Fetching xpmarket index...")
    xpm = fetch_xpmarket_index()
    print(f"xpmarket: {len(xpm)} AMM pools indexed")
    print()

    for tok in tokens[:10]:
        sym    = tok["symbol"]
        issuer = tok["issuer"]
        cur    = tok.get("currency","")
        hist   = ph.get(f"{sym}:{issuer}", [])
        intel  = enrich_token(sym, issuer, cur, hist, xpm)
        bonus  = score_from_intel(intel)
        print(f"[+{bonus:+d}] {format_intel_log(intel)}")
        time.sleep(0.3)

======================================================================
# SNIPER — sniper.py
======================================================================

"""
sniper.py — Watch for new AMM pools and trustline surges.
Runs as a background WebSocket listener alongside bot.py.
Entry threshold: score >= 4 (out of 5 heuristics), size = XRP_SNIPER_BASE.
Dynamically adds tokens to TOKEN_SPECS.
"""

import json
import os
import time
import threading
import logging
from typing import Dict, List, Optional, Set
from config import STATE_DIR, WS_URL, XRP_SNIPER_BASE

os.makedirs(STATE_DIR, exist_ok=True)
SNIPER_LOG = os.path.join(STATE_DIR, "sniper.log")

logger = logging.getLogger("sniper")

# Dynamically discovered tokens
discovered_tokens: List[Dict] = []
_known_issuers: Set[str] = set()
_sniper_running = False


def _log(msg: str) -> None:
    ts   = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    with open(SNIPER_LOG, "a") as f:
        f.write(line)
    logger.info(msg)


def _score_new_token(tx_data: Dict) -> int:
    """
    Score a newly discovered token 0-5.
    Heuristics: has AMM, pool funded, creator active, not known scam pattern, recent.
    """
    score = 0
    # 1. AMMCreate transaction found
    score += 1

    # 2. Pool funded (has amounts)
    amm = tx_data.get("amm", {})
    if amm.get("amount") and amm.get("amount2"):
        score += 1

    # 3. LP token present
    if amm.get("lp_token"):
        score += 1

    # 4. Trading fee is reasonable (< 1%)
    fee = amm.get("trading_fee", 0)
    if fee < 10000:  # 10000 = 1%
        score += 1

    # 5. Recent creation (within last 10 minutes)
    created = tx_data.get("created_at", 0)
    if time.time() - created < 600:
        score += 1

    return score


def handle_amm_create(tx: Dict) -> Optional[Dict]:
    """
    Process an AMMCreate transaction.
    Returns token spec if worth sniping, else None.
    """
    meta   = tx.get("meta", {})
    tx_obj = tx.get("transaction", tx)

    asset  = tx_obj.get("Asset",  {})
    asset2 = tx_obj.get("Asset2", {})

    # We want XRP/TOKEN pairs
    token_asset = None
    if asset.get("currency") == "XRP" and asset2.get("currency"):
        token_asset = asset2
    elif asset2.get("currency") == "XRP" and asset.get("currency"):
        token_asset = asset

    if not token_asset:
        return None

    currency = token_asset.get("currency", "")
    issuer   = token_asset.get("issuer", "")

    if not currency or not issuer:
        return None

    if issuer in _known_issuers:
        return None

    _known_issuers.add(issuer)

    # Build AMM info from AffectedNodes
    amm_data = {"amount": 0, "amount2": {"value": "0"}, "lp_token": None}
    for node_wrapper in meta.get("AffectedNodes", []):
        for _, node in node_wrapper.items():
            nf = node.get("NewFields", {})
            if nf.get("Asset2", {}).get("issuer") == issuer:
                amm_data["amount"]  = nf.get("Amount", 0)
                amm_data["amount2"] = nf.get("Amount2", {"value": "0"})
                amm_data["lp_token"] = nf.get("LPTokenBalance")
                amm_data["trading_fee"] = nf.get("TradingFee", 500)

    token_spec = {
        "symbol":     currency if len(currency) <= 3 else bytes.fromhex(currency.ljust(40,'0')[:40]).decode('ascii', errors='ignore').rstrip('\x00').strip(),
        "issuer":     issuer,
        "currency":   currency,
        "created_at": time.time(),
        "amm":        amm_data,
        "source":     "sniper",
    }

    score = _score_new_token(token_spec)
    token_spec["sniper_score"] = score

    _log(f"New AMM: {currency}/{issuer} score={score}/5")

    if score >= 4:
        _log(f"SNIPER HIT: {currency}/{issuer} score={score}/5 size={XRP_SNIPER_BASE} XRP")
        discovered_tokens.append(token_spec)
        return token_spec

    return None


def sniper_loop(callback=None) -> None:
    """
    Main sniper loop. Subscribes to XRPL ledger stream and watches for AMMCreate.
    callback: optional function(token_spec) called when sniper hit found.
    """
    global _sniper_running
    _sniper_running = True

    _log("Sniper loop starting...")

    while _sniper_running:
        try:
            from xrpl.clients import WebsocketClient
            from xrpl.models.requests import Subscribe, StreamParameter

            with WebsocketClient(WS_URL) as ws:
                ws.send(Subscribe(streams=[StreamParameter.TRANSACTIONS]))
                _log("Subscribed to transaction stream")

                for msg in ws:
                    if not _sniper_running:
                        break

                    if not isinstance(msg, dict):
                        continue

                    tx_type = (msg.get("transaction", {}).get("TransactionType") or
                               msg.get("tx_json", {}).get("TransactionType") or "")

                    if tx_type == "AMMCreate":
                        token_spec = handle_amm_create(msg)
                        if token_spec and callback:
                            callback(token_spec)

        except Exception as e:
            _log(f"Sniper connection error: {e} — reconnecting in 5s")
            if _sniper_running:
                time.sleep(5)


def start_sniper_thread(callback=None) -> threading.Thread:
    """Start sniper in background thread."""
    t = threading.Thread(target=sniper_loop, args=(callback,), daemon=True)
    t.start()
    _log("Sniper thread started")
    return t


def stop_sniper() -> None:
    global _sniper_running
    _sniper_running = False
    _log("Sniper stopping")


def get_discovered_tokens() -> List[Dict]:
    return discovered_tokens.copy()


if __name__ == "__main__":
    def on_hit(spec):
        print(f"SNIPER HIT: {spec['symbol']} score={spec['sniper_score']}")

    print("Starting sniper (Ctrl+C to stop)...")
    try:
        sniper_loop(callback=on_hit)
    except KeyboardInterrupt:
        print("Sniper stopped")

======================================================================
# MAIN_BOT — bot.py
======================================================================

"""
bot.py — Main trading bot loop.
Start: python3 bot.py
Stop:  kill the process (or Ctrl+C)

Loop every POLL_INTERVAL_SEC:
  1. scanner → candidates
  2. regime check → skip if danger
  3. safety gate per candidate
  4. chart_intelligence + scoring
  5. route_engine check
  6. execution if score passes
  7. dynamic_exit checks on all positions
  8. reconcile every 30 min
  9. improve every 6 hours
"""

import os
import sys
import json
import time
import signal
import logging
import traceback
from typing import Dict, List, Optional

# ── Setup ────────────────────────────────────────────────────────────────────
os.makedirs(os.path.join(os.path.dirname(__file__), "state"), exist_ok=True)

# Configure logging BEFORE any imports that use logging
LOG_FILE = os.path.join(os.path.dirname(__file__), "state", "bot.log")
_root_logger = logging.getLogger()
if not _root_logger.handlers:
    logging.basicConfig(
        level   = logging.INFO,
        format  = "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers= [
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(sys.stdout),
        ]
    )
else:
    logging.root.setLevel(logging.INFO)
logger = logging.getLogger("bot")
logger.propagate = True  # use root handlers only — prevent duplicate handler attachment

# ── Imports ───────────────────────────────────────────────────────────────────
from config import (POLL_INTERVAL_SEC, MAX_POSITIONS, SCORE_TRADEABLE,
                    SCORE_SMALL, SCORE_ELITE, XRP_PER_TRADE_BASE, XRP_SNIPER_BASE, XRP_ELITE_BASE, XRP_SMALL_BASE,
                    XRP_MICRO_BASE, TVL_MICRO_CAP_XRP,
                    CONTINUATION_MIN_SCORE, ORPHAN_MIN_SCORE,
                    PREFERRED_CHART_STATES,
                    SCALP_MIN_SCORE, SCALP_MAX_SCORE, SCALP_SIZE_XRP,
                    SCALP_TP_PCT, SCALP_STOP_PCT, SCALP_MAX_HOLD_MIN,
                    TRADING_HOURS_UTC, COOLDOWN_AFTER_STOP_MIN,
                    PROVEN_TOKEN_MIN_WINS, PROVEN_TOKEN_RELOAD_XRP, PROVEN_TOKEN_SCORE_GATE,
                    TVL_SCALP_MAX, TVL_HOLD_MIN, TVL_HOLD_MAX, TVL_VELOCITY_RUNNER,
                    STATE_DIR, BOT_WALLET_ADDRESS, SKIP_REENTRY_SYMBOLS)

# ── Dashboard API integration (HTTP calls to separate process) ───────────────
try:
    import urllib.request
    _DASH_URL = "http://localhost:5000"
    def dash_log(msg):
        logging.info(msg)
    def update_stats(**kw):
        try:
            data = json.dumps(kw).encode()
            req = urllib.request.Request(_DASH_URL + "/update_stats", data=data, headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=2)
        except: pass
    def update_position(token, entry, current, size_xrp=0):
        try:
            data = json.dumps({"token": token, "entry": entry, "current": current, "size_xrp": size_xrp}).encode()
            req = urllib.request.Request(_DASH_URL + "/update_position", data=data, headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=2)
        except: pass
    def remove_position(token):
        try:
            data = json.dumps({"token": token}).encode()
            req = urllib.request.Request(_DASH_URL + "/remove_position", data=data, headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=2)
        except: pass
    def set_running(running):
        try:
            endpoint = "/start" if running else "/stop"
            req = urllib.request.Request(_DASH_URL + endpoint, data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=2)
        except: pass
    _DASH_AVAILABLE = True
except Exception as _dash_err:
    _DASH_AVAILABLE = False
    def dash_log(msg): logging.info(msg)
    def update_stats(**kw): pass
    def update_position(*a, **kw): pass
    def remove_position(*a): pass
    def set_running(*a): pass

import state as state_mod
import scanner
import safety
import breakout as breakout_mod
import chart_intelligence
import pre_move_detector
import scoring as scoring_mod
import regime as regime_mod
import route_engine
import execution
import execution_core
from execution_core import execute_trade
import dynamic_exit
import smart_money
import learn as learn_mod
import reconcile as reconcile_mod
import wallet_hygiene
import improve as improve_mod
import report as report_mod
import sniper as sniper_mod
import brain

# ── New Modules (Audit Improvements) ───────────────────────────────────────────
import new_wallet_discovery as wallet_discovery_mod
import wallet_cluster as cluster_mod
import alpha_recycler as recycler_mod
import dynamic_tp as dynamic_tp_mod
import classifier as classifier_mod

# ── Safety Controller & Shadow Lane ──────────────────────────────────────────
import safety_controller as safety_ctrl_mod
_safety_ctrl = safety_ctrl_mod.get_safety_controller()

try:
    import shadow_ml as shadow_ml_mod
    _shadow_ml = shadow_ml_mod.get_shadow_ml()
    _SHADOW_ML_AVAILABLE = True
except Exception as _shadow_ml_err:
    _SHADOW_ML_AVAILABLE = False
    logger.debug(f"[shadow_ml] import failed (non-fatal): {_shadow_ml_err}")

# ── Improvement Loop ──────────────────────────────────────────────────────────
try:
    import improve_loop as improve_loop_mod
    _IMPROVE_LOOP_AVAILABLE = True
except Exception as _il_err:
    _IMPROVE_LOOP_AVAILABLE = False
    logger.debug(f"[improve_loop] import failed (non-fatal): {_il_err}")

# ── Confidence-Based Sizing ───────────────────────────────────────────────────
try:
    from sizing import calculate_position_size as _calc_position_size
    _SIZING_AVAILABLE = True
except Exception as _sz_err:
    _SIZING_AVAILABLE = False
    logger.debug(f"[sizing] import failed (non-fatal): {_sz_err}")

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "relay"))
import bridge as relay_bridge

# ── ML Pipeline ───────────────────────────────────────────────────────────────
try:
    import ml_features as ml_features_mod
    import ml_model as ml_model_mod
    _ML_AVAILABLE = True
except Exception as _ml_import_err:
    _ML_AVAILABLE = False
    logger.debug(f"[ml] pipeline import failed (non-fatal): {_ml_import_err}")
relay_bridge.set_url("https://together-lawyer-arrivals-bargains.trycloudflare.com")

STATUS_FILE = os.path.join(STATE_DIR, "status.json")

# ── Globals ────────────────────────────────────────────────────────────────────
_running    = True
_bot_state  = None
_cycle_count = 0
_last_report_day = -1

# ── Signal Handling ────────────────────────────────────────────────────────────
def _handle_signal(signum, frame):
    global _running
    logger.info(f"Signal {signum} received — shutting down...")
    _running = False

signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT,  _handle_signal)


def _write_status(cycle: int, positions: int, last_error: str = "") -> None:
    status = {
        "last_cycle":   time.time(),
        "cycle_count":  cycle,
        "open_positions": positions,
        "last_error":   last_error,
        "pid":          os.getpid(),
    }
    with open(STATUS_FILE, "w") as f:
        json.dump(status, f, indent=2)


def _get_price_history(token_key: str) -> List[float]:
    """Get price list from breakout data."""
    try:
        import breakout as bm
        data = bm._load_data()
        readings = data.get(token_key, [])
        return [r["price"] for r in readings if r.get("price", 0) > 0]
    except Exception:
        return []


def _get_proven_tokens(bot_state: Dict) -> dict:
    """
    Returns dict of {symbol: win_count} for tokens with PROVEN_TOKEN_MIN_WINS+ TP exits.
    These get priority reload with no cooldown and bigger sizing.
    """
    history = bot_state.get("trade_history", [])
    wins = {}
    for t in history:
        sym = t.get("symbol", "")
        if "tp" in t.get("exit_reason", ""):
            wins[sym] = wins.get(sym, 0) + 1
    return {sym: cnt for sym, cnt in wins.items() if cnt >= PROVEN_TOKEN_MIN_WINS}


def _classify_hold_or_scalp(tvl: float, tvl_change_pct: float, score: int) -> str:
    """
    Determine trade mode based on TVL tier and momentum.
    Returns: 'hold', 'scalp', or 'skip'
    DATA: micro TVL (<1K) = fast launches, quick 10-15% moves, then dump.
          early stage (1K-10K) = still growing, room for 300%+.
          large (>10K) = discovered, no explosive upside.
    """
    if tvl > TVL_HOLD_MAX and tvl_change_pct < TVL_VELOCITY_RUNNER:
        return "skip"   # Established pool, not growing fast — stale risk
    if tvl < TVL_SCALP_MAX:
        return "scalp"  # Micro TVL — fast scalp, too risky to hold
    if TVL_HOLD_MIN <= tvl <= TVL_HOLD_MAX:
        return "hold"   # Sweet spot — early stage, hold for big move
    if tvl_change_pct >= TVL_VELOCITY_RUNNER:
        return "hold"   # Rapid TVL growth overrides — runner in progress
    return "scalp"


def _token_key(token: Dict) -> str:
    return f"{token['symbol']}:{token['issuer']}"


def run_cycle(bot_state: Dict) -> Dict:
    """
    One full bot cycle. Returns updated bot_state.
    """
    global _cycle_count
    _cycle_count += 1
    now = time.time()

    logger.info(f"─── Cycle {_cycle_count} ───")

    # ── Safety Controller check (top of every cycle) ──────────────────────────
    _paused_mode = False  # default: not paused
    _safety_status = _safety_ctrl.check_cycle(bot_state)
    if _safety_status == "stopped":
        logger.warning("🛑 EMERGENCY STOP active — halting cycle")
        return bot_state
    elif _safety_status == "paused":
        logger.warning("⏸️ Bot paused — managing exits only, no new entries")
        # Don't return — fall through to exit management below, skip entry logic
        # _paused_mode flag used below to skip entry section
    _paused_mode = (_safety_status == "paused")

    # ── Wallet balance (fetched ONCE per cycle — used for Kelly sizing) ───────
    try:
        import requests as _req_wb
        _r_wb = _req_wb.post("https://rpc.xrplclaw.com",
            json={"method":"account_info","params":[{"account":BOT_WALLET_ADDRESS,"ledger_index":"current"}]},
            timeout=6)
        _d_wb = _r_wb.json().get("result",{}).get("account_data",{})
        _bal_wb  = int(_d_wb.get("Balance",0)) / 1e6
        _owner_wb = _d_wb.get("OwnerCount", 0)
        cycle_wallet_xrp = max(0, _bal_wb - 1 - (_owner_wb * 0.2))
        bot_state["_cycle_wallet_xrp"] = cycle_wallet_xrp
        logger.debug(f"Wallet: {cycle_wallet_xrp:.2f} XRP spendable")
    except Exception as _wb_e:
        cycle_wallet_xrp = 0.0
        logger.debug(f"Wallet balance fetch failed: {_wb_e}")

    # ── 0. New token discovery (every 4th cycle ~4min) ───────────────────────
    if _cycle_count % 4 == 1:
        try:
            import new_amm_watcher as _naw
            new_amms = _naw.scan_new_amms()
            if new_amms:
                logger.info(f"🆕 {len(new_amms)} new AMM pools detected: {[t['symbol'] for t in new_amms]}")
        except Exception as _e:
            logger.debug(f"New AMM scan error: {_e}")
        try:
            import hot_tokens as _ht
            hot = _ht.scan_hot_tokens()
            if hot:
                _ht.merge_into_registry(hot)
        except Exception as _e:
            logger.debug(f"Hot token scan error: {_e}")

    # ── 0c. TrustSet velocity scan (EVERY cycle) — PHX-type launch detector
    # Changed from every 4th cycle → every cycle for fastest possible burst detection
    if _cycle_count % 1 == 0:
        try:
            import trustset_watcher as _tsw
            _active_reg = {}
            try:
                import json as _json
                _active_reg = _json.load(open(os.path.join(os.path.dirname(__file__), "state", "active_registry.json")))
            except:
                pass
            ts_signals = _tsw.scan(_active_reg)
            for sig in ts_signals:
                logger.info(
                    f"🔥 TRUSTSET LAUNCH {sig['symbol']}: {sig['trustsets_1h']}/hr "
                    f"| total={sig['trustsets_total']} holders | TVL={sig['tvl_xrp']:.0f} XRP "
                    f"| age={sig['age_h']:.1f}h | score={sig['score']} → QUEUE FOR ENTRY"
                )
                # Inject into candidates for this cycle with override score
                candidate = {
                    "symbol": sig["symbol"],
                    "issuer": sig["issuer"],
                    "currency": sig["currency"],
                    "tvl_xrp": sig["tvl_xrp"],
                    "price": sig["price"],
                    "score": max(sig["score"], 55),  # floor at entry threshold
                    "chart_state": "pre_breakout",   # treat as pre-breakout
                    "signal_type": "trustset_velocity",
                    "key": sig["key"],
                }
                # Write to a trustset_signals file for next cycle pickup
                import json as _json2
                _ts_path = os.path.join(os.path.dirname(__file__), "state", "trustset_signals.json")
                try:
                    _existing = _json2.load(open(_ts_path))
                except:
                    _existing = []
                _existing = [s for s in _existing if s.get("key") != sig["key"]]  # dedup
                _existing.append(candidate)
                _json2.dump(_existing, open(_ts_path, "w"), indent=2)
        except Exception as _e:
            logger.debug(f"TrustSet watcher error: {_e}")

    # ── 0b. Smart wallet tracker (every 6th cycle ~6min) ─────────────────────
    if _cycle_count % 6 == 2:
        try:
            import smart_wallet_tracker as _swt
            sw_alerts = _swt.scan_smart_wallets()
            for alert in sw_alerts:
                logger.info(
                    f"🚨 SMART WALLET: {alert['wallet']} bought "
                    f"{alert['symbol']} → +{alert['score_bonus']} score bonus injected"
                )
        except Exception as _e:
            logger.debug(f"Smart wallet scan error: {_e}")

    # ── 0d. Alpha Recycler scan (every 5th cycle ~5min) — Audit #3 ────────────
    if _cycle_count % 5 == 3:
        try:
            recycle_signals = recycler_mod.scan_alpha_recycling(bot_state)
            for sig in recycle_signals:
                logger.info(
                    f"🔁 ALPHA RECYCLE: {sig['wallet'][:10]}... sold "
                    f"{sig['sold_token']} → just bought {sig['bought_token']}"
                )
        except Exception as _e:
            logger.debug(f"Alpha recycler scan error: {_e}")

    # ── 0g. Improvement loop (every 50th cycle) ────────────────────────────────
    if _cycle_count % 50 == 0 and _IMPROVE_LOOP_AVAILABLE:
        try:
            il_result = improve_loop_mod.ImprovementLoop().run_loop()
            critical = il_result.get("critical_tweaks", 0)
            high = il_result.get("high_tweaks", 0)
            logger.info(f"[improve_loop] Analysis done: {critical} critical, {high} high priority tweaks → state/improvement_log.json")
        except Exception as _ile:
            logger.debug(f"[improve_loop] error (non-fatal): {_ile}")

    # ── 0f. ML retrain check (every 20th cycle) ────────────────────────────────
    if _cycle_count % 20 == 0:
        if _ML_AVAILABLE:
            try:
                ml_model_mod.maybe_retrain()
            except Exception as _mle:
                logger.debug(f"[ml] retrain check: {_mle}")

    # ── 0e. Wallet Discovery refresh (every 20th cycle ~20min) — Audit #1 ─────
    if _cycle_count % 20 == 4:
        try:
            disc_result = wallet_discovery_mod.discover_smart_wallets(force_rescan=False)
            new_tracked = len(disc_result.get("tracked", []))
            logger.debug(f"Wallet discovery refresh: {new_tracked} tracked wallets")
        except Exception as _e:
            logger.debug(f"Wallet discovery refresh error: {_e}")

    # ── 1. Scanner ────────────────────────────────────────────────────────────
    try:
        scan_results = scanner.scan()
        candidates   = scanner.get_candidates(scan_results)
        logger.info(f"Scanner: {len(candidates)} candidates | "
                    f"fresh={len(scan_results['fresh_momentum'])} "
                    f"sustained={len(scan_results['sustained_momentum'])}")
        # Push top candidates to relay
        for c in candidates[:3]:
            relay_bridge.push_signal(symbol=c.get("symbol",""), score=c.get("score",0), chart=c.get("chart_state",""), tvl=c.get("tvl",0), pct=c.get("pct_change",0), regime=bot_state.get("regime","neutral"))

        # ── Shadow ML: evaluate ALL raw candidates (independent scoring) ────
        if _SHADOW_ML_AVAILABLE:
            try:
                logger.info(f"[shadow_ml] Evaluating {len(candidates)} candidates...")
                # Build market_data dict from candidates
                _market_data = {}
                for _c in candidates:
                    _sym = _c.get("symbol", "")
                    _price = _c.get("price", 0)
                    if _sym and _price > 0:
                        _market_data[_sym] = {"price": _price}
                _entered = _shadow_ml.run_cycle(candidates, _market_data)
                logger.info(f"👻 Shadow ML: evaluated {len(candidates)}, entered {_entered}")
            except Exception as _sle:
                logger.exception(f"[shadow_ml] cycle error: {_sle}")

        # ── Realtime CLOB entry trigger (fast movers) ────────────────────────
        _rt_trigger_file = os.path.join(STATE_DIR, "realtime_entry_trigger.json")
        if os.path.exists(_rt_trigger_file):
            try:
                with open(_rt_trigger_file) as _rtf:
                    _rt_trigger = json.load(_rtf)
                _rt_age = time.time() - _rt_trigger.get("ts", 0)
                if _rt_age < 120:  # Only use triggers < 2 min old
                    _rt_key = f"{_rt_trigger.get('currency','')}:{_rt_trigger.get('issuer','')}"
                    if not any(c.get("key") == _rt_key for c in candidates):
                        _rt_cand = {
                            "symbol": _rt_trigger.get("symbol", ""),
                            "currency": _rt_trigger.get("currency", ""),
                            "issuer": _rt_trigger.get("issuer", ""),
                            "key": _rt_key,
                            "tvl": 500,
                            "price": _rt_trigger.get("price", 0),
                            "score": 0,
                            "_clob_launch": True,
                            "_burst_mode": True,
                            "burst_count": 30,
                            "clob_vol_5min": _rt_trigger.get("vol_5min_xrp", 0),
                            "amm": {"amount": str(int(500 * 1e6)), "amount2": {"currency": _rt_trigger.get("currency",""), "issuer": _rt_trigger.get("issuer",""), "value": "1000000"}, "trading_fee": 1000, "account": _rt_trigger.get("issuer","")},
                        }
                        candidates.append(_rt_cand)
                        dash_log(f"⚡ REALTIME CLOB: {_rt_trigger.get('symbol','')} injected")
                        logger.info(f"⚡ REALTIME CLOB: {_rt_trigger.get('symbol','')} @ {_rt_trigger.get('price',0):.8f} injected")
                os.remove(_rt_trigger_file)
            except Exception as _rte:
                logger.debug(f"Realtime trigger error: {_rte}")
    except Exception as e:
        logger.error(f"Scanner error: {e}")
        candidates = []
        scan_results = {}

    # ── 1b. Pre-Move Detector — catch accumulation phase before explosive move ─
    # Scans token TVL/MC window ($400-$5k), LP supply, TS rate.
    # Injects pre_accumulation entries at 5 XRP size (fast, small, pre-explosion).
    try:
        _pm_result = pre_move_detector.inject_to_bot()
        _pm_file = os.path.join(os.path.dirname(__file__), "state", "pre_move_signals.json")
        if os.path.exists(_pm_file):
            with open(_pm_file) as _pmf:
                _pm_data = json.load(_pmf)
            _pm_age = time.time() - _pm_data.get("ts", 0)
            if _pm_age < 300:  # only use signals < 5 min old
                for _sig in _pm_data.get("signals", []):
                    _pm_key = f"{_sig.get('currency','')}:{_sig.get('addr','')}"
                    if _pm_key in bot_state.get("positions", {}):
                        continue
                    if any(c.get("key") == _pm_key for c in candidates):
                        continue
                    _pm_cand = {
                        "symbol":    _sig.get("symbol", ""),
                        "currency":  _sig.get("currency", ""),
                        "issuer":    _sig.get("addr", ""),
                        "key":       _pm_key,
                        "tvl":       _sig.get("tvl", 1000),
                        "price":     _sig.get("price", 0),
                        "score":     70,  # moderate score — let classifier decide routing
                        "burst_count": 5,  # light burst = early stage, not mid-move
                        "_pre_move": True,
                        "_pre_move_signal": _sig.get("signal", "pre_accumulation"),
                        "_pre_move_conf": _sig.get("confidence", 80),
                        "_pre_move_reason": _sig.get("reason", ""),
                        "_pre_move_size": _sig.get("size_xrp", 5.0),
                    }
                    candidates.append(_pm_cand)
                    logger.info(f"📡 PRE-MOVE INJECT: {_sig.get('symbol','')} | {_sig.get('reason','')}")
        else:
            logger.debug("Pre-move scan: no signals ready")
    except Exception as _e:
        logger.debug(f"Pre-move detector error: {_e}")

    # ── 1c. Inject TrustSet velocity signals (PHX-type launches) ─────────────
    try:
        import json as _json3
        _ts_path = os.path.join(os.path.dirname(__file__), "state", "trustset_signals.json")
        if os.path.exists(_ts_path):
            _ts_sigs = _json3.load(open(_ts_path))
            _now2 = time.time()
            fresh_sigs = [s for s in _ts_sigs if _now2 - s.get("ts", 0) < 3600]  # 1h TTL
            for sig in fresh_sigs:
                # Don't add if already in candidates or already in a position
                if not any(c.get("key") == sig.get("key") for c in candidates):
                    if sig.get("key") not in bot_state.get("positions", {}):
                        candidates.append(sig)
                        logger.info(f"🔥 TrustSet signal injected: {sig['symbol']} score={sig['score']}")
    except Exception as _e:
        logger.debug(f"TrustSet inject error: {_e}")

    # ── 1c. Inject realtime velocity alerts (burst tokens — PRSV/dkledger style) ──
    # realtime_watcher.py writes velocity_alerts to realtime_signals.json.
    # These are tokens with 10+ TrustSets in 5min — community forming fast.
    # Tradeable regardless of chart_state — momentum IS the signal.
    try:
        import json as _json4
        _rt_path = os.path.join(os.path.dirname(__file__), "state", "realtime_signals.json")
        if os.path.exists(_rt_path):
            _rt_sigs = _json4.load(open(_rt_path))
            _now3 = time.time()
            for _key, _alert in _rt_sigs.get("velocity_alerts", {}).items():
                _sym  = _alert.get("symbol", "")
                _cur  = _alert.get("currency", "")
                _iss  = _alert.get("issuer", "")
                _bc   = _alert.get("burst_count", 0)
                _age  = _now3 - _alert.get("updated_at", 0)
                if _age > 900:  # stale after 15 min
                    continue
                if not _sym or not _cur or not _iss:
                    continue
                _cand_key = f"{_cur}:{_iss}"
                if _cand_key in bot_state.get("positions", {}):
                    continue
                if any(c.get("key") == _cand_key for c in candidates):
                    # Already in candidates — just mark as burst
                    for c in candidates:
                        if c.get("key") == _cand_key:
                            c["burst_count"] = _bc
                            c["_burst_mode"] = True
                    continue
                # Inject as burst candidate — will bypass chart_state gate below
                _burst_cand = {
                    "symbol":      _sym,
                    "currency":    _cur,
                    "issuer":      _iss,
                    "key":         _cand_key,
                    "tvl":         _alert.get("xrp_tvl", 500),
                    "score":       0,  # will be scored below
                    "burst_count": _bc,
                    "_burst_mode": True,
                }
                candidates.append(_burst_cand)
                logger.info(f"⚡ Burst candidate injected: {_sym} — {_bc} TrustSets/5min")

            # ── CLOB launch signals (THE BRIZZLY FIX) ────────────────────────
            # Tokens moving on the orderbook (not AMM) — brizzly/PROPHET/PRSV pattern
            # Signal: 60+ TrustSets/10min AND 25+ XRP bought/5min on CLOB
            for _key, _alert in _rt_sigs.get("clob_launches", {}).items():
                if not _alert.get("entry_trigger"):
                    continue
                _sym  = _alert.get("symbol", "")
                _cur  = _alert.get("currency", "")
                _iss  = _alert.get("issuer", "")
                _vol  = _alert.get("vol_5min_xrp", 0)
                _bc   = _alert.get("ts_burst", 0)
                _cprice = _alert.get("clob_price", 0)
                _age  = _now3 - _alert.get("updated_at", 0)
                if _age > 600:  # 10 min TTL — CLOB launches are fast
                    continue
                if not _sym or not _cur or not _iss:
                    continue
                _cand_key = f"{_cur}:{_iss}"
                if _cand_key in bot_state.get("positions", {}):
                    continue
                if any(c.get("key") == _cand_key for c in candidates):
                    for c in candidates:
                        if c.get("key") == _cand_key:
                            c["_clob_launch"] = True
                            c["clob_vol_5min"] = _vol
                            c["clob_price"]   = _cprice
                    continue
                _clob_cand = {
                    "symbol":        _sym,
                    "currency":      _cur,
                    "issuer":        _iss,
                    "key":           _cand_key,
                    "tvl":           500,
                    "price":         _cprice if _cprice > 0 else None,
                    "score":         0,
                    "_clob_launch":  True,
                    "_burst_mode":   True,  # also treat as burst — bypasses chart/price gates
                    "burst_count":   _bc,
                    "clob_vol_5min": _vol,
                    # Synthesize AMM stub so safety check doesn't crash on missing AMM
                    "amm": {"amount": str(int(500 * 1e6)), "amount2": {"currency": _cur, "issuer": _iss, "value": "1000000"}, "trading_fee": 1000, "account": _iss},
                }
                candidates.append(_clob_cand)
                stype = _alert.get("signal_type", "clob_launch")
                logger.info(f"🚀 CLOB LAUNCH injected: {_sym} — {_vol:.0f} XRP/5min CLOB vol | ts_burst={_bc} | type={stype}")

            # Also inject momentum_alerts (buy clusters from OfferCreate stream)
            for _key, _alert in _rt_sigs.get("momentum_alerts", {}).items():
                _sym  = _alert.get("symbol", "")
                _cur  = _alert.get("currency", "")
                _iss  = _alert.get("issuer", "")
                _oc   = _alert.get("offer_count", 0)
                _vol  = _alert.get("total_xrp", 0)
                _age  = _now3 - _alert.get("updated_at", 0)
                if _age > 600:  # stale after 10 min — buy clusters fade fast
                    continue
                if not _sym or not _cur or not _iss:
                    continue
                _cand_key = f"{_cur}:{_iss}"
                if _cand_key in bot_state.get("positions", {}):
                    continue
                if any(c.get("key") == _cand_key for c in candidates):
                    # Already tracked — flag as momentum
                    for c in candidates:
                        if c.get("key") == _cand_key:
                            c["_momentum_mode"] = True
                            c["offer_count"] = _oc
                    continue
                # Inject as momentum candidate
                _mom_cand = {
                    "symbol":        _sym,
                    "currency":      _cur,
                    "issuer":        _iss,
                    "key":           _cand_key,
                    "tvl":           500,
                    "score":         0,
                    "_momentum_mode": True,
                    "offer_count":   _oc,
                    "offer_vol_xrp": _vol,
                }
                candidates.append(_mom_cand)
                logger.info(f"📈 Momentum candidate injected: {_sym} — {_oc} buys/{_alert.get('window_sec',120)}s | {_vol:.1f} XRP vol")

    except Exception as _e:
        logger.debug(f"Realtime signals inject error: {_e}")

    # ── Shadow lane moved to after scoring (inside entry loop) ────────────────

    # ── 2. Regime ─────────────────────────────────────────────────────────────
    candidates_above_70 = 0
    try:
        # Quick pre-score to count above-70 candidates
        for c in candidates[:10]:
            if c.get("score", 0) * 100 >= 70:
                candidates_above_70 += 1
        regime = regime_mod.update_and_get_regime(bot_state, candidates_above_70)
        adj    = regime_mod.get_regime_adjustments(regime)
        bot_state["regime"] = regime
        logger.info(f"Regime: {regime}")
    except Exception as e:
        logger.error(f"Regime error: {e}")
        regime = "neutral"
        adj    = regime_mod.get_regime_adjustments(regime)

    if regime == "danger":
        # DANGER: slight filter only — don't wall off entries entirely
        # Data shows high scores (70+) = 0% WR anyway, so filtering to 72+ is useless
        # Just log the state and let normal threshold logic handle it with half sizing
        logger.info(f"Regime=DANGER — half-sizing, +8 threshold, still trading")

    # Load score adjustments from improve.py
    score_adj = bot_state.get("score_overrides", {})
    threshold_adj    = score_adj.get("score_threshold_adj", 0)
    size_mult_global = score_adj.get("size_multiplier", 1.0)
    # FIX: Base is SCORE_TRADEABLE (45) — GodMode classifier adds quality layer on top
    # so we can afford lower composite threshold without capturing low-quality entries.
    # Regime adjustment still applies (danger = +5, cold = +2).
    effective_threshold = SCORE_TRADEABLE + threshold_adj + adj.get("score_threshold", 0)

    # ── 3-6. Evaluate candidates and enter positions ───────────────────────────
    # Trading hours gate — DATA: 04-07 UTC = 6-17% WR (dead). Skip new entries.
    _current_hour = now.hour if hasattr(now, 'hour') else __import__('datetime').datetime.utcnow().hour
    _in_trading_hours = _current_hour in TRADING_HOURS_UTC
    if not _in_trading_hours:
        logger.info(f"⏰ Outside trading hours ({_current_hour:02d}:xx UTC) — skipping new entries, managing exits only")

    open_positions = bot_state.get("positions", {})
    # Track symbols entered THIS cycle to prevent duplicate entries within same cycle
    _entered_this_cycle: set = set()
    # Build proven tokens map — bypass cooldown, bigger sizing
    _proven_tokens = _get_proven_tokens(bot_state)
    if _proven_tokens:
        logger.info(f"🏆 Proven tokens: {_proven_tokens}")
    # Load stop cooldown list — restore symbols still in cooldown from previous runs
    _cooldown_file = os.path.join(STATE_DIR, "stop_cooldown.json")
    try:
        _cooldowns = json.load(open(_cooldown_file))
    except:
        _cooldowns = {}
    # Clean expired cooldowns AND repopulate SKIP_REENTRY_SYMBOLS for surviving ones
    _now_ts = time.time()
    _valid = {}
    for _sym, _ts in _cooldowns.items():
        if _now_ts - _ts < COOLDOWN_AFTER_STOP_MIN * 60:
            _valid[_sym] = _ts
            SKIP_REENTRY_SYMBOLS.add(_sym)
    _cooldowns = _valid
    max_pos = min(MAX_POSITIONS, adj.get("max_positions", MAX_POSITIONS))

    if len(open_positions) < max_pos and _in_trading_hours and not _paused_mode:
        for candidate in candidates:
            if len(bot_state.get("positions", {})) >= max_pos:
                break

            symbol = candidate["symbol"]
            issuer = candidate["issuer"]
            currency = candidate.get("currency", "")
            key    = _token_key(candidate)
            price  = candidate.get("price")
            tvl    = candidate.get("tvl_xrp", 0)
            amm    = candidate.get("amm")

            if key in open_positions or symbol in _entered_this_cycle:
                logger.debug(f"Already in {symbol} — skip")
                continue

            # For CLOB-launch tokens, AMM may not exist yet — use CLOB price as fallback
            if not price and candidate.get("clob_price"):
                price = candidate["clob_price"]
                candidate["price"] = price
                logger.debug(f"CLOB price fallback for {symbol}: {price:.8f}")
            if not amm and candidate.get("_clob_launch"):
                # Synthesize minimal AMM stub so safety/route don't crash
                amm = {"amount": str(int(500 * 1e6)), "amount2": {"currency": currency, "issuer": issuer, "value": "1000000"}, "trading_fee": 1000, "account": issuer}
            if not amm or not price:
                continue

            # ── 3. Safety gate ────────────────────────────────────────────────
            try:
                safety_result = safety.run_safety(candidate, amm)
                if not safety_result.get("safe"):
                    logger.info(f"SKIP {symbol}: safety fail — {safety_result.get('tvl_reason','?')}")
                    continue
                if safety_result.get("warnings"):
                    logger.info(f"WARN {symbol}: {safety_result['warnings']}")
            except Exception as e:
                logger.warning(f"Safety error {symbol}: {e}")
                continue

            # ── 4. Chart intelligence + scoring ───────────────────────────────
            try:
                # Update breakout history
                breakout_mod.update_price(key, price)
                bq_result = breakout_mod.compute_breakout_quality(key)
                bq        = bq_result.get("breakout_quality", 0)

                # ── Early BQ gate — saves 4-6 RPC calls per reject ───────────
                # Burst and TVL-runner candidates bypass (their signal IS the BQ proxy)
                if bq < 40 and not candidate.get("_burst_mode") and not candidate.get("_momentum_mode") and not candidate.get("_tvl_runner"):
                    logger.debug(f"SKIP {symbol}: bq={bq} < 40 (weak breakout quality)")
                    continue

                prices_hist = _get_price_history(key)
                tvl_hist    = [tvl]  # simplified; ideally track over time

                chart_result = chart_intelligence.classify(key, prices_hist, tvl_hist, bq)
                chart_state  = chart_result["state"]
                chart_conf   = chart_result["confidence"]

                if not chart_result["tradeable"]:
                    logger.debug(f"SKIP {symbol}: chart_state={chart_state} not tradeable")
                    continue

                # Smart money check
                sm_result = smart_money.check_smart_money_signal(symbol, issuer)
                sm_boost  = sm_result.get("boost", 0)

                # Pre-move override: use detector's small sizing for early entries
                # Fast entry = 3-5 XRP, not full sizing — we enter BEFORE the move
                _pre_size = candidate.get("_pre_move_size", 0)
                if _pre_size > 0:
                    xrp_size = _pre_size
                    logger.info(f"  📡 {symbol}: pre-move size override → {_pre_size:.1f} XRP ({candidate.get('_pre_move_signal','?')})")
                else:
                    xrp_size = XRP_PER_TRADE_BASE * size_mult_global * adj.get("size_mult", 1.0)

                # Route check
                route = route_engine.evaluate_route(symbol, issuer, amm, xrp_size)
                # brain.select_best_route() integration point — use when route_engine exposes multi-route API
                _selected = brain.select_best_route(["primary"]) if route else None
                brain.update_execution_stats({"route": "primary", "slippage": route.get("best_slippage", 0)})
                if not route.get("trade_ok"):
                    logger.info(f"SKIP {symbol}: route fail — {route.get('reject_reason')}")
                    continue

                # Winner DNA analysis (PHX/ROOS/SPY pattern matching)
                # Only run for thin pools (<20K XRP) — where 5x moves happen
                dna_bonus = 0
                dna_flags = []
                if tvl < 20_000:
                    try:
                        import winner_dna as _wdna
                        dna = _wdna.get_winner_dna_score(symbol, issuer,
                              candidate.get("currency", ""), tvl)
                        dna_bonus = dna.get("bonus", 0)
                        dna_flags = dna.get("flags", [])
                        if dna_bonus > 0:
                            logger.info(f"  {symbol}: DNA bonus +{dna_bonus} flags={dna_flags}")
                    except Exception as _e:
                        logger.debug(f"DNA score error: {_e}")

                # Hot launch signal boost (from amm_launch_watcher.py)
                hot_launch_boost = 0
                try:
                    _hl_file = os.path.join(STATE_DIR, "hot_launches.json")
                    if os.path.exists(_hl_file):
                        _hl_data = json.loads(open(_hl_file).read())
                        for _hl_key, _hl in _hl_data.get("launches", {}).items():
                            if _hl.get("symbol","").upper() == symbol.upper():
                                if _hl.get("expires", 0) > time.time():
                                    hot_launch_boost = int(_hl.get("dna_score", 0))
                                    if hot_launch_boost > 0:
                                        logger.info(f"  {symbol}: HOT LAUNCH boost +{hot_launch_boost}pts flags={_hl.get('dna_flags',[])}")
                except Exception as _hle:
                    logger.debug(f"Hot launch read error: {_hle}")

                # Merge all boosts — DNA + TG scanner + hot launch
                sm_boost_total = min(sm_boost + dna_bonus + hot_launch_boost, 60)

                # Score
                score_result = scoring_mod.compute_score(
                    breakout_quality  = bq,
                    chart_state       = chart_state,
                    chart_confidence  = chart_conf,
                    tvl_xrp           = tvl,
                    tvl_change_pct    = candidate.get("tvl_change_pct", 0.0),
                    issuer_safe       = safety_result.get("issuer_blackhole", False),
                    issuer_warnings   = len(safety_result.get("warnings", [])),
                    route_slippage    = route.get("best_slippage", 0.05),
                    route_exit_ok     = route.get("exit_ok", True),
                    smart_money_boost = sm_boost_total,
                    extension_pct     = bq_result.get("pct_change", 0) / 100,
                    regime            = regime,
                    symbol            = symbol,
                )
                total_score = score_result["total"]
                band        = score_result["band"]

                # ── GodMode Token Classifier (audit #5) ───────────────────────
                # Runs BEFORE score threshold check — routes to strategy type,
                # adds classifier score bonus, and annotates candidate for logging.
                # Provides strategy-level signal boost independent of composite score.
                try:
                    _price_hist = scanner._load_history().get(key, [])
                    _gm_result = classifier_mod.classify_and_route(
                        candidate, _price_hist, cycle_wallet_xrp
                    )
                    _gm_action  = _gm_result.get("action", "skip")
                    _gm_type    = _gm_result.get("token_type", "none")
                    _gm_score   = _gm_result.get("strategy_score", 0)
                    _gm_reason  = _gm_result.get("reason", "")

                    if _gm_action == "enter":
                        _score_before = total_score
                        candidate["_godmode_type"] = _gm_type

                        # ── FAST PATH: BURST + CLOB_LAUNCH are authoritative ──
                        # These strategies have already passed valid() + confirm()
                        # + ExecutionValidator inside classify_and_route().
                        # Don't penalize them through the slow scoring/chart_state gate.
                        # Mark fast-path so chart_state gate is bypassed below.
                        if _gm_type in ("burst", "clob_launch"):
                            candidate["_fast_path"] = True
                            candidate["_burst_mode"] = True  # ensure burst gates pass
                            # Use strategy score directly — no blending with composite
                            total_score = max(total_score, int(_gm_score))
                            logger.info(
                                f"  🚀 FAST-PATH {symbol}: type={_gm_type} "
                                f"strat_score={_gm_score:.0f} → AUTHORITATIVE ENTRY"
                            )
                        else:
                            # PRE_BREAKOUT / TREND / MICRO_SCALP — advisory bonus only
                            total_score = min(100, total_score + int(_gm_score * 0.3))
                            logger.info(
                                f"  🧠 GODMODE {symbol}: type={_gm_type} strat_score={_gm_score:.0f} "
                                f"→ score {_score_before}→{total_score} (+{total_score-_score_before})"
                            )
                    elif _gm_action == "pending":
                        candidate["_godmode_pending"] = True
                        candidate["_godmode_type"]    = _gm_type
                        logger.info(f"  ⏳ GODMODE PENDING {symbol}: {_gm_reason} — awaiting confirmation")
                    else:
                        # skip — log only, let scoring gate decide
                        if _gm_score > 0:
                            logger.debug(f"  🧠 GODMODE {symbol}: {_gm_reason} (type={_gm_type})")
                except Exception as _gme:
                    logger.debug(f"GodMode classifier error {symbol}: {_gme}")

                # ── Disagreement Engine — second opinion before entry ─────────
                # Runs 6 independent checks. Any veto kills the trade.
                # Warns reduce confidence score. Passes add to it.
                try:
                    import disagreement as _disagree_mod
                    _disagree_result = _disagree_mod.evaluate(
                        candidate  = candidate,
                        bot_state  = bot_state,
                        regime     = regime,
                        score      = total_score,
                    )
                    if _disagree_result["verdict"] == "veto":
                        logger.info(
                            f"🚫 VETO {symbol}: {_disagree_result['reason']}"
                        )
                        continue   # hard skip — no overrides
                    # Apply confidence adjustment to score
                    _adj = _disagree_result.get("confidence_adj", 0)
                    if _adj != 0:
                        total_score = max(0, round(total_score + _adj * 10))
                        logger.debug(f"  [disagree] {symbol} score adj {_adj:+.2f} → {total_score}")
                except ImportError:
                    pass   # disagreement module not available — non-fatal
                except Exception as _de:
                    logger.debug(f"[disagree] error {symbol}: {_de}")

                # ── CLOB momentum score boost ────────────────────────────────
                _is_clob_boost = candidate.get("_clob_launch", False)
                _clob_vol_boost = candidate.get("clob_vol_5min", 0)
                if _is_clob_boost and _clob_vol_boost >= 20:
                    clob_adj = min(50, int(_clob_vol_boost))  # +1 per 5 XRP vol, max +30
                    total_score += clob_adj
                    logger.info(f"  ⚡ CLOB BOOST {symbol}: +{clob_adj} (vol={_clob_vol_boost:.0f} XRP)")

                # ── Apply learned score adjustment ────────────────────────────
                learn_adj = learn_mod.get_score_adjustment(chart_state)
                if learn_adj != 0:
                    total_score = round(total_score + learn_adj)
                    logger.debug(f"  [learn] {symbol} score adj {learn_adj:+.0f} → {total_score}")

                # Log full Lite Haus-style intel for every candidate
                intel = candidate.get("intel", {})
                if intel:
                    try:
                        import token_intel as _ti
                        logger.info(f"  📊 {_ti.format_intel_log(intel)}")
                    except:
                        pass
                _pre_modifier_score = total_score  # snapshot before post-modifiers for log later

                # ── Micro-Velocity Override ───────────────────────────────────
                # Tokens under 2000 XRP TVL that are already moving get a
                # LOWER score requirement (45 instead of effective_threshold).
                # Rationale: Serpent was 715 XRP TVL, showing +5.6% per reading.
                # We missed +255% because score was below threshold.
                # Risk is capped — we only enter 5 XRP (XRP_MICRO_BASE).
                # Robin, Serpent, BPHX all fit this profile exactly.
                _micro_override = False
                if tvl < 2000 and tvl >= 200:
                    try:
                        _hist_mv = scanner._load_history().get(key, [])
                        _mv_prices = [r["price"] for r in _hist_mv if r.get("price",0) > 0]
                        if len(_mv_prices) >= 3:
                            _mv_vel = (_mv_prices[-1] - _mv_prices[-3]) / _mv_prices[-3] * 100 if _mv_prices[-3] > 0 else 0
                            if _mv_vel >= 5.0 and total_score >= 45:
                                _micro_override = True
                                logger.info(f"  🎯 MICRO-VEL OVERRIDE {symbol}: TVL={tvl:.0f} vel={_mv_vel:+.1f}% score={total_score} → entering at {XRP_MICRO_BASE} XRP")
                    except:
                        pass

                if not _micro_override and total_score < effective_threshold and band != "elite":
                    # ── Scalp mode: catch 48-56 scoring pre_breakout tokens ───
                    # Quick +10% target, tight -8% stop, 45 min max hold
                    _is_scalp = (
                        chart_state == "pre_breakout"
                        and SCALP_MIN_SCORE <= total_score <= SCALP_MAX_SCORE
                        and tvl >= 500  # need some liquidity for scalps
                    )
                    if _is_scalp:
                        final_size = SCALP_SIZE_XRP
                        candidate["_scalp_mode"] = True
                        logger.info(f"  ⚡ SCALP {symbol}: score={total_score} → {SCALP_SIZE_XRP} XRP scalp entry")
                    else:
                        logger.info(f"SKIP {symbol}: score {total_score} < threshold {effective_threshold}")
                        continue

                # ── Chart State Gate ──────────────────────────────────────────
                # pre_breakout = primary edge (compressed, about to move)
                # continuation + burst = allowed when TrustSet velocity confirms momentum
                # expansion + burst    = allowed (already moving with conviction)
                # orphan               = DISABLED (14% WR, rugpull magnet)
                _is_burst    = candidate.get("_burst_mode", False)
                _burst_count = candidate.get("burst_count", 0)
                _is_momentum = candidate.get("_momentum_mode", False)
                _offer_count = candidate.get("offer_count", 0)
                _is_clob     = candidate.get("_clob_launch", False)
                _clob_vol    = candidate.get("clob_vol_5min", 0)
                
                # LOSS REDUCTION FILTER: Vol ≥30 XRP AND Burst ≥20 for CLOB entries
                # Keeps 3/4 winners, cuts 5/9 losers → WR 31% → 38%
                if _is_clob and (_clob_vol < 20 or _burst_count < 10):
                    logger.info(f"SKIP {symbol}: CLOB filter fail — vol={_clob_vol:.0f} (<20) or burst={_burst_count} (<10)")
                    continue
                
                if chart_state == "orphan":
                    logger.info(f"SKIP {symbol}: orphan — rugpull risk, disabled permanently")
                    continue
                elif chart_state not in PREFERRED_CHART_STATES:
                    # ── FAST PATH: BURST + CLOB_LAUNCH bypass chart_state gate ──
                    # Classifier already validated signal quality — chart_state is
                    # a lagging indicator for momentum plays. Don't block runners.
                    if candidate.get("_fast_path"):
                        logger.info(
                            f"✅ {symbol}: chart_state={chart_state} BYPASSED "
                            f"— fast-path {candidate.get('_godmode_type','burst')} strategy"
                        )
                    # Allow continuation/expansion with TrustSet burst
                    elif _is_burst and _burst_count >= 3 and chart_state in ("continuation", "expansion", "accumulation"):
                        logger.info(f"✅ {symbol}: {chart_state} ALLOWED — burst={_burst_count} TrustSets override")
                    # Allow any state if buy cluster is strong
                    elif _is_momentum and _offer_count >= 8:
                        logger.info(f"✅ {symbol}: {chart_state} ALLOWED — buy_cluster={_offer_count} offers override")
                    # CLOB launch — always allow
                    elif _is_clob:
                        logger.info(f"✅ {symbol}: {chart_state} ALLOWED — CLOB launch signal {_clob_vol:.0f} XRP/5min")
                    else:
                        logger.info(f"SKIP {symbol}: chart_state={chart_state} (burst={_burst_count}, momentum={_offer_count}) — need pre_breakout or realtime signal")
                        continue

                # ── MEMECOIN FILTER — strict XRPL meme-only gate ─────────────
                # Operator directive: strictly memecoins only. No utility, no
                # infrastructure, no wrapped assets, no established L1s.
                sym_up = symbol.upper()

                # Stablecoins / fiat-pegged
                STABLECOIN_SKIP = {
                    "USD","USDC","USDT","RLUSD","XUSD","AUDD","XSGD","XCHF","GYEN",
                    "EUR","EURO","EUROP","GBP","JPY","CNY","AUD","CAD","MXRP",
                    "USDD","FRAX","LUSD","SUSD","TUSD","BUSD","GUSD","HUSD",
                }
                FIAT_PREFIXES = ("USD","EUR","GBP","JPY","CNY","AUD","CAD","STABLE","PEGGED")
                if sym_up in STABLECOIN_SKIP or any(sym_up.startswith(p) or sym_up.endswith(p) for p in FIAT_PREFIXES):
                    logger.debug(f"SKIP {symbol}: stablecoin/fiat-pegged — no meme upside")
                    continue

                # Non-meme: established L1s, infrastructure, utility, DeFi protocols
                # These have real utility value — they do NOT have meme explosive upside
                NON_MEME_SKIP = {
                    # Real L1/L2 blockchain tokens (not memes)
                    "XDC","ETH","WETH","WBTC","BTC","SOL","AVAX","MATIC","BNB","ADA",
                    "DOT","LINK","UNI","AAVE","CRV","MKR","SNX","COMP","LDO","ATOM",
                    "ALGO","NEAR","FTM","OP","ARB","INJ","SUI","APT","SEI","TIA",
                    # Real HBAR (Hedera) — though XRPL meme token named HBAR is fine
                    # (anonymous issuer = meme; verified issuer = skip)
                    # XRPL ecosystem utility
                    "EVR","SOLO","CSC","CORE","LOBSTR","GATEHUB","BITSTAMP","XUMM","XAPP",
                    # Wrapped / bridged assets
                    "WXRP","WXDC","WFLR","WSGB","WXAH",
                    # DeFi / governance tokens (not memes)
                    "BLZE","VLX","EXFI","SFLR",
                    # Commodity / index
                    "GOLD","SLVR","OIL","SPX","NDX",
                    # Real-world asset tokens
                    "RLUSD","TREASU","TBILL",
                }
                NON_MEME_PREFIXES = ("W",)   # wrapped tokens
                NON_MEME_SUFFIXES = ("IOU", "LP", "POOL", "VAULT")
                if sym_up in NON_MEME_SKIP:
                    logger.debug(f"SKIP {symbol}: non-meme token — operator meme-only directive")
                    continue
                if any(sym_up.startswith(p) for p in NON_MEME_PREFIXES):
                    logger.debug(f"SKIP {symbol}: wrapped/bridged token — no meme upside")
                    continue
                if any(sym_up.endswith(s) for s in NON_MEME_SUFFIXES):
                    logger.debug(f"SKIP {symbol}: LP/vault token — not a meme")
                    continue

                # Meme signal requirement: anonymous issuer (no verified domain) OR
                # supply > 1M tokens (large supply = designed as meme speculation vehicle).
                # Verified/doxxed issuers with domains are typically NOT memes.
                _issuer_domain = candidate.get("issuer_domain", "")
                _supply = candidate.get("supply", 0)
                _is_verified_utility = bool(_issuer_domain) and _supply < 100_000
                if _is_verified_utility:
                    logger.debug(f"SKIP {symbol}: verified issuer domain={_issuer_domain} — likely utility, not meme")
                    continue

                # Skip known repeat hard-stop offenders
                # Proven token check — bypass cooldown/blacklist if token has proven itself
                _is_proven = symbol in _proven_tokens
                if _is_proven:
                    logger.info(f"🏆 PROVEN {symbol}: {_proven_tokens[symbol]} wins — bypassing cooldown, priority entry")
                elif symbol in SKIP_REENTRY_SYMBOLS:
                    logger.info(f"SKIP {symbol}: in hard-stop blacklist")
                    continue

                # BQ minimum filter — learned from session: BQ < 40 = unreliable signal
                if bq < 40:
                    logger.info(f"SKIP {symbol}: bq={bq} < 40 minimum (weak breakout quality)")
                    continue

                # ── Velocity Detector ─────────────────────────────────────────
                # Fast movers (+8%+ in 1h) get score boost — catches BPHX-style runners
                # before they fully score on BQ/chart_state alone
                try:
                    _hist = scanner._load_history().get(key, [])
                    if len(_hist) >= 5:
                        _prices = [r["price"] for r in _hist if r.get("price", 0) > 0]
                        _p_now  = _prices[-1] if _prices else 0
                        _p_1h   = _prices[-5] if len(_prices) >= 5 else _prices[0]
                        _vel_1h = (_p_now - _p_1h) / _p_1h * 100 if _p_1h > 0 else 0
                        if _vel_1h >= 15:
                            _vboost = min(12, int(_vel_1h / 5))
                            total_score = min(100, total_score + _vboost)
                            logger.info(f"  🚀 VELOCITY {symbol}: +{_vel_1h:.1f}% in 1h → score boost +{_vboost}")
                        elif _vel_1h >= 8:
                            total_score = min(100, total_score + 5)
                            logger.info(f"  ⚡ VELOCITY {symbol}: +{_vel_1h:.1f}% in 1h → score boost +5")
                except Exception as _ve:
                    pass

                # TVL sweet spot filter — avoid slow large pools (>40K XRP TVL)
                if tvl > 40_000:
                    logger.info(f"SKIP {symbol}: tvl={tvl:.0f} > 40K (too large, slow mover)")
                    continue

                # Position size: Kelly-influenced — use cycle_wallet_xrp fetched once above
                wallet_xrp = cycle_wallet_xrp

                # ── Hold vs Scalp Classifier ──────────────────────────────────
                # DATA: TVL 1K-10K = hold for 300%+. TVL <1K = quick scalp.
                # TVL >10K = stale risk (0% WR in data), skip or micro only.
                _tvl = candidate.get("tvl_xrp", 99999)
                _tvl_chg = candidate.get("tvl_change_pct", 0.0)

                # ── TVL Velocity Gate (real-time momentum check) ──────────────
                # If TVL grew ≥20% since 5 readings ago (~10 min), money is
                # flowing in NOW. This overrides chart_state and score gates —
                # TVL velocity is the strongest leading indicator we have.
                # Targets: DKLEDGER (+19% in 30min), RUGRATS, PROPHET-type moves.
                _is_tvl_runner = False
                if _tvl_chg >= TVL_VELOCITY_RUNNER and _tvl < 15000:
                    _is_tvl_runner = True
                    candidate["_tvl_runner"] = True
                    logger.info(f"🚀 TVL RUNNER {symbol}: TVL={_tvl:.0f} XRP +{_tvl_chg*100:.1f}% in ~10min — fast entry")

                _trade_mode = _classify_hold_or_scalp(_tvl, _tvl_chg, total_score)

                # Proven token always gets hold mode + bigger size
                if _is_proven:
                    _trade_mode = "hold"
                    final_size = PROVEN_TOKEN_RELOAD_XRP * adj.get("size_mult", 1.0) * size_mult_global
                    logger.info(f"  🏆 PROVEN reload: {symbol} → hold mode, size={final_size:.1f} XRP")
                elif _trade_mode == "skip":
                    logger.info(f"SKIP {symbol}: TVL={_tvl:.0f} stale zone (>10K, no growth) — data: 0% WR")
                    continue
                elif _trade_mode == "scalp" and not candidate.get("_scalp_mode"):
                    # Override to scalp mode
                    candidate["_scalp_mode"] = True
                    final_size = SCALP_SIZE_XRP
                    logger.info(f"  ⚡ TVL-SCALP {symbol}: TVL={_tvl:.0f} XRP → scalp mode {SCALP_SIZE_XRP} XRP")
                elif _micro_override:
                    final_size = XRP_MICRO_BASE
                    logger.info(f"MICRO-CAP entry for {symbol}: TVL={_tvl:.0f} XRP → size={XRP_MICRO_BASE} XRP")
                else:
                    # Hold mode — confidence-based sizing
                    _trade_mode = "hold"
                    if _SIZING_AVAILABLE:
                        # Gather confidence signals for dynamic sizing
                        _is_ts_burst = bool(candidate.get("signal_type") == "trustset_velocity" or candidate.get("_burst_mode"))
                        _ts_burst_count = int(candidate.get("burst_count", 0) or candidate.get("trustsets_1h", 0))
                        _ci = {
                            "wallet_cluster_active": bool(cluster_mod.get_cluster_signal(key) if hasattr(cluster_mod, "get_cluster_signal") else False),
                            "alpha_signal_active": bool(_is_ts_burst),
                            "ts_burst_active": _is_ts_burst,           # explosive early launch signal
                            "ts_burst_count": _ts_burst_count,         # TrustSets/hr — scales position
                            "ml_probability": 0.5,  # default; overridden by ML if available
                            "regime": regime,
                            "smart_wallet_count": len(sm_result.get("wallets", [])),
                            "tvl_xrp": _tvl,
                        }
                        if _ML_AVAILABLE:
                            try:
                                _ml_p = ml_model_mod.predict_probability(
                                    ml_features_mod.build_features(candidate, score_result, bot_state)
                                )
                                if _ml_p is not None:
                                    _ci["ml_probability"] = float(_ml_p)
                            except Exception:
                                pass
                        final_size = _calc_position_size(total_score, wallet_xrp, _ci)
                    else:
                        final_size = scoring_mod.position_size(
                            total_score, regime,
                            base_xrp=XRP_PER_TRADE_BASE,
                            elite_xrp=XRP_ELITE_BASE,
                            small_xrp=XRP_SMALL_BASE,
                            bq=bq,
                            wallet_xrp=wallet_xrp,
                        )
                    logger.info(f"  📈 HOLD mode {symbol}: TVL={_tvl:.0f} XRP → {final_size:.1f} XRP, targeting TP3+")

                # Apply learned size multiplier (from hot/cold streak + band performance)
                # Skip learn size mult for proven/scalp entries (already sized correctly)
                if not _is_proven and not candidate.get("_scalp_mode"):
                    learn_size_mult = learn_mod.get_size_multiplier(band)
                    if learn_size_mult != 1.0:
                        final_size = round(final_size * learn_size_mult, 2)
                        logger.debug(f"  [learn] size mult {learn_size_mult:.2f}x → {final_size:.2f} XRP")

                # Pool safety + adaptive sizing (learn_engine) -- BEFORE final_size check
                _pool_key = symbol + ":" + str(issuer)
                _pool_tok = {"key": _pool_key, "pool_id": _pool_key}
                if not brain.is_pool_safe(_pool_tok):
                    logger.info(f"POOL_UNSAFE {symbol}: pool behavior -- skipped")
                else:
                    _adj = brain.adjust_size_for_strategy(final_size, candidate.get("_godmode_type","unknown"))
                    if _adj < final_size:
                        final_size = _adj
                if final_size < 1.0:
                    logger.info(f"SKIP {symbol}: final_size={final_size:.2f} too small (score={total_score}, band={band}, regime={regime})")
                    continue

                # Store trade mode for position tracking
                candidate["_trade_mode"] = _trade_mode

            except Exception as e:
                logger.exception(f"Scoring error {symbol}: {e}")
                continue

            # ── Momentum Confirmation Gate ────────────────────────────────────
            # Backtest finding: pre_breakout WR=29% because tokens like UGA/SPY
            # scored well but NEVER moved after entry.
            # Gate: price must have ticked UP at least 1% from 2 readings ago.
            # This confirms the move is actually starting, not just set up.
            # Exception: velocity tokens (fast movers) skip this gate.
            _PENDING_FILE = os.path.join(STATE_DIR, "pending_confirmation.json")
            try:
                _hist = scanner._load_history().get(key, [])
                _prices = [r["price"] for r in _hist if r.get("price", 0) > 0]
                _vel_1h_check = 0
                if len(_prices) >= 5:
                    _vel_1h_check = (_prices[-1] - _prices[-5]) / _prices[-5] * 100 if _prices[-5] > 0 else 0

                # Load pending dict — purge stale entries (>30 min) at load time
                try:
                    with open(_PENDING_FILE) as _pf:
                        _pending = json.load(_pf)
                    _now_ts = time.time()
                    _pending = {k: v for k, v in _pending.items() if _now_ts - v.get("ts", 0) < 1800}
                except:
                    _pending = {}

                _confirmed = True
                # Burst tokens: TrustSet velocity IS the confirmation — skip price gate
                if _is_burst and _burst_count >= 3:
                    logger.info(f"⚡ BURST CONFIRMED {symbol}: {_burst_count} TrustSets/5min — entering without price gate")
                # Momentum tokens: buy clusters are live confirmation — skip price gate
                elif _is_momentum and _offer_count >= 5:
                    logger.info(f"📈 MOMENTUM CONFIRMED {symbol}: {_offer_count} buys/2min — entering without price gate")
                # TVL runners: money flowing into pool = real demand, skip price gate
                elif _is_tvl_runner:
                    logger.info(f"🚀 TVL RUNNER CONFIRMED {symbol}: +{_tvl_chg*100:.1f}% TVL — entering without price gate")
                # CLOB launch: orderbook buying = real demand, skip price gate
                elif _is_clob:
                    logger.info(f"🚀 CLOB LAUNCH CONFIRMED {symbol}: {_clob_vol:.0f} XRP/5min CLOB vol — entering without price gate")
                elif _vel_1h_check < 8:  # not a fast mover — require confirmation
                    if len(_prices) >= 3:
                        _chg_recent = (_prices[-1] - _prices[-3]) / _prices[-3] * 100 if _prices[-3] > 0 else 0
                        # DATA: stales = 40% of trades. Require modest movement but not excessive.
                        # Lowered from 3% → 1.5% — 3% was blocking ALL entries (64+ PENDINGs per token)
                        if _chg_recent < 1.5:
                            # Price hasn't moved yet — put on watch
                            if key not in _pending:
                                _pending[key] = {"ts": time.time(), "score": total_score, "price": price}
                                try:
                                    with open(_PENDING_FILE, "w") as _pf:
                                        json.dump(_pending, _pf)
                                except:
                                    pass
                            logger.info(f"PENDING {symbol}: pre_breakout but price flat ({_chg_recent:+.1f}% recent) — waiting for +1.5% confirmation")
                            _confirmed = False
                        else:
                            # Confirmation met — clear from pending
                            if key in _pending:
                                del _pending[key]
                                try:
                                    with open(_PENDING_FILE, "w") as _pf:
                                        json.dump(_pending, _pf)
                                except:
                                    pass
                            logger.info(f"✅ CONFIRMED {symbol}: price moved {_chg_recent:+.1f}% — entering")
                else:
                    logger.info(f"⚡ FAST MOVER {symbol}: vel={_vel_1h_check:+.1f}% — skip confirmation gate")

                if not _confirmed:
                    continue

                # Expire stale pending entries (>30 min without confirmation = signal died)
                _now_ts = time.time()
                _pending = {k: v for k, v in _pending.items() if _now_ts - v.get("ts", 0) < 1800}
                try:
                    with open(_PENDING_FILE, "w") as _pf:
                        json.dump(_pending, _pf)
                except:
                    pass

            except Exception as _cge:
                logger.debug(f"Confirmation gate error {symbol}: {_cge}")

            # ── 5-6. Execute entry ────────────────────────────────────────────
            # ── Execution Core path (GodMode-authorized) ──────────────────────
            # Fast-path tokens (BURST, CLOB_LAUNCH) use centralized execute_trade
            # with confidence gate, strategy ownership, liquidity-capped sizing, split entry.
            _exec_result    = None
            _using_core     = False
            _strategy_obj   = _gm_result.get("strategy") if "_gm_result" in dir() else None
            _use_gm_path    = (
                "_gm_result" in dir()
                and _gm_result.get("action") == "enter"
                and _gm_result.get("strategy") is not None
            )

            try:
                if _use_gm_path:
                    _classification = _gm_result.get("classification", {})
                    _wallet_st     = {"balance": cycle_wallet_xrp, "drawdown": _drawdown_pct}
                    _exec_result   = execute_trade(
                        token = {
                            "symbol":        symbol,
                            "issuer":        issuer,
                            "price":         price,
                            "liquidity_usd": candidate.get("liquidity_usd", 0),
                            "market_cap":    candidate.get("market_cap", 0),
                        },
                        classification = _classification,
                        strategy       = _gm_result["strategy"],
                        wallet_state   = _wallet_st,
                        route_quality  = route.get("quality", "GOOD"),
                        side           = "buy",
                    )
                    _using_core = True
                    logger.info(f"  🚀 EXEC_CORE {symbol}: core path size="
                                f"{_exec_result.get('size', final_size):.2f} XRP "
                                f"split={_exec_result.get('split', False)}")
                else:
                    # Legacy fallback — old score-threshold flow
                    logger.info(f"BUY {symbol}: {final_size:.2f} XRP @ {price:.8f} score={total_score}")
                    _exec_result = execution.buy_token(
                        symbol         = symbol,
                        issuer         = issuer,
                        xrp_amount     = final_size,
                        expected_price = price,
                    )
                    _exec_result = {"first": _exec_result, "split": False}

                # Unpack result for post-execution logic
                exec_result      = _exec_result["first"]
                split_executed   = _exec_result.get("split", False)
                split_total_size = _exec_result.get("size", final_size)

                if exec_result.get("success"):
                    tokens_received = exec_result.get("tokens_received", 0)
                    actual_price   = exec_result.get("actual_price", price)
                    actual_slippage = exec_result.get("slippage", 0)

                    # Guard: don't record a position if we received 0 tokens (ghost position prevention)
                    if tokens_received <= 0:
                        logger.warning(f"✗ BUY {symbol}: success but 0 tokens received — skipping position record")
                        continue

                    # Slippage guard: SKIP position if entry slippage > 2.5%
                    # 2026-04-05 audit: 0% WR on entries with >2.5% slippage (T3DDY 3.2%=-1.2, ROOSEVELT 1.9%=-2.0)
                    # Changed from warning to hard skip — don't hold a bad fill
                    if actual_slippage > 0.025:
                        logger.warning(f"🚫 {symbol}: entry slippage {actual_slippage:.1%} > 2.5% gate — attempting immediate sell to recover XRP")
                        try:
                            sell_result = execution.sell_token(
                                symbol         = symbol,
                                issuer         = issuer,
                                token_amount   = tokens_received,
                                expected_price = actual_price,
                                slippage_tolerance = brain.predict_slippage(token, final_size),
                            )
                            if sell_result.get("success"):
                                logger.info(f"✅ Slippage recovery sell succeeded for {symbol}: {sell_result.get('xrp_received', 0):.4f} XRP recovered")
                            else:
                                logger.error(f"❌ Slippage recovery sell FAILED for {symbol}: {sell_result.get('error')} — adding to orphan_positions")
                                if "orphan_positions" not in bot_state:
                                    bot_state["orphan_positions"] = {}
                                from config import get_currency as _get_currency
                                bot_state["orphan_positions"][symbol] = {
                                    "tokens":   tokens_received,
                                    "issuer":   issuer,
                                    "currency": _get_currency(symbol),
                                    "ts":       now,
                                }
                                state_mod.save(bot_state)
                        except Exception as _sell_exc:
                            logger.error(f"❌ Slippage recovery exception for {symbol}: {_sell_exc} — adding to orphan_positions")
                            if "orphan_positions" not in bot_state:
                                bot_state["orphan_positions"] = {}
                            bot_state["orphan_positions"][symbol] = {
                                "tokens":   tokens_received,
                                "issuer":   issuer,
                                "currency": symbol,
                                "ts":       now,
                            }
                            state_mod.save(bot_state)
                        continue

                    position = {
                        "symbol":       symbol,
                        "issuer":       issuer,
                        "entry_price":  actual_price,
                        "entry_time":   now,
                        "tokens_held":  tokens_received,
                        "xrp_spent":    exec_result.get("xrp_spent", final_size),
                        "peak_price":   actual_price,
                        "tp1_hit":      False,
                        "tp2_hit":      False,
                        "entry_tvl":    tvl,
                        "score":        total_score,
                        "chart_state":  chart_state,
                        "score_band":   band,
                        "entry_hash":   exec_result.get("hash"),
                        "smart_wallets": sm_result.get("wallets", []),
                        "scalp_mode":   candidate.get("_scalp_mode", False),
                        "trade_mode":   candidate.get("_trade_mode", "hold"),
                        "is_proven":    _is_proven,
                        # GodMode engine: strategy type + TP targets
                        "_godmode_type":  candidate.get("_godmode_type", "unknown"),
                        "_godmode_tp":    _gm_result.get("tp_targets") if candidate.get("_godmode_type") else None,
                        "_godmode_hardstop": _gm_result.get("hard_stop_pct") if candidate.get("_godmode_type") else None,
                    }
                    state_mod.add_position(bot_state, key, position)

                    # ── ML: log entry features ─────────────────────────────────
                    if _ML_AVAILABLE:
                        try:
                            ml_features_mod.log_entry_features(
                                position        = position,
                                bot_state       = bot_state,
                                score_breakdown = score_result.get("breakdown", {}),
                            )
                        except Exception as _mle:
                            logger.debug(f"[ml] log_entry_features error: {_mle}")

                    _entered_this_cycle.add(symbol)  # prevent duplicate in same cycle
                    open_positions = bot_state.get("positions", {})  # refresh for next iteration
                    logger.info(f"✓ ENTERED {symbol}: {tokens_received:.4f} tokens @ {actual_price:.8f}")
                    dash_log(f"✅ ENTERED {symbol}: {final_size:.1f} XRP @ {actual_price:.8f}")
                    update_position(symbol, actual_price, actual_price, final_size)
                    relay_bridge.push_trade(symbol=symbol, action="entry", xrp=exec_result.get("xrp_spent", final_size), score=total_score, chart=chart_state, note=f"entry @ {actual_price:.8f}")
                else:
                    logger.error(f"✗ BUY FAILED {symbol}: {exec_result.get('error')}")

            except Exception as e:
                logger.error(f"Execution error {symbol}: {e}")

    # ── 6b. Re-entry on pullback for TP1-hit winners with top-holder buying ────
    for key, pos in list(bot_state.get("positions", {}).items()):
        try:
            if not pos.get("tp1_hit"):
                continue  # only re-enter on TP1-hit winners
            symbol = pos["symbol"]
            issuer = pos["issuer"]
            reentry_key = f"{key}:reentry"
            if reentry_key in bot_state.get("positions", {}):
                continue  # already have a re-entry position
            if len(bot_state.get("positions", {})) >= MAX_POSITIONS:
                continue

            current_price, _, _, amm_data = scanner.get_token_price_and_tvl(symbol, issuer, currency=pos.get("currency"))
            if not current_price:
                continue

            entry_price = pos["entry_price"]
            peak_price  = pos.get("peak_price", entry_price)

            # Pullback condition: price pulled back 8–20% from peak (healthy retest)
            pullback_from_peak = (peak_price - current_price) / peak_price
            if not (0.08 <= pullback_from_peak <= 0.25):
                continue

            # Top-holder buying check via safety module
            safety_result = safety.check_token(symbol, issuer)
            warnings = safety_result.get("warnings", [])
            # Concentration risk: penalty not block — top holder may be supply control (PHX pattern)
            # Extract top holder % from warning and apply graduated score penalty
            conc_penalty = 0
            for w in warnings:
                if "concentration_risk" in w:
                    try:
                        pct = float(w.split("top_holder:")[1].split("%")[0])
                        if pct >= 70:
                            conc_penalty = 12
                        elif pct >= 50:
                            conc_penalty = 9
                        elif pct >= 40:
                            conc_penalty = 5
                        else:
                            conc_penalty = 2
                        logger.info(f"  ⚠️  {symbol}: concentration {pct:.0f}% → score penalty -{conc_penalty}")
                    except:
                        conc_penalty = 8
            total_score = max(0, total_score - conc_penalty)

            # ── Wallet Intelligence (Horizon-style on-chain analysis) ─────────
            # currency may not be in scope here (re-entry loop) — pull from pos
            _reentry_currency = pos.get("currency", "")
            _reentry_score = pos.get("last_score", 50)
            _reentry_pre   = _reentry_score
            try:
                import wallet_intelligence as _wi
                wi_result = _wi.analyze_token(symbol, _reentry_currency, issuer)
                wi_mod = wi_result.get("score_modifier", 0)
                sm_score = wi_result.get("smart_money_score", 50)
                wi_flags = wi_result.get("flags", [])
                _reentry_score = max(0, min(100, _reentry_score + wi_mod))
                logger.info(
                    f"  🧠 {symbol} wallet intel: smart_money={sm_score}/100 "
                    f"modifier={wi_mod:+d} holders={wi_result.get('total_holders',0)} "
                    f"clusters={wi_result.get('clusters',{}).get('cluster_count',0)} "
                    f"flags={wi_flags}"
                )
            except Exception as _wie:
                logger.debug(f"[wallet_intel] {symbol}: {_wie}")

            # Final score log — after ALL modifiers applied
            _wi_mod_final = _reentry_score - _reentry_pre
            logger.info(f"  RE-ENTRY {symbol}: score={_reentry_score} state=pullback_reentry tvl={pos.get('entry_tvl',0):.0f} intel={_wi_mod_final:+d}")

            # Check smart wallet buying — proxy: recent price recovery from pullback low
            # If price is now recovering (+3% from recent low), top holders likely accumulating
            price_hist = scanner._load_history().get(scanner.token_key(symbol, issuer), [])
            if len(price_hist) >= 3:
                recent_prices = [r["price"] for r in price_hist[-6:]]
                low = min(recent_prices)
                recovery = (current_price - low) / low if low > 0 else 0
                if recovery < 0.03:
                    continue  # not recovering yet, wait
            else:
                continue

            # All conditions met — re-enter with small size
            reentry_size = XRP_SMALL_BASE
            logger.info(f"RE-ENTRY {symbol}: pullback={pullback_from_peak:.1%} recovery detected, size={reentry_size} XRP")
            exec_result = execution.buy_token(
                symbol         = symbol,
                issuer         = issuer,
                xrp_amount     = reentry_size,
                expected_price = current_price,
            )
            if exec_result.get("success"):
                tokens_received = exec_result.get("tokens_received", 0)
                actual_price    = exec_result.get("actual_price", current_price)
                now = time.time()
                bot_state["positions"][reentry_key] = {
                    "symbol":       symbol,
                    "issuer":       issuer,
                    "currency":     pos.get("currency", symbol),
                    "tokens_held":  tokens_received,
                    "entry_price":  actual_price,
                    "xrp_spent":    exec_result.get("xrp_spent", reentry_size),
                    "entry_time":   now,
                    "peak_price":   actual_price,
                    "tp1_hit":      False,
                    "tp2_hit":      False,
                    "tp3_hit":      False,
                    "entry_tvl":    pos.get("entry_tvl", 0),
                    "chart_state":  "pullback_reentry",
                    "score_band":   "reentry",
                    "score":        pos.get("score", 45),
                    "reentry":      True,
                }
                state_mod.save(bot_state)
                logger.info(f"✓ RE-ENTERED {symbol}: {tokens_received:.4f} tokens @ {actual_price:.8f}")
            else:
                logger.warning(f"Re-entry failed {symbol}: {exec_result.get('error')}")
        except Exception as e:
            logger.warning(f"Re-entry check error {pos.get('symbol','?')}: {e}")

    # ── 7. Dynamic exit checks on all positions ────────────────────────────────
    for key, pos in list(bot_state.get("positions", {}).items()):
        symbol = pos["symbol"]
        issuer = pos["issuer"]
        currency = pos.get("currency", "")

        try:
            # Get current price
            current_price, current_tvl, price_source, amm_data = scanner.get_token_price_and_tvl(symbol, issuer, currency=pos.get("currency"))
            hold_hours_now = (now - pos.get("entry_time", now)) / 3600

            if not current_price:
                # If price has been zero for >2hr since entry → token is likely dead, force exit
                if hold_hours_now > 2.0:
                    logger.warning(f"⚰️  {symbol}: No live price after {hold_hours_now:.1f}hr — treating as dead token, force-exiting")
                    exit_check = {"exit": True, "partial": False, "reason": f"dead_token_{hold_hours_now:.1f}hr", "fraction": 1.0}
                    # Fall through to exit logic with entry price as current (best we can do)
                    current_price = pos.get("current_price") or pos.get("entry_price")
                    current_tvl   = 0
                else:
                    # Under 2hr — give it time, use last known
                    current_price = pos.get("current_price") or pos.get("entry_price")
                    current_tvl   = pos.get("last_tvl", 0)
                    if current_price:
                        logger.warning(f"No live price for {symbol} — using last known {current_price:.8f}")
                    else:
                        logger.warning(f"No price for {symbol} — skipping this cycle")
                        continue

            # Update price history and peak
            breakout_mod.update_price(key, current_price)
            pos = dynamic_exit.update_peak(pos, current_price)
            pos["current_price"] = current_price  # persist so fallback works next cycle
            pos["last_tvl"]      = current_tvl
            bot_state["positions"][key] = pos

            bq_result = breakout_mod.compute_breakout_quality(key)
            bq        = bq_result.get("breakout_quality", 50)

            price_hist = _get_price_history(key)

            exit_check = dynamic_exit.check_exit(
                position        = pos,
                current_price   = current_price,
                current_tvl     = current_tvl,
                breakout_quality = bq,
                price_history   = price_hist,
            )

            # Score-collapse fast exit: if live score drops to <20 AND we're losing — dead signal, cut it
            if not exit_check["exit"]:
                pnl_now = (current_price - pos["entry_price"]) / pos["entry_price"]
                if bq < 20 and pnl_now < -0.05:
                    exit_check = {"exit": True, "partial": False, "reason": f"score_collapse_bq{bq}", "fraction": 1.0}
                    logger.info(f"⚡ {symbol}: BQ collapsed to {bq} with {pnl_now:+.1%} PnL — fast exit")

            # TVL drain exit: pool being pulled — get out before it's zero
            if not exit_check["exit"] and current_tvl > 0:
                prev_tvl = pos.get("last_tvl", current_tvl)
                if prev_tvl > 0:
                    tvl_drop = (prev_tvl - current_tvl) / prev_tvl
                    from config import MIN_TVL_DROP_EXIT
                    if tvl_drop > MIN_TVL_DROP_EXIT:
                        exit_check = {"exit": True, "partial": False, "reason": f"tvl_drain_{tvl_drop:.0%}", "fraction": 1.0}
                        logger.info(f"🚨 {symbol}: TVL dropped {tvl_drop:.0%} ({prev_tvl:.0f}→{current_tvl:.0f} XRP) — pool drain exit")

            # ── Strategy-aware stale exit ────────────────────────────────────
            # Each strategy has its own max hold time. BURST exits in 1hr,
            # PRE_BREAKOUT gets 3hr. Prevents capital being locked in dead trades.
            if not exit_check["exit"]:
                try:
                    _strat_exits = dynamic_tp_mod._get_strategy_exits(pos)
                    _stale_limit = _strat_exits.get("stale_hours", 2.0)
                    _held_hours  = (now - pos.get("entry_time", now)) / 3600
                    if _held_hours > _stale_limit:
                        _strat_name = pos.get("_godmode_type", "default")
                        exit_check = {
                            "exit": True, "partial": False, "fraction": 1.0,
                            "reason": f"stale_{_strat_name}_{_held_hours:.1f}hr",
                        }
                        logger.info(
                            f"⏰ STALE EXIT {symbol}: {_strat_name} held {_held_hours:.1f}hr "
                            f"> limit {_stale_limit}hr"
                        )
                except Exception as _ste:
                    logger.debug(f"Stale exit check error: {_ste}")

            # ── Dynamic TP Module (Audit #4) — 3-layer exit system ────────────
            # Runs AFTER scoring, BEFORE execution. Overrides existing TP if enabled.
            from config import DYNAMIC_TP_ENABLED
            if DYNAMIC_TP_ENABLED and not exit_check["exit"]:
                try:
                    dt_result = dynamic_tp_mod.should_exit(
                        position=pos,
                        bot_state=bot_state,
                        current_price=current_price,
                        current_tvl=current_tvl,
                        price_history=price_hist,
                    )

                    if dt_result["action"] == "emergency":
                        # Emergency exit — override everything
                        exit_check = {
                            "exit": True,
                            "partial": dt_result["pct"] < 1.0,
                            "reason": f"dynamic_tp_{dt_result['reason']}",
                            "fraction": dt_result["pct"],
                        }
                        logger.warning(
                            f"🚨 DYNAMIC-TP EMERGENCY {symbol}: {dt_result['reason']} — "
                            f"sell {dt_result['pct']:.0%}"
                        )
                    elif dt_result["action"] == "exit":
                        # Planned scale-out
                        exit_check = {
                            "exit": True,
                            "partial": dt_result["pct"] < 1.0,
                            "reason": f"dynamic_tp_{dt_result['reason']}",
                            "fraction": dt_result["pct"],
                        }
                        # Mark profit lock levels as exited (pass tp_flag for new system)
                        dynamic_tp_mod.mark_profit_lock_exit(
                            pos, dt_result["reason"],
                            tp_flag=dt_result.get("_tp_flag")
                        )
                    # If 'hold', fall through to existing TP system as fallback

                except Exception as _dte:
                    logger.debug(f"Dynamic TP error {symbol}: {_dte}")

            if not exit_check["exit"]:
                pnl = (current_price - pos["entry_price"]) / pos["entry_price"]
                logger.info(f"  HOLD {symbol}: pnl={pnl:+.1%} reason={exit_check['reason']}")
                continue

            reason   = exit_check["reason"]
            fraction = exit_check["fraction"]
            partial  = exit_check["partial"]

            # ── Partial exit dedup guard ──────────────────────────────────────
            # Prevent firing the same TP level twice before state updates.
            # If we sold within the last 90s on this same TP level, skip.
            # Dedup: use flag state not time window (90s timer caused TP levels to skip on fast movers)
            if partial and reason.startswith("tp1") and pos.get("tp1_hit"):
                logger.debug(f"[dedup] {symbol}: tp1 already hit — skipping duplicate")
                continue
            if partial and reason.startswith("tp2") and pos.get("tp2_hit"):
                logger.debug(f"[dedup] {symbol}: tp2 already hit — skipping duplicate")
                continue
            if partial and reason.startswith("tp3") and pos.get("tp3_hit"):
                logger.debug(f"[dedup] {symbol}: tp3 already hit — skipping duplicate")
                continue

            tokens_to_sell = pos["tokens_held"] * fraction
            logger.info(f"EXIT {symbol}: {reason} fraction={fraction:.0%} tokens={tokens_to_sell:.4f}")

            exec_result = execution.sell_token(
                symbol         = symbol,
                issuer         = issuer,
                token_amount   = tokens_to_sell,
                expected_price = current_price,
            )

            if exec_result.get("success"):
                xrp_received = exec_result.get("xrp_received", tokens_to_sell * current_price)
                # FIX: pnl_xrp = what we got back minus what this fraction cost us
                pnl_xrp      = xrp_received - (pos["xrp_spent"] * fraction)
                # FIX: pnl_pct should reflect actual XRP return not just price move
                # Price-based pct is misleading after partial sells reduce position size.
                # Use XRP-based pct: (received - spent_fraction) / spent_fraction
                spent_fraction = pos["xrp_spent"] * fraction
                pnl_pct = (pnl_xrp / spent_fraction) if spent_fraction > 0 else 0.0

                # CRITICAL: only update state if sell actually succeeded
                if not exec_result.get("success"):
                    logger.error(f"✗ SELL FAILED {symbol}: {exec_result.get('error')} — position kept in state")
                    continue

                if partial and fraction < 1.0:
                    # Update position
                    pos["tokens_held"]  -= tokens_to_sell
                    pos["xrp_spent"]    *= (1 - fraction)
                    pos["last_sell_ts"]     = time.time()
                    pos["last_sell_reason"] = reason
                    if reason.startswith("tp1"):
                        pos["tp1_hit"] = True
                    elif reason.startswith("tp2"):
                        pos["tp2_hit"] = True
                    elif reason.startswith("tp3"):
                        pos["tp3_hit"] = True
                    bot_state["positions"][key] = pos
                    state_mod.save(bot_state)
                    logger.info(f"✓ PARTIAL EXIT {symbol}: sold {fraction:.0%}, remaining {pos['tokens_held']:.4f}")
                else:
                    # Full exit
                    state_mod.remove_position(bot_state, key)

                    # Build trade record first so ML can log outcome
                    trade = {
                        "symbol":       symbol,
                        "issuer":       issuer,
                        "entry_price":  pos["entry_price"],
                        "exit_price":   exec_result.get("actual_price", current_price),
                        "entry_time":   pos["entry_time"],
                        "exit_time":    now,
                        "xrp_spent":    pos.get("xrp_spent", 0),    # FIX: always store cost basis
                        "xrp_received": xrp_received,               # FIX: always store proceeds
                        "pnl_pct":      pnl_pct,                    # FIX: now XRP-based not price-based
                        "pnl_xrp":      pnl_xrp,
                        "exit_reason":  reason,
                        "chart_state":  pos.get("chart_state"),
                        "score_band":   pos.get("score_band"),
                        "score":        pos.get("score", 0),
                        "entry_tvl":    pos.get("entry_tvl"),
                        "smart_wallets": pos.get("smart_wallets", []),
                    }
                    # ── ML: log exit features ─────────────────────────────────
                    if _ML_AVAILABLE:
                        try:
                            ml_features_mod.log_exit_features(
                                position     = pos,
                                trade_result = trade,
                            )
                        except Exception as _mle:
                            logger.debug(f"[ml] log_exit_features error: {_mle}")

                    state_mod.record_trade(bot_state, trade)
                    brain.update_after_trade({
                        "strategy": pos.get("_godmode_type","unknown"),
                        "pnl_xrp": pnl_xrp,
                        "win": pnl_xrp > 0,
                        "route": pos.get("_godmode_type","unknown"),
                        "entry_price": pos.get("entry_price", 1.0),
                        "exit_price": current_price,
                        "key": key,
                    })
                    logger.info(f"✓ CLOSED {symbol}: pnl={pnl_pct:+.1%} ({pnl_xrp:+.4f} XRP) [{reason}]")
                    dash_log(f"📤 CLOSED {symbol}: {pnl_pct:+.1%} ({pnl_xrp:+.2f} XRP) [{reason}]")
                    update_stats(pnl=pnl_xrp, trades=len(bot_state.get("trade_history", [])), win=(pnl_xrp > 0), loss=(pnl_xrp <= 0))
                    remove_position(symbol)

                    # ── Feed real outcome back into Shadow ML strategy weights ──
                    try:
                        if _SHADOW_ML_AVAILABLE:
                            _shadow_ml.record_real_outcome(
                                symbol        = symbol,
                                strategy_type = pos.get("_godmode_type", "unknown"),
                                entry_price   = pos.get("entry_price", 0),
                                exit_price    = current_price,
                                exit_reason   = reason,
                            )
                    except Exception as _sme:
                        logger.debug(f"[shadow_ml] record_real_outcome error: {_sme}")

                    # Trigger self-learning after every closed trade
                    try:
                        learn_mod.run_learning()
                    except Exception as _le:
                        logger.debug(f"[learn] update failed: {_le}")

                    # Auto-cleanup: sell dust + burn remainder + remove trustline
                    # Triggered on every full position close — recovers 0.20 XRP reserve
                    try:
                        from xrpl.wallet import Wallet as _W
                        from xrpl.clients import JsonRpcClient as _JRC
                        from xrpl.models.transactions import TrustSet as _TS, Payment as _PAY
                        from xrpl.models.amounts import IssuedCurrencyAmount as _ICA
                        from xrpl.transaction import submit_and_wait as _saw
                        from xrpl.models.requests import AccountLines as _AL
                        import os as _os, time as _time
                        _seed = None
                        _secrets_path = _os.path.expanduser("~/workspace/memory/secrets.md")
                        if _os.path.exists(_secrets_path):
                            for _line in open(_secrets_path):
                                if "Seed:" in _line:
                                    _seed = _line.split("Seed:")[-1].strip()
                                    break
                        if not _seed:
                            raise ValueError("no seed")
                        _w = _W.from_seed(_seed)
                        _c = _JRC("https://rpc.xrplclaw.com")
                        # Step 1: sell any remaining dust on DEX
                        _lines = _c.request(_AL(account=_w.address)).result.get("lines", [])
                        _tl = next((l for l in _lines if l.get("account") == issuer), None)
                        if _tl:
                            _dust_bal = float(_tl.get("balance", 0))
                            if _dust_bal > 0:
                                # Try DEX sell first (with generous slippage)
                                try:
                                    _sell_r = execution.sell_token(symbol, issuer, _dust_bal, pos.get("current_price", 0.00001), 0.40)
                                    logger.info(f"🧹 Sold dust {symbol}: {_dust_bal:.6f} tokens → {_sell_r.get('xrp_received',0):.4f} XRP")
                                    _time.sleep(3)
                                except Exception:
                                    pass
                                # Re-check balance — if still > 0, burn to issuer
                                _lines2 = _c.request(_AL(account=_w.address)).result.get("lines", [])
                                _tl2 = next((l for l in _lines2 if l.get("account") == issuer), None)
                                _remaining = float(_tl2.get("balance", 0)) if _tl2 else 0
                                if _remaining > 0:
                                    try:
                                        _burn = _PAY(
                                            account=_w.address,
                                            destination=issuer,
                                            amount=_ICA(currency=currency, issuer=issuer, value=str(_remaining)),
                                            send_max=_ICA(currency=currency, issuer=issuer, value=str(_remaining)),
                                        )
                                        _burn_resp = _saw(_burn, _c, _w)
                                        _burn_r = _burn_resp.result.get("meta", {}).get("TransactionResult", "")
                                        logger.info(f"🔥 Burned dust {symbol}: {_remaining:.6f} tokens → issuer ({_burn_r})")
                                        _time.sleep(3)
                                    except Exception as _be:
                                        logger.debug(f"[cleanup] burn failed: {_be}")
                        # Step 2: remove trustline (balance should now be 0)
                        _tx = _TS(
                            account=_w.address,
                            limit_amount=_ICA(currency=currency, issuer=issuer, value="0"),
                            flags=0x00020000,
                        )
                        _resp = _saw(_tx, _c, _w)
                        _r = _resp.result.get("meta", {}).get("TransactionResult", "")
                        if _r in ("tesSUCCESS", "tecNO_LINE_REDUNDANT"):
                            logger.info(f"🧹 Trustline {symbol} removed — recovered 0.20 XRP reserve")
                        else:
                            logger.warning(f"[cleanup] TrustSet {symbol}: {_r}")
                    except Exception as _ce:
                        logger.warning(f"[cleanup] trustline remove failed for {symbol}: {_ce}")

                    # Short cooldown after hard stop (stop hunt protection: re-enter fast if signal returns)
                    # Only block 5 min after hard_stop — price may bounce right back
                    # Block 15 min after other losses (momentum_stall, lower_highs etc)
                    if pnl_pct < -0.02:
                        cooldown = 300 if "hard_stop" in reason else 900
                        SKIP_REENTRY_SYMBOLS.add(symbol)
                        # Persist to disk so cooldown survives bot restart
                        _now_ts = time.time()
                        _cd_out = dict(_cooldowns) if '_cooldowns' in dir() else {}
                        _cd_out[symbol] = _now_ts
                        try:
                            with open(_cooldown_file, "w") as _f:
                                json.dump(_cd_out, _f)
                        except Exception:
                            pass
                        import threading
                        def _unblock(sym=symbol):
                            import time as _t; _t.sleep(cooldown)
                            SKIP_REENTRY_SYMBOLS.discard(sym)
                            # Also remove from disk after expiry
                            try:
                                _cd = json.load(open(_cooldown_file))
                                _cd.pop(sym, None)
                                with open(_cooldown_file, "w") as _f:
                                    json.dump(_cd, _f)
                            except Exception:
                                pass
                            logger.info(f"🔓 {sym} cooldown expired ({cooldown//60}min) — re-entry allowed")
                        threading.Thread(target=_unblock, daemon=True).start()
                        logger.info(f"⏳ {symbol} on {cooldown//60}min cooldown after {pnl_pct:+.1%} [{reason}]")

                    # Hard-stop blacklist: 3+ hard stops = session-long block (raised from 2)
                    if "hard_stop" in reason:
                        hard_stops = sum(1 for t in bot_state.get("trade_history",[])
                                        if t.get("symbol")==symbol and "hard_stop" in t.get("exit_reason",""))
                        if hard_stops >= 3:
                            SKIP_REENTRY_SYMBOLS.add(symbol)
                            # Persist permanent blacklist to disk too
                            try:
                                _perm = json.load(open(_cooldown_file))
                                _perm[symbol] = _now_ts
                                with open(_cooldown_file, "w") as _f:
                                    json.dump(_perm, _f)
                            except Exception:
                                pass
                            logger.warning(f"⛔ {symbol} permanently blacklisted after {hard_stops} hard stops")
                    relay_bridge.push_trade(symbol=symbol, action="exit", xrp=abs(pnl_xrp), pnl_pct=round(pnl_pct*100,2), exit_reason=reason, score=pos.get("score",0), chart=pos.get("chart_state",""))
                    if pnl_pct < -0.03:
                        relay_bridge.push_warning(symbol=symbol, message=f"Loss exit {pnl_pct:+.1%} [{reason}]", level="caution")


        except Exception as e:
            logger.exception(f"Exit check error {symbol}: {e}")

    return bot_state


def startup(bot_state: Dict) -> Dict:
    """Run startup tasks."""
    logger.info("=== DKTrenchBot v2 Starting ===")
    logger.info(f"Wallet: {BOT_WALLET_ADDRESS}")

    # Reconcile on startup
    try:
        logger.info("Running startup reconcile...")
        reconcile_mod.reconcile(bot_state)
    except Exception as e:
        logger.error(f"Startup reconcile error: {e}")

    # Wallet hygiene on startup
    try:
        logger.info("Running wallet hygiene...")
        wallet_hygiene.run_hygiene(bot_state, force=False)
    except Exception as e:
        logger.error(f"Startup hygiene error: {e}")

    # Run initial token discovery (XRPL-native, 350 token target)
    try:
        import xrpl_amm_discovery as discovery_mod
        logger.info("Running XRPL-native token discovery (target: 350 tokens)...")
        discovered = discovery_mod.run_discovery(force=True)
        logger.info(f"Discovery: {len(discovered)} tokens in active registry")
    except Exception as e:
        logger.warning(f"Startup discovery error (non-fatal): {e}")

    # Start real-time XRPL stream watcher (catches new AMMs + TrustSet bursts instantly)
    try:
        import realtime_watcher
        realtime_watcher.start_background()
        logger.info("📡 Realtime watcher started — catching launches instantly")
    except Exception as e:
        logger.warning(f"Realtime watcher startup error (non-fatal): {e}")

    # Start sniper in background
    try:
        def on_sniper_hit(spec):
            logger.info(f"SNIPER: New token discovered: {spec['symbol']} score={spec['sniper_score']}/5")
        sniper_mod.start_sniper_thread(callback=on_sniper_hit)
    except Exception as e:
        logger.warning(f"Sniper start error: {e}")

    # ── Smart Wallet Auto-Discovery (Audit #1) ────────────────────────────────
    try:
        logger.info("Running smart wallet auto-discovery...")
        discovery_result = wallet_discovery_mod.discover_smart_wallets(force_rescan=True)
        tracked_count = len(discovery_result.get("tracked", []))
        candidate_count = len(discovery_result.get("candidates", []))
        logger.info(f"  Discovered: {candidate_count} candidates, {tracked_count} tracked wallets")
    except Exception as e:
        logger.warning(f"Wallet discovery error (non-fatal): {e}")

    # ── Wallet Cluster Monitor (Audit #2) ─────────────────────────────────────
    try:
        cluster_mod.start_cluster_monitor(bot_state=bot_state)
        logger.info("📡 Wallet cluster monitor started — watching for coordinated entries")
    except Exception as e:
        logger.warning(f"Cluster monitor startup error (non-fatal): {e}")

    return bot_state


def main():
    global _running, _bot_state, _last_report_day

    _bot_state = state_mod.load()
    _bot_state = startup(_bot_state)

    last_reconcile  = time.time()
    last_improve    = _bot_state.get("last_improve", 0)
    last_discovery  = time.time()  # discovery runs every 15 min independently

    logger.info(f"Starting main loop (interval={POLL_INTERVAL_SEC}s)")
    set_running(True)
    dash_log("🟢 DKTrenchBot v2 started — fresh build")
    logger.info("Waiting 3s for RPC rate limit to clear after startup...")
    time.sleep(3)

    while _running:
        cycle_start = time.time()

        try:
            _bot_state = run_cycle(_bot_state)

            # ── 8. Reconcile every 30 min ──────────────────────────────────────
            if time.time() - last_reconcile >= 1800:
                try:
                    logger.info("Running periodic reconcile...")
                    reconcile_mod.reconcile(_bot_state)
                    last_reconcile = time.time()
                except Exception as e:
                    logger.error(f"Reconcile error: {e}")

            # ── 8b. Discovery refresh every 10 min ───────────────────────────
            if time.time() - last_discovery >= 600:
                try:
                    import xrpl_amm_discovery as _disc_mod
                    discovered = _disc_mod.run_discovery()
                    logger.info(f"Discovery refresh: {len(discovered)} tokens in registry")
                    last_discovery = time.time()
                except Exception as _de:
                    logger.debug(f"Discovery refresh error: {_de}")

            # ── 9. Improve every 2 hours ──────────────────────────────────────
            if time.time() - _bot_state.get("last_improve", 0) >= 2 * 3600:
                try:
                    logger.info("Running improve analysis...")
                    improve_mod.run_improve(_bot_state)
                except Exception as e:
                    logger.error(f"Improve error: {e}")
                try:
                    import xrpl_amm_discovery as discovery_mod
                    logger.info("Running XRPL-native dynamic token discovery...")
                    discovered = discovery_mod.run_discovery()
                    logger.info(f"Discovery: {len(discovered)} tokens now in active registry")
                    _bot_state["last_improve"] = time.time()
                except Exception as e:
                    logger.error(f"Discovery error: {e}")

            # Daily report
            today = int(time.time() // 86400)
            if today != _last_report_day:
                try:
                    report_mod.generate_report(_bot_state)
                    _last_report_day = today
                    logger.info("Daily report generated")
                except Exception as e:
                    logger.error(f"Report error: {e}")

            _write_status(_cycle_count, len(_bot_state.get("positions", {})))

        except Exception as e:
            logger.exception(f"Cycle error: {e}")
            _write_status(_cycle_count, 0, str(e))

        # Sleep until next cycle
        elapsed = time.time() - cycle_start
        sleep_for = max(0, POLL_INTERVAL_SEC - elapsed)

        # Update dashboard stats with current balance
        try:
            _bal = bot_state.get("xrp_balance", 0)
            _pnl = sum(t.get("pnl_xrp", 0) for t in bot_state.get("trade_history", []))
            _trades = len(bot_state.get("trade_history", []))
            update_stats(balance=_bal, pnl=_pnl, trades=_trades)
        except Exception:
            pass

        logger.info(f"Cycle done in {elapsed:.1f}s — sleeping {sleep_for:.0f}s")

        # Interruptible sleep
        for _ in range(int(sleep_for)):
            if not _running:
                break
            time.sleep(1)

    logger.info("=== Bot stopped cleanly ===")
    state_mod.save(_bot_state)


if __name__ == "__main__":
    main()

# EOF
