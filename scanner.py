"""
scanner.py — Token discovery, AMM data collection, and momentum bucketing.
Fetches AMM pool data for all registry tokens and ranks by momentum.
Writes: state/scan_results.json
"""

import json
import logging
import os
import time

logger = logging.getLogger("scanner")
import requests
from typing import Dict, List, Optional, Tuple
from config import CLIO_URL, STATE_DIR, TOKEN_REGISTRY, MIN_TVL_XRP, get_currency

os.makedirs(STATE_DIR, exist_ok=True)

SCAN_HISTORY_FILE  = os.path.join(STATE_DIR, "scan_history.json")
SCAN_RESULTS_FILE  = os.path.join(STATE_DIR, "scan_results.json")
ACTIVE_REGISTRY_FILE = os.path.join(STATE_DIR, "active_registry.json")


def hex_to_name(h: str) -> str:
    """Convert XRPL hex currency code to readable name."""
    if not h or len(h) <= 3:
        return h or ""
    try:
        decoded = bytes.fromhex(h).decode('ascii', errors='replace')
        # Strip null bytes and trailing whitespace
        return decoded.rstrip('\x00').strip()
    except Exception:
        return h


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
    Pass currency directly if known (avoids get_currency() recomputation errors).
    
    Falls back to direct AMM account query if amm_info RPC fails (CLIO bug).
    """
    if not currency:
        currency = get_currency(symbol)
    
    # Try amm_info RPC first
    result = _rpc("amm_info", {
        "asset":  {"currency": "XRP"},
        "asset2": {"currency": currency, "issuer": issuer},
    })
    if result and result.get("status") == "success":
        return result.get("amm")
    
    # Fallback: try reverse asset order (token/XRP instead of XRP/token)
    result2 = _rpc("amm_info", {
        "asset":  {"currency": currency, "issuer": issuer},
        "asset2": {"currency": "XRP"},
    })
    if result2 and result2.get("status") == "success":
        return result2.get("amm")
    
    # Final fallback: find AMM by checking issuer's account_info for AMMID
    # Some AMMs have the issuer account itself as the AMM account
    try:
        info_resp = _rpc("account_info", {"account": issuer})
        if info_resp and isinstance(info_resp, dict):
            # _rpc returns data["result"] directly, so account_data is at top level
            account_data = info_resp.get("account_data", {})
            amm_id = account_data.get("AMMID")
            if amm_id:
                # Issuer IS the AMM! Query its balances directly
                xrp_drops = int(account_data.get("Balance", 0))
                
                # Get token balance from issuer's trustlines
                lines_resp = _rpc("account_lines", {"account": issuer})
                token_bal = 0
                if lines_resp and isinstance(lines_resp, dict):
                    for line in lines_resp.get("lines", []):
                        line_currency = line.get("currency", "")
                        # Match either exact currency or decoded name
                        if line_currency == currency or line_currency == hex_to_name(currency):
                            # For AMM-as-issuer, the token balance is what the AMM holds
                            token_bal = abs(float(line.get("balance", 0)))
                            break
                
                if token_bal > 0 and xrp_drops > 0:
                    logger.debug(f"AMM fallback found for {symbol}: XRP={xrp_drops/1e6:.2f}, Tokens={token_bal:.2f}")
                    # Return synthetic AMM dict matching amm_info format
                    return {
                        "amount": str(xrp_drops),
                        "amount2": {
                            "currency": currency,
                            "issuer": issuer,
                            "value": str(token_bal)
                        },
                        "lp_token": {"value": "0"},
                    }
    except Exception as e:
        logger.debug(f"AMM fallback query failed for {symbol}: {e}")
        pass
    
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
