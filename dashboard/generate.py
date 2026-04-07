"""
DKTrenchBot Terminal — generate.py
Builds index.html from live bot state. Called every 60s by deploy_loop.py.
Stats reset: 2026-04-06 03:00 UTC (post-optimization baseline)
"""
import json, os, sys, time, re, requests
from pathlib import Path
from datetime import datetime, timezone

# ── Paths ──────────────────────────────────────────────────────────────────
BASE        = Path(__file__).parent.parent
DASH        = Path(__file__).parent
STATE_FILE  = BASE / "state/state.json"
EXEC_LOG    = BASE / "state/execution_log.json"
REGIME_FILE = BASE / "state/regime.json"
WEIGHTS_FILE= BASE / "state/learned_weights.json"
BRIEFING    = Path("/home/agent/workspace/state/market/briefing.json")
AXIOM_POS   = Path("/home/agent/workspace/axiom-bot/bot/state/state_data/positions.json")
BOT_LOG     = BASE / "state/bot.log"
AXIOM_LOG   = Path("/home/agent/workspace/axiom-bot/bot.log")
CONFIG_FILE = BASE / "config.py"
OUT         = DASH / "index.html"

CLIO        = "https://rpc.xrplclaw.com"
WALLET      = "rKQACag8Td9TrMxBwYJPGRMDV8cxGfKsmF"
RESET_TS    = 1775444400  # 2026-04-06 03:00 UTC

# ── Data collectors ────────────────────────────────────────────────────────

def get_xrpl_balance():
    try:
        r = requests.post(CLIO, json={"method":"account_info","params":[{
            "account":WALLET,"ledger_index":"current"}]}, timeout=6)
        d = r.json()["result"]["account_data"]
        bal   = int(d["Balance"]) / 1e6
        owner = d.get("OwnerCount", 0)
        spendable = round(max(0, bal - 1 - owner * 0.2), 3)
        return round(bal, 3), spendable, owner
    except:
        return 0.0, 0.0, 0

def get_positions():
    try:
        with open(STATE_FILE) as f:
            s = json.load(f)
        positions = s.get("positions", {})
        now = time.time()
        result = []
        for key, p in positions.items():
            held_min = (now - p.get("entry_time", now)) / 60
            ep = p.get("entry_price", 0)
            cp = p.get("current_price", ep)
            pnl_pct = (cp - ep) / ep * 100 if ep > 0 else 0
            xrp_in  = p.get("xrp_spent", 0)
            unreal  = xrp_in * pnl_pct / 100
            result.append({
                "symbol":      p.get("symbol", key),
                "entry_price": ep,
                "current_price": cp,
                "xrp_in":      xrp_in,
                "unreal_pnl":  round(unreal, 3),
                "pnl_pct":     round(pnl_pct, 2),
                "held_min":    round(held_min, 1),
                "score":       p.get("score", 0),
                "chart_state": p.get("chart_state", "?"),
                "peak_price":  p.get("peak_price", cp),
            })
        return result
    except:
        return []

def get_trade_history(since_ts=RESET_TS):
    try:
        with open(STATE_FILE) as f:
            s = json.load(f)
        trades = [t for t in s.get("trade_history", []) if t.get("entry_time", 0) >= since_ts]
        return trades
    except:
        return []

def get_all_trade_history():
    """Full history for equity curve anchor"""
    try:
        with open(STATE_FILE) as f:
            s = json.load(f)
        return s.get("trade_history", [])
    except:
        return []

def get_regime():
    try:
        with open(REGIME_FILE) as f:
            return json.load(f)
    except:
        return {"regime": "unknown", "details": {}}

def get_learned_weights():
    try:
        with open(WEIGHTS_FILE) as f:
            return json.load(f)
    except:
        return {}

def get_xrp_price():
    try:
        with open(BRIEFING) as f:
            d = json.load(f)
        return float(d.get("prices", {}).get("xrp", {}).get("usd", 0) or
                     d.get("xrp_price", 0) or
                     d.get("market", {}).get("xrp_usd", 0) or 0)
    except:
        return 0.0

def get_fear_greed():
    try:
        with open(BRIEFING) as f:
            d = json.load(f)
        return int(d.get("fear_greed", {}).get("value", 0) or
                   d.get("indicators", {}).get("fear_greed", 0) or 0)
    except:
        return 0

def get_btc_price():
    try:
        with open(BRIEFING) as f:
            d = json.load(f)
        return float(d.get("prices", {}).get("btc", {}).get("usd", 0) or
                     d.get("btc_price", 0) or 0)
    except:
        return 0.0

def get_axiom_data():
    result = {"open": [], "closed": [], "vault": 0.0, "gas": 0.0}
    try:
        with open(AXIOM_POS) as f:
            raw = json.load(f)
        positions = raw if isinstance(raw, list) else raw.get("positions", [])
        now = time.time()
        for p in positions:
            ends = p.get("ends_at", 0) or p.get("end_time", 0)
            status = p.get("result", p.get("status", "open"))
            rec = {
                "title":      p.get("title", p.get("market", "?"))[:55],
                "direction":  p.get("direction", "?"),
                "stake":      p.get("stake_xrp", p.get("stake", 0)),
                "confidence": p.get("confidence", 0),
                "family":     p.get("family", "?"),
                "ends_at":    ends,
                "hours_left": round((ends - now) / 3600, 1) if ends > now else 0,
                "result":     status,
                "pnl":        p.get("pnl_xrp", p.get("pnl", 0)),
                "ts":         p.get("ts", p.get("created_at", 0)),
            }
            if status in ("win","loss","claimed") or (ends > 0 and ends < now):
                if rec["ts"] >= RESET_TS:
                    result["closed"].append(rec)
            else:
                result["open"].append(rec)
    except:
        pass
    # Try to get vault balance
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path("/home/agent/workspace/axiom-bot/bot")))
        from chain.vault import VaultClient
        with open("/home/agent/workspace/axiom-bot/deployed_contracts.json") as f:
            c = json.load(f)
        v = VaultClient(c["AxiomVault"])
        result["vault"] = v.total_xrp()
        result["gas"]   = v.gas_wallet_xrp()
    except:
        pass
    return result

def get_bot_status():
    """Returns 'running', 'stale', or 'offline' for each bot"""
    def check_log(path, keyword="Cycle", window_sec=300):
        try:
            with open(path, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - 30000))
                tail = f.read().decode("utf-8", errors="ignore")
            lines = tail.strip().split("\n")[-200:]
            now = time.time()
            for line in reversed(lines):
                if keyword in line:
                    # Try to parse timestamp
                    m = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
                    if m:
                        try:
                            ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
                            if now - ts < window_sec:
                                return "running"
                        except:
                            pass
                    return "running"  # found keyword recently
            return "stale"
        except:
            return "offline"
    return {
        "dkbot":  check_log(BOT_LOG),
        "axiom":  check_log(AXIOM_LOG, keyword="cycle"),
    }

