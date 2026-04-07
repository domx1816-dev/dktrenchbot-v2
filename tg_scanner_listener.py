#!/usr/bin/env python3
"""
tg_scanner_listener.py — Lite Haus Alerts Hub Parser + Signal Injector

Polls @DkTrenchBot for Lite Haus scanner messages and extracts:
  - Symbol, issuer address, dev wallet
  - Holder count, top 10 concentration %
  - Circulating supply, market cap, liquidity
  - Price momentum: 5m / 30m / 1h / 6h / 24h
  - Buy pressure %
  - Top 10 holder wallet addresses (for smart wallet cross-reference)
  - First scan wallet (early mover intel)
  - Bullish/Bearish sentiment

Writes enriched signals to:
  state/tg_scanner_signals.json  → score boosts for bot.py
  state/tg_discovered_wallets.json → new smart wallets to track
"""

import json, os, sys, time, re, requests, logging
from pathlib import Path

BOT_DIR   = Path(__file__).parent
STATE_DIR = BOT_DIR / "state"
SIG_FILE  = STATE_DIR / "tg_scanner_signals.json"
WALLET_F  = STATE_DIR / "tg_discovered_wallets.json"
LOG_FILE  = STATE_DIR / "tg_scanner.log"
SEEN_FILE = STATE_DIR / "tg_seen_updates.json"

TG_TOKEN  = "8498015516:AAHt_MfpW-c64yL22xumDc0WyUF-vIBdYAU"
CLIO_URL  = "http://xrpl-rpc.goons.app:51233"
POLL_SEC  = 15

os.makedirs(STATE_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [TGScan] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("tg_scanner")


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_number(s: str) -> float:
    """Parse '7.5k', '$30.8k', '972.6k', '33.36%' etc into float."""
    if not s:
        return 0.0
    s = s.strip().replace(",", "").replace("$", "").replace("%", "")
    m = re.match(r"([\d.]+)([KkMmBb]?)", s)
    if not m:
        return 0.0
    n = float(m.group(1))
    suffix = m.group(2).upper()
    if suffix == "K":  n *= 1_000
    elif suffix == "M": n *= 1_000_000
    elif suffix == "B": n *= 1_000_000_000
    return n


def parse_pct(s: str) -> float:
    """Parse '+4.40%' or '⬆️ 4.40%' or '⬇️ -4.74%' → float (e.g. 0.044)"""
    if not s:
        return 0.0
    # strip emoji and whitespace
    s = re.sub(r"[⬆⬇️\s↑↓+]", "", s).strip()
    try:
        return float(s) / 100.0
    except:
        return 0.0


def load_signals() -> dict:
    try:
        if SIG_FILE.exists():
            return json.loads(SIG_FILE.read_text())
    except:
        pass
    return {}


def save_signals(sigs: dict):
    tmp = str(SIG_FILE) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(sigs, f, indent=2)
    os.replace(tmp, str(SIG_FILE))


def load_wallets() -> dict:
    try:
        if WALLET_F.exists():
            return json.loads(WALLET_F.read_text())
    except:
        pass
    return {}


def save_wallets(w: dict):
    tmp = str(WALLET_F) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(w, f, indent=2)
    os.replace(tmp, str(WALLET_F))


def load_seen() -> set:
    try:
        if SEEN_FILE.exists():
            return set(json.loads(SEEN_FILE.read_text()))
    except:
        pass
    return set()


def save_seen(seen: set):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen)[-1000:], f)


# ── Lite Haus Format Parser ───────────────────────────────────────────────────

