"""
14-Day Backtest — DKTrenchBot v2 MASTERPIECE CONFIG
Starting Balance: 183 XRP
Dynamic sizing, 10 max positions, quality filters
"""

import json
import requests
import time
import random
from datetime import datetime, timezone
from collections import defaultdict

CLIO_URL = "https://rpc.xrplclaw.com"
REPORT_PATH = "/home/agent/workspace/trading-bot-v2/state/backtest_masterpiece.md"

STARTING_BALANCE = 183.0
MAX_TOKENS = 30

# ── Masterpiece Config ─────────────────────────────────────────────────
SCORE_THRESHOLD   = 30        # Entry threshold (wide net)
SCORE_ELITE       = 65        # Elite tier for sizing
SCORE_NORMAL      = 50        # Normal tier
SCORE_SMALL       = 40        # Small tier

MIN_TVL_XRP       = 200       # Quality filter
MAX_POSITIONS     = 10        # Concurrent positions

# Dynamic sizing (% of current balance)
SIZE_ELITE_PCT    = 0.20      # 20%
SIZE_NORMAL_PCT   = 0.12      # 12%
SIZE_SMALL_PCT    = 0.06      # 6%

# Hard caps
MAX_TRADE_XRP     = 100.0
MIN_TRADE_XRP     = 3.0

# Exit rules (Masterpiece)
HARD_STOP_PCT     = 0.30      # -30% hard stop (trailing covers earlier)
TRAIL_STOP_PCT    = 0.30      # -30% from peak (trailing stop)

# TP ladder
TP1_MULT          = 2.0       # 2x → sell 50%
TP1_SELL_FRAC     = 0.50
TP2_MULT          = 3.0       # 3x → sell 20% of original
TP2_SELL_FRAC     = 0.20
TP3_MULT          = 5.0       # 5x → remaining 15%

SLIPPAGE_PCT      = 0.10      # 10% slippage buffer

NOW = time.time()
BACKTEST_START = NOW - (14 * 86400)

def rpc(method, params):
    try:
        r = requests.post(CLIO_URL, json={"method": method, "params": [params]}, timeout=20)
        return r.json().get("result", {})
    except Exception as e:
        return {"error": str(e)}

def get_amm_info(currency, issuer):
    return rpc("amm_info", {
        "asset": {"currency": "XRP"},
        "asset2": {"currency": currency, "issuer": issuer},
        "ledger_index": "validated"
    })

def get_amm_account_txs(account, limit=400):
    all_txs = []
    marker = None
    for _ in range(10):
        params = {"account": account, "forward": True, "limit": limit,
                  "ledger_index_min": -1, "ledger_index_max": -1}
        if marker:
            params["marker"] = marker
        result = rpc("account_tx", params)
        txs = result.get("transactions", [])
        all_txs.extend(txs)
        marker = result.get("marker")
        if not marker or not txs:
            break
        time.sleep(0.2)
    return all_txs

def extract_price_from_tx(tx_obj, token_currency, token_issuer):
    tx = tx_obj.get("tx", tx_obj.get("tx_json", {}))
    meta = tx_obj.get("meta", tx_obj.get("metaData", {}))
    if not tx or not meta:
        return None
    close_time = tx.get("date", 0)
    if not close_time:
        return None
    ts = close_time + 946684800
    if ts < BACKTEST_START:
        return None
    tx_type = tx.get("TransactionType", "")
    if tx_type not in ("AMMSwap", "OfferCreate", "Payment"):
        return None
    affected = meta.get("AffectedNodes", [])
    xrp_delta = token_delta = 0
    for node in affected:
        for node_type in ("ModifiedNode", "CreatedNode", "DeletedNode"):
            if node_type not in node:
                continue
            n = node[node_type]
            if n.get("LedgerEntryType") != "AMMState":
                continue
            ff = n.get("FinalFields", {})
            pf = n.get("PreviousFields", {})
            if not pf:
                continue
            def parse_amount(a):
                if isinstance(a, str):
                    return float(a) / 1e6, "XRP"
                elif isinstance(a, dict):
                    return float(a.get("value", 0)), a.get("currency", "")
                return 0, ""
            for field in ["Amount", "Amount2"]:
                if field in ff and field in pf:
                    fv, fc = parse_amount(ff[field])
                    pv, pc = parse_amount(pf[field])
                    delta = fv - pv
                    if fc == "XRP":
                        xrp_delta += delta
                    elif fc == token_currency:
                        token_delta += delta
    if xrp_delta != 0 and token_delta != 0:
        return (ts, abs(xrp_delta) / abs(token_delta))
    return None

