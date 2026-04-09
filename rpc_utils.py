"""
rpc_utils.py — Shared RPC utility with robust retry logic.
All modules should import from here instead of defining their own _rpc().
"""

import requests
import time
from typing import Optional, Dict

CLIO_URL = "https://rpc.xrplclaw.com"


def rpc_call(method: str, params: dict, max_retries: int = 5, base_timeout: int = 15) -> Optional[dict]:
    """
    Make XRPL RPC call with exponential backoff retry.
    
    Retries on: slowDown, notReady errors (RPC overloaded)
    Backoff: 1s, 2s, 4s, 8s, 16s
    
    Returns result dict or None if all retries exhausted.
    """
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                CLIO_URL,
                json={"method": method, "params": [params]},
                timeout=base_timeout,
            )
            data = resp.json()
            result = data.get("result")
            
            # Retry on transient errors
            if isinstance(result, dict) and result.get("error") in ("slowDown", "notReady"):
                wait_time = 2 ** attempt  # 1, 2, 4, 8, 16 seconds
                time.sleep(wait_time)
                continue
            
            return result
        except Exception:
            wait_time = 0.5 * (attempt + 1)
            time.sleep(wait_time)
    
    return None