def parse_lite_haus(text: str) -> dict:
    """
    Parse a Lite Haus Alerts Hub message.

    Example input:
    📊 Sentiment Analysis for $SENT
    🔎 Issuer Address: rspYcqzdPTjaUPmWg9i1vK5LJLSyfJUpH4
    💻 Dev: rM6Xe...
    👥 Holders: 244
    🐋 Top 10: 33.36%
    🔍 Circulating Supply: 972.6k SENT
    |💰: $30.8k |💧: $7.5k
    |🧠🟢 Bullish
    | 5m: ⬆️ 4.40% | 30m: ⬆️ 6.98%
    | 1h: ⬆️ 6.98% | 6h: ⬇️ -4.74%
    | 24h: ⬆️ 10.98% |
    | Buy Pressure: 0.49% |
    📜 Top 10 Holders Breakdown:
    #1: rEwQm... - 122.1k (12.56%)⚖️
    ...
    👤 First scan: ebyam_oB ($41.6k)
    """
    sig = {}

    # ── Symbol ────────────────────────────────────────────────────────────────
    m = re.search(r"\$([A-Z][A-Z0-9]{1,12})", text)
    if not m:
        # try "for TOKEN" pattern
        m = re.search(r"for\s+\$?([A-Z][A-Z0-9]{1,12})", text)
    if m:
        sig["symbol"] = m.group(1)
    else:
        return {}  # can't proceed without symbol

    # ── Issuer address ────────────────────────────────────────────────────────
    m = re.search(r"Issuer Address[:\s]+([rR][a-zA-Z0-9]{20,50})", text)
    if m:
        sig["issuer"] = m.group(1)

    # ── Dev wallet ────────────────────────────────────────────────────────────
    m = re.search(r"Dev[:\s]+([rR][a-zA-Z0-9]{5,50})", text)
    if m:
        sig["dev_wallet"] = m.group(1)

    # ── Holders ───────────────────────────────────────────────────────────────
    m = re.search(r"Holders[:\s]+([\d,]+)", text)
    if m:
        sig["holders"] = int(m.group(1).replace(",", ""))

    # ── Top 10 concentration % ────────────────────────────────────────────────
    m = re.search(r"Top\s*10[:\s]+([\d.]+)%", text)
    if m:
        sig["top10_pct"] = float(m.group(1))

    # ── Circulating supply ────────────────────────────────────────────────────
    m = re.search(r"Circulating Supply[:\s]+([\d.]+[KkMm]?)\s", text)
    if m:
        sig["circ_supply"] = parse_number(m.group(1))

    # ── Market cap & liquidity ────────────────────────────────────────────────
    # |💰: $30.8k |💧: $7.5k
    m = re.search(r"💰[:\s]+\$([\d.]+[KkMm]?)", text)
    if m:
        sig["mcap_usd"] = parse_number(m.group(1))

    m = re.search(r"💧[:\s]+\$([\d.]+[KkMm]?)", text)
    if m:
        sig["liquidity_usd"] = parse_number(m.group(1))

    # ── Sentiment ─────────────────────────────────────────────────────────────
    if re.search(r"Bullish|🟢", text, re.IGNORECASE):
        sig["sentiment"] = "bullish"
    elif re.search(r"Bearish|🔴", text, re.IGNORECASE):
        sig["sentiment"] = "bearish"
    else:
        sig["sentiment"] = "neutral"

    # ── Price momentum (5m / 30m / 1h / 6h / 24h) ───────────────────────────
    for tf, pat in [
        ("5m",  r"5m[:\s]+[⬆⬇️↑↓\s]*([-+]?[\d.]+)%"),
        ("30m", r"30m[:\s]+[⬆⬇️↑↓\s]*([-+]?[\d.]+)%"),
        ("1h",  r"1h[:\s]+[⬆⬇️↑↓\s]*([-+]?[\d.]+)%"),
        ("6h",  r"6h[:\s]+[⬆⬇️↑↓\s]*([-+]?[\d.]+)%"),
        ("24h", r"24h[:\s]+[⬆⬇️↑↓\s]*([-+]?[\d.]+)%"),
    ]:
        m = re.search(pat, text)
        if m:
            sig[f"pct_{tf}"] = float(m.group(1)) / 100.0

    # ── Buy pressure ─────────────────────────────────────────────────────────
    m = re.search(r"Buy Pressure[:\s]+([\d.]+)%", text)
    if m:
        sig["buy_pressure_pct"] = float(m.group(1))

    # ── Top 10 holder wallets ─────────────────────────────────────────────────
    # #1: rEwQm... - 122.1k (12.56%)⚖️
    holder_pat = re.compile(r"#(\d+)[:\s]+([rR][a-zA-Z0-9.]{4,50})\s*[-–]\s*([\d.]+[KkMm]?)\s*\(([\d.]+)%\)")
    holders_list = []
    for m in holder_pat.finditer(text):
        rank    = int(m.group(1))
        wallet  = m.group(2)
        amount  = parse_number(m.group(3))
        pct     = float(m.group(4))
        # wallet might be truncated (rEwQm...) — store as-is, mark as partial
        full    = not wallet.endswith("...")
        holders_list.append({
            "rank": rank, "wallet": wallet, "amount": amount,
            "pct": pct, "full_address": full
        })
    if holders_list:
        sig["top_holders"] = holders_list

    # ── First scan wallet ─────────────────────────────────────────────────────
    # 👤 First scan: ebyam_oB ($41.6k)
    m = re.search(r"First scan[:\s]+(\S+)\s*\(\$([\d.]+[KkMm]?)\)", text)
    if m:
        sig["first_scan_wallet"] = m.group(1)
        sig["first_scan_value_usd"] = parse_number(m.group(2))

    sig["source"] = "lite_haus"
    sig["raw_ts"] = time.time()
    return sig


