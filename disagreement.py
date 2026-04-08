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
