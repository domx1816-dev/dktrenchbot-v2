"""
WARDEN SECURITY PATCH — RPC FAILOVER ONLY
Removes all Telegram dependencies.
"""

import requests

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