# ── Score computation from Lite Haus data ────────────────────────────────────

def compute_boost(sig: dict) -> int:
    """
    Convert Lite Haus data into a score boost for our bot.
    Calibrated against PHX/ROOS/SPY winner DNA.
    Max: 50 pts.
    """
    pts = 0
    reasons = []

    # ── Holder count (PHX=104, ROOS=115, SPY=197 = sweet spot 50-300) ────────
    holders = sig.get("holders", 0)
    if 50 <= holders <= 150:
        pts += 20
        reasons.append(f"holders={holders}(sweet_spot)")
    elif 150 < holders <= 300:
        pts += 12
        reasons.append(f"holders={holders}(early)")
    elif holders < 50:
        pts += 8
        reasons.append(f"holders={holders}(very_early)")
    elif holders > 500:
        pts -= 5
        reasons.append(f"holders={holders}(mature-penalty)")

    # ── Top 10 concentration (PHX=20%, ROOS=12%, SPY=64%=bad) ───────────────
    top10 = sig.get("top10_pct", 0)
    if 0 < top10 <= 25:
        pts += 10
        reasons.append(f"top10={top10:.1f}%(healthy)")
    elif top10 <= 40:
        pts += 5
    elif top10 > 60:
        pts -= 15
        reasons.append(f"top10={top10:.1f}%(rug_risk)")

    # ── Price momentum (multi-timeframe alignment) ────────────────────────────
    p5m  = sig.get("pct_5m", 0)
    p30m = sig.get("pct_30m", 0)
    p1h  = sig.get("pct_1h", 0)
    p6h  = sig.get("pct_6h", 0)
    p24h = sig.get("pct_24h", 0)

    # All timeframes green = strong momentum
    green_count = sum(1 for p in [p5m, p30m, p1h, p24h] if p > 0)
    if green_count == 4:
        pts += 15
        reasons.append("all_tf_green")
    elif green_count >= 3:
        pts += 8
        reasons.append(f"{green_count}tf_green")
    elif green_count <= 1:
        pts -= 5
        reasons.append("weak_momentum")

    # Short-term strength (5m/30m) = entry timing
    if p5m > 0.03:   pts += 5;  reasons.append(f"5m=+{p5m:.1%}")
    if p30m > 0.05:  pts += 5;  reasons.append(f"30m=+{p30m:.1%}")

    # 6h negative but others positive = healthy pullback = ENTRY SIGNAL
    if p6h < -0.03 and p24h > 0.05 and p1h > 0:
        pts += 8
        reasons.append("pullback_entry")

    # ── Sentiment ─────────────────────────────────────────────────────────────
    if sig.get("sentiment") == "bullish":
        pts += 5
        reasons.append("bullish")
    elif sig.get("sentiment") == "bearish":
        pts -= 8

    # ── Buy pressure ─────────────────────────────────────────────────────────
    bp = sig.get("buy_pressure_pct", 0)
    if bp > 2.0:
        pts += 8
        reasons.append(f"buy_pressure={bp:.2f}%")
    elif bp > 0.5:
        pts += 3

    # ── Liquidity (thin pool = our sweet spot) ────────────────────────────────
    liq = sig.get("liquidity_usd", 0)
    # Convert USD to approx XRP (rough: $0.5/XRP)
    liq_xrp = liq / 0.5
    if 1000 <= liq_xrp <= 15000:
        pts += 8
        reasons.append(f"liq={liq_xrp:.0f}xrp(sweet_spot)")
    elif liq_xrp < 1000 and liq_xrp > 0:
        pts += 4

    sig["boost_reasons"] = reasons
    return max(0, min(pts, 50))


