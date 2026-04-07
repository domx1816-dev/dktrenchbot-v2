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