def get_activity_feed(n=12):
    events = []

    # DKBot log events
    try:
        with open(BOT_LOG, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 40000))
            tail = f.read().decode("utf-8", errors="ignore")
        for line in tail.split("\n"):
            line = line.strip()
            if not line:
                continue
            ts_match = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
            ts_str = ts_match.group(1) if ts_match else ""
            if "BUY " in line:
                m = re.search(r"BUY (\w+):.*?(\d+\.?\d*) XRP", line) or re.search(r"BUY (\w+)", line)
                sym = m.group(1) if m else "?"
                xrp_m = re.search(r"(\d+\.?\d+) XRP", line)
                xrp = xrp_m.group(1) if xrp_m else "?"
                score_m = re.search(r"score=(\d+)", line)
                score = score_m.group(1) if score_m else "?"
                events.append({"ts": ts_str, "bot": "DKBot", "type": "BUY", "color": "good",
                                "msg": f"BUY {sym} {xrp} XRP score={score}"})
            elif "SELL" in line or "EXIT" in line.upper():
                m = re.search(r"(?:SELL|EXIT) (\w+)", line)
                sym = m.group(1) if m else "?"
                pnl_m = re.search(r"pnl=([+-]?\d+\.?\d+)", line)
                pnl = pnl_m.group(1) if pnl_m else "?"
                events.append({"ts": ts_str, "bot": "DKBot", "type": "SELL", "color": "bad" if pnl != "?" and float(pnl) < 0 else "good",
                                "msg": f"SELL {sym} pnl={pnl} XRP"})
    except:
        pass

    # Axiom log events
    try:
        with open(AXIOM_LOG, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 40000))
            tail = f.read().decode("utf-8", errors="ignore")
        for line in tail.split("\n"):
            line = line.strip()
            if not line:
                continue
            ts_match = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
            ts_str = ts_match.group(1) if ts_match else ""
            if "Placing bet" in line or "BET" in line.upper() or "bet placed" in line.lower():
                events.append({"ts": ts_str, "bot": "Axiom", "type": "BET", "color": "accent",
                                "msg": line[:80]})
            elif "claimed" in line.lower() or "WIN" in line or "LOSS" in line:
                color = "good" if "WIN" in line or "win" in line else "bad"
                events.append({"ts": ts_str, "bot": "Axiom", "type": "CLAIM", "color": color,
                                "msg": line[:80]})
    except:
        pass

    events.sort(key=lambda x: x.get("ts",""), reverse=True)
    return events[:n]

def build_equity_curve(trades):
    if not trades:
        return []
    sorted_trades = sorted(trades, key=lambda x: x.get("exit_time", x.get("entry_time", 0)))
    cumulative = 0.0
    curve = []
    for t in sorted_trades:
        pnl = t.get("pnl_xrp", 0)
        cumulative += pnl
        ts = t.get("exit_time", t.get("entry_time", 0))
        curve.append({
            "ts":         ts,
            "label":      datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%m/%d %H:%M") if ts else "",
            "pnl":        round(pnl, 3),
            "cumulative": round(cumulative, 3),
        })
    return curve

def compute_stats(trades):
    if not trades:
        return {"wr":0,"avg_win":0,"avg_loss":0,"best":0,"worst":0,"total":0,
                "wins":0,"losses":0,"drawdown":0,"sharpe":0,"total_realized":0,
                "total_fees":0,"total_volume":0}
    wins   = [t for t in trades if t.get("pnl_xrp", 0) > 0]
    losses = [t for t in trades if t.get("pnl_xrp", 0) <= 0]
    pnls   = [t.get("pnl_xrp", 0) for t in trades]
    total_realized = sum(pnls)
    avg_win  = sum(t.get("pnl_xrp",0) for t in wins) / max(len(wins),1)
    avg_loss = sum(t.get("pnl_xrp",0) for t in losses) / max(len(losses),1)
    best  = max(pnls) if pnls else 0
    worst = min(pnls) if pnls else 0

    # Max drawdown
    peak = 0
    max_dd = 0
    cum = 0
    for p in pnls:
        cum += p
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd

    # Sharpe (annualized, assume 1h per trade)
    import statistics
    sharpe = 0
    if len(pnls) > 2:
        try:
            std = statistics.stdev(pnls)
            mean = statistics.mean(pnls)
            sharpe = round((mean / std) * (8760 ** 0.5), 2) if std > 0 else 0
        except:
            pass

    # Fee estimate: 0.3% of XRP volume
    total_volume = sum(t.get("xrp_spent", t.get("xrp_in", 0)) for t in trades)
    total_fees   = round(total_volume * 0.003, 3)

    return {
        "wr":            round(len(wins) / len(trades) * 100, 1),
        "avg_win":       round(avg_win, 3),
        "avg_loss":      round(avg_loss, 3),
        "best":          round(best, 3),
        "worst":         round(worst, 3),
        "total":         len(trades),
        "wins":          len(wins),
        "losses":        len(losses),
        "drawdown":      round(max_dd, 3),
        "sharpe":        sharpe,
        "total_realized": round(total_realized, 3),
        "total_fees":    total_fees,
        "total_volume":  round(total_volume, 3),
    }

def compute_health_score(stats, regime, weights):
    # Warmup mode: no trades since reset yet — system is fresh, not broken
    # Show 50 (neutral) rather than penalising for zero data
    if stats.get("total", 0) == 0:
        return 50

    score = 50  # baseline

    # Win rate component (0-25 pts)
    wr = stats.get("wr", 0)
    if wr >= 50:   score += 25
    elif wr >= 40: score += 15
    elif wr >= 30: score += 5
    elif wr < 20:  score -= 15

    # Drawdown component (0 to -20 pts)
    dd = stats.get("drawdown", 0)
    if dd < 5:    pass
    elif dd < 10: score -= 5
    elif dd < 20: score -= 12
    else:         score -= 20

    # Regime component (-10 to +10) — only apply when we have 5+ trades
    if stats.get("total", 0) >= 5:
        r = regime.get("regime", "neutral")
        if r == "hot":     score += 10
        elif r == "cold":  score -= 10

    # Cold streak from weights — only meaningful with real post-reset trades
    if stats.get("total", 0) >= 5:
        insights = weights.get("insights", [])
        cold = any("Cold streak" in i for i in insights)
        if cold: score -= 8

    return max(1, min(100, score))

def get_state_breakdown(trades):
    """PnL by chart state"""
    from collections import defaultdict
    by_state = defaultdict(list)
    for t in trades:
        by_state[t.get("chart_state","?")].append(t.get("pnl_xrp",0))
    result = {}
    for state, pnls in by_state.items():
        wins = [p for p in pnls if p > 0]
        result[state] = {
            "n":    len(pnls),
            "wr":   round(len(wins)/len(pnls)*100,1) if pnls else 0,
            "total": round(sum(pnls),3),
            "avg":  round(sum(pnls)/len(pnls),3) if pnls else 0,
        }
    return result

def get_band_breakdown(trades):
    """WR by score band"""
    from collections import defaultdict
    by_band = defaultdict(list)
    for t in trades:
        by_band[t.get("score_band","?")].append(t.get("pnl_xrp",0))
    result = {}
    for band, pnls in by_band.items():
        wins = [p for p in pnls if p > 0]
        result[band] = {
            "n":  len(pnls),
            "wr": round(len(wins)/len(pnls)*100,1) if pnls else 0,
        }
    return result

def get_axiom_family_stats(closed):
    from collections import defaultdict
    by_fam = defaultdict(list)
    for p in closed:
        by_fam[p.get("family","?")].append(p)
    result = {}
    for fam, preds in by_fam.items():
        wins = [p for p in preds if p.get("result") == "win"]
        pnls = [p.get("pnl",0) for p in preds]
        result[fam] = {
            "n":    len(preds),
            "wr":   round(len(wins)/len(preds)*100,1) if preds else 0,
            "avg":  round(sum(pnls)/len(pnls),3) if pnls else 0,
        }
    return result