# ── Wallet intelligence ───────────────────────────────────────────────────────

def process_holder_wallets(sig: dict):
    """
    Extract full wallet addresses from top holders.
    Add to tg_discovered_wallets.json for smart_wallet_tracker to monitor.
    Only saves wallets that appear to be full addresses (not truncated).
    """
    symbol  = sig.get("symbol", "?")
    holders = sig.get("top_holders", [])
    wallets = load_wallets()
    new_count = 0

    for h in holders:
        wallet = h.get("wallet", "")
        if not wallet or wallet.endswith("...") or len(wallet) < 25:
            continue  # truncated — skip

        if wallet not in wallets:
            wallets[wallet] = {
                "discovered_via": f"lite_haus_{symbol}",
                "rank_in_token":  h.get("rank"),
                "pct_held":       h.get("pct"),
                "first_seen":     time.time(),
                "tokens_held":    [symbol],
            }
            new_count += 1
        else:
            # Update: add this token to their portfolio
            held = wallets[wallet].get("tokens_held", [])
            if symbol not in held:
                held.append(symbol)
                wallets[wallet]["tokens_held"] = held

    # Also save issuer address
    issuer = sig.get("issuer", "")
    if issuer and issuer not in wallets:
        wallets[issuer] = {
            "discovered_via": f"lite_haus_{symbol}_issuer",
            "role": "issuer",
            "first_seen": time.time(),
            "tokens_held": [symbol],
        }

    if new_count > 0 or issuer:
        save_wallets(wallets)
        log.info(f"  Saved {new_count} new wallets from {symbol} top holders")

    # Try to add full addresses to smart_wallet_tracker state
    try:
        sw_file = STATE_DIR / "smart_wallet_state.json"
        if sw_file.exists() and new_count > 0:
            sw = json.loads(sw_file.read_text())
            changed = False
            for addr, info in wallets.items():
                if addr not in sw.get("wallet_trustlines", {}):
                    if info.get("role") != "issuer":  # don't track issuers as smart wallets
                        sw.setdefault("wallet_trustlines", {})[addr] = []
                        changed = True
            if changed:
                tmp = str(sw_file) + ".tmp"
                with open(tmp, "w") as f:
                    json.dump(sw, f)
                os.replace(tmp, str(sw_file))
                log.info(f"  Added {new_count} wallets to smart_wallet_tracker")
    except Exception as e:
        log.debug(f"Smart wallet update error: {e}")


# ── Signal injection ──────────────────────────────────────────────────────────

