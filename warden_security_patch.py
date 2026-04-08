"""
WARDEN SECURITY PATCH
Fixes:
1. Removes hardcoded Telegram token (uses env variable)
2. Adds RPC failover system

Plug-and-play usage across your bot.
"""

import os
import requests

# ─────────────────────────────────────────────
# 🔐 TELEGRAM TOKEN (SECURE)
# ─────────────────────────────────────────────

def get_tg_token():
    token = os.getenv("TG_TOKEN")
    if not token:
        raise ValueError("❌ TG_TOKEN not set in environment variables.")
    return token


def send_telegram_message(message: str, chat_id: str):
    token = get_tg_token()

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    try:
        requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown"
            },
            timeout=5
        )
    except Exception as e:
        print(f"⚠️ Telegram send error: {e}")


# ─────────────────────────────────────────────
# 🌐 RPC FAILOVER SYSTEM
# ─────────────────────────────────────────────

RPC_ENDPOINTS = [
    "https://rpc.xrplclaw.com",
    "https://xrplcluster.com",
    "https://s1.ripple.com:51234"
]


def rpc_call(method: str, params: dict, timeout: int = 10):
    """
    Try multiple RPC endpoints until one succeeds.
    """

    for url in RPC_ENDPOINTS:
        try:
            response = requests.post(
                url,
                json={"method": method, "params": [params]},
                timeout=timeout
            )

            data = response.json()

            if "result" in data:
                return data["result"]

        except Exception:
            continue

    print("❌ All RPC endpoints failed.")
    return {}