def get_config_values():
    """Read key config values from config.py"""
    vals = {}
    try:
        with open(CONFIG_FILE) as f:
            text = f.read()
        patterns = {
            "SCORE_TRADEABLE": r"SCORE_TRADEABLE\s*=\s*(\d+)",
            "SCORE_ELITE":     r"SCORE_ELITE\s*=\s*(\d+)",
            "XRP_PER_TRADE_BASE": r"XRP_PER_TRADE_BASE\s*=\s*([\d.]+)",
            "XRP_ELITE_BASE":  r"XRP_ELITE_BASE\s*=\s*([\d.]+)",
            "XRP_MICRO_BASE":  r"XRP_MICRO_BASE\s*=\s*([\d.]+)",
            "HARD_STOP_PCT":   r"HARD_STOP_PCT\s*=\s*([\d.]+)",
            "HARD_STOP_EARLY_PCT": r"HARD_STOP_EARLY_PCT\s*=\s*([\d.]+)",
            "MIN_TVL_XRP":     r"MIN_TVL_XRP\s*=\s*(\d+)",
            "TVL_MICRO_CAP_XRP": r"TVL_MICRO_CAP_XRP\s*=\s*(\d+)",
            "MIN_TVL_DROP_EXIT": r"MIN_TVL_DROP_EXIT\s*=\s*([\d.]+)",
        }
        for k, pat in patterns.items():
            m = re.search(pat, text)
            if m:
                vals[k] = m.group(1)
        # Chart states
        m = re.search(r"PREFERRED_CHART_STATES\s*=\s*\{([^}]+)\}", text)
        if m:
            vals["PREFERRED_CHART_STATES"] = m.group(1).strip()
    except:
        pass
    return vals

def _j(v):
    """Safe JSON encode"""
    return json.dumps(v, ensure_ascii=False)

# ── HTML render ────────────────────────────────────────────────────────────

def render_html(d):
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    xrp_p   = d["xrp_price"]
    total_xrp = d["balance"][0]
    spendable = d["balance"][1]
    axiom_vault = d["axiom"]["vault"]
    positions   = d["positions"]
    trades      = d["trades"]
    stats       = d["stats"]
    regime      = d["regime"]
    weights     = d["weights"]
    health      = d["health"]
    activity    = d["activity"]
    equity      = d["equity"]
    state_bk    = d["state_breakdown"]
    band_bk     = d["band_breakdown"]
    axiom_fam   = d["axiom_family"]
    bot_status  = d["bot_status"]
    cfg         = d["config"]
    fg          = d["fear_greed"]
    btc_price   = d["btc_price"]
    axiom_open  = d["axiom"]["open"]
    axiom_closed = d["axiom"]["closed"]
    axiom_stats  = d["axiom_stats"]

    # Derived
    portfolio_usd = round(total_xrp * xrp_p, 2)
    net_pnl   = stats.get("total_realized", 0)
    net_pnl_c = "good" if net_pnl >= 0 else "bad"

    # DKBot exposure
    open_xrp = sum(p.get("xrp_in", 0) for p in positions)
    axiom_xrp = sum(p.get("stake", 0) for p in axiom_open)
    total_exposed = open_xrp + axiom_xrp + axiom_vault
    dkbot_pct = round(open_xrp / max(total_xrp, 1) * 100, 1)
    axiom_pct = round((axiom_vault + axiom_xrp) / max(total_xrp, 1) * 100, 1)
    var_dkbot = round(open_xrp * 0.15, 2)
    var_axiom = round(axiom_xrp, 2)
    var_total = round(var_dkbot + var_axiom, 2)
    corr_warn = dkbot_pct > 40 and axiom_pct > 20

    dk_status_color  = "good" if bot_status["dkbot"]  == "running" else "warn"
    ax_status_color  = "good" if bot_status["axiom"]  == "running" else "warn"
    dk_status_label  = bot_status["dkbot"].upper()
    ax_status_label  = bot_status["axiom"].upper()

    # Accounting
    earned = sum(t.get("pnl_xrp", 0) for t in trades if t.get("pnl_xrp", 0) > 0)
    lost   = sum(t.get("pnl_xrp", 0) for t in trades if t.get("pnl_xrp", 0) < 0)
    fees   = stats.get("total_fees", 0)
    growth_pct = round(net_pnl / max(spendable - net_pnl, 1) * 100, 2) if spendable > 0 else 0

    # Equity curve labels/data
    eq_labels = [e["label"] for e in equity] or ["Start"]
    eq_data   = [e["cumulative"] for e in equity] or [0]

    # Chart state bar chart
    cs_labels = list(state_bk.keys())
    cs_pnl    = [state_bk[k]["total"] for k in cs_labels]
    cs_wr     = [state_bk[k]["wr"] for k in cs_labels]

    # Band WR bar chart
    band_labels = list(band_bk.keys())
    band_wr     = [band_bk[k]["wr"] for k in band_labels]

    # Axiom family
    af_labels = list(axiom_fam.keys()) or ["hourly_crypto","daily_crypto","sports"]
    af_wr     = [axiom_fam.get(k, {}).get("wr", 0) for k in af_labels]
    af_avg    = [axiom_fam.get(k, {}).get("avg", 0) for k in af_labels]

    # Exposure doughnut
    exp_labels = [p["symbol"] for p in positions] + ["Axiom Vault", "Available"]
    exp_data   = [p.get("xrp_in", 0) for p in positions] + [axiom_vault, max(0, spendable - open_xrp)]

    # Active positions rows
    def pos_rows():
        rows = ""
        for p in positions:
            color = "good" if p["pnl_pct"] >= 0 else "bad"
            held_str = f"{int(p['held_min']//60)}h {int(p['held_min']%60)}m" if p['held_min'] >= 60 else f"{int(p['held_min'])}m"
            rows += f"""<tr class="row-{color}">
              <td><b>{p['symbol']}</b></td>
              <td class="mono">{p['entry_price']:.8f}</td>
              <td class="mono">{p['current_price']:.8f}</td>
              <td class="mono">{p['xrp_in']:.2f}</td>
              <td class="mono c-{color}">{p['unreal_pnl']:+.3f}</td>
              <td class="mono c-{color}">{p['pnl_pct']:+.2f}%</td>
              <td class="muted">{held_str}</td>
              <td>{p['score']}</td>
              <td><span class="badge">{p['chart_state']}</span></td>
            </tr>"""
        if not rows:
            rows = '<tr><td colspan="9" class="muted center">No open positions</td></tr>'
        return rows

    # Trade history rows
    def trade_rows():
        rows = ""
        for t in sorted(trades, key=lambda x: -x.get("exit_time", x.get("entry_time", 0)))[:20]:
            pnl  = t.get("pnl_xrp", 0)
            pct  = t.get("pnl_pct", t.get("pnl_pct", 0))
            color = "good" if pnl > 0 else "bad"
            ts   = datetime.fromtimestamp(t.get("exit_time", t.get("entry_time", 0)), tz=timezone.utc).strftime("%m/%d %H:%M")
            ep   = t.get("entry_price", 0)
            xp   = t.get("exit_price", 0)
            xrp  = t.get("xrp_spent", t.get("xrp_in", 0))
            reason = t.get("exit_reason","?")
            rows += f"""<tr>
              <td class="muted mono">{ts}</td>
              <td><b>{t.get('symbol','?')}</b></td>
              <td class="mono">{ep:.8f}</td>
              <td class="mono">{xp:.8f}</td>
              <td class="mono">{xrp:.2f}</td>
              <td class="mono c-{color}">{pnl:+.3f}</td>
              <td class="mono c-{color}">{pct:+.1f}%</td>
              <td class="muted small">{reason}</td>
            </tr>"""
        if not rows:
            rows = '<tr><td colspan="8" class="muted center">No closed trades since reset (2026-04-06)</td></tr>'
        return rows

    # Axiom open rows
    def axiom_open_rows():
        rows = ""
        for p in axiom_open:
            rows += f"""<tr>
              <td class="small">{p['title']}</td>
              <td><span class="badge badge-{'good' if p['direction']=='Higher' else 'bad'}">{p['direction']}</span></td>
              <td class="mono">{p['stake']:.2f}</td>
              <td class="mono">{p['confidence']:.0%}</td>
              <td class="muted">{p['hours_left']:.1f}h</td>
              <td><span class="badge">OPEN</span></td>
            </tr>"""
        if not rows:
            rows = '<tr><td colspan="6" class="muted center">No open predictions</td></tr>'
        return rows

    def axiom_closed_rows():
        rows = ""
        for p in sorted(axiom_closed, key=lambda x: -x.get("ts",0))[:20]:
            result = p.get("result","?")
            color  = "good" if result == "win" else "bad"
            pnl    = p.get("pnl", 0)
            rows += f"""<tr>
              <td class="small">{p['title']}</td>
              <td><span class="badge badge-{'good' if p['direction']=='Higher' else 'bad'}">{p['direction']}</span></td>
              <td class="mono">{p['stake']:.2f}</td>
              <td><span class="badge badge-{color}">{result.upper()}</span></td>
              <td class="mono c-{color}">{pnl:+.3f}</td>
              <td class="muted small">{p['family']}</td>
            </tr>"""
        if not rows:
            rows = '<tr><td colspan="6" class="muted center">No closed predictions since reset</td></tr>'
        return rows

    # Activity feed
    def activity_rows():
        rows = ""
        icons = {"BUY":"🟢","SELL":"🔴","BET":"🔵","CLAIM":"💰"}
        for ev in activity:
            icon = icons.get(ev.get("type",""),"⚪")
            rows += f"""<div class="feed-item">
              <span class="feed-ts">{ev.get('ts','')[-8:]}</span>
              <span class="feed-bot">{ev.get('bot','')}</span>
              {icon} <span class="feed-msg">{ev.get('msg','')}</span>
            </div>"""
        if not rows:
            rows = '<div class="feed-item muted">No recent activity</div>'
        return rows

    # Learning insights
    def insight_cards():
        cards = ""
        for ins in weights.get("insights", []):
            color = "warn" if "⚠️" in ins or "Cold" in ins else "good"
            cards += f'<div class="insight-card c-{color}">{ins}</div>'
        if not cards:
            cards = '<div class="insight-card muted">Learning module warming up — needs more trades</div>'
        return cards

    # Settings rows
    def cfg_rows():
        labels = {
            "SCORE_TRADEABLE":    "Score Floor (normal entry)",
            "SCORE_ELITE":        "Score Floor (elite entry)",
            "XRP_PER_TRADE_BASE": "Normal Position Size (XRP)",
            "XRP_ELITE_BASE":     "Elite Position Size (XRP)",
            "XRP_MICRO_BASE":     "Micro-cap Position Size (XRP)",
            "HARD_STOP_PCT":      "Hard Stop %",
            "HARD_STOP_EARLY_PCT":"Early Stop % (first 30min)",
            "MIN_TVL_XRP":        "Min TVL (XRP)",
            "TVL_MICRO_CAP_XRP":  "Micro-cap TVL Threshold (XRP)",
            "MIN_TVL_DROP_EXIT":  "TVL Drain Exit Trigger",
            "PREFERRED_CHART_STATES": "Allowed Chart States",
        }
        rows = ""
        for k, label in labels.items():
            val = cfg.get(k, "—")
            rows += f"""<tr>
              <td class="muted">{label}</td>
              <td class="mono accent">{val}</td>
            </tr>"""
        return rows

    # Health score color
    h_color = "good" if health >= 60 else ("warn" if health >= 35 else "bad")
    regime_label = regime.get("regime","?").upper()
    regime_color = "good" if regime_label == "HOT" else ("warn" if regime_label == "NEUTRAL" else "bad")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DKTrenchBot Terminal</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;900&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
