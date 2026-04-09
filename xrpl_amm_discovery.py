#!/usr/bin/env python3
"""
XRPL-Native AMM Discovery
--------------------------
Replaces the xpmarket API dependency with direct XRPL chain queries.
Fetches the full AMM pool universe from the XRPL ledger itself.
Runs on demand and on a 15-minute refresh cycle.

Strategy:
1. Pull top tokens from xrpl.to (volume-ranked)
2. For each, verify AMM exists via amm_info RPC
3. Get live TVL from the AMM object
4. Merge with existing registry, add new tokens, prune dead ones
"""

import json
import os
import time
import requests
from datetime import datetime, timezone
from typing import List, Dict, Optional

STATE_DIR = os.path.join(os.path.dirname(__file__), "state")
REGISTRY_FILE   = os.path.join(STATE_DIR, "active_registry.json")
DISCOVERY_FILE  = os.path.join(STATE_DIR, "discovered_tokens.json")
DISCOVERY_LOG   = os.path.join(STATE_DIR, "discovery.log")

# Direct XRPL RPC — no rate limits
CLIO_URL = "https://rpc.xrplclaw.com"

# Discovery settings
TARGET_TOKENS     = 350   # target pool size
MIN_TVL_XRP       = 100   # ~$200 MC at $2/XRP — catches full $400-$2K MC sweet spot
STALE_REMOVE_HRS  = 48    # remove tokens with no AMM after 48h

# Stablecoin/fiat issuers and symbols to exclude
SKIP_SYMBOLS = {
    "RLUSD","USDC","USDT","EUROP","AUDD","BITSTAMP-USD","BITSTAMP-BTC",
    "USD","EUR","GBP","AUD","BTC","ETH","XLM","LTC","BCH","SOLO",
}
# Known large-cap stablecoin issuers
SKIP_ISSUERS = {
    "rMxCKbEDwqr76QuheSUMdEGf4B9xJ8m5De",  # RLUSD
}

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


def hex_to_name(h: str) -> str:
    if not h or len(h) <= 3:
        return h or ""
    try:
        # XRPL pads currency codes to 40 hex chars with trailing zeros
        # Must decode the full 40 chars, strip null bytes AFTER decoding
        padded = h.ljust(40, "0")[:40]
        raw = bytes.fromhex(padded).decode("ascii", errors="ignore")
        name = raw.rstrip("\x00").strip()
        if name and name.isprintable():
            return name
        # Fallback: strip trailing zero pairs then decode
        cleaned = h.rstrip("0")
        if len(cleaned) % 2 != 0:
            cleaned += "0"
        return bytes.fromhex(cleaned).decode("ascii").rstrip("\x00").strip()
    except:
        return h[:8]


def to_hex(symbol: str) -> str:
    if len(symbol) <= 3:
        return symbol
    return symbol.encode().hex().upper().ljust(40, "0")


def get_amm_tvl(currency: str, issuer: str) -> Optional[float]:
    """
    Check AMM exists and return XRP-side TVL. None = no AMM.
    
    Fallback chain for CLIO amm_info bugs:
    1. Try amm_info RPC (XRP/token direction)
    2. Try amm_info RPC (token/XRP direction)
    3. Check if issuer account has AMMID field
    4. Scan trustline holders for accounts with AMMID holding this token
    """
    # Method 1: amm_info RPC (XRP/token)
    result = _rpc("amm_info", {
        "asset":  {"currency": "XRP"},
        "asset2": {"currency": currency, "issuer": issuer},
    })
    if result and result.get("status") == "success":
        amm = result.get("amm", {})
        if amm and amm.get("amount"):
            try:
                return int(amm["amount"]) / 1e6
            except:
                pass
    
    # Method 2: amm_info RPC (token/XRP reverse)
    result2 = _rpc("amm_info", {
        "asset":  {"currency": currency, "issuer": issuer},
        "asset2": {"currency": "XRP"},
    })
    if result2 and result2.get("status") == "success":
        amm = result2.get("amm", {})
        if amm and amm.get("amount"):
            try:
                return int(amm["amount"]) / 1e6
            except:
                pass
    
    # Method 3: Check if issuer itself is the AMM (has AMMID)
    try:
        info_resp = _rpc("account_info", {"account": issuer})
        if info_resp and isinstance(info_resp, dict):
            account_data = info_resp.get("account_data", {})
            amm_id = account_data.get("AMMID")
            if amm_id:
                # Issuer IS the AMM — get balances directly
                xrp_drops = int(account_data.get("Balance", 0))
                # Get token balance from issuer's trustlines
                lines_resp = _rpc("account_lines", {"account": issuer})
                if lines_resp and isinstance(lines_resp, dict):
                    for line in lines_resp.get("lines", []):
                        if line.get("currency") == currency:
                            token_bal = abs(float(line.get("balance", 0)))
                            if token_bal > 0 and xrp_drops > 0:
                                return xrp_drops / 1e6
    except Exception:
        pass
    
    # Method 4: Scan trustline holders for AMM accounts
    # This catches cases where the AMM is a separate account (like XYZ)
    # Note: currency might be hex-encoded OR plain 3-char — try both
    try:
        lines_resp = _rpc("account_lines", {"account": issuer, "limit": 200})
        if lines_resp and isinstance(lines_resp, dict):
            for line in lines_resp.get("lines", []):
                holder = line.get("account", "")
                bal = float(line.get("balance", 0))
                line_currency = line.get("currency", "")
                # Match either exact currency or hex-encoded version
                if holder and abs(bal) > 0 and (line_currency == currency or line_currency == hex_to_name(currency)):
                    # Check if this holder is an AMM
                    holder_info = _rpc("account_info", {"account": holder})
                    if holder_info and isinstance(holder_info, dict):
                        holder_data = holder_info.get("account_data", {})
                        if holder_data.get("AMMID"):
                            # Found the AMM account! Get its XRP balance
                            xrp_drops = int(holder_data.get("Balance", 0))
                            if xrp_drops > 0:
                                return xrp_drops / 1e6
    except Exception:
        pass
    
    return None


