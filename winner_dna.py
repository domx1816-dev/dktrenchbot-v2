"""
winner_dna.py — Pattern matching for PHX/ROOSEVELT/SPY-style 5x moves.

What we learned from studying these tokens on-chain:

PHX ($PHOENIX):
- 104 holders, top wallet holds 20.9% (2500 XRP conviction buy)
- Low supply: ~562K tokens — easy to move the price
- Political/meme theme with narrative backing
- Thin pool at launch (<5K XRP TVL) — small buys = big price impact
- Whale with 2500 XRP = HIGH conviction. Not a flipper.

ROOSEVELT:
- 115 holders, distributed (top = 12%) — healthier concentration
- Multiple 100-682 XRP wallets buying = INSTITUTIONAL-style accumulation
- Political meme with strong narrative (Trump-era)
- Multiple smart wallets from DONNIE/PHX ecosystem also buying

SPY:
- 197 holders but WARNING: 64% in 1 wallet (13 XRP) = rug risk
- However: concentrated supply + thin pool = easy 5x on small volume
- JEET holders present (known in our loser database)
- Pattern: works until the 64% holder dumps

COMMON DNA of 5x WINNERS:
1. Thin pool at entry (1K-15K XRP TVL) — NOT 20K-100K as we had
2. Strong narrative (political, cultural moment, recognizable name)
3. Smart wallet accumulation BEFORE the move (tracked wallets)
4. Holder count 50-200 (early enough, not yet pumped)
5. Low supply / fixed supply tokens move faster
6. No signs of immediate dump (LP not burned = risk)

WHAT OUR BOT WAS MISSING:
- Entry was too late (tokens already extended by the time we bought)
- TVL sweet spot was WRONG — we were favoring 20K+ pools that are slow
- We were NOT scoring for narrative/theme momentum
- Smart wallet buys weren't boosting score enough
"""

import json, os, time, requests
from pathlib import Path
from typing import Dict, Optional

CLIO      = "https://rpc.xrplclaw.com"
STATE_DIR = Path(__file__).parent / "state"

# ── Narrative keywords that indicate meme potential ────────────────────────
POLITICAL_KEYWORDS = [
    "trump", "biden", "maga", "america", "president", "congress", "senate",
    "republican", "democrat", "election", "vote", "eagle", "flag",
    "roosevelt", "lincoln", "washington", "reagan", "kennedy", "harris",
    "spy", "cia", "fbi", "nsa", "agent", "patriot", "freedom", "liberty",
    "militia", "revolution", "constitution", "founding", "republic",
]

VIRAL_KEYWORDS = [
    # AI / tech memes
    "ai", "gpt", "llm", "robot", "bot", "neural", "matrix",
    # Pop culture
    "pepe", "wojak", "chad", "based", "degen", "ape", "moon", "wagmi",
    "gm", "ngmi", "hodl", "diamond", "hands", "yolo", "fomo",
    # Anime / gaming
    "anime", "naruto", "goku", "pikachu", "zelda", "mario",
    # Food memes
    "pizza", "burger", "taco", "sushi", "donut",
    # Misc viral
    "rick", "morty", "simpsons", "sponge", "bob", "homer",
    "elon", "musk", "spacex", "tesla", "twitter", "x",
]

CULTURAL_KEYWORDS = [
    "phoenix", "phx", "fire", "risen", "dragon", "samurai", "ninja",
    "king", "queen", "god", "legend", "hero", "warrior", "titan",
    "pump", "degen", "rich", "million", "billion", "lambo", "yacht",
    "gold", "silver", "diamond", "crystal", "gem",
]

ANIMAL_KEYWORDS = [
    "cat", "dog", "frog", "doge", "shib", "bear", "bull",
    "whale", "shark", "lion", "tiger", "wolf", "fox", "rabbit", "bunny",
    "duck", "penguin", "panda", "monkey", "ape", "gorilla", "chimp",
    "horse", "donkey", "elephant", "snake", "turtle", "parrot",
    "hamster", "rat", "mouse", "bat", "owl", "eagle", "hawk",
    "fish", "crab", "lobster", "shrimp", "seal", "walrus", "bear",
]


def score_narrative(symbol: str, title: str = "") -> int:
    """
    Score token based on meme/narrative potential.
    Returns 0-20 pts.
    PHX/ROOS/SPY all had strong single-word narratives.
    """
    s = (symbol + " " + title).lower()
    pts = 0

    # Any strong meme narrative scores high — not just political
    if any(k in s for k in POLITICAL_KEYWORDS):
        pts += 20    # political = highest conviction right now
    elif any(k in s for k in VIRAL_KEYWORDS):
        pts += 18    # viral/AI/pop culture = near-equal potential
    elif any(k in s for k in ANIMAL_KEYWORDS):
        pts += 15    # animal coins = proven demand, always buyers
    elif any(k in s for k in CULTURAL_KEYWORDS):
        pts += 12    # general meme/cultural

    # Short symbol = catchier, more shareable = more retail FOMO
    sym_clean = symbol.strip().replace(" ","")
    if 1 <= len(sym_clean) <= 3:
        pts += 5    # XRP, BTC, ETH style — instantly recognizable
    elif len(sym_clean) <= 5:
        pts += 3
    elif len(sym_clean) <= 8:
        pts += 1

    # All-caps symbol = more professional looking = more trust
    if sym_clean == sym_clean.upper() and len(sym_clean) >= 2:
        pts += 2

    return min(pts, 20)