:root{{
  --bg:#080e1a;--panel:#0d1526;--panel2:#111e35;--border:#1e2d4a;
  --text:#e8eeff;--muted:#6b7fa3;--good:#00d4aa;--warn:#f5a623;
  --bad:#ff4d6d;--accent:#3d9bff;--accent2:#7b5ea7;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Inter',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;font-size:13px;line-height:1.5}}
a{{color:var(--accent);text-decoration:none}}
.wrap{{max-width:1480px;margin:0 auto;padding:16px 20px}}

/* TOP BAR */
.topbar{{display:flex;align-items:center;gap:16px;padding:12px 20px;background:var(--panel);border-bottom:1px solid var(--border);flex-wrap:wrap;position:sticky;top:0;z-index:100}}
.topbar-title{{font-size:15px;font-weight:700;letter-spacing:-.01em;color:var(--text)}}
.topbar-title span{{color:var(--accent)}}
.topbar-pills{{display:flex;gap:8px;flex-wrap:wrap;align-items:center;flex:1}}
.pill{{background:var(--panel2);border:1px solid var(--border);padding:5px 12px;border-radius:999px;font-size:12px;display:flex;align-items:center;gap:6px;cursor:pointer}}
.pill:hover{{border-color:var(--accent)}}
.dot{{width:7px;height:7px;border-radius:50%;display:inline-block;flex-shrink:0}}
.dot.good{{background:var(--good);box-shadow:0 0 6px var(--good)}}
.dot.warn{{background:var(--warn)}}
.dot.bad{{background:var(--bad)}}
.dot.pulse{{animation:pulse 2s infinite}}
@keyframes pulse{{0%,100%{{opacity:1;transform:scale(1)}}50%{{opacity:.6;transform:scale(1.3)}}}}
#timer{{font-weight:700;color:var(--accent)}}
#timer.urgent{{color:var(--warn);animation:blink .5s infinite}}
@keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:.4}}}}

/* TABS */
.tabs{{display:flex;gap:0;border-bottom:1px solid var(--border);margin:20px 0 0 0;background:var(--panel)}}
.tab{{padding:12px 20px;cursor:pointer;font-size:13px;font-weight:500;color:var(--muted);border-bottom:2px solid transparent;transition:all .15s;white-space:nowrap}}
.tab:hover{{color:var(--text)}}
.tab.active{{color:var(--accent);border-bottom-color:var(--accent)}}
.tab-content{{display:none;padding:20px 0}}
.tab-content.active{{display:block}}

/* CARDS */
.cards{{display:grid;gap:12px;margin-bottom:16px}}
.cards-4{{grid-template-columns:repeat(4,1fr)}}
.cards-3{{grid-template-columns:repeat(3,1fr)}}
.cards-6{{grid-template-columns:repeat(6,1fr)}}
.card{{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:16px 18px}}
.card-label{{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px}}
.card-value{{font-size:22px;font-weight:700}}
.card-sub{{font-size:12px;color:var(--muted);margin-top:4px}}
.card-sub.c-good{{color:var(--good)}}
.card-sub.c-bad{{color:var(--bad)}}
.card-sub.c-warn{{color:var(--warn)}}

/* METRICS BAR */
.metrics-bar{{display:flex;gap:0;background:var(--panel);border:1px solid var(--border);border-radius:10px;overflow:hidden;margin-bottom:16px}}
.metric{{flex:1;padding:14px 16px;border-right:1px solid var(--border);text-align:center}}
.metric:last-child{{border-right:none}}
.metric-label{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.07em;margin-bottom:5px}}
.metric-val{{font-size:18px;font-weight:700}}

/* TABLES */
.table-wrap{{background:var(--panel);border:1px solid var(--border);border-radius:10px;overflow:hidden;margin-bottom:16px}}
.table-header{{padding:12px 16px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center}}
.table-header h3{{font-size:13px;font-weight:600}}
table{{width:100%;border-collapse:collapse}}
th{{padding:10px 12px;text-align:left;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);border-bottom:1px solid var(--border)}}
td{{padding:10px 12px;border-bottom:1px solid rgba(30,45,74,.5);font-size:12px}}
tr:last-child td{{border-bottom:none}}
tr.row-good{{background:rgba(0,212,170,.04)}}
tr.row-bad{{background:rgba(255,77,109,.04)}}
tr:hover td{{background:rgba(61,155,255,.05)}}
.mono{{font-family:monospace;font-size:11px}}
.small{{font-size:11px}}
.center{{text-align:center}}

/* COLORS */
.c-good{{color:var(--good)}}
.c-bad{{color:var(--bad)}}
.c-warn{{color:var(--warn)}}
.accent{{color:var(--accent)}}
.muted{{color:var(--muted)}}

