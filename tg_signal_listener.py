"""
tg_signal_listener.py — Telegram signal monitor for DKTrenchBot
Reads messages from monitored channels/groups and injects score boosts
into the trading bot's signal state.

Runs as a background process alongside bot.py.
"""

import os
import json
import time
import logging
import re
import requests
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] tg: %(message)s")
logger = logging.getLogger("tg_signal")

BOT_TOKEN   = "8498015516:AAHt_MfpW-c64yL22xumDc0WyUF-vIBdYAU"
API_BASE    = f"https://api.telegram.org/bot{BOT_TOKEN}"
STATE_DIR   = Path(__file__).parent / "state"
SIGNAL_FILE = STATE_DIR / "tg_signals.json"

# Channels/groups to monitor (add more as needed)
# For public channels: add bot as admin or forward messages to a group with bot
MONITORED_CHATS = []  # filled via runtime config

# Keywords that indicate bullish sentiment
BULLISH_KEYWORDS = [
    "lfg", "lfg!", "🚀", "🔥", "pump", "moon", "mooning", "buy",
    "aping", "ape", "entry", "signal", "breakout", "listing",
    "amm", "launch", "gem", "100x", "early", "accumulate", "load"
]

# Known XRPL token symbols to watch for
XRPL_TOKENS = [
    "FUZZY", "MAG", "XPM", "PHNIX", "ARMY", "EVR", "DROP", "BEAR",
    "ATM", "CULT", "SOLO", "SLT", "XAH", "FLR", "BERT", "GOAT",
    "CSC", "XRPH", "SIGMA", "JELLY", "CORE", "TOTO", "SEAL", "DONNIE",
    "SGB", "ROOSEVELT", "PHX", "PORKER", "PBM", "DOBE", "NOX", "BRETT",
    "BAALZ", "BAALZ", "SPY", "M1N", "TRVL", "CHICKEN", "GRIM",
]