def score_holder_structure(issuer: str, currency: str) -> Dict:
    """
    Analyze holder distribution for winner DNA.
    PHX: 104 holders, 20.9% top. ROOS: 115 holders, 12% top.
    Sweet spot: 50-300 holders, top holder <25%, NO single wallet >60%.

    Returns: {"pts": int, "flags": list, "holder_count": int, "top_pct": float}
    """
    try:
        r = requests.post(CLIO, json={"method": "account_lines", "params": [{
            "account": issuer, "limit": 400
        }]}, timeout=8)
        lines = r.json().get("result", {}).get("lines", [])
        time.sleep(0.15)
    except:
        return {"pts": 0, "flags": ["fetch_error"], "holder_count": 0, "top_pct": 0}

    holders = [(l["account"], abs(float(l.get("balance", 0)))) for l in lines
               if abs(float(l.get("balance", 0))) > 0]
    if not holders:
        return {"pts": 0, "flags": ["no_holders"], "holder_count": 0, "top_pct": 0}

    holders.sort(key=lambda x: -x[1])
    total_supply = sum(b for _, b in holders)
    top_pct = holders[0][1] / total_supply * 100 if total_supply > 0 else 0
    count = len(holders)

    pts = 0
    flags = []

    # Holder count scoring (PHX=104, ROOS=115, SPY=197 at peak)
    if 50 <= count <= 150:
        pts += 15   # sweet spot — early enough
    elif 150 < count <= 300:
        pts += 10   # still early
    elif count < 50:
        pts += 5    # very early — higher risk
    elif count > 500:
        pts -= 5    # too mature, likely already pumped
        flags.append(f"mature_{count}_holders")

    # Top holder concentration (ROOS=12% = healthy, PHX=20.9% = ok, SPY=64% = danger)
    if top_pct > 60:
        pts -= 15
        flags.append(f"rug_risk_top_{top_pct:.0f}pct")
    elif top_pct > 35:
        pts -= 8
        flags.append(f"concentrated_{top_pct:.0f}pct")
    elif top_pct <= 20:
        pts += 10   # well distributed = ROOS-style health
        flags.append("distributed")
    elif top_pct <= 30:
        pts += 5

    # Check for known smart wallet accumulation (big positive signal)
    smart_wallets = _load_smart_wallet_addresses()
    sw_holders = [addr for addr, _ in holders[:20] if addr in smart_wallets]
    if sw_holders:
        pts += 15
        flags.append(f"smart_wallet_holding_{len(sw_holders)}")

    # High-XRP wallet buying = conviction (PHX whale had 2500 XRP)
    # Parallelized — was 500ms serial, now ~100ms concurrent
    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed as _asc
        def _fetch_xrp_bal(addr):
            try:
                r2 = requests.post(CLIO, json={"method": "account_info", "params": [{
                    "account": addr, "ledger_index": "validated"
                }]}, timeout=5)
                return int(r2.json().get("result", {}).get("account_data", {}).get("Balance", 0)) / 1e6
            except Exception:
                return 0.0
        conviction_buyers = 0
        with ThreadPoolExecutor(max_workers=5) as _ex:
            _futs = {_ex.submit(_fetch_xrp_bal, addr): addr for addr, _ in holders[:5]}
            for _f in _asc(_futs):
                if _f.result() > 200:
                    conviction_buyers += 1
        if conviction_buyers >= 2:
            pts += 10
            flags.append(f"whale_conviction_{conviction_buyers}")
        elif conviction_buyers == 1:
            pts += 5
            flags.append("whale_conviction_1")
    except:
        pass

    return {
        "pts":          max(0, min(pts, 30)),
        "flags":        flags,
        "holder_count": count,
        "top_pct":      round(top_pct, 1),
    }


