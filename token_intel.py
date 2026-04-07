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