/* BADGES */
.badge{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:600;background:var(--panel2);border:1px solid var(--border);text-transform:uppercase}}
.badge-good{{background:rgba(0,212,170,.15);border-color:var(--good);color:var(--good)}}
.badge-bad{{background:rgba(255,77,109,.15);border-color:var(--bad);color:var(--bad)}}
.badge-warn{{background:rgba(245,166,35,.15);border-color:var(--warn);color:var(--warn)}}

/* CHARTS */
.chart-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px}}
.chart-box{{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:16px}}
.chart-box h3{{font-size:12px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:12px}}

/* HEALTH SCORE */
.health-wrap{{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:16px}}
.health-score{{font-size:64px;font-weight:900;line-height:1;margin:8px 0}}
.health-bar{{margin:8px 0 4px;background:var(--panel2);border-radius:4px;height:6px;overflow:hidden}}
.health-bar-fill{{height:100%;border-radius:4px;transition:width .5s}}

/* ACTIVITY FEED */
.feed{{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:16px}}
.feed h3{{font-size:12px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:12px}}
.feed-item{{display:flex;gap:10px;align-items:baseline;padding:6px 0;border-bottom:1px solid rgba(30,45,74,.4);font-size:12px}}
.feed-item:last-child{{border-bottom:none}}
.feed-ts{{color:var(--muted);font-family:monospace;font-size:11px;flex-shrink:0;width:50px}}
.feed-bot{{font-size:10px;font-weight:600;text-transform:uppercase;color:var(--accent2);flex-shrink:0;width:42px}}
.feed-msg{{color:var(--text)}}

/* INSIGHTS */
.insights-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:8px;margin-bottom:16px}}
.insight-card{{background:var(--panel2);border:1px solid var(--border);border-radius:8px;padding:12px 14px;font-size:12px}}

/* RISK */
.risk-warn{{background:rgba(255,77,109,.1);border:1px solid var(--bad);border-radius:8px;padding:12px 16px;margin-bottom:16px;color:var(--bad);font-weight:600}}
.var-box{{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:16px}}
.var-row{{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border);font-size:13px}}
.var-row:last-child{{border-bottom:none}}

