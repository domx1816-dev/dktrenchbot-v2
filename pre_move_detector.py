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