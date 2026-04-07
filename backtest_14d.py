"""
14-Day Backtest — DKTrenchBot v2
Uses XRPL on-chain AMM data to reconstruct price history and simulate trades.
"""

import json
import requests
import time
from datetime import datetime, timezone
from collections import defaultdict

CLIO_URL = "https://rpc.xrplclaw.com"
REPORT_PATH = "/home/agent/workspace/trading-bot-v2/state/backtest_14d.md"

# Use top tokens by TVL from active_registry + config TOKEN_REGISTRY
# We'll try top 30 by TVL for realistic coverage vs. time
MAX_TOKENS = 30

# Config thresholds (from config.py)
SCORE_ELITE = 65
SCORE_TRADEABLE = 57
HARD_STOP_PCT = 0.15
TRAIL_STOP_PCT = 0.20
TP1_PCT = 0.20
TP1_SELL_FRAC = 0.30
TP2_PCT = 0.50
TP3_PCT = 1.50
XRP_ELITE = 15.0
XRP_NORMAL = 10.0
XRP_MICRO = 5.0
TVL_MICRO_CAP = 2000
MIN_TVL_XRP = 300

# 14 days ago in seconds since epoch
NOW = time.time()
BACKTEST_START = NOW - (14 * 86400)

def rpc(method, params):
    try:
        r = requests.post(CLIO_URL, json={"method": method, "params": [params]}, timeout=20)
        return r.json().get("result", {})
    except Exception as e:
        return {"error": str(e)}

def get_amm_info(currency, issuer):
    """Get AMM pool info for token vs XRP"""
    if len(currency) <= 3:
        asset = {"currency": currency, "issuer": issuer}
    else:
        asset = {"currency": currency, "issuer": issuer}
    
    result = rpc("amm_info", {
        "asset": {"currency": "XRP"},
        "asset2": asset,
        "ledger_index": "validated"
    })
    return result

def get_amm_account_txs(account, limit=400):
    """Get AMM pool transactions going forward (oldest first)"""
    all_txs = []
    marker = None
    
    for page in range(10):  # max 10 pages
        params = {
            "account": account,
            "forward": True,
            "limit": limit,
            "ledger_index_min": -1,
            "ledger_index_max": -1,
        }
        if marker:
            params["marker"] = marker
        
        result = rpc("account_tx", params)
        txs = result.get("transactions", [])
        all_txs.extend(txs)
        
        marker = result.get("marker")
        if not marker or len(txs) == 0:
            break
        
        time.sleep(0.2)
    
    return all_txs

def extract_price_from_tx(tx_obj, token_currency, token_issuer):
    """
    Extract XRP/token price from AMM swap transaction.
    Returns (timestamp, price_in_xrp_per_token) or None
    """
    tx = tx_obj.get("tx", tx_obj.get("tx_json", {}))
    meta = tx_obj.get("meta", tx_obj.get("metaData", {}))
    
    if not tx or not meta:
        return None
    
    # Get close time
    close_time = tx.get("date", 0)
    if close_time:
        # XRPL epoch starts 2000-01-01
        ts = close_time + 946684800
    else:
        return None
    
    # Only look at transactions in our window
    if ts < BACKTEST_START:
        return None
    
    # Look for AMMSwap or OfferCreate affecting AMM
    tx_type = tx.get("TransactionType", "")
    
    if tx_type not in ("AMMSwap", "OfferCreate", "Payment"):
        return None
    
    affected = meta.get("AffectedNodes", [])
    
    xrp_delta = 0
    token_delta = 0
    
    for node in affected:
        for node_type in ("ModifiedNode", "CreatedNode", "DeletedNode"):
            if node_type not in node:
                continue
            n = node[node_type]
            ledger_entry = n.get("LedgerEntryType", "")
            
            if ledger_entry == "AMMState":
                # Direct AMM state changes
                ff = n.get("FinalFields", {})
                pf = n.get("PreviousFields", {})
                
                if not pf:
                    continue
                
                # Try to extract XRP and token amounts from Amount/Amount2
                def parse_amount(a):
                    if isinstance(a, str):
                        return float(a) / 1e6, "XRP"
                    elif isinstance(a, dict):
                        return float(a.get("value", 0)), a.get("currency", "")
                    return 0, ""
                
                for field in ["Amount", "Amount2"]:
                    if field in ff and field in pf:
                        final_val, final_cur = parse_amount(ff[field])
                        prev_val, prev_cur = parse_amount(pf[field])
                        delta = final_val - prev_val
                        
                        if final_cur == "XRP":
                            xrp_delta += delta
                        elif final_cur == token_currency:
                            token_delta += delta
    
    if xrp_delta != 0 and token_delta != 0 and token_delta != 0:
        # price = XRP per token (absolute value since one goes up, one goes down)
        price = abs(xrp_delta) / abs(token_delta)
        return (ts, price)
    
    return None