/* ACCOUNTING */
.flow-table{{background:var(--panel);border:1px solid var(--border);border-radius:10px;overflow:hidden;margin-bottom:16px}}
.flow-row{{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;border-bottom:1px solid var(--border);font-size:13px}}
.flow-row:last-child{{border-bottom:none}}
.flow-row.total{{background:var(--panel2);font-weight:700}}
.export-btn{{display:inline-block;padding:10px 20px;background:var(--accent);color:#fff;border-radius:8px;font-weight:600;cursor:pointer;font-size:13px;border:none}}
.export-btn:hover{{background:#2d8aef}}

/* SETTINGS */
.settings-wrap{{background:var(--panel);border:1px solid var(--border);border-radius:10px;overflow:hidden;margin-bottom:16px}}
.settings-header{{padding:12px 16px;border-bottom:1px solid var(--border);font-size:12px;color:var(--muted)}}

/* SECTION TITLE */
.section-title{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin:20px 0 12px}}

@media(max-width:900px){{
  .cards-4,.cards-6{{grid-template-columns:repeat(2,1fr)}}
  .chart-grid{{grid-template-columns:1fr}}
  .metrics-bar{{flex-wrap:wrap}}
  .metric{{min-width:50%}}
}}
</style>
</head>
<body>

<!-- TOP BAR -->
<div class="topbar">
  <div class="topbar-title">DKTrenchBot <span>Terminal</span></div>
  <div class="topbar-pills">
    <div class="pill" onclick="navigator.clipboard.writeText('{WALLET}')" title="Click to copy">
      📋 {WALLET[:8]}...{WALLET[-4:]}
    </div>
    <div class="pill">
      <span class="dot {'good' if bot_status['dkbot'] == 'running' else 'warn'} pulse"></span>
      DKBot {dk_status_label}
    </div>
    <div class="pill">
      <span class="dot {'good' if bot_status['axiom'] == 'running' else 'warn'}"></span>
      Axiom {ax_status_label}
    </div>
    <div class="pill">💱 XRP <b style="color:var(--accent)">${xrp_p:.4f}</b></div>
    <div class="pill">😱 F&G <b style="color:var({'--bad' if fg < 35 else '--warn' if fg < 50 else '--good'})">{fg}</b></div>
    <div class="pill">₿ <b>${btc_price:,.0f}</b></div>
    <div class="pill">🕐 Updated {now_utc}</div>
    <div class="pill" style="margin-left:auto">↻ <b id="timer">60s</b></div>
  </div>
</div>

<!-- NAV TABS -->
<div class="wrap">
<div class="tabs">
  <div class="tab active" onclick="showTab('overview')">📊 Overview</div>
  <div class="tab" onclick="showTab('dkbot')">🤖 DK Bot</div>
  <div class="tab" onclick="showTab('axiom')">🗳 Axiom Bot</div>
  <div class="tab" onclick="showTab('risk')">⚠️ Risk</div>
  <div class="tab" onclick="showTab('accounting')">💰 Accounting</div>
  <div class="tab" onclick="showTab('settings')">⚙️ Settings</div>
</div>

<!-- ═══════════════════════════════════════════════════════
     TAB 1: OVERVIEW
═══════════════════════════════════════════════════════ -->
<div id="tab-overview" class="tab-content active">

  <div class="cards cards-4">
    <div class="card">
      <div class="card-label">Total Portfolio</div>
      <div class="card-value">{total_xrp:.2f} <small style="font-size:14px;color:var(--muted)">XRP</small></div>
      <div class="card-sub">${portfolio_usd:,.2f} USD</div>
    </div>
    <div class="card">
      <div class="card-label">DKBot Capital</div>
      <div class="card-value">{spendable:.2f} <small style="font-size:14px;color:var(--muted)">XRP</small></div>
      <div class="card-sub c-{'good' if open_xrp > 0 else 'muted'}">{len(positions)} positions open · {open_xrp:.2f} XRP deployed</div>
    </div>
    <div class="card">
      <div class="card-label">Axiom Vault</div>
      <div class="card-value">{axiom_vault:.2f} <small style="font-size:14px;color:var(--muted)">XRP</small></div>
      <div class="card-sub">{len(axiom_open)} open bets · gas: {d['axiom']['gas']:.2f} XRP</div>
    </div>
    <div class="card">
      <div class="card-label">Net PnL (since 04/06)</div>
      <div class="card-value c-{net_pnl_c}">{net_pnl:+.3f} <small style="font-size:14px">XRP</small></div>
      <div class="card-sub c-{net_pnl_c}">${net_pnl*xrp_p:+.2f} USD</div>
    </div>
  </div>

  <div class="metrics-bar">
    <div class="metric">
      <div class="metric-label">Win Rate</div>
      <div class="metric-val c-{'good' if stats['wr'] >= 40 else 'warn' if stats['wr'] >= 25 else 'bad'}">{stats['wr']:.1f}%</div>
    </div>
    <div class="metric">
      <div class="metric-label">Avg Win</div>
      <div class="metric-val c-good">{stats['avg_win']:+.3f}</div>
    </div>
    <div class="metric">
      <div class="metric-label">Avg Loss</div>
      <div class="metric-val c-bad">{stats['avg_loss']:+.3f}</div>
    </div>
    <div class="metric">
      <div class="metric-label">Best Trade</div>
      <div class="metric-val c-good">{stats['best']:+.3f}</div>
    </div>
    <div class="metric">
      <div class="metric-label">Total Trades</div>
      <div class="metric-val">{stats['total']}</div>
    </div>
    <div class="metric">
      <div class="metric-label">Sharpe</div>
      <div class="metric-val c-{'good' if stats['sharpe'] > 1 else 'warn' if stats['sharpe'] > 0 else 'bad'}">{stats['sharpe']}</div>
    </div>
    <div class="metric">
      <div class="metric-label">Max Drawdown</div>
      <div class="metric-val c-bad">{stats['drawdown']:.2f} XRP</div>
    </div>
    <div class="metric">
      <div class="metric-label">Axiom Accuracy</div>
      <div class="metric-val c-{'good' if axiom_stats['wr'] >= 50 else 'warn'}">{axiom_stats['wr']:.1f}%</div>
    </div>
  </div>

  <div class="chart-grid">
    <div class="chart-box">
      <h3>Equity Curve — Cumulative PnL (XRP) since reset</h3>
      <canvas id="equityChart" height="160"></canvas>
    </div>
    <div class="health-wrap">
      <div class="card-label">Bot Health Score</div>
      <div class="health-score c-{h_color}">{health}</div>
      <div class="card-sub" style="margin-bottom:12px">out of 100 — {'Healthy' if health >= 60 else 'Caution' if health >= 35 else 'Critical'}</div>
      <div class="card-label" style="margin-top:8px">Win Rate</div>
      <div class="health-bar"><div class="health-bar-fill" style="width:{min(100,stats['wr'])}%;background:var(--{'good' if stats['wr']>=40 else 'warn' if stats['wr']>=25 else 'bad'})"></div></div>
      <div class="card-label" style="margin-top:8px">Regime</div>
      <div style="margin-top:4px"><span class="badge badge-{regime_color.lower()}">{regime_label}</span>
        <span class="muted" style="margin-left:8px;font-size:11px">{regime.get('details',{}).get('consecutive_losses',0)} consec. losses</span>
      </div>
      <div class="card-label" style="margin-top:12px">Trade Count</div>
      <div class="health-bar"><div class="health-bar-fill" style="width:{min(100,stats['total']*5)}%;background:var(--accent)"></div></div>
      <div style="margin-top:4px;font-size:11px;color:var(--muted)">{stats['total']} trades since reset</div>
    </div>
  </div>

  <div class="section-title">Recent Activity</div>
  <div class="feed">
    <h3>Live Feed — Both Bots</h3>
    {activity_rows()}
  </div>

</div>

<!-- ═══════════════════════════════════════════════════════
     TAB 2: DK BOT
═══════════════════════════════════════════════════════ -->
<div id="tab-dkbot" class="tab-content">

  <div class="cards cards-6">
    <div class="card">
      <div class="card-label">Status</div>
      <div class="card-value" style="font-size:16px"><span class="dot {dk_status_color}" style="margin-right:6px"></span>{dk_status_label}</div>
    </div>
    <div class="card">
      <div class="card-label">Capital</div>
      <div class="card-value" style="font-size:18px">{spendable:.2f} XRP</div>
    </div>
    <div class="card">
      <div class="card-label">Open Positions</div>
      <div class="card-value" style="font-size:18px">{len(positions)}</div>
      <div class="card-sub">{open_xrp:.2f} XRP deployed</div>
    </div>
    <div class="card">
      <div class="card-label">Regime</div>
      <div class="card-value" style="font-size:18px"><span class="c-{regime_color.lower()}">{regime_label}</span></div>
    </div>
    <div class="card">
      <div class="card-label">Win Rate</div>
      <div class="card-value" style="font-size:18px c-{'good' if stats['wr']>=40 else 'bad'}">{stats['wr']}%</div>
      <div class="card-sub">{stats['wins']}W / {stats['losses']}L</div>
    </div>
    <div class="card">
      <div class="card-label">Realized PnL</div>
      <div class="card-value c-{net_pnl_c}" style="font-size:18px">{net_pnl:+.3f} XRP</div>
    </div>
  </div>

  <div class="section-title">Active Positions</div>
  <div class="table-wrap">
    <div class="table-header"><h3>Open Positions</h3></div>
    <table>
      <thead><tr>
        <th>Token</th><th>Entry Price</th><th>Current Price</th>
        <th>Size XRP</th><th>Unreal PnL</th><th>% Chg</th>
        <th>Time Held</th><th>Score</th><th>State</th>
      </tr></thead>
      <tbody>{pos_rows()}</tbody>
    </table>
  </div>

  <div class="section-title">Trade History <span class="muted" style="font-weight:400;font-size:11px">— post-optimization only (since 2026-04-06)</span></div>
  <div class="table-wrap">
    <div class="table-header"><h3>Closed Trades</h3><span class="muted">{stats['total']} total</span></div>
    <table>
      <thead><tr>
        <th>Time</th><th>Token</th><th>Entry</th><th>Exit</th>
        <th>Size</th><th>PnL XRP</th><th>PnL %</th><th>Exit Reason</th>
      </tr></thead>
      <tbody>{trade_rows()}</tbody>
    </table>
  </div>

  <div class="section-title">Analytics</div>
  <div class="chart-grid">
    <div class="chart-box">
      <h3>PnL by Chart State</h3>
      <canvas id="stateChart" height="180"></canvas>
    </div>
    <div class="chart-box">
      <h3>Win Rate by Score Band</h3>
      <canvas id="bandChart" height="180"></canvas>
    </div>
  </div>

  <div class="section-title">Self-Learning Module</div>
  <div class="insights-grid">{insight_cards()}</div>

</div>

<!-- ═══════════════════════════════════════════════════════
     TAB 3: AXIOM BOT
═══════════════════════════════════════════════════════ -->
<div id="tab-axiom" class="tab-content">

  <div class="cards cards-6">
    <div class="card">
      <div class="card-label">Status</div>
      <div class="card-value" style="font-size:16px"><span class="dot {ax_status_color}" style="margin-right:6px"></span>{ax_status_label}</div>
    </div>
    <div class="card">
      <div class="card-label">Vault Balance</div>
      <div class="card-value" style="font-size:18px">{axiom_vault:.2f} XRP</div>
    </div>
    <div class="card">
      <div class="card-label">Gas Wallet</div>
      <div class="card-value" style="font-size:18px">{d['axiom']['gas']:.2f} XRP</div>
    </div>
    <div class="card">
      <div class="card-label">Open Bets</div>
      <div class="card-value" style="font-size:18px">{len(axiom_open)}</div>
    </div>
    <div class="card">
      <div class="card-label">Win Rate (post-reset)</div>
      <div class="card-value c-{'good' if axiom_stats['wr']>=50 else 'bad'}" style="font-size:18px">{axiom_stats['wr']:.1f}%</div>
      <div class="card-sub">{axiom_stats['wins']}W / {axiom_stats['losses']}L</div>
    </div>
    <div class="card">
      <div class="card-label">Total PnL</div>
      <div class="card-value c-{'good' if axiom_stats['total_pnl']>=0 else 'bad'}" style="font-size:18px">{axiom_stats['total_pnl']:+.3f} XRP</div>
    </div>
  </div>

  <div class="section-title">Open Predictions</div>
  <div class="table-wrap">
    <div class="table-header"><h3>Open Predictions</h3></div>
    <table>
      <thead><tr><th>Market</th><th>Direction</th><th>Stake XRP</th><th>Confidence</th><th>Time Left</th><th>Status</th></tr></thead>
      <tbody>{axiom_open_rows()}</tbody>
    </table>
  </div>

  <div class="section-title">Closed Predictions <span class="muted" style="font-weight:400;font-size:11px">— post-optimization only</span></div>
  <div class="table-wrap">
    <div class="table-header"><h3>Closed Bets</h3><span class="muted">{axiom_stats['total']} total</span></div>
    <table>
      <thead><tr><th>Market</th><th>Direction</th><th>Stake</th><th>Result</th><th>PnL</th><th>Family</th></tr></thead>
      <tbody>{axiom_closed_rows()}</tbody>
    </table>
  </div>

  <div class="section-title">Performance by Family</div>
  <div class="chart-box" style="background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:16px">
    <h3 class="chart-box h3">Win Rate & Avg PnL by Family</h3>
    <canvas id="familyChart" height="160"></canvas>
  </div>

</div>

<!-- ═══════════════════════════════════════════════════════
     TAB 4: RISK
═══════════════════════════════════════════════════════ -->
<div id="tab-risk" class="tab-content">

  {'<div class="risk-warn">⚠️ HIGH SYSTEMIC CORRELATION — Both bots are XRP-directional. Combined exposure exceeds 60% of wallet.</div>' if corr_warn else ''}

  <div class="cards cards-4">
    <div class="card">
      <div class="card-label">Total Exposed Capital</div>
      <div class="card-value">{total_exposed:.2f} XRP</div>
      <div class="card-sub">{round(total_exposed/max(total_xrp,1)*100,1)}% of portfolio</div>
    </div>
    <div class="card">
      <div class="card-label">DKBot Exposure</div>
      <div class="card-value c-{'warn' if dkbot_pct > 40 else 'good'}">{dkbot_pct}%</div>
      <div class="card-sub">{open_xrp:.2f} XRP in {len(positions)} tokens</div>
    </div>
    <div class="card">
      <div class="card-label">Axiom Exposure</div>
      <div class="card-value c-{'warn' if axiom_pct > 30 else 'good'}">{axiom_pct}%</div>
      <div class="card-sub">{axiom_vault:.2f} XRP vault</div>
    </div>
    <div class="card">
      <div class="card-label">Liquidity Risk</div>
      <div class="card-value c-{'bad' if len(positions) > 3 else 'warn' if len(positions) > 1 else 'good'}">{'HIGH' if len(positions) > 3 else 'MEDIUM' if len(positions) > 1 else 'LOW'}</div>
      <div class="card-sub">Meme token illiquidity</div>
    </div>
  </div>

  <div class="var-box">
    <div class="section-title" style="margin-top:0">Value at Risk — Worst Case Scenario</div>
    <div class="var-row">
      <span>DKBot max drawdown (all stops hit @ -15%)</span>
      <span class="c-bad">-{var_dkbot:.2f} XRP</span>
    </div>
    <div class="var-row">
      <span>Axiom max loss (all open bets lose)</span>
      <span class="c-bad">-{var_axiom:.2f} XRP</span>
    </div>
    <div class="var-row">
      <span>Historical max drawdown</span>
      <span class="c-bad">-{stats['drawdown']:.2f} XRP</span>
    </div>
    <div class="var-row" style="font-weight:700">
      <span>Total worst-case downside</span>
      <span class="c-bad">-{var_total:.2f} XRP</span>
    </div>
    <div class="var-row">
      <span>Portfolio after worst case</span>
      <span class="c-warn">{max(0, total_xrp - var_total):.2f} XRP (${max(0, total_xrp - var_total)*xrp_p:.2f})</span>
    </div>
  </div>

  <div class="chart-box" style="background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:16px">
    <h3>Capital Exposure Breakdown</h3>
    <div style="max-width:340px;margin:0 auto">
      <canvas id="exposureChart" height="240"></canvas>
    </div>
  </div>

</div>

<!-- ═══════════════════════════════════════════════════════
     TAB 5: ACCOUNTING
═══════════════════════════════════════════════════════ -->
<div id="tab-accounting" class="tab-content">

  <div class="section-title">XRP Flow Statement — Post-Optimization (since 2026-04-06)</div>
  <div class="flow-table">
    <div class="flow-row">
      <span class="muted">Starting Capital (baseline)</span>
      <span class="mono">{round(spendable - net_pnl, 3)} XRP</span>
    </div>
    <div class="flow-row">
      <span>Realized Gains (winning trades)</span>
      <span class="mono c-good">+{earned:.3f} XRP</span>
    </div>
    <div class="flow-row">
      <span>Realized Losses (losing trades)</span>
      <span class="mono c-bad">{lost:.3f} XRP</span>
    </div>
    <div class="flow-row">
      <span class="muted">Est. Fees & Slippage (0.3% of volume)</span>
      <span class="mono c-warn">-{fees:.3f} XRP</span>
    </div>
    <div class="flow-row">
      <span class="muted">Total Volume Traded</span>
      <span class="mono">{stats['total_volume']:.2f} XRP</span>
    </div>
    <div class="flow-row total">
      <span>Net XRP Change</span>
      <span class="mono c-{net_pnl_c}">{net_pnl:+.3f} XRP ({growth_pct:+.1f}%)</span>
    </div>
    <div class="flow-row total">
      <span>Current Portfolio Value</span>
      <span class="mono accent">{total_xrp:.3f} XRP · ${portfolio_usd:,.2f}</span>
    </div>
  </div>

  <div class="section-title">Trade Summary</div>
  <div class="table-wrap">
    <div class="table-header"><h3>Trade Breakdown</h3></div>
    <table>
      <thead><tr><th>Metric</th><th>Value</th></tr></thead>
      <tbody>
        <tr><td class="muted">Total Trades</td><td class="mono">{stats['total']}</td></tr>
        <tr><td class="muted">Winners</td><td class="mono c-good">{stats['wins']}</td></tr>
        <tr><td class="muted">Losers</td><td class="mono c-bad">{stats['losses']}</td></tr>
        <tr><td class="muted">Win Rate</td><td class="mono">{stats['wr']}%</td></tr>
        <tr><td class="muted">Average Win</td><td class="mono c-good">{stats['avg_win']:+.3f} XRP</td></tr>
        <tr><td class="muted">Average Loss</td><td class="mono c-bad">{stats['avg_loss']:+.3f} XRP</td></tr>
        <tr><td class="muted">Best Trade</td><td class="mono c-good">{stats['best']:+.3f} XRP</td></tr>
        <tr><td class="muted">Worst Trade</td><td class="mono c-bad">{stats['worst']:+.3f} XRP</td></tr>
        <tr><td class="muted">Sharpe Ratio</td><td class="mono">{stats['sharpe']}</td></tr>
        <tr><td class="muted">Max Drawdown</td><td class="mono c-bad">-{stats['drawdown']:.3f} XRP</td></tr>
      </tbody>
    </table>
  </div>

  <button class="export-btn" onclick="exportCSV()">⬇ Export Trades CSV</button>

</div>

<!-- ═══════════════════════════════════════════════════════
     TAB 6: SETTINGS
═══════════════════════════════════════════════════════ -->
<div id="tab-settings" class="tab-content">

  <div class="settings-wrap">
    <div class="settings-header">⚙️ Live Bot Configuration — Read Only · Last generated {now_utc}</div>
    <table>
      <thead><tr><th>Parameter</th><th>Value</th></tr></thead>
      <tbody>{cfg_rows()}</tbody>
    </table>
  </div>

  <div class="section-title">Axiom Bot Config</div>
  <div class="settings-wrap">
    <table>
      <thead><tr><th>Parameter</th><th>Value</th></tr></thead>
      <tbody>
        <tr><td class="muted">Active Families</td><td class="mono accent">hourly_crypto, daily_crypto</td></tr>
        <tr><td class="muted">Confidence Floor</td><td class="mono accent">0.65</td></tr>
        <tr><td class="muted">Max Bet Horizon</td><td class="mono accent">48 hours</td></tr>
        <tr><td class="muted">F&G Filter</td><td class="mono accent">No Higher bets when F&G &lt; 35</td></tr>
        <tr><td class="muted">Min Edge</td><td class="mono accent">5% hourly / 7% daily</td></tr>
        <tr><td class="muted">Stake Sizing</td><td class="mono accent">Kelly criterion, 8-10% max per bet</td></tr>
      </tbody>
    </table>
  </div>

</div>
</div><!-- /wrap -->

<!-- DATA + JS -->
<script>
window.DASH_DATA = {{
  equity:    {_j(equity)},
  stateLabels: {_j(cs_labels)},
  statePnl:    {_j(cs_pnl)},
  stateWr:     {_j(cs_wr)},
  bandLabels:  {_j(band_labels)},
  bandWr:      {_j(band_wr)},
  afLabels:    {_j(af_labels)},
  afWr:        {_j(af_wr)},
  afAvg:       {_j(af_avg)},
  expLabels:   {_j(exp_labels)},
  expData:     {_j(exp_data)},
  trades:      {_j(trades)},
}};

// Tabs
function showTab(name) {{
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  event.target.classList.add('active');
}}

// Timer
let timeLeft = 60;
const timerEl = document.getElementById('timer');
setInterval(() => {{
  timeLeft--;
  timerEl.textContent = timeLeft + 's';
  if (timeLeft <= 5) timerEl.classList.add('urgent');
  if (timeLeft <= 0) location.reload();
}}, 1000);

// Chart defaults
Chart.defaults.color = '#6b7fa3';
Chart.defaults.borderColor = '#1e2d4a';
Chart.defaults.font.family = 'Inter';

const D = window.DASH_DATA;

// 1. Equity curve
if (D.equity.length > 0) {{
  new Chart(document.getElementById('equityChart'), {{
    type: 'line',
    data: {{
      labels: D.equity.map(e => e.label),
      datasets: [{{
        label: 'Cumulative PnL (XRP)',
        data: D.equity.map(e => e.cumulative),
        borderColor: '#3d9bff',
        backgroundColor: 'rgba(61,155,255,.08)',
        fill: true,
        tension: .3,
        pointRadius: 3,
        pointHoverRadius: 5,
      }}]
    }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ display: false }} }},
      scales: {{
        x: {{ ticks: {{ maxTicksLimit: 6 }} }},
        y: {{ ticks: {{ callback: v => v.toFixed(2) + ' XRP' }} }}
      }}
    }}
  }});
}} else {{
  const ctx = document.getElementById('equityChart');
  if (ctx) {{
    const c = ctx.getContext('2d');
    c.fillStyle = '#6b7fa3';
    c.font = '13px Inter';
    c.textAlign = 'center';
    c.fillText('No trades since reset — equity curve will appear after first exit', ctx.width/2, 80);
  }}
}}