def inject_signal(sig: dict):
    """Write enriched signal to tg_scanner_signals.json for bot to consume."""
    symbol = sig.get("symbol", "").upper()
    if not symbol:
        return

    boost = compute_boost(sig)

    # Log the full analysis
    log.info(f"📊 {symbol}: boost=+{boost}pts | "
             f"holders={sig.get('holders')} | top10={sig.get('top10_pct')}% | "
             f"sentiment={sig.get('sentiment')} | "
             f"5m={sig.get('pct_5m',0):+.1%} 1h={sig.get('pct_1h',0):+.1%} 24h={sig.get('pct_24h',0):+.1%} | "
             f"reasons={sig.get('boost_reasons',[])} | "
             f"liq=${sig.get('liquidity_usd',0):.1f} | "
             f"mcap=${sig.get('mcap_usd',0):.1f}")

    signals = load_signals()

    signals[symbol] = {
        "symbol":          symbol,
        "boost":           boost,
        # Structural data
        "holders":         sig.get("holders"),
        "top10_pct":       sig.get("top10_pct"),
        "circ_supply":     sig.get("circ_supply"),
        "mcap_usd":        sig.get("mcap_usd"),
        "liquidity_usd":   sig.get("liquidity_usd"),
        "liquidity_xrp":   (sig.get("liquidity_usd", 0) / 0.5) if sig.get("liquidity_usd") else None,
        # Momentum
        "sentiment":       sig.get("sentiment"),
        "pct_5m":          sig.get("pct_5m"),
        "pct_30m":         sig.get("pct_30m"),
        "pct_1h":          sig.get("pct_1h"),
        "pct_6h":          sig.get("pct_6h"),
        "pct_24h":         sig.get("pct_24h"),
        "buy_pressure_pct": sig.get("buy_pressure_pct"),
        # Provenance
        "issuer":          sig.get("issuer"),
        "dev_wallet":      sig.get("dev_wallet"),
        "first_scan":      sig.get("first_scan_wallet"),
        "first_scan_usd":  sig.get("first_scan_value_usd"),
        "boost_reasons":   sig.get("boost_reasons", []),
        "source":          "lite_haus",
        "ts":              time.time(),
        "expires":         time.time() + 3600,
    }
    save_signals(signals)

    # Process holder wallets for smart tracking
    process_holder_wallets(sig)


# ── TG polling ────────────────────────────────────────────────────────────────

def get_updates(offset: int = 0) -> list:
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates",
            params={"offset": offset, "limit": 20, "timeout": 10},
            timeout=15,
        )
        return r.json().get("result", [])
    except Exception as e:
        log.warning(f"getUpdates error: {e}")
        return []


def get_file_content(file_id: str) -> str:
    try:
        r  = requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/getFile",
                          params={"file_id": file_id}, timeout=8)
        fp = r.json().get("result", {}).get("file_path", "")
        if fp:
            return requests.get(
                f"https://api.telegram.org/file/bot{TG_TOKEN}/{fp}", timeout=10
            ).text
    except Exception as e:
        log.warning(f"File download error: {e}")
    return ""


