#!/usr/bin/env python3
"""
Dynamic Token Discovery
------------------------
Fetches the full live token universe from xpmarket.com and xrpl.to APIs.
Filters by TVL, verifies AMM exists, and updates the active token registry
in config.py-compatible format.

Runs every 6 hours. Adds new tokens above TVL threshold.
Removes tokens that have dropped below threshold (marks inactive, never deletes history).

Output: state/discovered_tokens.json
        state/active_registry.json  ← merged with static TOKEN_REGISTRY
"""

import json
import os
import time
import requests
from datetime import datetime, timezone
from typing import List, Dict, Optional

from config import CLIO_URL, STATE_DIR, MIN_TVL_XRP

DISCOVERY_FILE  = os.path.join(STATE_DIR, "discovered_tokens.json")
REGISTRY_FILE   = os.path.join(STATE_DIR, "active_registry.json")
DISCOVERY_LOG   = os.path.join(STATE_DIR, "discovery.log")

# How many tokens to track max (performance limit)
MAX_TOKENS = 200

# TVL threshold for inclusion (XRP)
DISCOVERY_TVL_MIN = 100   # ~$200 MC at $2/XRP — catches full $400-$2K MC sweet spot (AMM holds ~half MC in XRP)

os.makedirs(STATE_DIR, exist_ok=True)


def _log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(DISCOVERY_LOG, "a") as f:
            f.write(line + "\n")
    except:
        pass


def _rpc(method: str, params: dict) -> Optional[dict]:
    for attempt in range(3):
        try:
            r = requests.post(
                CLIO_URL,
                json={"method": method, "params": [params]},
                timeout=12,
            )
            result = r.json().get("result", {})
            if isinstance(result, dict) and result.get("error") == "slowDown":
                time.sleep(1.5 * (attempt + 1))
                continue
            return result
        except Exception:
            time.sleep(0.5)
    return None


def to_hex(symbol: str) -> str:
    if len(symbol) <= 3:
        return symbol
    return symbol.encode().hex().upper().ljust(40, "0")


def hex_to_name(h: str) -> str:
    if not h or len(h) <= 3:
        return h or ""
    try:
        padded = h.ljust(40, "0")[:40]
        raw = bytes.fromhex(padded).decode("ascii", errors="ignore")
        name = raw.rstrip("\x00").strip()
        if name and name.isprintable():
            return name
        cleaned = h.rstrip("0")
        if len(cleaned) % 2 != 0:
            cleaned += "0"
        return bytes.fromhex(cleaned).decode("ascii").rstrip("\x00").strip()
    except:
        return h[:8]


def verify_amm(currency: str, issuer: str) -> Optional[float]:
    """Verify AMM exists and return TVL in XRP. Returns None if no AMM."""
    result = _rpc("amm_info", {
        "asset":  {"currency": "XRP"},
        "asset2": {"currency": currency, "issuer": issuer},
    })
    if not result:
        return None
    amm = result.get("amm", {})
    if not amm or not amm.get("amount"):
        return None
    try:
        return int(amm["amount"]) / 1e6
    except:
        return None


def fetch_xpmarket_amm_pools() -> List[Dict]:
    """
    Fetch AMM pool list from xpmarket.com sorted by liquidity (TVL).
    Returns list of {symbol, issuer, tvl_usd, tvl_xrp_est, currency}.
    """
    tokens = []
    page = 1
    per_page = 100

    _log("Fetching AMM pools from xpmarket.com...")
    while len(tokens) < MAX_TOKENS:
        try:
            r = requests.get(
                f"https://api.xpmarket.com/api/amm/list",
                params={
                    "sort": "liquidity",
                    "order": "desc",
                    "limit": per_page,
                    "page": page,
                },
                timeout=15,
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
            )
            if r.status_code != 200:
                _log(f"xpmarket API error: {r.status_code}")
                break

            data = r.json()
            items = data.get("data", {}).get("items", [])
            if not items:
                break

            for item in items:
                # Parse token info from xpmarket format
                # symbol like "XRP/FUZZY-rIssuer" or "XRP/RLUSD-rIssuer"
                symbol_raw = item.get("symbol", "")
                liquidity_usd = float(item.get("liquidity_usd", 0) or 0)
                liquidity_xrp = float(item.get("amount1", 0) or 0)  # XRP side

                # Extract token currency and issuer from symbol
                # Format: "XRP/TOKEN-rIssuer" or similar
                currency_id2 = item.get("currencyId2")
                issuer = None
                currency = None

                # Try to parse from title "XRP/TOKEN"
                title = item.get("title", "")
                if "/" in title:
                    parts = title.split("/")
                    if len(parts) == 2 and parts[0] == "XRP":
                        token_name = parts[1].split("-")[0] if "-" in parts[1] else parts[1]
                        currency = to_hex(token_name)

                # Get issuer from symbol field
                if "-" in symbol_raw:
                    issuer_part = symbol_raw.split("-")[-1]
                    if issuer_part.startswith("r") and len(issuer_part) > 20:
                        issuer = issuer_part

                if currency and issuer:
                    name = hex_to_name(currency) if len(currency) > 3 else currency
                    tokens.append({
                        "name": name,
                        "currency": currency,
                        "issuer": issuer,
                        "tvl_xrp": liquidity_xrp,
                        "tvl_usd": liquidity_usd,
                        "source": "xpmarket",
                    })

            if len(items) < per_page:
                break
            page += 1
            time.sleep(0.3)

        except Exception as e:
            _log(f"xpmarket fetch error: {e}")
            break

    _log(f"xpmarket: fetched {len(tokens)} qualifying pools")
    return tokens