def reconstruct_price_series(txs, token_currency, token_issuer):
    prices = []
    for tx_obj in txs:
        r = extract_price_from_tx(tx_obj, token_currency, token_issuer)
        if r:
            prices.append(r)
    prices.sort(key=lambda x: x[0])
    return prices

def build_ohlc(prices, interval_sec=3600):
    if not prices:
        return []
    bars = {}
    for ts, price in prices:
        bar_ts = int(ts // interval_sec) * interval_sec
        if bar_ts not in bars:
            bars[bar_ts] = {"open": price, "high": price, "low": price, "close": price, "ts": bar_ts}
        else:
            bars[bar_ts]["high"] = max(bars[bar_ts]["high"], price)
            bars[bar_ts]["low"] = min(bars[bar_ts]["low"], price)
            bars[bar_ts]["close"] = price
    return sorted(bars.values(), key=lambda x: x["ts"])

def score_token(tvl_xrp, momentum_pct):
    """Masterpiece scoring — TVL quality + momentum"""
    if tvl_xrp >= 100000: tvl_score = 50
    elif tvl_xrp >= 10000: tvl_score = 35
    elif tvl_xrp >= 2000: tvl_score = 25
    elif tvl_xrp >= 500: tvl_score = 15
    else: tvl_score = 8

    if momentum_pct >= 10: mom_score = 50
    elif momentum_pct >= 5: mom_score = 40
    elif momentum_pct >= 2: mom_score = 30
    elif momentum_pct >= 1: mom_score = 20
    else: mom_score = 0

    # Confidence multiplier simulation
    # Real bot has cluster, alpha, ML, bull, smart wallet signals
    # Simulate with a probabilistic boost based on score tier
    base = min(100, tvl_score + mom_score)
    return base

def determine_size(score, balance):
    """Dynamic sizing based on score tier and current balance"""
    if score >= SCORE_ELITE:
        size = balance * SIZE_ELITE_PCT
    elif score >= SCORE_NORMAL:
        size = balance * SIZE_NORMAL_PCT
    elif score >= SCORE_SMALL:
        size = balance * SIZE_SMALL_PCT
    else:
        size = balance * SIZE_SMALL_PCT
    # Apply caps
    size = min(size, MAX_TRADE_XRP)
    size = max(size, MIN_TRADE_XRP)
    return size

def has_momentum(bars, i, threshold_pct=1.0, readings=2):
    if i < readings:
        return False
    prev = bars[i - readings]["close"]
    curr = bars[i]["close"]
    if prev <= 0:
        return False
    return (curr - prev) / prev * 100 >= threshold_pct

def is_pre_breakout(bars, i, lookback=24):
    if i < 2:
        return False
    start = max(0, i - lookback)
    local_high = max(b["high"] for b in bars[start:i+1])
    return bars[i]["close"] >= local_high * 0.80

def simulate_portfolio(token_bars_list, starting_balance):
    """
    Multi-position simulation across all tokens simultaneously.
    Processes bars hour by hour to allow concurrent positions.
    """
    # Build unified timeline
    all_timestamps = sorted(set(
        b["ts"] for tok_bars in token_bars_list for b in tok_bars
    ))

    # Index bars by token
    token_index = {}
    for tok_name, bars in token_bars_list:
        token_index[tok_name] = {b["ts"]: b for b in bars}

    balance = starting_balance
    positions = {}   # tok_name → position dict
    all_trades = []

    for ts in all_timestamps:
        # ── Process exits first ──
        to_close = []
        for tok_name, pos in positions.items():
            bar = token_index[tok_name].get(ts)
            if not bar:
                continue
            price = bar["close"]
            entry = pos["entry_price"]
            peak = pos["peak_price"]

            if price > peak:
                pos["peak_price"] = price
                peak = price

            pnl_pct = (price - entry) / entry

            # Apply slippage to exit price
            exit_price = price * (1 - SLIPPAGE_PCT)
            realized_pct = (exit_price - entry) / entry

            closed = False
            exit_reason = None

            # Hard stop -30%
            if realized_pct <= -HARD_STOP_PCT:
                exit_reason = "hard_stop"
                closed = True

            # Trail stop -30% from peak
            elif exit_price <= peak * (1 - TRAIL_STOP_PCT):
                exit_reason = "trail_stop"
                closed = True

            # TP1: 2x → sell 50%
            elif realized_pct >= (TP1_MULT - 1) and not pos.get("tp1_done"):
                pos["tp1_done"] = True
                sell_xrp = pos["size_xrp"] * TP1_SELL_FRAC
                pnl_from_tp = sell_xrp * realized_pct
                pos["realized_pnl"] = pos.get("realized_pnl", 0) + pnl_from_tp
                pos["remaining_frac"] -= TP1_SELL_FRAC
                balance += pnl_from_tp

            # TP2: 3x → sell 20%
            if realized_pct >= (TP2_MULT - 1) and not pos.get("tp2_done"):
                pos["tp2_done"] = True
                sell_xrp = pos["size_xrp"] * TP2_SELL_FRAC
                pnl_from_tp = sell_xrp * realized_pct
                pos["realized_pnl"] = pos.get("realized_pnl", 0) + pnl_from_tp
                pos["remaining_frac"] -= TP2_SELL_FRAC
                balance += pnl_from_tp

            # TP3: 5x → full exit remaining
            if realized_pct >= (TP3_MULT - 1) and not closed:
                exit_reason = "tp3"
                closed = True

            # Stale exit: 6 hours
            bars_held = (ts - pos["entry_ts"]) / 3600
            if bars_held >= 6 and not closed:
                exit_reason = "stale_exit"
                closed = True

            if closed:
                final_pnl = pos["size_xrp"] * pos["remaining_frac"] * realized_pct
                total_pnl = pos.get("realized_pnl", 0) + final_pnl
                balance += final_pnl
                all_trades.append({
                    "symbol": tok_name,
                    "entry_ts": pos["entry_ts"],
                    "exit_ts": ts,
                    "entry_price": entry,
                    "exit_price": exit_price,
                    "pnl_pct": realized_pct * 100,
                    "pnl_xrp": total_pnl,
                    "exit_reason": exit_reason,
                    "size_xrp": pos["size_xrp"],
                    "score": pos["score"]
                })
                to_close.append(tok_name)

        for t in to_close:
            del positions[t]

        # ── Process entries ──
        if len(positions) < MAX_POSITIONS:
            for tok_name, bars in token_bars_list:
                if tok_name in positions:
                    continue
                if len(positions) >= MAX_POSITIONS:
                    break

                bar = token_index[tok_name].get(ts)
                if not bar:
                    continue

                # Get recent bars for this token
                tok_bars = [b for b in token_index[tok_name].values() if b["ts"] <= ts]
                tok_bars.sort(key=lambda x: x["ts"])
                i = len(tok_bars) - 1

                if i < 4:
                    continue

                price = bar["close"]
                tvl_xrp = bars[1] if isinstance(bars, tuple) else 0

                mom_2bar = 0
                if i >= 2 and tok_bars[i-2]["close"] > 0:
                    mom_2bar = (price - tok_bars[i-2]["close"]) / tok_bars[i-2]["close"] * 100

                score = score_token(getattr(tok_name, 'tvl', 1000), mom_2bar)

                pre_bo = is_pre_breakout(tok_bars, i)
                mom_ok = has_momentum(tok_bars, i, threshold_pct=1.0, readings=2)

                if pre_bo and mom_ok and score >= SCORE_THRESHOLD:
                    # Apply slippage to entry
                    entry_price = price * (1 + SLIPPAGE_PCT)
                    size = determine_size(score, balance)

                    if size < MIN_TRADE_XRP or balance - size < 10:
                        continue

                    balance -= 0  # size is position, PnL applied on exit
                    positions[tok_name] = {
                        "entry_price": entry_price,
                        "peak_price": entry_price,
                        "entry_ts": ts,
                        "size_xrp": size,
                        "remaining_frac": 1.0,
                        "score": score,
                        "tp1_done": False,
                        "tp2_done": False,
                        "realized_pnl": 0.0
                    }

    # Close any open positions at end
    for tok_name, pos in positions.items():
        last_bar = max(token_index[tok_name].values(), key=lambda b: b["ts"], default=None)
        if not last_bar:
            continue
        price = last_bar["close"]
        realized_pct = (price - pos["entry_price"]) / pos["entry_price"]
        final_pnl = pos["size_xrp"] * pos["remaining_frac"] * realized_pct
        total_pnl = pos.get("realized_pnl", 0) + final_pnl
        balance += final_pnl
        all_trades.append({
            "symbol": tok_name,
            "entry_ts": pos["entry_ts"],
            "exit_ts": last_bar["ts"],
            "entry_price": pos["entry_price"],
            "exit_price": price,
            "pnl_pct": realized_pct * 100,
            "pnl_xrp": total_pnl,
            "exit_reason": "end_of_data",
            "size_xrp": pos["size_xrp"],
            "score": pos["score"]
        })

    return all_trades, balance

def fmt_ts(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")

# ─── Simplified single-token simulation (per token, then aggregate) ───────────
def simulate_trades_single(bars, tvl_xrp, symbol, balance_ref):
    """Single-token simulation for the aggregate approach"""
    trades = []
    position = None

    for i, bar in enumerate(bars):
        if i < 4:
            continue
        price = bar["close"]

        if position:
            entry = position["entry_price"]
            peak = position["peak_price"]
            size_xrp = position["size_xrp"]

            if price > peak:
                position["peak_price"] = price
                peak = price

            pnl_pct = (price - entry) / entry
            exit_price = price * (1 - SLIPPAGE_PCT)
            realized_pct = (exit_price - entry) / entry

            closed = False
            exit_reason = None

            if realized_pct <= -HARD_STOP_PCT:
                exit_reason = "hard_stop"
                closed = True
            elif exit_price <= peak * (1 - TRAIL_STOP_PCT):
                exit_reason = "trail_stop"
                closed = True

            if not closed and realized_pct >= (TP1_MULT - 1) and not position.get("tp1_done"):
                position["tp1_done"] = True
                pnl = size_xrp * TP1_SELL_FRAC * realized_pct
                position["realized_pnl"] = position.get("realized_pnl", 0) + pnl
                position["remaining_frac"] -= TP1_SELL_FRAC

            if not closed and realized_pct >= (TP2_MULT - 1) and not position.get("tp2_done"):
                position["tp2_done"] = True
                pnl = size_xrp * TP2_SELL_FRAC * realized_pct
                position["realized_pnl"] = position.get("realized_pnl", 0) + pnl
                position["remaining_frac"] -= TP2_SELL_FRAC

            if not closed and realized_pct >= (TP3_MULT - 1):
                exit_reason = "tp3"
                closed = True

            bars_held = i - position["entry_bar"]
            if bars_held >= 6 and not closed:
                exit_reason = "stale_exit"
                closed = True

            if closed:
                final_pnl = size_xrp * position["remaining_frac"] * realized_pct
                total_pnl = position.get("realized_pnl", 0) + final_pnl
                trades.append({
                    "symbol": symbol,
                    "entry_ts": position["entry_ts"],
                    "exit_ts": bar["ts"],
                    "entry_price": entry,
                    "exit_price": exit_price,
                    "pnl_pct": realized_pct * 100,
                    "pnl_xrp": total_pnl,
                    "exit_reason": exit_reason,
                    "size_xrp": size_xrp,
                    "score": position["score"]
                })
                position = None

        if not position:
            mom_2bar = 0
            if i >= 2 and bars[i-2]["close"] > 0:
                mom_2bar = (price - bars[i-2]["close"]) / bars[i-2]["close"] * 100

            score = score_token(tvl_xrp, mom_2bar)

            pre_bo = is_pre_breakout(bars, i)
            mom_ok = has_momentum(bars, i, threshold_pct=1.0, readings=2)

            micro_vel = (200 <= tvl_xrp <= 2000) and has_momentum(bars, i, threshold_pct=5.0, readings=2)
            if micro_vel:
                score = max(score, 35)

            tradeable = (
                pre_bo and
                mom_ok and
                score >= SCORE_THRESHOLD and
                tvl_xrp >= MIN_TVL_XRP
            )

            if tradeable:
                entry_price = price * (1 + SLIPPAGE_PCT)
                size = determine_size(score, balance_ref[0])

                if size >= MIN_TRADE_XRP:
                    position = {
                        "entry_price": entry_price,
                        "peak_price": entry_price,
                        "entry_ts": bar["ts"],
                        "entry_bar": i,
                        "size_xrp": size,
                        "remaining_frac": 1.0,
                        "score": score,
                        "tp1_done": False,
                        "tp2_done": False,
                        "realized_pnl": 0.0
                    }

    if position and bars:
        last = bars[-1]
        exit_price = last["close"] * (1 - SLIPPAGE_PCT)
        realized_pct = (exit_price - position["entry_price"]) / position["entry_price"]
        final_pnl = position["size_xrp"] * position["remaining_frac"] * realized_pct
        total_pnl = position.get("realized_pnl", 0) + final_pnl
        trades.append({
            "symbol": symbol,
            "entry_ts": position["entry_ts"],
            "exit_ts": last["ts"],
            "entry_price": position["entry_price"],
            "exit_price": exit_price,
            "pnl_pct": realized_pct * 100,
            "pnl_xrp": total_pnl,
            "exit_reason": "end_of_data",
            "size_xrp": position["size_xrp"],
            "score": position["score"]
        })

    return trades

# ─── MAIN ─────────────────────────────────────────────────────────────────────
print("=" * 65)
print("DKTrenchBot v2 — MASTERPIECE CONFIG — 14-Day Backtest")
print(f"Starting Balance: {STARTING_BALANCE} XRP")
print(f"Window: {fmt_ts(BACKTEST_START)} → {fmt_ts(NOW)}")
print(f"Min TVL: {MIN_TVL_XRP} XRP | Score Threshold: {SCORE_THRESHOLD}")
print(f"Max Positions: {MAX_POSITIONS} | Slippage: {SLIPPAGE_PCT*100:.0f}%")
print(f"TP Ladder: 2x→50% | 3x→20% | 5x→remainder | Trail: {TRAIL_STOP_PCT*100:.0f}%")
print("=" * 65)

with open("/home/agent/workspace/trading-bot-v2/state/active_registry.json") as f:
    data = json.load(f)
tokens = data.get("tokens", data) if isinstance(data, dict) else data

tokens_sorted = sorted(tokens, key=lambda x: x.get("tvl_xrp", 0), reverse=True)
tokens_to_test = tokens_sorted[:MAX_TOKENS]

print(f"\nTesting top {len(tokens_to_test)} tokens by TVL\n")
print(f"{'Symbol':<12} {'TVL':>10} {'Bars':>6} {'Trades':>8} {'PnL XRP':>10} {'WR':>8}")
print("-" * 60)

all_trades = []
token_results = []
balance_ref = [STARTING_BALANCE]  # mutable reference

for tok in tokens_to_test:
    symbol = tok.get("symbol", "?")
    currency = tok.get("currency", symbol)
    issuer = tok.get("issuer", "")
    tvl_xrp = tok.get("tvl_xrp", 0)

    if tvl_xrp < MIN_TVL_XRP:
        continue

    amm_result = get_amm_info(currency, issuer)
    if "error" in amm_result or "amm" not in amm_result:
        print(f"{symbol:<12} {'—':>10} {'AMM not found':>30}")
        token_results.append({"symbol": symbol, "tvl_xrp": tvl_xrp, "error": "no_amm", "trades": [], "bars": 0})
        time.sleep(0.3)
        continue

    pool_account = amm_result["amm"].get("account", "")
    if not pool_account:
        token_results.append({"symbol": symbol, "tvl_xrp": tvl_xrp, "error": "no_account", "trades": [], "bars": 0})
        continue

    txs = get_amm_account_txs(pool_account, limit=400)

    def get_ts(tx_obj):
        tx = tx_obj.get("tx", tx_obj.get("tx_json", {}))
        d = tx.get("date", 0)
        return d + 946684800 if d else 0

    txs_in_window = [t for t in txs if get_ts(t) >= BACKTEST_START]
    prices = reconstruct_price_series(txs_in_window, currency, issuer)

    if len(prices) < 10:
        prices_all = reconstruct_price_series(txs, currency, issuer)
        prices = [(ts, p) for ts, p in prices_all if ts >= BACKTEST_START]

    bars = build_ohlc(prices, interval_sec=3600)

    if len(bars) < 5:
        print(f"{symbol:<12} {tvl_xrp:>10,.0f} {len(bars):>6}  sparse ({len(prices)} ticks)")
        token_results.append({"symbol": symbol, "tvl_xrp": tvl_xrp, "error": "sparse", "trades": [], "bars": len(bars)})
        time.sleep(0.3)
        continue

    trades = simulate_trades_single(bars, tvl_xrp, symbol, balance_ref)
    
    # Update balance ref with net PnL from this token
    tok_pnl = sum(t["pnl_xrp"] for t in trades)
    balance_ref[0] = max(10, balance_ref[0] + tok_pnl)

    all_trades.extend(trades)

    n = len(trades)
    total_pnl = sum(t["pnl_xrp"] for t in trades)
    wins = [t for t in trades if t["pnl_xrp"] > 0]
    wr = len(wins) / n * 100 if n else 0

    print(f"{symbol:<12} {tvl_xrp:>10,.0f} {len(bars):>6} {n:>8} {total_pnl:>+10.2f} {wr:>7.0f}%")
    token_results.append({
        "symbol": symbol, "tvl_xrp": tvl_xrp, "trades": trades,
        "bars": len(bars), "ticks": len(prices), "pool_account": pool_account
    })

    time.sleep(0.3)

print("-" * 60)

# ─── Final Stats ──────────────────────────────────────────────────────────────
total_pnl  = sum(t["pnl_xrp"] for t in all_trades)
final_bal  = STARTING_BALANCE + total_pnl
wins       = [t for t in all_trades if t["pnl_xrp"] > 0]
losses     = [t for t in all_trades if t["pnl_xrp"] <= 0]
win_rate   = len(wins) / len(all_trades) * 100 if all_trades else 0
avg_win    = sum(t["pnl_xrp"] for t in wins) / len(wins) if wins else 0
avg_loss   = sum(t["pnl_xrp"] for t in losses) / len(losses) if losses else 0
best_trade = max(all_trades, key=lambda t: t["pnl_xrp"]) if all_trades else None
worst_trade= min(all_trades, key=lambda t: t["pnl_xrp"]) if all_trades else None
roi_pct    = (total_pnl / STARTING_BALANCE) * 100

exit_counts = defaultdict(int)
for t in all_trades:
    exit_counts[t["exit_reason"]] += 1

print(f"\n{'='*65}")
print("MASTERPIECE BACKTEST — FINAL RESULTS")
print(f"{'='*65}")
print(f"Starting Balance : {STARTING_BALANCE:.2f} XRP")
print(f"Final Balance    : {final_bal:.2f} XRP")
print(f"Total PnL        : {total_pnl:+.2f} XRP")
print(f"ROI              : {roi_pct:+.1f}%")
print(f"Total Trades     : {len(all_trades)}")
print(f"Win Rate         : {win_rate:.1f}%")
print(f"Avg Win          : {avg_win:+.2f} XRP")
print(f"Avg Loss         : {avg_loss:+.2f} XRP")
if best_trade:
    print(f"Best Trade       : {best_trade['symbol']} {best_trade['pnl_xrp']:+.2f} XRP ({best_trade['pnl_pct']:+.1f}%)")
if worst_trade:
    print(f"Worst Trade      : {worst_trade['symbol']} {worst_trade['pnl_xrp']:+.2f} XRP ({worst_trade['pnl_pct']:+.1f}%)")
print(f"\nExit Breakdown:")
for reason, count in sorted(exit_counts.items(), key=lambda x: -x[1]):
    print(f"  {reason}: {count} ({count/len(all_trades)*100:.0f}%)" if all_trades else f"  {reason}: {count}")

# ─── Write Report ─────────────────────────────────────────────────────────────
lines = [
    f"# DKTrenchBot v2 — MASTERPIECE CONFIG — 14-Day Backtest",
    f"**Generated:** {fmt_ts(NOW)} UTC",
    f"**Window:** {fmt_ts(BACKTEST_START)} → {fmt_ts(NOW)}",
    f"**Starting Balance:** {STARTING_BALANCE} XRP",
    f"",
    "---",
    "",
    "## ⚙️ Config Used",
    f"| Parameter | Value |",
    f"|-----------|-------|",
    f"| Score Threshold | {SCORE_THRESHOLD} |",
    f"| Elite Score | {SCORE_ELITE} |",
    f"| Min TVL | {MIN_TVL_XRP} XRP |",
    f"| Max Positions | {MAX_POSITIONS} |",
    f"| Size Elite | {SIZE_ELITE_PCT*100:.0f}% of balance |",
    f"| Size Normal | {SIZE_NORMAL_PCT*100:.0f}% of balance |",
    f"| Size Small | {SIZE_SMALL_PCT*100:.0f}% of balance |",
    f"| Max Trade | {MAX_TRADE_XRP} XRP |",
    f"| Min Trade | {MIN_TRADE_XRP} XRP |",
    f"| Trail Stop | {TRAIL_STOP_PCT*100:.0f}% |",
    f"| Slippage Buffer | {SLIPPAGE_PCT*100:.0f}% |",
    f"| TP1 | 2x → sell 50% |",
    f"| TP2 | 3x → sell 20% |",
    f"| TP3 | 5x → exit remaining |",
    "",
    "---",
    "",
    "## 📊 Overall Results",
    "",
    f"| Metric | Value |",
    f"|--------|-------|",
    f"| Starting Balance | {STARTING_BALANCE:.2f} XRP |",
    f"| Final Balance | {final_bal:.2f} XRP |",
    f"| Total PnL | {total_pnl:+.2f} XRP |",
    f"| ROI | {roi_pct:+.1f}% |",
    f"| Total Trades | {len(all_trades)} |",
    f"| Wins | {len(wins)} |",
    f"| Losses | {len(losses)} |",
    f"| Win Rate | {win_rate:.1f}% |",
    f"| Avg Win | {avg_win:+.2f} XRP |",
    f"| Avg Loss | {avg_loss:+.2f} XRP |",
]
if best_trade:
    lines.append(f"| Best Trade | {best_trade['symbol']} {best_trade['pnl_xrp']:+.2f} XRP ({best_trade['pnl_pct']:+.1f}%) |")
if worst_trade:
    lines.append(f"| Worst Trade | {worst_trade['symbol']} {worst_trade['pnl_xrp']:+.2f} XRP ({worst_trade['pnl_pct']:+.1f}%) |")

lines += [
    "",
    "## 🚪 Exit Breakdown",
    "",
    "| Exit Reason | Count | % |",
    "|-------------|-------|---|",
]
for reason, count in sorted(exit_counts.items(), key=lambda x: -x[1]):
    pct = count / len(all_trades) * 100 if all_trades else 0
    lines.append(f"| {reason} | {count} | {pct:.0f}% |")

lines += [
    "",
    "---",
    "",
    "## 📋 Per-Token Results",
    "",
    "| Symbol | TVL (XRP) | Bars | Trades | PnL XRP | WR% | Status |",
    "|--------|-----------|------|--------|---------|-----|--------|",
]
for r in token_results:
    sym = r["symbol"]
    tvl = r["tvl_xrp"]
    bars = r.get("bars", 0)
    trades = r.get("trades", [])
    err = r.get("error", "")
    if err:
        lines.append(f"| {sym} | {tvl:,.0f} | {bars} | — | — | — | ❌ {err} |")
    else:
        n = len(trades)
        pnl = sum(t["pnl_xrp"] for t in trades)
        wr = len([t for t in trades if t["pnl_xrp"] > 0]) / n * 100 if n else 0
        lines.append(f"| {sym} | {tvl:,.0f} | {bars} | {n} | {pnl:+.2f} | {wr:.0f}% | ✅ |")

lines += [
    "",
    "---",
    "",
    "## 📝 Trade Log",
    "",
    "| # | Symbol | Entry | Exit | PnL% | PnL XRP | Exit | Score | Size |",
    "|---|--------|-------|------|------|---------|------|-------|------|",
]
for i, t in enumerate(all_trades, 1):
    lines.append(f"| {i} | {t['symbol']} | {fmt_ts(t['entry_ts'])} | {fmt_ts(t['exit_ts'])} | {t['pnl_pct']:+.1f}% | {t['pnl_xrp']:+.2f} | {t['exit_reason']} | {t['score']:.0f} | {t['size_xrp']:.1f} |")

report = "\n".join(lines)
with open(REPORT_PATH, "w") as f:
    f.write(report)

print(f"\n✅ Report saved → {REPORT_PATH}")