def _load_signals() -> dict:
    if SIGNAL_FILE.exists():
        try:
            return json.loads(SIGNAL_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_signals(signals: dict):
    STATE_DIR.mkdir(exist_ok=True)
    SIGNAL_FILE.write_text(json.dumps(signals, indent=2))


def _extract_tickers(text: str) -> list:
    """Extract token tickers mentioned in message."""
    text_upper = text.upper()
    found = []
    for token in XRPL_TOKENS:
        # Match as whole word
        if re.search(r'\b' + re.escape(token) + r'\b', text_upper):
            found.append(token)
    return found


def _is_bullish(text: str) -> bool:
    """Check if message has bullish sentiment."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in BULLISH_KEYWORDS)


def _sentiment_strength(text: str) -> int:
    """Score 0-30 based on keyword density and emoji count."""
    text_lower = text.lower()
    hits = sum(1 for kw in BULLISH_KEYWORDS if kw in text_lower)
    rocket_count = text.count("🚀")
    fire_count = text.count("🔥")
    return min(30, hits * 5 + rocket_count * 3 + fire_count * 2)


def inject_signal(symbol: str, strength: int, source: str, message: str):
    """Write a score boost signal to state/tg_signals.json for the scanner to pick up."""
    signals = _load_signals()
    key = symbol.upper()
    existing = signals.get(key, {})

    # Don't downgrade an existing stronger signal
    if existing.get("strength", 0) >= strength:
        return

    signals[key] = {
        "symbol":    key,
        "strength":  strength,
        "source":    source,
        "message":   message[:200],
        "ts":        time.time(),
        "expires":   time.time() + 600,  # 10 min boost window
    }
    _save_signals(signals)
    logger.info(f"📡 SIGNAL: {key} +{strength}pts from {source} — \"{message[:60]}\"")


def purge_expired():
    """Remove expired signals."""
    signals = _load_signals()
    now = time.time()
    active = {k: v for k, v in signals.items() if v.get("expires", 0) > now}
    if len(active) != len(signals):
        _save_signals(active)


def process_message(text: str, chat_title: str):
    """Parse a message and inject signals for any tickers found."""
    if not text or len(text) < 3:
        return
    tickers = _extract_tickers(text)
    bullish = _is_bullish(text)
    if not tickers:
        return
    strength = _sentiment_strength(text) if bullish else 5
    for ticker in tickers:
        inject_signal(ticker, strength, chat_title, text)


def poll_updates():
    """Long-poll Telegram for new messages."""
    offset = None
    logger.info(f"🤖 TG Signal Listener started — monitoring {len(MONITORED_CHATS)} configured chats")
    logger.info("📡 Waiting for forwarded signals... (add DkTrenchBot as admin to channels)")

    while True:
        try:
            params = {"timeout": 30, "allowed_updates": ["message", "channel_post"]}
            if offset:
                params["offset"] = offset

            r = requests.get(f"{API_BASE}/getUpdates", params=params, timeout=40)
            data = r.json()

            if not data.get("ok"):
                logger.warning(f"API error: {data}")
                time.sleep(5)
                continue

            for update in data.get("result", []):
                offset = update["update_id"] + 1

                # Handle both regular messages and channel posts
                msg = update.get("message") or update.get("channel_post")
                if not msg:
                    continue

                text = msg.get("text") or msg.get("caption") or ""
                chat = msg.get("chat", {})
                chat_title = chat.get("title") or chat.get("username") or "unknown"
                chat_id = chat.get("id")

                if text:
                    process_message(text, chat_title)

            # Purge stale signals every loop
            purge_expired()

        except requests.exceptions.Timeout:
            pass  # normal for long polling
        except Exception as e:
            logger.error(f"Poll error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    poll_updates()


def handle_direct_command(text: str, from_user: str):
    """Handle direct messages to the bot as manual signal injections."""
    text = text.strip().lstrip("/")
    # Extract ticker — first word that looks like a token
    words = text.upper().split()
    tickers = []
    for w in words:
        clean = re.sub(r'[^A-Z0-9]', '', w)
        if 2 <= len(clean) <= 10:
            tickers.append(clean)
            if len(tickers) >= 3:
                break

    strength = _sentiment_strength(text) or 20  # default 20 for manual signals
    for ticker in tickers:
        inject_signal(ticker, strength, f"manual:{from_user}", text)
    return tickers


def poll_updates_v2():
    """Long-poll with direct message + channel post support."""
    offset = None
    logger.info("🤖 TG Signal Listener v2 started")
    logger.info("💬 Send tickers directly to @DkTrenchBot to inject signals")

    while True:
        try:
            params = {"timeout": 30, "allowed_updates": ["message", "channel_post"]}
            if offset:
                params["offset"] = offset

            r = requests.get(f"{API_BASE}/getUpdates", params=params, timeout=40)
            data = r.json()

            if not data.get("ok"):
                time.sleep(5)
                continue

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message") or update.get("channel_post")
                if not msg:
                    continue

                text = msg.get("text") or msg.get("caption") or ""
                chat = msg.get("chat", {})
                chat_type = chat.get("type", "")
                from_user = msg.get("from", {}).get("username") or "user"

                if not text:
                    continue

                if chat_type == "private":
                    # Direct message to bot — treat as manual signal injection
                    tickers = handle_direct_command(text, from_user)
                    if tickers:
                        reply = f"📡 Signal injected: {', '.join(tickers)}\nBoost active for 10 min ⚡"
                    else:
                        reply = "Send a token ticker to boost it — e.g. FUZZY or ARMY 🚀"
                    requests.post(f"{API_BASE}/sendMessage", json={
                        "chat_id": msg["chat"]["id"],
                        "text": reply
                    })
                else:
                    # Group/channel message — parse for signals
                    chat_title = chat.get("title") or chat.get("username") or "group"
                    process_message(text, chat_title)

            purge_expired()

        except requests.exceptions.Timeout:
            pass
        except Exception as e:
            logger.error(f"Poll error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    poll_updates_v2()