// 2. PnL by chart state
if (D.stateLabels.length > 0) {{
  new Chart(document.getElementById('stateChart'), {{
    type: 'bar',
    data: {{
      labels: D.stateLabels,
      datasets: [{{
        label: 'Total PnL (XRP)',
        data: D.statePnl,
        backgroundColor: D.statePnl.map(v => v >= 0 ? 'rgba(0,212,170,.7)' : 'rgba(255,77,109,.7)'),
        borderRadius: 4,
      }}]
    }},
    options: {{
      indexAxis: 'y',
      responsive: true,
      plugins: {{ legend: {{ display: false }} }},
      scales: {{ x: {{ ticks: {{ callback: v => v.toFixed(2) }} }} }}
    }}
  }});
}}

// 3. Score band WR
if (D.bandLabels.length > 0) {{
  new Chart(document.getElementById('bandChart'), {{
    type: 'bar',
    data: {{
      labels: D.bandLabels,
      datasets: [{{
        label: 'Win Rate %',
        data: D.bandWr,
        backgroundColor: D.bandWr.map(v => v >= 40 ? 'rgba(0,212,170,.7)' : 'rgba(245,166,35,.7)'),
        borderRadius: 4,
      }}]
    }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ display: false }} }},
      scales: {{ y: {{ max: 100, ticks: {{ callback: v => v + '%' }} }} }}
    }}
  }});
}}

