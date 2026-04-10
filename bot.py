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
# import brain  # DISABLED — no trained ML model yet (need 50+ trades first)
import ml_trainer as ml_trainer_mod
_ml_model = None  # Will be loaded/trained when enough data available

# ── New Modules (Audit Improvements) ───────────────────────────────────────────
import new_wallet_discovery as wallet_discovery_mod
# import wallet_cluster as cluster_mod  # DISABLED — removed, WebSocket failing constantly
# import alpha_recycler as recycler_mod  # DISABLED — depends on smart_money tracked wallets
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

# DISABLED — improve_loop removed for optimization
_IMPROVE_LOOP_AVAILABLE = False

# ── ML Model Training Check ──────────────────────────────────────────────────
# Auto-trains XGBoost-like model when 50+ completed trades available
_ml_model = ml_trainer_mod.load_model()  # Load existing model if any
if _ml_model:
    logger.info(f"ML model loaded: trained on {_ml_model.get('num_trades', 0)} trades, base WR: {_ml_model.get('base_win_rate', 0):.1%}")
else:
    logger.info("No ML model yet — will auto-train when 50+ trades completed")

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

    # ── 0. Hot token scan (every 4th cycle ~4min) ────────────────────────────
    if _cycle_count % 4 == 1:
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
            # recycle_signals = recycler_mod.scan_alpha_recycling  # DISABLED(bot_state)
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

    # ── 0f. ML model training check (every 20th cycle) ───────────────────────
    if _cycle_count % 20 == 0:
        try:
            global _ml_model
            new_model = ml_trainer_mod.check_and_train()
            if new_model:
                _ml_model = new_model
                logger.info(f"🧠 ML model trained/updated: {new_model.get('num_trades', 0)} trades, base WR: {new_model.get('base_win_rate', 0):.1%}")
        except Exception as _mle:
            logger.debug(f"[ml] training check: {_mle}")

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
        # FIX #4: tag accumulation tokens so they bypass chart_state gate
        for c in candidates:
            if c.get("bucket") == "accumulation":
                c["_accumulation_mode"] = True
        logger.info(f"Scanner: {len(candidates)} candidates | "
                    f"fresh={len(scan_results['fresh_momentum'])} "
                    f"sustained={len(scan_results['sustained_momentum'])} "
                    f"accumulation={len(scan_results.get('accumulation', []))}")
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
                # _shadow_ml.run_cycle(candidates, _market_data)  # DISABLED
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
                        _rt_sym = _rt_trigger.get("symbol", "")
                        _rt_cur = _rt_trigger.get("currency", "")
                        _rt_iss = _rt_trigger.get("issuer", "")
                        _rt_tvl = 0
                        try:
                            _, _rt_tvl, _, _ = scanner.get_token_price_and_tvl(_rt_sym, _rt_iss, currency=_rt_cur)
                            _rt_tvl = _rt_tvl or 500
                        except Exception:
                            _rt_tvl = 500
                        _rt_cand = {
                            "symbol":        _rt_sym,
                            "currency":      _rt_cur,
                            "issuer":        _rt_iss,
                            "key":           _rt_key,
                            "tvl_xrp":       _rt_tvl,
                            "tvl":           _rt_tvl,
                            "price":         _rt_trigger.get("price", 0),
                            "score":         0,
                            "_clob_launch":  True,
                            "_burst_mode":   True,
                            "burst_count":   30,
                            "clob_vol_5min": _rt_trigger.get("vol_5min_xrp", 0),
                            "amm": {"amount": str(int(_rt_tvl * 1e6)), "amount2": {"currency": _rt_cur, "issuer": _rt_iss, "value": "1000000"}, "trading_fee": 1000, "account": _rt_iss},
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
                # Fetch live TVL so burst candidates don't hit the >10K stale-zone skip
                _burst_tvl = _alert.get("xrp_tvl", 0) or 0
                if _burst_tvl <= 0:
                    try:
                        _, _burst_tvl, _, _ = scanner.get_token_price_and_tvl(_sym, _iss, currency=_cur)
                        _burst_tvl = _burst_tvl or 500
                    except Exception:
                        _burst_tvl = 500
                _burst_cand = {
                    "symbol":      _sym,
                    "currency":    _cur,
                    "issuer":      _iss,
                    "key":         _cand_key,
                    "tvl_xrp":     _burst_tvl,   # use tvl_xrp — what bot.py reads
                    "tvl":         _burst_tvl,
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
                # Fetch live TVL for CLOB candidates too
                _clob_tvl = 0
                try:
                    _, _clob_tvl, _, _ = scanner.get_token_price_and_tvl(_sym, _iss, currency=_cur)
                    _clob_tvl = _clob_tvl or 500
                except Exception:
                    _clob_tvl = 500
                _clob_cand = {
                    "symbol":        _sym,
                    "currency":      _cur,
                    "issuer":        _iss,
                    "key":           _cand_key,
                    "tvl_xrp":       _clob_tvl,   # real TVL — prevents stale-zone skip
                    "tvl":           _clob_tvl,
                    "price":         _cprice if _cprice > 0 else None,
                    "score":         0,
                    "_clob_launch":  True,
                    "_burst_mode":   True,  # also treat as burst — bypasses chart/price gates
                    "burst_count":   _bc,
                    "clob_vol_5min": _vol,
                    # Synthesize AMM stub so safety check doesn't crash on missing AMM
                    "amm": {"amount": str(int(_clob_tvl * 1e6)), "amount2": {"currency": _cur, "issuer": _iss, "value": "1000000"}, "trading_fee": 1000, "account": _iss},
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
            # ── Hex symbol decode: XRPL currencies can be 40-char hex strings.
            # The memecoin/stablecoin filters compare against human-readable names,
            # so we must decode hex → ASCII here before ANY filter checks.
            if isinstance(symbol, str) and len(symbol) == 40 and all(c in "0123456789ABCDEFabcdef" for c in symbol):
                try:
                    _decoded = bytes.fromhex(symbol).rstrip(b"\x00").decode("utf-8", errors="replace")
                    if _decoded and _decoded.isprintable():
                        symbol = _decoded
                        candidate["symbol"] = symbol  # update in-place so downstream uses decoded name
                except Exception:
                    pass
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

            # For burst candidates without price — fetch live price now
            if not price and candidate.get("_burst_mode"):
                try:
                    _bp, _bt, _, _ = scanner.get_token_price_and_tvl(symbol, issuer, currency=currency)
                    if _bp and _bp > 0:
                        price = _bp
                        candidate["price"] = price
                        if _bt and _bt > 0:
                            candidate["tvl_xrp"] = _bt
                            tvl = _bt
                    logger.debug(f"Burst price fetch {symbol}: {price}")
                except Exception:
                    pass

            # Synthesize AMM stub for burst/CLOB candidates so safety/routing don't crash
            if not amm and (candidate.get("_burst_mode") or candidate.get("_clob_launch")):
                _stub_tvl = candidate.get("tvl_xrp", tvl) or 500
                amm = {"amount": str(int(_stub_tvl * 1e6)), "amount2": {"currency": currency, "issuer": issuer, "value": "1000000"}, "trading_fee": 1000, "account": issuer}

            if not amm or not price:
                if candidate.get("_burst_mode") or candidate.get("_clob_launch"):
                    logger.info(f"SKIP {symbol}: burst candidate — no price/AMM available")
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

                # ── STRATEGY ALLOWLIST — operator directive Apr 9 ────────────
                # BACKTEST RESULTS (current token universe, 14d sim):
                #   burst       : 67% WR | +1200 XRP | avg_win +5.3 XRP  ✅ AUTHORIZED
                #   pre_breakout: 36% WR | +1463 XRP | avg_win +13.1 XRP ✅ AUTHORIZED
                #   micro_scalp : 71% WR |  +158 XRP  — small contrib, keep
                #   clob_launch : 36% WR |   +71 XRP  — reclassify as burst if burst-backed
                #   trend       : 18% WR |   -0.9 XRP ❌ BLOCKED — outside our MC zone
                #
                # Rule: BLOCK trend (TVL > 200K = way outside our $400-$5K MC sweet spot).
                # clob_launch → reclassify as burst if TS burst signal present.
                # micro_scalp → keep (71% WR in backtest, same TVL tier as our sweet spot).
                _classified_type = candidate.get("_godmode_type", "")
                _chart_pb = candidate.get("chart_state", "") == "pre_breakout"
                _is_burst_flag = bool(candidate.get("_burst_mode") or candidate.get("_clob_launch"))

                if _classified_type == "trend":
                    logger.info(f"SKIP {symbol}: strategy=trend — TVL > 200K outside sweet spot (18% WR, -0.9 XRP PnL)")
                    continue
                elif _classified_type == "clob_launch":
                    if _is_burst_flag:
                        candidate["_godmode_type"] = "burst"
                        logger.info(f"  ↪️  {symbol}: clob_launch → burst (TS burst signal confirmed)")
                    # else: let it through as clob_launch — scores gate will handle it
                elif not _classified_type and not _chart_pb and not _is_burst_flag:
                    logger.debug(f"SKIP {symbol}: no strategy signal (type=none, chart={candidate.get('chart_state','?')})")
                    continue

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
                    # FIX #4: Accumulation mode — TVL growing, price flat = smart money loading
                    elif candidate.get("_accumulation_mode"):
                        logger.info(f"✅ {symbol}: chart_state={chart_state} ALLOWED — accumulation pattern (TVL building)")
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

                # ── TVL HARD FLOOR — kill $0 MC / near-zero liquidity tokens ──
                # Operator directive: focus on $400–$2K MC sweet spot.
                # Any token with TVL < 400 XRP has essentially $0 market cap —
                # no liquidity, no real price discovery. Hard skip.
                _entry_tvl = candidate.get("tvl_xrp", tvl)
                if _entry_tvl < 100:
                    logger.info(f"SKIP {symbol}: TVL={_entry_tvl:.0f} XRP < 100 XRP (~$200 MC) — true dust, not our tier")
                    continue

                # ── TVL TIER GATE — ghost/micro/small with score band 42-52 ──
                # Operator sweet spot: $400–$2,000 MC. At ~$2/XRP, AMM holds ~50% MC in XRP:
                #   ghost  (<200 XRP TVL)        ~<$400 MC  — burst/realtime signal only
                #   micro  (200–500 XRP TVL)     ~$400–$1K MC  — CORE sweet spot
                #   small  (500–2,500 XRP TVL)   ~$1K–$5K MC   — secondary sweet spot
                # Hard ceiling: >2,500 XRP TVL (~$5K MC) = stale/discovered zone — hard skip.
                # Score band: 42–52. Pre-breakout chart_state requires score ≥ 45.
                _tier_tvl = _entry_tvl
                if _tier_tvl > 2_500:
                    logger.info(f"SKIP {symbol}: TVL={_tier_tvl:.0f} XRP (~${_tier_tvl*2:.0f} MC) > sweet spot ceiling — stale/discovered")
                    continue

                # Classify tier
                if _tier_tvl < 200:
                    _tvl_tier = "ghost"
                    # Ghost (<$400 MC): only enter on strong burst/realtime — too early for scan
                    _is_ghost_burst = (candidate.get("_burst_mode") or candidate.get("_clob_launch")
                                       or candidate.get("signal_type") == "trustset_velocity")
                    if not _is_ghost_burst:
                        logger.info(f"SKIP {symbol}: ghost tier TVL={_tier_tvl:.0f} XRP (~${_tier_tvl*2:.0f} MC) — needs burst/realtime")
                        continue
                elif _tier_tvl <= 500:
                    _tvl_tier = "micro"   # $400–$1K MC — core sweet spot
                else:
                    _tvl_tier = "small"   # $1K–$5K MC — secondary sweet spot

                candidate["_tvl_tier"] = _tvl_tier
                logger.debug(f"  [tier] {symbol}: {_tvl_tier} TVL={_tier_tvl:.0f} XRP")

                # Pre-breakout score gate: ≥45 required (backtest best WR tier)
                _chart = candidate.get("chart_state", chart_state)
                if _chart == "pre_breakout" and total_score < 45:
                    logger.info(f"SKIP {symbol}: pre_breakout score={total_score} < 42 gate — backtest 42-44 band has 60% WR")
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
                    # Payment / fintech infrastructure (NOT memes)
                    "XRPAYNET","PAYNET","XPAYN","XPAY","XRPN","XRPL","XRPLFDN",
                    "RIPPLE","RIPPLEX","XRPF","XRPH","XRPP","XRPS","XRPT","XRPU","XRPV",
                    # Utility / bridge protocols (frequently slip through)
                    "BRIDGE","SWAP","XSWAP","XBRIDGE","REMIT","REMITTANCE",
                    "WALLET","WALLT","CUSTODY","EXCHANGE","EXCH",
                    # Index / tracker tokens
                    "INDEX","IDX","TRACKER","PORTFOLIO",
                }
                NON_MEME_PREFIXES = ("W",)   # wrapped tokens
                NON_MEME_SUFFIXES = ("IOU", "LP", "POOL", "VAULT")
                # Substring keyword filter — catches utility tokens regardless of exact name
                NON_MEME_SUBSTRINGS = (
                    "PAYNET","PAYMENT","REMIT","BRIDGE","FINANCE","PROTOCOL",
                    "NETWORK","CHAIN","LAYER","TOKEN","EXCHANGE","CUSTODY","WALLET",
                )
                if sym_up in NON_MEME_SKIP:
                    logger.debug(f"SKIP {symbol}: non-meme token — operator meme-only directive")
                    continue
                if any(sym_up.startswith(p) for p in NON_MEME_PREFIXES):
                    logger.debug(f"SKIP {symbol}: wrapped/bridged token — no meme upside")
                    continue
                if any(sym_up.endswith(s) for s in NON_MEME_SUFFIXES):
                    logger.debug(f"SKIP {symbol}: LP/vault token — not a meme")
                    continue
                if any(kw in sym_up for kw in NON_MEME_SUBSTRINGS):
                    logger.debug(f"SKIP {symbol}: utility keyword in name — not a meme")
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
                # BYPASS for burst/CLOB launch: these are NEW tokens with no price history.
                # BQ is meaningless at launch — the signal IS the burst count + volume.
                _is_burst_signal = candidate.get("_burst_mode") or candidate.get("_clob_launch")
                if bq < 40 and not _is_burst_signal:
                    logger.info(f"SKIP {symbol}: bq={bq} < 40 minimum (weak breakout quality)")
                    continue
                elif bq < 40 and _is_burst_signal:
                    logger.info(f"  ⚡ BQ bypass {symbol}: bq={bq} but burst/CLOB signal — proceeding")

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
                    # Burst/CLOB signals bypass stale-zone: real TVL may be low,
                    # but default 99999 was polluting the check. If it's a burst
                    # with real TVL now, allow it.
                    if candidate.get("_burst_mode") or candidate.get("_clob_launch"):
                        _trade_mode = "hold"
                        logger.info(f"  ⚡ Stale-zone bypass {symbol}: burst/CLOB signal overrides TVL={_tvl:.0f}")
                    else:
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
                            "wallet_cluster_active": False,  # DISABLED
                            "alpha_signal_active": bool(_is_ts_burst),
                            "ts_burst_active": _is_ts_burst,
                            "ts_burst_count": _ts_burst_count,
                            "ml_probability": 0.5,
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

            # ── ML Prediction filter (if model trained) ───────────────────────
            if _ml_model and total_score >= SCORE_TRADEABLE:
                try:
                    # Build features for prediction
                    ml_features = {
                        "score": total_score / 100.0,  # normalize to 0-1
                        "tvl_xrp": tvl / 10000.0 if tvl > 0 else 0,  # normalize
                        "momentum": candidate.get("momentum_score", 0) / 100.0,
                        "ts_burst_1h": min(candidate.get("ts_burst_1h", 0) / 50.0, 1.0),
                        "concentration_pct": candidate.get("concentration_pct", 0) / 100.0,
                        "strategy_burst": 1 if candidate.get("_godmode_type") == "burst" else 0,
                        "strategy_pre_breakout": 1 if candidate.get("_godmode_type") == "pre_breakout" else 0,
                        "strategy_micro_scalp": 1 if candidate.get("_godmode_type") == "micro_scalp" else 0,
                        "strategy_clob_launch": 1 if candidate.get("_godmode_type") == "clob_launch" else 0,
                        "strategy_trend": 1 if candidate.get("_godmode_type") == "trend" else 0,
                    }
                    win_prob = ml_trainer_mod.predict_win_probability(_ml_model, ml_features)
                    
                    # Filter: only enter if predicted win probability > 55%
                    ML_CONFIDENCE_THRESHOLD = 0.55
                    if win_prob < ML_CONFIDENCE_THRESHOLD:
                        logger.info(f"🧠 ML FILTER: {symbol} blocked — predicted WR {win_prob:.1%} < {ML_CONFIDENCE_THRESHOLD:.0%} threshold")
                        continue
                    else:
                        logger.info(f"🧠 ML PASS: {symbol} — predicted WR {win_prob:.1%} (confidence OK)")
                except Exception as _ml_err:
                    logger.debug(f"[ml] prediction error for {symbol}: {_ml_err}")
                    # Don't block on ML errors — fall through to normal execution

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
                            "tvl_xrp":       candidate.get("tvl_xrp", tvl),
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

                    # Slippage guard: SKIP position if entry slippage > 15%
                    # NOTE: Raised from 2.5% → 15% after removing min_tokens floor in execution.py
                    # With dust_min="1" IOC fills are now accepted at any price — slippage is checked here.
                    # Meme tokens on thin AMMs regularly show 5-10% fill slippage which still prints profit.
                    # Above 15% = over-chased, bad fill, cut immediately.
                    # SKIP slippage check if expected_price was 0 (CLOB-only token, no AMM baseline) —
                    # division by ~0 produces garbage slippage values in the billions of percent.
                    _expected_for_slippage = exec_result.get("expected_price", 0)
                    if _expected_for_slippage <= 0:
                        actual_slippage = 0.0  # can't compute meaningful slippage — trust the fill
                    if actual_slippage > 0.15:
                        logger.warning(f"🚫 {symbol}: entry slippage {actual_slippage:.1%} > 15% gate — attempting immediate sell to recover XRP")
                        _slippage_token = {
                            "symbol": symbol, "issuer": issuer,
                            "tvl_xrp": candidate.get("tvl_xrp", tvl),
                        }
                        try:
                            sell_result = execution.sell_token(
                                symbol         = symbol,
                                issuer         = issuer,
                                token_amount   = tokens_received,
                                expected_price = actual_price,
                                slippage_tolerance = brain.predict_slippage(_slippage_token, final_size),
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
            # Concentration risk: XRPL meme tokens often split supply across wallets
            # for legitimate reasons (LP provisioning, marketing, vesting).
            # Only penalize extreme concentration (>50%), block at >70%.
            conc_penalty = 0
            for w in warnings:
                if "top_holder" in w and "%" in w:
                    try:
                        pct = float(w.split("top_holder:")[1].split("%")[0])
                        if pct >= 70:
                            # Extreme concentration — heavy penalty (but safety.py already blocked)
                            conc_penalty = 15
                            logger.info(f"  ⚠️  {symbol}: EXTREME concentration {pct:.0f}% → score penalty -{conc_penalty}")
                        elif pct >= 50:
                            # High but acceptable for XRPL memes (supply control pattern)
                            conc_penalty = 5
                            logger.info(f"  ℹ️  {symbol}: high concentration {pct:.0f}% (acceptable for XRPL memes) → penalty -{conc_penalty}")
                        else:
                            # Normal range, no penalty
                            conc_penalty = 0
                    except:
                        conc_penalty = 3
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
        def _on_cluster_alert(alert: dict):
            """Realtime sniper callback — DISABLED: smart_cluster signal showed 0 wins, spray-and-pray wallets."""
            return  # DISABLED Apr 9 2026 — false signal, same 2 wallets buying everything indiscriminately
            try:
                import realtime_sniper
                import scanner as _sc
                sym      = alert.get("symbol", "")
                tok_key  = alert.get("token", "")
                wallets  = alert.get("wallets", [])
                if not sym or not tok_key or len(wallets) < 2:
                    return
                parts    = tok_key.split(":")
                currency = parts[0] if len(parts) > 0 else ""
                issuer   = parts[1] if len(parts) > 1 else ""
                if not currency or not issuer:
                    return
                # Get current burst count for this token
                import realtime_watcher as _rtw
                burst = len(_rtw._trustset_times.get(tok_key, []))
                # Get live price + TVL
                price, tvl, _, _ = _sc.get_token_price_and_tvl(sym, issuer, currency=currency)
                realtime_sniper.on_smart_cluster(
                    symbol=sym, currency=currency, issuer=issuer,
                    wallets=wallets, tvl_xrp=tvl, price=price or 0.0,
                    burst_count=burst,
                )
            except Exception as _cbe:
                logger.debug(f"Cluster alert callback error: {_cbe}")

        # cluster_mod.start_cluster_monitor  # DISABLED(bot_state=bot_state, on_alert=_on_cluster_alert)
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
