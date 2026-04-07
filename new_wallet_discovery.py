"""
new_wallet_discovery.py — Smart Wallet Auto-Discovery (Audit #1)

Goal: Mine our own trade_history from state.json to auto-discover smart wallets
that bought alongside us on winners.

Algorithm:
1. Load state.json trade_history
2. For each trade where we profited (profit_xrp > 0), get entry_time, currency/issuer, entry_price
3. Query ledger txs around entry_time ± 10 min to find OTHER wallets that bought the same token
4. Score those wallets by how well they timed the entry vs ours
5. If they entered before or at the same time as us on a winner → add to candidate_wallets
6. Track candidate_wallet conviction over time: if they keep appearing on winners, promote to TRACKED_WALLET
7. Store discovered wallets in state/discovered_wallets.json
8. At startup, re-check all historical winners to continuously expand the list
9. Log discoveries clearly

Key constraint: XRPL has no "AMM history" — use account_tx on the AMM account address
(pool's account) filtering by currency, or scan ledger for Payment transactions to the
token issuer in that time window.
"""

import json
import os
import time
import logging
import requests
from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict

logger = logging.getLogger("wallet_discovery")

STATE_DIR = os.path.join(os.path.dirname(__file__), "state")
DISCOVERED_FILE = os.path.join(STATE_DIR, "discovered_wallets.json")
CLIO_URL = "https://rpc.xrplclaw.com"

# Minimum XRP profit to consider a trade a "winner" worth mining
MIN_PROFIT_XRP = 1.0

# Time window around our entry to look for co-buyers (seconds)
ENTRY_WINDOW_SEC = 600  # ±10 minutes

# Conviction threshold: wallet must appear on N winning trades to be promoted
CONVICTION_THRESHOLD = 3

# Maximum candidates to track
MAX_CANDIDATES = 100


def _rpc(method: str, params: dict, timeout: int = 15) -> Optional[dict]:
    """Send RPC request to CLIO."""
    try:
        resp = requests.post(CLIO_URL, json={"method": method, "params": [params]}, timeout=timeout)
        result = resp.json().get("result", {})
        return result
    except Exception as e:
        logger.debug(f"RPC error {method}: {e}")
        return None


def _load_state() -> Dict:
    """Load bot state.json."""
    state_file = os.path.join(STATE_DIR, "state.json")
    if os.path.exists(state_file):
        try:
            with open(state_file) as f:
                return json.load(f)
        except Exception:
            pass
    return {"trade_history": [], "positions": {}}


def _load_discovered() -> Dict:
    """Load discovered wallets file."""
    if os.path.exists(DISCOVERED_FILE):
        try:
            with open(DISCOVERED_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "candidates": {},   # wallet -> {appearances, tokens, first_seen, last_seen, conviction_score}
        "tracked": [],      # list of wallet addresses promoted to tracked
        "last_scan_ledger": 0,
    }


def _save_discovered(data: Dict) -> None:
    """Save discovered wallets."""
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = DISCOVERED_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, DISCOVERED_FILE)
    except Exception:
        with open(DISCOVERED_FILE, "w") as f:
            json.dump(data, f, indent=2)


def _get_currency_code(symbol: str) -> str:
    """Convert symbol to XRPL currency code (same logic as config.get_currency)."""
    s = symbol.upper()
    if len(s) <= 3:
        return s.ljust(3)
    if len(s) == 40 and all(c in "0123456789ABCDEF" for c in s):
        return s
    encoded = s.encode("utf-8").hex().upper()
    return encoded.ljust(40, "0")[:40]


def _find_amm_account(currency: str, issuer: str) -> Optional[str]:
    """
    Find the AMM pool account for a currency/issuer pair.
    The AMM account is deterministic but we need to query it.
    We search for accounts holding this token via account_lines on the issuer.
    """
    # Strategy: look for AMM-related accounts by checking who holds large amounts
    # of this token. The AMM pool will be the largest holder besides the issuer.
    result = _rpc("account_lines", {
        "account": issuer,
        "limit": 100,
    })
    if not result or result.get("status") != "success":
        return None

    lines = result.get("lines", [])
    # Sort by balance descending — AMM pool should be near top
    sorted_lines = sorted(lines, key=lambda x: float(x.get("balance", "0")), reverse=True)

    for line in sorted_lines[:5]:
        peer = line.get("account", "")
        # AMM accounts typically have very high balances
        bal = float(line.get("balance", "0"))
        if bal > 1000000:  # Large holder likely AMM
            return peer

    return None