// 4. Family performance
if (D.afLabels.length > 0) {{
  new Chart(document.getElementById('familyChart'), {{
    type: 'bar',
    data: {{
      labels: D.afLabels,
      datasets: [
        {{ label: 'Win Rate %', data: D.afWr, backgroundColor: 'rgba(61,155,255,.7)', borderRadius: 4 }},
        {{ label: 'Avg PnL (XRP)', data: D.afAvg, backgroundColor: 'rgba(123,94,167,.7)', borderRadius: 4 }},
      ]
    }},
    options: {{
      responsive: true,
      scales: {{
        y: {{ ticks: {{ callback: v => v.toFixed(1) }} }}
      }}
    }}
  }});
}}

// 5. Exposure doughnut
if (D.expData.some(v => v > 0)) {{
  new Chart(document.getElementById('exposureChart'), {{
    type: 'doughnut',
    data: {{
      labels: D.expLabels,
      datasets: [{{
        data: D.expData,
        backgroundColor: ['#3d9bff','#00d4aa','#f5a623','#ff4d6d','#7b5ea7','#1e2d4a'],
        borderWidth: 1,
        borderColor: '#0d1526',
      }}]
    }},
    options: {{
      responsive: true,
      plugins: {{
        legend: {{ position: 'bottom', labels: {{ boxWidth: 12, padding: 16 }} }}
      }}
    }}
  }});
}}

// CSV export
function exportCSV() {{
  const rows = [['Time','Token','Entry','Exit','Size XRP','PnL XRP','PnL %','Exit Reason','Chart State','Score']];
  D.trades.forEach(t => {{
    const ts = t.exit_time ? new Date(t.exit_time*1000).toISOString() : '';
    rows.push([ts, t.symbol||'', t.entry_price||0, t.exit_price||0,
               t.xrp_spent||0, t.pnl_xrp||0, t.pnl_pct||0,
               t.exit_reason||'', t.chart_state||'', t.score||0]);
  }});
  const csv = rows.map(r => r.join(',')).join('\\n');
  const blob = new Blob([csv], {{type:'text/csv'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'dktrenchbot_trades.csv';
  a.click();
}}
</script>
</body>
</html>"""
    return html

# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print("Generating DKTrenchBot Terminal dashboard...")

    balance      = get_xrpl_balance()
    positions    = get_positions()
    trades       = get_trade_history()
    all_trades   = get_all_trade_history()
    regime       = get_regime()
    weights      = get_learned_weights()
    xrp_price    = get_xrp_price()
    btc_price    = get_btc_price()
    fg           = get_fear_greed()
    axiom        = get_axiom_data()
    bot_status   = get_bot_status()
    activity     = get_activity_feed()
    equity       = build_equity_curve(trades)
    stats        = compute_stats(trades)
    health       = compute_health_score(stats, regime, weights)
    state_bk     = get_state_breakdown(trades)
    band_bk      = get_band_breakdown(trades)
    axiom_fam    = get_axiom_family_stats(axiom["closed"])
    cfg          = get_config_values()

    # Axiom stats
    ac = axiom["closed"]
    aw = [p for p in ac if p.get("result") == "win"]
    axiom_stats = {
        "wr":        round(len(aw)/len(ac)*100, 1) if ac else 0,
        "wins":      len(aw),
        "losses":    len(ac) - len(aw),
        "total":     len(ac),
        "total_pnl": round(sum(p.get("pnl",0) for p in ac), 3),
    }

    data = {
        "balance":        balance,
        "positions":      positions,
        "trades":         trades,
        "stats":          stats,
        "regime":         regime,
        "weights":        weights,
        "xrp_price":      xrp_price,
        "btc_price":      btc_price,
        "fear_greed":     fg,
        "axiom":          axiom,
        "axiom_stats":    axiom_stats,
        "bot_status":     bot_status,
        "activity":       activity,
        "equity":         equity,
        "state_breakdown": state_bk,
        "band_breakdown":  band_bk,
        "axiom_family":   axiom_fam,
        "health":         health,
        "config":         cfg,
    }

    html = render_html(data)
    with open(OUT, "w") as f:
        f.write(html)

    print(f"✅ index.html written ({len(html):,} chars, {OUT.stat().st_size//1024}KB)")
    print(f"   Wallet: {balance[0]} XRP | Positions: {len(positions)} | Trades: {stats['total']} | Health: {health}/100")

if __name__ == "__main__":
    main()