def reconstruct_price_series(txs, token_currency, token_issuer):
    """Build a time series of prices from AMM transactions"""
    prices = []
    
    for tx_obj in txs:
        result = extract_price_from_tx(tx_obj, token_currency, token_issuer)
        if result:
            prices.append(result)
    
    # Sort by time
    prices.sort(key=lambda x: x[0])
    return prices

def build_ohlc(prices, interval_sec=3600):
    """Aggregate tick prices into hourly OHLC bars"""
    if not prices:
        return []
    
    bars = {}
    for ts, price in prices:
        bar_ts = int(ts // interval_sec) * interval_sec
        if bar_ts not in bars:
            bars[bar_ts] = {"open": price, "high": price, "low": price, "close": price, "ts": bar_ts, "count": 0}
        else:
            bars[bar_ts]["high"] = max(bars[bar_ts]["high"], price)
            bars[bar_ts]["low"] = min(bars[bar_ts]["low"], price)
            bars[bar_ts]["close"] = price
            bars[bar_ts]["count"] += 1
    
    return sorted(bars.values(), key=lambda x: x["ts"])

def simple_score(tvl_xrp, momentum_pct):
    """Simplified scoring: TVL + momentum → 0-100"""
    # TVL score: 0-50 based on TVL
    if tvl_xrp >= 100000:
        tvl_score = 50
    elif tvl_xrp >= 10000:
        tvl_score = 35
    elif tvl_xrp >= 2000:
        tvl_score = 25
    elif tvl_xrp >= 500:
        tvl_score = 15
    else:
        tvl_score = 8
    
    # Momentum score: 0-50 based on % change
    if momentum_pct >= 10:
        mom_score = 50
    elif momentum_pct >= 5:
        mom_score = 40
    elif momentum_pct >= 2:
        mom_score = 30
    elif momentum_pct >= 1:
        mom_score = 20
    else:
        mom_score = 0
    
    return min(100, tvl_score + mom_score)

def is_pre_breakout(bars, i, lookback=24):
    """Check if price is within 20% of local high (pre_breakout state)"""
    if i < 2:
        return False
    
    start = max(0, i - lookback)
    window = bars[start:i+1]
    local_high = max(b["high"] for b in window)
    current = bars[i]["close"]
    
    return current >= local_high * 0.80

def has_momentum(bars, i, threshold_pct=1.0, readings=2):
    """Check for +threshold% gain in last `readings` bars"""
    if i < readings:
        return False
    
    prev = bars[i - readings]["close"]
    curr = bars[i]["close"]
    
    if prev <= 0:
        return False
    
    change = (curr - prev) / prev * 100
    return change >= threshold_pct

def simulate_trades(bars, tvl_xrp, symbol):
    """
    Simulate entry/exit on OHLC bars.
    Returns list of trade dicts.
    """
    trades = []
    position = None
    
    for i, bar in enumerate(bars):
        if i < 4:
            continue
        
        price = bar["close"]
        
        # ── Exit logic if in position ──
        if position:
            entry = position["entry_price"]
            peak = position["peak_price"]
            size_xrp = position["size_xrp"]
            remaining_frac = position["remaining_frac"]
            
            # Update peak
            if price > peak:
                position["peak_price"] = price
                peak = price
            
            pnl_pct = (price - entry) / entry
            
            # Hard stop -15%
            if pnl_pct <= -HARD_STOP_PCT:
                realized_pnl = size_xrp * remaining_frac * pnl_pct
                trades.append({
                    "symbol": symbol,
                    "entry_ts": position["entry_ts"],
                    "exit_ts": bar["ts"],
                    "entry_price": entry,
                    "exit_price": price,
                    "pnl_pct": pnl_pct * 100,
                    "pnl_xrp": realized_pnl,
                    "exit_reason": "hard_stop",
                    "size_xrp": size_xrp,
                    "score": position["score"]
                })
                position = None
                continue
            
            # Trail stop -20% from peak
            if price <= peak * (1 - TRAIL_STOP_PCT):
                realized_pnl = size_xrp * remaining_frac * pnl_pct
                trades.append({
                    "symbol": symbol,
                    "entry_ts": position["entry_ts"],
                    "exit_ts": bar["ts"],
                    "entry_price": entry,
                    "exit_price": price,
                    "pnl_pct": pnl_pct * 100,
                    "pnl_xrp": realized_pnl,
                    "exit_reason": "trail_stop",
                    "size_xrp": size_xrp,
                    "score": position["score"]
                })
                position = None
                continue
            
            # TP1 +20% → sell 30%
            if pnl_pct >= TP1_PCT and not position.get("tp1_done"):
                position["tp1_done"] = True
                sell_frac = TP1_SELL_FRAC
                realized_pnl = size_xrp * sell_frac * pnl_pct
                position["remaining_frac"] -= sell_frac
                position["tp1_pnl"] = realized_pnl
                # Don't close, continue
            
            # TP2 +50% → sell 30% of remaining
            if pnl_pct >= TP2_PCT and not position.get("tp2_done"):
                position["tp2_done"] = True
                sell_frac = 0.30
                realized_pnl = size_xrp * sell_frac * pnl_pct
                position["remaining_frac"] -= sell_frac
                position["tp2_pnl"] = realized_pnl
            
            # TP3 +150% → full exit
            if pnl_pct >= TP3_PCT:
                tp1_pnl = position.get("tp1_pnl", 0)
                tp2_pnl = position.get("tp2_pnl", 0)
                realized_pnl = size_xrp * position["remaining_frac"] * pnl_pct + tp1_pnl + tp2_pnl
                trades.append({
                    "symbol": symbol,
                    "entry_ts": position["entry_ts"],
                    "exit_ts": bar["ts"],
                    "entry_price": entry,
                    "exit_price": price,
                    "pnl_pct": pnl_pct * 100,
                    "pnl_xrp": realized_pnl,
                    "exit_reason": "tp3",
                    "size_xrp": size_xrp,
                    "score": position["score"]
                })
                position = None
                continue
            
            # Stale exit: 6 hours (6 bars)
            bars_held = i - position["entry_bar"]
            if bars_held >= 6:
                tp1_pnl = position.get("tp1_pnl", 0)
                tp2_pnl = position.get("tp2_pnl", 0)
                realized_pnl = size_xrp * position["remaining_frac"] * pnl_pct + tp1_pnl + tp2_pnl
                trades.append({
                    "symbol": symbol,
                    "entry_ts": position["entry_ts"],
                    "exit_ts": bar["ts"],
                    "entry_price": entry,
                    "exit_price": price,
                    "pnl_pct": pnl_pct * 100,
                    "pnl_xrp": realized_pnl,
                    "exit_reason": "stale_exit",
                    "size_xrp": size_xrp,
                    "score": position["score"]
                })
                position = None
                continue
        
        # ── Entry logic if no position ──
        if not position:
            # Compute momentum (last 2 bars)
            mom_2bar = 0
            if i >= 2 and bars[i-2]["close"] > 0:
                mom_2bar = (price - bars[i-2]["close"]) / bars[i-2]["close"] * 100
            
            score = simple_score(tvl_xrp, mom_2bar)
            
            pre_bo = is_pre_breakout(bars, i)
            mom_ok = has_momentum(bars, i, threshold_pct=1.0, readings=2)
            
            # Micro-vel override: TVL 200-2000 + 5% in 2 readings
            micro_vel = (TVL_MICRO_CAP >= tvl_xrp >= 200) and has_momentum(bars, i, threshold_pct=5.0, readings=2)
            if micro_vel:
                score = max(score, 45)
            
            tradeable = (
                pre_bo and
                (score >= SCORE_TRADEABLE or (micro_vel and score >= 45)) and
                mom_ok and
                tvl_xrp >= MIN_TVL_XRP
            )
            
            if tradeable:
                if score >= SCORE_ELITE:
                    size = XRP_ELITE
                elif tvl_xrp < TVL_MICRO_CAP:
                    size = XRP_MICRO
                else:
                    size = XRP_NORMAL
                
                position = {
                    "entry_price": price,
                    "peak_price": price,
                    "entry_ts": bar["ts"],
                    "entry_bar": i,
                    "size_xrp": size,
                    "remaining_frac": 1.0,
                    "score": score,
                    "tp1_done": False,
                    "tp2_done": False,
                }
    
    # Close any open position at end
    if position and bars:
        last = bars[-1]
        pnl_pct = (last["close"] - position["entry_price"]) / position["entry_price"]
        tp1_pnl = position.get("tp1_pnl", 0)
        tp2_pnl = position.get("tp2_pnl", 0)
        realized_pnl = position["size_xrp"] * position["remaining_frac"] * pnl_pct + tp1_pnl + tp2_pnl
        trades.append({
            "symbol": symbol,
            "entry_ts": position["entry_ts"],
            "exit_ts": last["ts"],
            "entry_price": position["entry_price"],
            "exit_price": last["close"],
            "pnl_pct": pnl_pct * 100,
            "pnl_xrp": realized_pnl,
            "exit_reason": "end_of_data",
            "size_xrp": position["size_xrp"],
            "score": position["score"]
        })
    
    return trades

def fmt_ts(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")

# ─── Main ────────────────────────────────────────────────────────────────────

print("=" * 60)
print("DKTrenchBot 14-Day Backtest — Starting")
print(f"Window: {fmt_ts(BACKTEST_START)} → {fmt_ts(NOW)}")
print("=" * 60)

# Load token registry
with open("/home/agent/workspace/trading-bot-v2/state/active_registry.json") as f:
    data = json.load(f)
tokens = data.get("tokens", data) if isinstance(data, dict) else data

# Sort by TVL desc, pick top MAX_TOKENS
tokens_sorted = sorted(tokens, key=lambda x: x.get("tvl_xrp", 0), reverse=True)
tokens_to_test = tokens_sorted[:MAX_TOKENS]

print(f"\nTesting top {len(tokens_to_test)} tokens by TVL")
print(f"{'Symbol':<12} {'TVL (XRP)':>12} {'Trades':>8} {'PnL XRP':>10} {'WR':>8}")
print("-" * 55)

all_trades = []
token_results = []

for tok in tokens_to_test:
    symbol = tok.get("symbol", "?")
    currency = tok.get("currency", symbol)
    issuer = tok.get("issuer", "")
    tvl_xrp = tok.get("tvl_xrp", 0)
    
    # Skip if TVL too low
    if tvl_xrp < MIN_TVL_XRP:
        continue
    
    # Get AMM info to find pool account
    amm_result = get_amm_info(currency, issuer)
    
    if "error" in amm_result or "amm" not in amm_result:
        print(f"{symbol:<12} {'AMM not found':>22}")
        token_results.append({"symbol": symbol, "tvl_xrp": tvl_xrp, "error": "no_amm", "trades": [], "bars": 0})
        time.sleep(0.3)
        continue
    
    amm_data = amm_result["amm"]
    pool_account = amm_data.get("account", "")
    
    if not pool_account:
        print(f"{symbol:<12} {'No pool account':>22}")
        token_results.append({"symbol": symbol, "tvl_xrp": tvl_xrp, "error": "no_account", "trades": [], "bars": 0})
        continue
    
    # Get AMM transactions
    txs = get_amm_account_txs(pool_account, limit=400)
    
    # Filter to our 14-day window
    def get_ts(tx_obj):
        tx = tx_obj.get("tx", tx_obj.get("tx_json", {}))
        d = tx.get("date", 0)
        return d + 946684800 if d else 0
    
    txs_in_window = [t for t in txs if get_ts(t) >= BACKTEST_START]
    
    # Reconstruct prices
    prices = reconstruct_price_series(txs_in_window, currency, issuer)
    
    if len(prices) < 10:
        # Try alternative: use all txs and filter differently
        # Sometimes AMMSwap state changes appear differently
        # Fallback: if we have bars from older txs, still use them
        prices_all = reconstruct_price_series(txs, currency, issuer)
        prices_window = [(ts, p) for ts, p in prices_all if ts >= BACKTEST_START]
        prices = prices_window
    
    bars = build_ohlc(prices, interval_sec=3600)
    
    if len(bars) < 5:
        print(f"{symbol:<12} {tvl_xrp:>12,.0f} {'sparse data':>18} ({len(prices)} ticks, {len(bars)} bars)")
        token_results.append({"symbol": symbol, "tvl_xrp": tvl_xrp, "error": "sparse", "trades": [], "bars": len(bars), "ticks": len(prices), "pool_account": pool_account, "total_txs": len(txs)})
        time.sleep(0.3)
        continue
    
    # Simulate trades
    trades = simulate_trades(bars, tvl_xrp, symbol)
    all_trades.extend(trades)
    
    n_trades = len(trades)
    total_pnl = sum(t["pnl_xrp"] for t in trades)
    wins = [t for t in trades if t["pnl_xrp"] > 0]
    win_rate = len(wins) / n_trades * 100 if n_trades else 0
    
    print(f"{symbol:<12} {tvl_xrp:>12,.0f} {n_trades:>8} {total_pnl:>+10.2f} {win_rate:>7.0f}%")
    token_results.append({
        "symbol": symbol,
        "tvl_xrp": tvl_xrp,
        "trades": trades,
        "bars": len(bars),
        "ticks": len(prices),
        "total_txs": len(txs),
        "pool_account": pool_account
    })
    
    time.sleep(0.3)

print("-" * 55)

# ─── Aggregate Stats ─────────────────────────────────────────────────────────
total_pnl = sum(t["pnl_xrp"] for t in all_trades)
wins = [t for t in all_trades if t["pnl_xrp"] > 0]
losses = [t for t in all_trades if t["pnl_xrp"] <= 0]
win_rate = len(wins) / len(all_trades) * 100 if all_trades else 0
avg_win = sum(t["pnl_xrp"] for t in wins) / len(wins) if wins else 0
avg_loss = sum(t["pnl_xrp"] for t in losses) / len(losses) if losses else 0
best_trade = max(all_trades, key=lambda t: t["pnl_xrp"]) if all_trades else None
worst_trade = min(all_trades, key=lambda t: t["pnl_xrp"]) if all_trades else None

exit_counts = defaultdict(int)
for t in all_trades:
    exit_counts[t["exit_reason"]] += 1

# ─── Build Report ────────────────────────────────────────────────────────────
lines = []
lines.append(f"# DKTrenchBot — 14-Day Backtest Report")
lines.append(f"**Generated:** {fmt_ts(NOW)} UTC")
lines.append(f"**Backtest Window:** {fmt_ts(BACKTEST_START)} → {fmt_ts(NOW)}")
lines.append(f"**Tokens Analyzed:** {len(tokens_to_test)}")
lines.append(f"**Data Source:** XRPL on-chain AMM transactions via CLIO RPC")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## ⚠️ Data Quality Notes")
lines.append("")
lines.append("XRPL AMM price extraction from `AffectedNodes` is challenging because:")
lines.append("- `AMMSwap` transactions store pool state changes in `AMMState` ledger entries")
lines.append("- `AffectedNodes` structure varies between transaction types")
lines.append("- Some swaps go via DEX path (OfferCreate) vs direct AMM, making price extraction non-trivial")
lines.append("- Sparse data is common for lower-TVL tokens with few swaps/hour")
lines.append("")

# Count data quality
sparse_count = sum(1 for r in token_results if r.get("error") in ("sparse", "no_amm", "no_account"))
tradeable_tokens = [r for r in token_results if "trades" in r and r.get("bars", 0) >= 5]
lines.append(f"- **Tokens with AMM data (≥5 bars):** {len(tradeable_tokens)}")
lines.append(f"- **Sparse/missing data:** {sparse_count} tokens")
lines.append(f"- **Total trades simulated:** {len(all_trades)}")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## 📊 Overall Results")
lines.append("")
lines.append(f"| Metric | Value |")
lines.append(f"|--------|-------|")
lines.append(f"| Total Trades | {len(all_trades)} |")
lines.append(f"| Win Rate | {win_rate:.1f}% |")
lines.append(f"| Total PnL | {total_pnl:+.2f} XRP |")
lines.append(f"| Avg Win | {avg_win:+.2f} XRP |")
lines.append(f"| Avg Loss | {avg_loss:+.2f} XRP |")
if best_trade:
    lines.append(f"| Best Trade | {best_trade['symbol']} {best_trade['pnl_pct']:+.1f}% ({best_trade['pnl_xrp']:+.2f} XRP) |")
if worst_trade:
    lines.append(f"| Worst Trade | {worst_trade['symbol']} {worst_trade['pnl_pct']:+.1f}% ({worst_trade['pnl_xrp']:+.2f} XRP) |")
lines.append("")

lines.append("## 🚪 Exit Breakdown")
lines.append("")
lines.append(f"| Exit Reason | Count | % |")
lines.append(f"|-------------|-------|---|")
for reason, count in sorted(exit_counts.items(), key=lambda x: -x[1]):
    pct = count / len(all_trades) * 100 if all_trades else 0
    lines.append(f"| {reason} | {count} | {pct:.0f}% |")
lines.append("")

lines.append("---")
lines.append("")
lines.append("## 📋 Per-Token Results")
lines.append("")
lines.append(f"| Symbol | TVL (XRP) | Bars | Ticks | Trades | PnL XRP | WR% | Status |")
lines.append(f"|--------|-----------|------|-------|--------|---------|-----|--------|")

for r in token_results:
    sym = r["symbol"]
    tvl = r["tvl_xrp"]
    bars = r.get("bars", 0)
    ticks = r.get("ticks", 0)
    trades = r.get("trades", [])
    err = r.get("error", "")
    
    if err:
        lines.append(f"| {sym} | {tvl:,.0f} | {bars} | {ticks} | — | — | — | ❌ {err} |")
    else:
        n = len(trades)
        pnl = sum(t["pnl_xrp"] for t in trades)
        wr = len([t for t in trades if t["pnl_xrp"] > 0]) / n * 100 if n else 0
        lines.append(f"| {sym} | {tvl:,.0f} | {bars} | {ticks} | {n} | {pnl:+.2f} | {wr:.0f}% | ✅ |")

lines.append("")
lines.append("---")
lines.append("")
lines.append("## 📝 Trade Log")
lines.append("")

if all_trades:
    lines.append(f"| # | Symbol | Entry | Exit | PnL% | PnL XRP | Exit Reason | Score | Size |")
    lines.append(f"|---|--------|-------|------|------|---------|-------------|-------|------|")
    for i, t in enumerate(all_trades, 1):
        entry_dt = fmt_ts(t["entry_ts"])
        exit_dt = fmt_ts(t["exit_ts"])
        lines.append(f"| {i} | {t['symbol']} | {entry_dt} | {exit_dt} | {t['pnl_pct']:+.1f}% | {t['pnl_xrp']:+.2f} | {t['exit_reason']} | {t['score']:.0f} | {t['size_xrp']:.0f} XRP |")
else:
    lines.append("No trades were generated. See data quality notes above.")

lines.append("")
lines.append("---")
lines.append("")
lines.append("## 🔍 Methodology & Limitations")
lines.append("")
lines.append("### Entry Rules Applied")
lines.append("- `pre_breakout`: price within 20% of 24-bar local high")
lines.append(f"- Score ≥ {SCORE_TRADEABLE} (or ≥45 with micro-vel override)")
lines.append("- Momentum: +1% over 2 bars")
lines.append("- TVL ≥ 300 XRP")
lines.append("")
lines.append("### Scoring Model")
lines.append("- TVL tiers: <500→8, <2k→15, <10k→25, <100k→35, 100k+→50 pts")
lines.append("- Momentum tiers: ≥1%→20, ≥2%→30, ≥5%→40, ≥10%→50 pts")
lines.append("- Cap: 100 pts")
lines.append("")
lines.append("### Key Limitations")
lines.append("1. **Price extraction**: AMMSwap AffectedNodes parsing is best-effort. If AMMState changes didn't capture XRP+token deltas simultaneously, the tick is skipped → sparse bars → fewer simulated trades than reality.")
lines.append("2. **No slippage model**: Real AMM swaps have price impact. Large positions would move price more.")
lines.append("3. **Simplified scoring**: Real bot scoring includes DNA60, VWAP, liquidity health checks not reproduced here.")
lines.append("4. **Hourly bars**: Real bot runs at 60-second poll intervals — higher resolution would produce different entry/exit signals.")
lines.append("5. **Single token, no concurrent positions**: Real bot holds up to 3 concurrent positions (MAX_POSITIONS=3).")
lines.append(f"6. **No real cost data**: Doesn't account for AMM swap fees (0.5-1% typically on XRPL AMM).")

report = "\n".join(lines)
print("\n" + "=" * 60)
print("FINAL SUMMARY")
print("=" * 60)
print(f"Total Trades: {len(all_trades)}")
print(f"Win Rate: {win_rate:.1f}%")
print(f"Total PnL: {total_pnl:+.2f} XRP")
print(f"Avg Win: {avg_win:+.2f} XRP | Avg Loss: {avg_loss:+.2f} XRP")
print("\nExit Breakdown:")
for reason, count in sorted(exit_counts.items(), key=lambda x: -x[1]):
    print(f"  {reason}: {count}")

with open(REPORT_PATH, "w") as f:
    f.write(report)

print(f"\n✅ Report written to {REPORT_PATH}")
print("\n" + "=" * 60)
print("FULL REPORT:")
print("=" * 60)
print(report)
