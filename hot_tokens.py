"""
hot_tokens.py — Detect explosive new/low-cap tokens BEFORE they moon.

Two signals:
1. xpmarket: Sort by txn count, find tokens where vol/liquidity ratio > 1.5 (turnover spike)
2. xrpl.to: Sort by most recently created, check if any have AMM with growing TVL

This runs every scan cycle alongside normal scanner.
Adds qualifying tokens to active_registry.json as temporary entries.
"""

import json, os, time, requests, logging
from config import CLIO_URL, STATE_DIR
from discovery import to_hex, hex_to_name, verify_amm

log = logging.getLogger("bot")

HOT_REGISTRY_FILE = os.path.join(STATE_DIR, "hot_tokens.json")
HOT_WATCHLIST_FILE = os.path.join(STATE_DIR, "hot_watchlist.json")

# Min TVL to consider (XRP) — low enough to catch early movers
HOT_MIN_TVL_XRP = 500
HOT_MAX_TVL_XRP = 50_000   # Ignore whale pools — we want early stage

# Volume/liquidity turnover ratio to qualify
HOT_TURNOVER_MIN = 0.8   # 80% of pool TVL traded in 24h = hot

# Max tokens to add to watchlist per run
HOT_MAX_WATCH = 15


def _rpc(method, params):
    try:
        r = requests.post(CLIO_URL, json={"method": method, "params": [params]}, timeout=12)
        return r.json().get("result", {})
    except:
        return {}