def _scan_transactions_for_buyers(
    issuer: str,
    currency: str,
    entry_time: float,
    our_entry_time: float,
    window_sec: int = ENTRY_WINDOW_SEC,
) -> List[Dict]:
    """
    Scan transactions on the issuer account around entry_time to find buyers.
    Returns list of {wallet, ts, amount_xrp} for wallets that bought the token.
    """
    buyers = []
    cutoff_start = entry_time - window_sec
    cutoff_end = entry_time + window_sec

    # Convert to Ripple epoch for comparison
    ripple_cutoff_start = cutoff_start - 946684800
    ripple_cutoff_end = cutoff_end - 946684800

    result = _rpc("account_tx", {
        "account": issuer,
        "limit": 100,
        "ledger_index_min": -1,
        "ledger_index_max": -1,
    })

    if not result or result.get("status") != "success":
        return buyers

    for tx_wrapper in result.get("transactions", []):
        tx = tx_wrapper.get("tx", {})
        meta = tx_wrapper.get("meta", {})
        tx_type = tx.get("TransactionType", "")
        tx_date = tx.get("date", 0)  # Ripple epoch seconds

        # Convert to Unix epoch
        tx_time_unix = tx_date + 946684800

        # Check time window
        if tx_time_unix < cutoff_start or tx_time_unix > cutoff_end:
            continue

        sender = tx.get("Account", "")
        if not sender:
            continue

        # Skip our own wallet
        from config import BOT_WALLET_ADDRESS
        if sender == BOT_WALLET_ADDRESS:
            continue

        # Detect buys: OfferCreate where TakerPays=token, TakerGets=XRP
        if tx_type == "OfferCreate":
            tp = tx.get("TakerPays", {})
            tg = tx.get("TakerGets", {})

            # Buying token: paying token, getting XRP
            if (isinstance(tp, dict) and
                tp.get("currency") == currency and
                tp.get("issuer") == issuer and
                isinstance(tg, str)):

                try:
                    xrp_amount = int(tg) / 1e6
                    buyers.append({
                        "wallet": sender,
                        "ts": tx_time_unix,
                        "amount_xrp": xrp_amount,
                        "timing_offset": tx_time_unix - our_entry_time,
                    })
                except (ValueError, TypeError):
                    pass

        elif tx_type == "Payment":
            # Direct payment of token
            amt = tx.get("Amount", {})
            if isinstance(amt, dict) and amt.get("currency") == currency and amt.get("issuer") == issuer:
                dest = tx.get("Destination", "")
                if dest:
                    buyers.append({
                        "wallet": dest,
                        "ts": tx_time_unix,
                        "amount_xrp": 0,  # Can't determine XRP value easily
                        "timing_offset": tx_time_unix - our_entry_time,
                    })

    return buyers


def _score_wallet_timing(buyers: List[Dict], our_entry_time: float) -> Dict[str, float]:
    """
    Score wallets by how well they timed their entry relative to ours.
    Earlier entry = higher score. Same time = good. Later = lower.
    Returns {wallet: score} where score is 0-100.
    """
    scores = {}
    for buyer in buyers:
        offset = buyer["timing_offset"]  # negative = before us, positive = after us
        wallet = buyer["wallet"]

        # Scoring: entered before us = 80-100, same time = 70-80, within 5min after = 50-70
        if offset <= 0:
            # Entered before or at same time — best signal
            score = max(70, min(100, 80 + abs(offset) / 60))  # +1 per minute early
        elif offset <= 300:
            # Within 5 min after us — still good, they saw the same signal
            score = max(50, 70 - offset / 15)  # -1 per 15 sec late
        else:
            # More than 5 min late — weaker signal
            score = max(20, 50 - (offset - 300) / 30)

        # Accumulate if wallet appears multiple times
        scores[wallet] = scores.get(wallet, 0) + score

    return scores


