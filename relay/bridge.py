"""
bridge.py — A2A relay client for DKTrenchBot
Pushes signals + trades to relay, pulls Predator's signals to boost scoring.
"""

import requests
import logging
import time

logger = logging.getLogger("bridge")

RELAY_URL = None   # set after tunnel starts
API_KEY   = "dk-7x9m2p-trench"
AGENT     = "DKTrench"

_last_pull = 0
_peer_signals = []   # cache of other agent's signals


def set_url(url: str):
    global RELAY_URL
    RELAY_URL = url.rstrip("/")
    logger.info(f"Relay URL set: {RELAY_URL}")


def _headers():
    return {"X-API-Key": API_KEY, "Content-Type": "application/json"}


def push_signal(symbol: str, score: float, chart: str, tvl: float,
                pct: float, regime: str = "neutral", note: str = ""):
    if not RELAY_URL:
        return
    try:
        requests.post(f"{RELAY_URL}/signal", json={
            "symbol": symbol, "score": score, "chart": chart,
            "tvl": tvl, "pct": pct, "regime": regime, "note": note,
        }, headers=_headers(), timeout=5)
    except Exception as e:
        logger.debug(f"Relay push_signal failed: {e}")


def push_trade(symbol: str, action: str, xrp: float, pnl_pct=None,
               exit_reason: str = "", score: float = 0, chart: str = "", note: str = ""):
    if not RELAY_URL:
        return
    try:
        requests.post(f"{RELAY_URL}/trade", json={
            "symbol": symbol, "action": action, "xrp": xrp,
            "pnl_pct": pnl_pct, "exit_reason": exit_reason,
            "score": score, "chart": chart, "note": note,
        }, headers=_headers(), timeout=5)
    except Exception as e:
        logger.debug(f"Relay push_trade failed: {e}")


def push_warning(symbol: str, message: str, level: str = "caution"):
    if not RELAY_URL:
        return
    try:
        requests.post(f"{RELAY_URL}/warning", json={
            "symbol": symbol, "message": message, "level": level,
        }, headers=_headers(), timeout=5)
    except Exception as e:
        logger.debug(f"Relay push_warning failed: {e}")


def push_learning(insight: str, category: str = "general", impact: str = "medium"):
    if not RELAY_URL:
        return
    try:
        requests.post(f"{RELAY_URL}/learning", json={
            "insight": insight, "category": category, "impact": impact,
        }, headers=_headers(), timeout=5)
    except Exception as e:
        logger.debug(f"Relay push_learning failed: {e}")


def pull_peer_signals(max_age_seconds: int = 300) -> list:
    """Pull signals from the other agent. Cached for 60s."""
    global _last_pull, _peer_signals
    if not RELAY_URL:
        return []
    if time.time() - _last_pull < 60:
        return _peer_signals
    try:
        r = requests.get(f"{RELAY_URL}/signals?other_only=true&limit=20",
                         headers=_headers(), timeout=5)
        data = r.json()
        signals = data.get("signals", [])
        # Filter to recent signals only
        cutoff = time.time() - max_age_seconds
        from datetime import datetime, timezone
        recent = []
        for s in signals:
            try:
                ts = datetime.fromisoformat(s["ts"]).timestamp()
                if ts > cutoff:
                    recent.append(s)
            except:
                pass
        _peer_signals = recent
        _last_pull = time.time()
        return recent
    except Exception as e:
        logger.debug(f"Relay pull_peer_signals failed: {e}")
        return []


def peer_signal_boost(symbol: str) -> int:
    """
    Return score boost (0-10) if the other agent is also watching this token.
    Higher boost if they have a high score on it.
    """
    signals = pull_peer_signals()
    for s in signals:
        if s.get("symbol", "").upper() == symbol.upper():
            peer_score = s.get("score", 0)
            if peer_score >= 80:
                return 10
            elif peer_score >= 65:
                return 7
            elif peer_score >= 50:
                return 4
            else:
                return 2
    return 0


def get_peer_warnings(symbol: str = None) -> list:
    """Get active warnings from the other agent."""
    if not RELAY_URL:
        return []
    try:
        r = requests.get(f"{RELAY_URL}/warnings", headers=_headers(), timeout=5)
        warnings = r.json().get("warnings", [])
        if symbol:
            warnings = [w for w in warnings if w.get("symbol","").upper() == symbol.upper()
                        and w.get("agent") != AGENT]
        return warnings
    except:
        return []


def status() -> dict:
    if not RELAY_URL:
        return {"online": False, "reason": "no relay URL"}
    try:
        r = requests.get(f"{RELAY_URL}/status", timeout=5)
        return r.json()
    except Exception as e:
        return {"online": False, "reason": str(e)}