def fetch_xrpl_to_tokens(limit: int = 500) -> List[Dict]:
    """Fetch tokens sorted by 24h volume from xrpl.to — paginated"""
    all_tokens = []
    batch_size = 100
    try:
        for start in range(0, limit, batch_size):
            r = requests.get(
                "https://api.xrpl.to/api/tokens",
                params={"sort": "vol24h", "limit": batch_size, "start": start},
                timeout=15,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if r.status_code != 200:
                _log(f"xrpl.to error at start={start}: {r.status_code}")
                break
            data = r.json()
            raw = data.get("tokens", [])
            if not raw:
                break
            for t in raw:
                currency  = t.get("currency", "")
                issuer    = t.get("issuer", "")
                if not currency or not issuer:
                    continue
                name = hex_to_name(currency) if len(currency) > 3 else currency
                if name.upper() in SKIP_SYMBOLS:
                    continue
                if issuer in SKIP_ISSUERS:
                    continue
                if int(t.get("trustlines", 0) or 0) < 5:
                    continue
                all_tokens.append({
                    "name": name,
                    "currency": currency,
                    "issuer": issuer,
                    "vol24h_xrp": float(t.get("vol24hxrp", 0) or 0),
                    "trustlines": int(t.get("trustlines", 0) or 0),
                    "source": "xrpl_to",
                })
            time.sleep(0.3)
        _log(f"xrpl.to: {len(all_tokens)} candidate tokens fetched")
    except Exception as e:
        _log(f"xrpl.to fetch error: {e}")
    return all_tokens


def fetch_firstledger_tokens() -> List[Dict]:
    """Fetch newly launched tokens from firstledger.net"""
    tokens = []
    try:
        r = requests.get(
            "https://api.firstledger.net/api/v1/tokens?sort=created&limit=100",
            timeout=12,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if r.status_code == 200:
            data = r.json()
            items = data.get("tokens", data.get("data", []))
            for t in items:
                currency = t.get("currency", "")
                issuer   = t.get("issuer", t.get("account", ""))
                if not currency or not issuer:
                    continue
                name = hex_to_name(currency) if len(currency) > 3 else currency
                if name.upper() in SKIP_SYMBOLS:
                    continue
                tokens.append({
                    "name": name,
                    "currency": currency,
                    "issuer": issuer,
                    "vol24h_xrp": 0,
                    "trustlines": 0,
                    "source": "firstledger",
                })
            _log(f"firstledger: {len(tokens)} new tokens")
    except Exception as e:
        _log(f"firstledger fetch error: {e}")
    return tokens


def load_existing() -> Dict:
    try:
        with open(DISCOVERY_FILE) as f:
            return json.load(f)
    except:
        return {"tokens": {}, "last_updated": 0}


def save_registry(verified_tokens: List[Dict]):
    """Write scanner-compatible active_registry.json — merges with existing."""
    # Load existing registry to preserve tokens between runs
    existing_map = {}
    try:
        with open(REGISTRY_FILE) as f:
            existing_data = json.load(f)
        for t in existing_data.get("tokens", []):
            k = f"{t.get('currency','')}:{t.get('issuer','')}"
            existing_map[k] = t
    except:
        pass

    # Merge new tokens in — new data overwrites old for same key (fresher TVL)
    seen = set()
    registry = []
    for t in verified_tokens:
        key = f"{t['currency']}:{t['issuer']}"
        if key not in seen:
            seen.add(key)
            registry.append({
                "symbol":   t["name"],
                "currency": t["currency"],
                "issuer":   t["issuer"],
                "tvl_xrp":  round(t.get("tvl_xrp", 0), 2),
                "source":   t.get("source", "unknown"),
            })
            existing_map[key] = registry[-1]

    # Add back any existing tokens not in current fetch (recently added)
    for key, tok in existing_map.items():
        if key not in seen:
            registry.append(tok)

    payload = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "count": len(registry),
        "tokens": registry,
        "last_updated_ts": time.time(),
    }
    with open(REGISTRY_FILE, "w") as f:
        json.dump(payload, f, indent=2)
    # Also write a backup that never gets wiped
    backup = REGISTRY_FILE.replace(".json", "_backup.json")
    with open(backup, "w") as f:
        json.dump(payload, f, indent=2)
    _log(f"Registry saved: {len(registry)} tokens → {REGISTRY_FILE}")


def run_discovery(force: bool = False) -> List[Dict]:
    """
    Full discovery run.
    Returns list of verified active token dicts.
    """
    existing = load_existing()
    existing_tokens = existing.get("tokens", {})

    last_run = float(existing.get("last_updated_ts", 0))
    if not force and (time.time() - last_run) < 600:  # 10 min cache
        _log("Discovery: cache fresh, skipping full run")
        return list(existing_tokens.values())

    _log("=== XRPL-Native Discovery Starting ===")

    # Fetch candidates from all sources
    candidates = {}

    for t in fetch_xrpl_to_tokens(600):
        key = f"{t['currency']}:{t['issuer']}"
        candidates[key] = t

    for t in fetch_firstledger_tokens():
        key = f"{t['currency']}:{t['issuer']}"
        if key not in candidates:
            candidates[key] = t

    _log(f"Total candidates to verify: {len(candidates)}")

    # Verify AMM + TVL for each
    verified = {}
    new_count = 0

    for key, token in candidates.items():
        # Use cached TVL if verified recently (< 15 min)
        if key in existing_tokens:
            cached = existing_tokens[key]
            if (time.time() - cached.get("last_verified", 0)) < 900:
                verified[key] = cached
                continue

        # Check AMM on-chain
        tvl = get_amm_tvl(token["currency"], token["issuer"])
        time.sleep(0.12)  # rate limit respect

        if tvl is None or tvl < MIN_TVL_XRP:
            continue

        entry = {
            "name":          token["name"],
            "currency":      token["currency"],
            "issuer":        token["issuer"],
            "tvl_xrp":       round(tvl, 2),
            "vol24h_xrp":    token.get("vol24h_xrp", 0),
            "trustlines":    token.get("trustlines", 0),
            "source":        token.get("source", "unknown"),
            "last_verified": time.time(),
            "first_seen":    existing_tokens.get(key, {}).get("first_seen", time.time()),
            "active":        True,
        }
        verified[key] = entry

        if key not in existing_tokens:
            new_count += 1
            _log(f"  NEW: {token['name']:12} TVL={tvl:>10,.0f} XRP  {token['issuer'][:24]}")

    # Sort by TVL desc, cap at TARGET_TOKENS
    sorted_tokens = sorted(verified.values(), key=lambda x: x.get("tvl_xrp", 0), reverse=True)
    top_tokens    = sorted_tokens[:TARGET_TOKENS]

    # Save
    with open(DISCOVERY_FILE, "w") as f:
        json.dump({
            "last_updated":    datetime.now(timezone.utc).isoformat(),
            "last_updated_ts": time.time(),
            "total_verified":  len(top_tokens),
            "new_this_run":    new_count,
            "tokens": {
                f"{t['currency']}:{t['issuer']}": t
                for t in top_tokens
            },
        }, f, indent=2)

    save_registry(top_tokens)
    _log(f"Discovery complete: {len(top_tokens)} tokens ({new_count} new)")
    return top_tokens


if __name__ == "__main__":
    tokens = run_discovery(force=True)
    print(f"\n{'='*60}")
    print(f"Total verified tokens: {len(tokens)}")
    print(f"\nTop 30 by TVL:")
    print(f"{'#':3} {'Symbol':15} {'TVL XRP':>12}  {'Source'}")
    print("-"*50)
    for i, t in enumerate(sorted(tokens, key=lambda x: -x.get('tvl_xrp',0))[:30], 1):
        print(f"{i:3}. {t['name']:15} {t.get('tvl_xrp',0):>12,.0f}  {t.get('source','?')}")
    print(f"\nSmall-cap runners (200-5000 XRP TVL): {len([t for t in tokens if 200 <= t.get('tvl_xrp',0) <= 5000])}")