def discover_smart_wallets(force_rescan: bool = False) -> Dict:
    """
    Main discovery function. Mines trade_history for winning trades and finds
    co-buying wallets. Returns updated discovered data.
    """
    logger.info("🔍 Starting smart wallet discovery...")

    state = _load_state()
    discovered = _load_discovered()
    trade_history = state.get("trade_history", [])

    # Filter to winning trades only
    winners = [
        t for t in trade_history
        if t.get("pnl_xrp", 0) > MIN_PROFIT_XRP
    ]

    if not winners:
        logger.info("No winning trades found to mine.")
        return discovered

    logger.info(f"Found {len(winners)} winning trades (pnl_xrp > {MIN_PROFIT_XRP})")

    new_candidates = defaultdict(lambda: {
        "appearances": 0,
        "tokens": set(),
        "total_score": 0.0,
        "first_seen": time.time(),
        "last_seen": 0,
        "win_details": [],
    })

    for trade in winners:
        symbol = trade.get("symbol", "")
        issuer = trade.get("issuer", "")
        entry_time = trade.get("entry_time", 0)
        pnl_xrp = trade.get("pnl_xrp", 0)
        exit_reason = trade.get("exit_reason", "")

        if not symbol or not issuer or not entry_time:
            continue

        currency = _get_currency_code(symbol)
        logger.info(f"  Mining winner: {symbol} (pnl={pnl_xrp:+.2f} XRP, reason={exit_reason})")

        # Scan for co-buyers around entry time
        buyers = _scan_transactions_for_buyers(
            issuer=issuer,
            currency=currency,
            entry_time=entry_time,
            our_entry_time=entry_time,
        )

        if not buyers:
            logger.debug(f"    No co-buyers found for {symbol}")
            continue

        # Score timing
        timing_scores = _score_wallet_timing(buyers, entry_time)

        for wallet, score in timing_scores.items():
            # Only consider wallets that entered before or close to our entry
            # (within 5 min after is acceptable — they may have seen the same signal)
            matching_buyers = [b for b in buyers if b["wallet"] == wallet]
            earliest_offset = min(b["timing_offset"] for b in matching_buyers)

            # Key criterion: they entered before or at roughly the same time as us
            if earliest_offset <= 300:  # within 5 min of our entry
                cand = new_candidates[wallet]
                cand["appearances"] += 1
                cand["tokens"].add(symbol)
                cand["total_score"] += score
                cand["last_seen"] = time.time()
                cand["win_details"].append({
                    "symbol": symbol,
                    "pnl_xrp": pnl_xrp,
                    "exit_reason": exit_reason,
                    "our_entry": entry_time,
                    "their_offset": earliest_offset,
                })
                logger.info(f"    🎯 Candidate: {wallet[:8]}... appeared on {symbol} "
                          f"(offset={earliest_offset:+.0f}s, score={score:.0f})")

    # Merge with existing candidates
    for wallet, data in new_candidates.items():
        existing = discovered["candidates"].get(wallet, {})
        existing["appearances"] = existing.get("appearances", 0) + data["appearances"]
        existing_tokens = set(existing.get("tokens", []))
        existing_tokens.update(data["tokens"])
        existing["tokens"] = list(existing_tokens)
        existing["total_score"] = existing.get("total_score", 0) + data["total_score"]
        existing["last_seen"] = max(existing.get("last_seen", 0), data["last_seen"])
        if "first_seen" not in existing:
            existing["first_seen"] = data["first_seen"]
        existing_wins = existing.get("win_details", [])
        existing_wins.extend(data["win_details"])
        # Keep last 20 win details
        existing["win_details"] = existing_wins[-20:]

        # Calculate conviction score: appearances * avg_score / 100
        avg_score = existing["total_score"] / max(existing["appearances"], 1)
        existing["conviction_score"] = round(avg_score * existing["appearances"] / 10, 2)

        discovered["candidates"][wallet] = existing

    # Promote high-conviction candidates to tracked
    newly_tracked = []
    for wallet, data in list(discovered["candidates"].items()):
        if (data["appearances"] >= CONVICTION_THRESHOLD and
            wallet not in discovered["tracked"]):
            discovered["tracked"].append(wallet)
            newly_tracked.append(wallet)
            logger.info(f"  ⭐ PROMOTED to tracked: {wallet} "
                       f"(appearances={data['appearances']}, conviction={data['conviction_score']})")

    # Prune low-quality candidates (keep top MAX_CANDIDATES by conviction)
    if len(discovered["candidates"]) > MAX_CANDIDATES:
        sorted_cands = sorted(
            discovered["candidates"].items(),
            key=lambda x: x[1].get("conviction_score", 0),
            reverse=True,
        )
        keep = dict(sorted_cands[:MAX_CANDIDATES])
        discovered["candidates"] = keep

    discovered["last_scan_ledger"] = int(time.time())
    _save_discovered(discovered)

    logger.info(f"✅ Discovery complete: {len(discovered['candidates'])} candidates, "
               f"{len(discovered['tracked'])} tracked wallets")
    if newly_tracked:
        logger.info(f"  Newly tracked: {len(newly_tracked)} wallets")

    return discovered


def get_discovered_wallets() -> List[str]:
    """Return list of all discovered wallet addresses (candidates + tracked)."""
    discovered = _load_discovered()
    wallets = set(discovered.get("tracked", []))
    wallets.update(discovered.get("candidates", {}).keys())
    return list(wallets)


def get_tracked_wallets() -> List[str]:
    """Return list of promoted tracked wallet addresses."""
    discovered = _load_discovered()
    return discovered.get("tracked", [])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    result = discover_smart_wallets(force_rescan=True)
    print(json.dumps({
        "candidates": len(result["candidates"]),
        "tracked": len(result["tracked"]),
        "tracked_addresses": result["tracked"][:10],
    }, indent=2))