def score_launch_freshness(issuer: str) -> Dict:
    """
    Fresh launches move fastest. PHX/ROOS/SPY were all <48h old at peak move.
    Use issuer account sequence as freshness proxy.
    Lower recent sequences = newer account.
    Returns: {"pts": int, "fresh": bool}
    """
    try:
        r = requests.post(CLIO, json={"method": "account_tx", "params": [{
            "account": issuer, "limit": 5, "forward": True
        }]}, timeout=8)
        txs = r.json().get("result", {}).get("transactions", [])
        time.sleep(0.15)
        if txs:
            first_tx = txs[0].get("tx", {})
            date = first_tx.get("date", 0)
            # XRPL epoch: add 946684800 to get Unix
            unix_ts = date + 946684800
            age_hours = (time.time() - unix_ts) / 3600
            if age_hours < 6:
                return {"pts": 20, "fresh": True, "age_hours": age_hours}
            elif age_hours < 24:
                return {"pts": 12, "fresh": True, "age_hours": age_hours}
            elif age_hours < 72:
                return {"pts": 6, "fresh": False, "age_hours": age_hours}
            else:
                return {"pts": 0, "fresh": False, "age_hours": age_hours}
    except:
        pass
    return {"pts": 0, "fresh": False, "age_hours": 999}


def _load_smart_wallet_addresses():
    """Load the set of known smart wallet addresses."""
    try:
        p = STATE_DIR / "smart_wallet_state.json"
        if p.exists():
            s = json.loads(p.read_text())
            return set(s.get("wallet_trustlines", {}).keys())
    except:
        pass
    # Hardcoded fallback — known winners from PHX/ROOS/DONNIE study
    return {
        "rGeaXk8Hgh9qA3aQYj9MACMwqzUdB38DH6",  # ROOS first mover
        "rfgSotfAUmCueXUiBAg4nhBAgcHmKgBZ54",  # ROOS top holder
        "rHoLiJz8tkvzFUz3HyE5AJGvi5vGTTHF3w",  # DONNIE top holder
        "r3FfFoFF6NLDf96KtrezZHpWP7RvDNnKEC",  # PHX whale (2500 XRP)
        "r9PnQbMnno1knm4WT1paLqtGRQiN2ztUzt",  # PHX top holder
        "rNZLDrnqtoiXiqEN971txs8ptTvnJ7JnVj",  # PHX dev
        "rXSYHuUUrFsk8CABEf6PtrYwFWoAfUMrK",   # ROOS #2 (104 XRP, 200 tokens)
    }


def get_winner_dna_score(symbol: str, issuer: str, currency: str,
                          tvl_xrp: float = 0) -> Dict:
    """
    Full winner DNA analysis. Returns total bonus pts + flags.
    Called from scanner for promising tokens.
    Max bonus: ~70 pts (narrative 20 + holders 30 + freshness 20)
    Applied as score_bonus on top of momentum score.
    Only run for tokens with TVL < 20K (thin pools = early stage).
    """
    if tvl_xrp > 20_000:
        return {"bonus": 0, "flags": ["too_mature"], "details": {}}

    narrative_pts = score_narrative(symbol)
    freshness     = score_launch_freshness(issuer)
    holders       = score_holder_structure(issuer, currency)

    # Thin pool bonus — PHX/ROOS/SPY all launched thin
    # Thin pool = price sensitive = small buys = big moves
    if tvl_xrp < 3_000:
        thin_pts = 15   # ultra thin = maximum volatility
    elif tvl_xrp < 8_000:
        thin_pts = 10
    elif tvl_xrp < 15_000:
        thin_pts = 5
    else:
        thin_pts = 0

    total_bonus = narrative_pts + freshness["pts"] + holders["pts"] + thin_pts
    total_bonus = min(total_bonus, 60)  # cap contribution

    all_flags = holders["flags"] + (["fresh"] if freshness.get("fresh") else [])
    if narrative_pts >= 15:
        all_flags.append("political_narrative")
    elif narrative_pts >= 8:
        all_flags.append("meme_narrative")

    return {
        "bonus":   total_bonus,
        "flags":   all_flags,
        "details": {
            "narrative_pts":  narrative_pts,
            "freshness_pts":  freshness["pts"],
            "age_hours":      freshness.get("age_hours", 999),
            "holder_pts":     holders["pts"],
            "holder_count":   holders["holder_count"],
            "top_holder_pct": holders["top_pct"],
            "thin_pool_pts":  thin_pts,
            "tvl_xrp":        tvl_xrp,
        }
    }


if __name__ == "__main__":
    # Test against our known winners
    tests = [
        ("PHX",       "rskkPc3Eea3phZmzYqdoRFXeHg1GF7oVzG", "5048580000000000000000000000000000000000", 4000),
        ("ROOSEVELT", "rUaSSCMTdM4eFEqD4VfAE5CC3Vkz3nVGMA", "524F4F5345564554000000000000000000000000", 8000),
        ("SPY",       "rnmJEi7hzEL34R7x48e732qvSnmF5wsLtQ",  "5350590000000000000000000000000000000000", 5000),
    ]
    for sym, issuer, cur, tvl in tests:
        print(f"\n--- {sym} ---")
        result = get_winner_dna_score(sym, issuer, cur, tvl)
        print(f"Bonus: +{result['bonus']} pts")
        print(f"Flags: {result['flags']}")
        print(f"Details: {result['details']}")
        time.sleep(1)