def _xpmarket_movers():
    """Fetch xpmarket tokens sorted by txn count, filter for volume spikes."""
    movers = []
    try:
        for page in range(1, 5):
            r = requests.get(
                "https://api.xpmarket.com/api/amm/list",
                params={"sort": "txns", "order": "desc", "limit": 100, "page": page},
                timeout=15,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if not r.ok:
                break
            items = r.json().get("data", {}).get("items", [])
            if not items:
                break

            for item in items:
                liq_xrp = float(item.get("amount1") or 0)  # XRP side of pool
                vol_usd  = float(item.get("volume_usd") or 0)
                liq_usd  = float(item.get("liquidity_usd") or 1)
                txns     = int(item.get("txns") or 0)

                # Filter: sweet spot TVL range
                if liq_xrp < HOT_MIN_TVL_XRP or liq_xrp > HOT_MAX_TVL_XRP:
                    continue

                # Volume turnover check
                turnover = vol_usd / max(liq_usd, 1)
                if turnover < HOT_TURNOVER_MIN:
                    continue

                # Parse symbol/issuer
                sym_raw = item.get("symbol", "")
                title   = item.get("title", "")
                issuer  = None
                currency = None

                if "-" in sym_raw:
                    issuer_part = sym_raw.split("-")[-1]
                    if issuer_part.startswith("r") and len(issuer_part) > 20:
                        issuer = issuer_part

                if "/" in title:
                    token_name = title.split("/")[1].split("-")[0] if "/" in title else ""
                    if token_name and token_name != "XRP":
                        currency = to_hex(token_name)
                        name = token_name
                    else:
                        continue
                else:
                    continue

                if currency and issuer:
                    movers.append({
                        "symbol": name,
                        "currency": currency,
                        "issuer": issuer,
                        "tvl_xrp": liq_xrp,
                        "turnover": round(turnover, 2),
                        "txns": txns,
                        "source": "hot_xpmarket",
                    })

            time.sleep(0.2)

    except Exception as e:
        log.warning(f"hot_tokens xpmarket error: {e}")

    return movers


def _xrpl_to_new():
    """Fetch recently created tokens from xrpl.to with trading activity."""
    movers = []
    try:
        r = requests.get(
            "https://api.xrpl.to/api/tokens",
            params={"sortBy": "date", "descending": "true", "limit": 50},
            timeout=12,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        tokens = r.json().get("tokens", [])
        for t in tokens:
            currency = t.get("currency", "")
            issuer   = t.get("issuer", "")
            name     = t.get("name", currency[:8])
            exch     = t.get("exch")   # price in XRP

            if not issuer or not exch:
                continue

            # Only tokens with actual trading (exch > 0 and offers > 0)
            offers = t.get("offers", 0)
            if offers < 5:
                continue

            movers.append({
                "symbol": name,
                "currency": currency,
                "issuer": issuer,
                "tvl_xrp": 0,   # unknown, will verify AMM
                "source": "hot_xrpl_to",
            })
    except Exception as e:
        log.warning(f"hot_tokens xrpl.to error: {e}")

    return movers


def scan_hot_tokens() -> list:
    """
    Main function: find explosive new tokens.
    Returns list of tokens to add to active watchlist.
    """
    candidates = []
    seen = set()

    # 1. xpmarket movers (volume/TVL spike)
    xpm = _xpmarket_movers()
    for t in xpm:
        key = f"{t['currency']}:{t['issuer']}"
        if key not in seen:
            seen.add(key)
            candidates.append(t)

    # 2. New tokens from xrpl.to with activity
    new = _xrpl_to_new()
    for t in new:
        key = f"{t['currency']}:{t['issuer']}"
        if key not in seen:
            seen.add(key)
            candidates.append(t)

    # Verify each has an AMM and check TVL
    qualified = []
    for t in candidates[:HOT_MAX_WATCH * 2]:
        try:
            tvl = verify_amm(t["currency"], t["issuer"])
            if tvl and tvl >= HOT_MIN_TVL_XRP:
                t["tvl_xrp"] = round(tvl, 2)
                qualified.append(t)
            time.sleep(0.15)
        except Exception as e:
            log.debug(f"verify_amm failed for {t['symbol']}: {e}")

    # Limit to top HOT_MAX_WATCH by TVL
    qualified.sort(key=lambda x: x.get("turnover", 0), reverse=True)
    final = qualified[:HOT_MAX_WATCH]

    # Save to watchlist
    try:
        existing = {}
        if os.path.exists(HOT_WATCHLIST_FILE):
            with open(HOT_WATCHLIST_FILE) as f:
                existing = {f"{t['currency']}:{t['issuer']}": t for t in json.load(f)}
        for t in final:
            key = f"{t['currency']}:{t['issuer']}"
            existing[key] = t
        with open(HOT_WATCHLIST_FILE, "w") as f:
            json.dump(list(existing.values()), f, indent=2)
    except Exception as e:
        log.warning(f"hot watchlist save error: {e}")

    if final:
        log.info(f"🔥 Hot tokens detected: {[t['symbol'] for t in final]}")

    return final


def merge_into_registry(hot_tokens: list):
    """Add hot tokens to the active_registry.json for scanning."""
    registry_file = os.path.join(STATE_DIR, "active_registry.json")
    try:
        with open(registry_file) as f:
            registry = json.load(f)
    except:
        registry = {"tokens": []}

    tokens = registry if isinstance(registry, list) else registry.get("tokens", [])
    existing_keys = {f"{t.get('currency','')}:{t.get('issuer','')}": True for t in tokens}

    added = 0
    for ht in hot_tokens:
        key = f"{ht['currency']}:{ht['issuer']}"
        if key not in existing_keys:
            tokens.append({
                "symbol": ht["symbol"],
                "currency": ht["currency"],
                "issuer": ht["issuer"],
                "hot": True,
            })
            existing_keys[key] = True
            added += 1

    if added:
        out = registry if isinstance(registry, list) else {"tokens": tokens}
        if isinstance(out, list):
            out = tokens
        with open(registry_file, "w") as f:
            json.dump({"tokens": tokens} if isinstance(registry, dict) else tokens, f, indent=2)
        log.info(f"🔥 Added {added} hot tokens to scanner registry")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    hot = scan_hot_tokens()
    print(f"\nFound {len(hot)} hot tokens:")
    for t in hot:
        print(f"  {t['symbol']:15} TVL={t['tvl_xrp']:8.0f} XRP | turnover={t.get('turnover','?')} | src={t['source']}")