def store_chat_id(chat_id: int):
    """Persist chat_id so amm_launch_watcher can send TG alerts."""
    try:
        hl_file = STATE_DIR / "hot_launches.json"
        hl = {}
        if hl_file.exists():
            try: hl = json.loads(hl_file.read_text())
            except: pass
        if not hl.get("tg_chat_id"):
            hl["tg_chat_id"] = chat_id
            tmp = str(hl_file) + ".tmp"
            with open(tmp, "w") as f: json.dump(hl, f)
            os.replace(tmp, str(hl_file))
            log.info(f"Stored chat_id={chat_id} for TG alerts")
    except Exception as e:
        log.debug(f"chat_id store error: {e}")


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    log.info("TG Scanner Listener starting — Lite Haus format parser")
    log.info(f"Polling @DkTrenchBot every {POLL_SEC}s")

    seen   = load_seen()
    offset = (max(seen) + 1) if seen else 0

    while True:
        try:
            updates = get_updates(offset)

            for upd in updates:
                uid = upd.get("update_id", 0)
                if uid in seen:
                    continue
                seen.add(uid)
                offset = max(offset, uid + 1)

                msg = upd.get("message", {}) or upd.get("channel_post", {})
                if not msg:
                    continue

                # Store chat_id for TG alerts
                chat_id = msg.get("chat", {}).get("id")
                if chat_id:
                    store_chat_id(chat_id)

                text = msg.get("text", "") or msg.get("caption", "") or ""

                # Handle file attachments
                doc = msg.get("document", {})
                if doc:
                    fname = doc.get("file_name", "")
                    if fname.endswith((".txt", ".json", ".csv")):
                        content = get_file_content(doc.get("file_id", ""))
                        if content:
                            text = content
                            log.info(f"File received: {fname} ({len(content)} chars)")

                if not text:
                    continue

                frm    = msg.get("from", {}) or {}
                sender = frm.get("username") or frm.get("first_name") or "?"
                log.info(f"Message from {sender}: {text[:80].strip()}")

                # ── Try Lite Haus format first ────────────────────────────────
                if "Issuer Address" in text or "Holders:" in text or "Sentiment Analysis" in text:
                    sig = parse_lite_haus(text)
                    if sig.get("symbol"):
                        inject_signal(sig)
                        log.info(f"✅ Lite Haus signal processed: {sig['symbol']}")
                    else:
                        log.warning("Lite Haus format detected but couldn't extract symbol")

                # ── Fallback: plain ticker ────────────────────────────────────
                else:
                    clean = text.strip().upper().replace("$", "")
                    if re.match(r'^[A-Z][A-Z0-9]{1,12}$', clean):
                        signals = load_signals()
                        signals[clean] = {
                            "symbol":  clean,
                            "boost":   15,
                            "source":  "manual_ticker",
                            "ts":      time.time(),
                            "expires": time.time() + 3600,
                        }
                        save_signals(signals)
                        log.info(f"Manual ticker boost: {clean} +15pts")

            save_seen(seen)

            # Expire old signals
            sigs  = load_signals()
            now   = time.time()
            expired = [k for k, v in sigs.items() if v.get("expires", 0) < now]
            if expired:
                for k in expired:
                    del sigs[k]
                save_signals(sigs)

        except Exception as e:
            log.error(f"Main loop error: {e}")

        time.sleep(POLL_SEC)


if __name__ == "__main__":
    # Test the parser against the example from the user
    test_msg = """
📊 Sentiment Analysis for $SENT

🔎 Issuer Address: rspYcqzdPTjaUPmWg9i1vK5LJLSyfJUpH4

💻 Dev: rM6Xe...
👥 Holders: 244
🐋 Top 10: 33.36%

🔍 Circulating Supply: 972.6k SENT
|💰: $30.8k |💧: $7.5k
|🧠🟢 Bullish
| 5m: ⬆️ 4.40% | 30m: ⬆️ 6.98% 
| 1h: ⬆️ 6.98% | 6h: ⬇️ -4.74% 
| 24h: ⬆️ 10.98% |
| Buy Pressure: 0.49% |

📜 Top 10 Holders Breakdown:
#1: rEwQm... - 122.1k (12.56%)⚖️
#2: rM6Xe... - 80k (8.23%)💻
#3: r93eB... - 60.2k (6.19%)
#4: rBvro... - 32.2k (3.31%)
#5: rJZ7g... - 30.8k (3.16%)
#6: rHScq... - 30.5k (3.14%)
#7: r9MDf... - 30.4k (3.13%)
#8: rnb2V... - 30.4k (3.12%)
#9: rGS5P... - 30k (3.08%)
#10: r9nKz... - 29.4k (3.02%)⚖️
👤 First scan: ebyam_oB ($41.6k) 

🔗 Socials: 🌐 ✈️ 🐦
~Metrics provided by api.sentxrpl.com
Bot is in 86 chats
    """
    print("=== PARSER TEST ===")
    sig = parse_lite_haus(test_msg)
    boost = compute_boost(sig)
    print(json.dumps(sig, indent=2))
    print(f"\nComputed boost: +{boost} pts")
    print(f"Reasons: {sig.get('boost_reasons', [])}")
    main()