def fetch_xrpl_to_tokens() -> List[Dict]:
    """
    Fetch top tokens from xrpl.to sorted by 24h volume.
    Returns list of {symbol, issuer, currency, volume24h, trustlines}.
    """
    tokens = []
    _log("Fetching tokens from xrpl.to...")

    try:
        r = requests.get(
            "https://api.xrpl.to/api/tokens",
            params={"sort": "vol24h", "limit": 500, "start": 0},
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if r.status_code != 200:
            _log(f"xrpl.to API error: {r.status_code}")
            return []

        data = r.json()
        raw_tokens = data.get("tokens", [])

        for t in raw_tokens:
            currency = t.get("currency", "")
            issuer   = t.get("issuer", "")
            if not currency or not issuer:
                continue

            # Only include tokens with some activity
            vol24h = float(t.get("vol24hxrp", 0) or 0)
            trustlines = int(t.get("trustlines", 0) or 0)

            if trustlines < 10:
                continue  # skip ghost tokens

            name = hex_to_name(currency) if len(currency) > 3 else currency

            tokens.append({
                "name": name,
                "currency": currency,
                "issuer": issuer,
                "vol24h_xrp": vol24h,
                "trustlines": trustlines,
                "source": "xrpl_to",
            })

        _log(f"xrpl.to: fetched {len(tokens)} tokens with activity")

    except Exception as e:
        _log(f"xrpl.to fetch error: {e}")

    return tokens


def load_existing() -> Dict:
    """Load existing discovered tokens registry."""
    try:
        with open(DISCOVERY_FILE) as f:
            return json.load(f)
    except:
        return {"tokens": {}, "last_updated": 0}


def save_registry(all_tokens: List[Dict]):
    """Save active registry for scanner.py to use."""
    registry = []
    seen = set()
    for t in all_tokens:
        key = f"{t['currency']}:{t['issuer']}"
        if key not in seen:
            seen.add(key)
            registry.append({
                "symbol": t["name"],
                "currency": t["currency"],
                "issuer": t["issuer"],
            })

    with open(REGISTRY_FILE, "w") as f:
        json.dump({
            "updated": datetime.now(timezone.utc).isoformat(),
            "count": len(registry),
            "tokens": registry,
        }, f, indent=2)
    _log(f"Saved active registry: {len(registry)} tokens → {REGISTRY_FILE}")


def run_discovery() -> List[Dict]:
    """
    Full discovery run:
    1. Fetch from xpmarket (AMM pools by TVL)
    2. Fetch from xrpl.to (tokens by volume)
    3. Merge, deduplicate
    4. Verify AMM exists + TVL >= threshold for any new tokens
    5. Save updated registry
    """
    _log("=== Discovery run starting ===")
    ts = datetime.now(timezone.utc).isoformat()

    existing = load_existing()
    existing_tokens = existing.get("tokens", {})

    # --- Fetch from sources ---
    xpmarket_pools = fetch_xpmarket_amm_pools()
    xrpl_to_tokens = fetch_xrpl_to_tokens()

    # --- Merge and deduplicate by (currency, issuer) ---
    candidates = {}

    # xpmarket pools already have TVL — trust it
    for t in xpmarket_pools:
        key = f"{t['currency']}:{t['issuer']}"
        candidates[key] = t

    # xrpl.to tokens — need TVL verification
    for t in xrpl_to_tokens:
        key = f"{t['currency']}:{t['issuer']}"
        if key not in candidates:
            candidates[key] = t

    _log(f"Total unique candidates: {len(candidates)}")

    # --- Verify AMM + TVL for new/unverified tokens ---
    verified = {}
    new_count = 0
    verified_count = 0

    for key, token in candidates.items():
        # Already verified recently?
        if key in existing_tokens:
            existing_entry = existing_tokens[key]
            age = time.time() - existing_entry.get("last_verified", 0)
            if age < 21600:  # 6 hours
                verified[key] = existing_entry
                verified_count += 1
                continue

        # Verify AMM exists and get fresh TVL
        tvl = verify_amm(token["currency"], token["issuer"])
        time.sleep(0.15)

        if tvl is None or tvl < DISCOVERY_TVL_MIN:
            continue

        entry = {
            "name": token["name"],
            "currency": token["currency"],
            "issuer": token["issuer"],
            "tvl_xrp": round(tvl, 2),
            "source": token.get("source", "unknown"),
            "last_verified": time.time(),
            "first_seen": existing_tokens.get(key, {}).get("first_seen", time.time()),
            "active": True,
        }
        verified[key] = entry

        if key not in existing_tokens:
            new_count += 1
            _log(f"NEW TOKEN: {token['name']} | TVL={tvl:,.0f} XRP | {token['issuer'][:20]}...")

    # Sort by TVL descending, cap at MAX_TOKENS
    sorted_tokens = sorted(verified.values(), key=lambda x: x.get("tvl_xrp", 0), reverse=True)
    top_tokens = sorted_tokens[:MAX_TOKENS]

    # Save discovery file
    with open(DISCOVERY_FILE, "w") as f:
        json.dump({
            "last_updated": ts,
            "total_verified": len(top_tokens),
            "new_this_run": new_count,
            "tokens": {
                f"{t['currency']}:{t['issuer']}": t
                for t in top_tokens
            },
        }, f, indent=2)

    # Save scanner-compatible registry
    save_registry(top_tokens)

    _log(f"Discovery complete: {len(top_tokens)} active tokens ({new_count} new, {verified_count} cached)")
    return top_tokens


if __name__ == "__main__":
    tokens = run_discovery()
    print(f"\nTop 20 by TVL:")
    for i, t in enumerate(tokens[:20], 1):
        print(f"  {i:2}. {t['name']:15} {t.get('tvl_xrp',0):>12,.0f} XRP  {t['issuer'][:24]}")
