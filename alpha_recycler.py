"""
alpha_recycler.py — Alpha Recycling Tracker (Audit #6)

Goal: When a tracked smart wallet sells a winner, immediately look for their NEXT buy.
This is the best leading indicator.

Algorithm:
1. Maintain state/alpha_recycler.json: {wallet: {"last_sell": {token, time, pnl_pct}, "next_buy": None}}
2. Poll account_tx on known smart wallets every 5 minutes
3. Detect: wallet had a sell transaction (outgoing payment of a token they hold) on a winner
4. Then: watch for their NEXT incoming payment (buy) of ANY token within next 30 minutes
5. If that next buy is a token we don't already hold → add to bot_state["signals"]["alpha_recycler"]
6. Alpha recycler signals get a +25 score boost in scoring.py
7. Log: "🔁 ALPHA RECYCLE: @wallet sold XYZ at +Yx, just bought ABC"
"""

import json
import os
import time
import logging
import requests
from typing import Dict, List, Optional, Set
from collections import defaultdict

logger = logging.getLogger("alpha_recycler")

STATE_DIR = os.path.join(os.path.dirname(__file__), "state")
RECYCLER_FILE = os.path.join(STATE_DIR, "alpha_recycler.json")
SIGNALS_FILE = os.path.join(STATE_DIR, "alpha_recycler_signals.json")
CLIO_URL = "https://rpc.xrplclaw.com"

# Poll interval for checking wallet transactions (seconds)
POLL_INTERVAL_SEC = 300  # 5 minutes

# Window to watch for next buy after a sell (seconds)
BUY_WINDOW_SEC = 1800  # 30 minutes

# Minimum profit multiple to consider a "winner" sell
MIN_WIN_MULTIPLE = 1.5  # 1.5x+


def _rpc(method: str, params: dict, timeout: int = 15) -> Optional[dict]:
    """Send RPC request to CLIO."""
    try:
        resp = requests.post(CLIO_URL, json={"method": method, "params": [params]}, timeout=timeout)
        return resp.json().get("result", {})
    except Exception as e:
        logger.debug(f"RPC error {method}: {e}")
        return None


def _load_recycler_state() -> Dict:
    """Load alpha recycler state."""
    if os.path.exists(RECYCLER_FILE):
        try:
            with open(RECYCLER_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_recycler_state(data: Dict) -> None:
    """Save alpha recycler state."""
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = RECYCLER_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, RECYCLER_FILE)
    except Exception:
        with open(RECYCLER_FILE, "w") as f:
            json.dump(data, f, indent=2)


def _load_discovered_wallets() -> Set[str]:
    """Load tracked and candidate wallets from discovered_wallets.json."""
    wallets = set()

    # From config TRACKED_WALLETS
    try:
        from config import TRACKED_WALLETS
        if isinstance(TRACKED_WALLETS, (list, tuple)):
            wallets.update(TRACKED_WALLETS)
    except (ImportError, AttributeError):
        pass

    # From discovered_wallets.json
    discovered_file = os.path.join(STATE_DIR, "discovered_wallets.json")
    if os.path.exists(discovered_file):
        try:
            with open(discovered_file) as f:
                data = json.load(f)
            wallets.update(data.get("tracked", []))
            wallets.update(data.get("candidates", {}).keys())
        except Exception as e:
            logger.debug(f"Error loading discovered wallets: {e}")

    return wallets


def _get_currency_code(symbol: str) -> str:
    """Convert symbol to XRPL currency code."""
    s = symbol.upper()
    if len(s) <= 3:
        return s.ljust(3)
    if len(s) == 40 and all(c in "0123456789ABCDEF" for c in s):
        return s
    encoded = s.encode("utf-8").hex().upper()
    return encoded.ljust(40, "0")[:40]


def _get_token_symbol(currency: str, issuer: str) -> str:
    """Try to resolve currency code back to symbol."""
    # Check active registry
    registry_file = os.path.join(STATE_DIR, "active_registry.json")
    if os.path.exists(registry_file):
        try:
            with open(registry_file) as f:
                registry = json.load(f)
            for entry in registry.values() if isinstance(registry, dict) else registry:
                if isinstance(entry, dict):
                    if entry.get("currency") == currency and entry.get("issuer") == issuer:
                        return entry.get("symbol", currency[:8])
        except Exception:
            pass
    return currency[:8]  # Fallback to first 8 chars


def _check_wallet_transactions(wallet: str, lookback_ledgers: int = 50) -> List[Dict]:
    """
    Check recent transactions for a wallet.
    Returns list of {type, token, currency, issuer, amount, ts, direction} events.
    direction: 'in' (buy/receive) or 'out' (sell/send)
    """
    events = []

    result = _rpc("account_tx", {
        "account": wallet,
        "limit": lookback_ledgers,
        "ledger_index_min": -1,
        "ledger_index_max": -1,
    })

    if not result or result.get("status") != "success":
        return events

    for tx_wrapper in result.get("transactions", []):
        tx = tx_wrapper.get("tx", {})
        meta = tx_wrapper.get("meta", {})
        tx_type = tx.get("TransactionType", "")
        tx_date = tx.get("date", 0)
        tx_time_unix = tx_date + 946684800  # Convert Ripple epoch to Unix

        account = tx.get("Account", "")
        destination = tx.get("Destination", "")

        if tx_type == "OfferCreate":
            tp = tx.get("TakerPays", {})
            tg = tx.get("TakerGets", {})

            # Selling token: TakerPays=token, TakerGets=XRP
            if isinstance(tp, dict) and isinstance(tg, str):
                currency = tp.get("currency", "")
                issuer = tp.get("issuer", "")
                if currency and issuer:
                    events.append({
                        "type": "sell",
                        "direction": "out",
                        "currency": currency,
                        "issuer": issuer,
                        "ts": tx_time_unix,
                        "wallet": account,
                    })

            # Buying token: TakerPays=XRP, TakerGets=token
            elif isinstance(tp, str) and isinstance(tg, dict):
                currency = tg.get("currency", "")
                issuer = tg.get("issuer", "")
                if currency and issuer:
                    events.append({
                        "type": "buy",
                        "direction": "in",
                        "currency": currency,
                        "issuer": issuer,
                        "ts": tx_time_unix,
                        "wallet": account,
                    })

        elif tx_type == "Payment":
            amount = tx.get("Amount", {})
            if isinstance(amount, dict):
                currency = amount.get("currency", "")
                issuer = amount.get("issuer", "")
                if currency and issuer:
                    # Determine direction: did this wallet send or receive?
                    if account == wallet:
                        direction = "out"  # Wallet sent tokens (sell)
                    elif destination == wallet:
                        direction = "in"   # Wallet received tokens (buy)
                    else:
                        continue

                    events.append({
                        "type": "payment",
                        "direction": direction,
                        "currency": currency,
                        "issuer": issuer,
                        "ts": tx_time_unix,
                        "wallet": wallet,
                    })

    return events


def _is_token_held_by_bot(token_key: str, bot_state: Optional[Dict] = None) -> bool:
    """Check if the bot already holds this token."""
    if bot_state is None:
        return False

    positions = bot_state.get("positions", {})
    return token_key in positions


def scan_alpha_recycling(bot_state: Optional[Dict] = None) -> List[Dict]:
    """
    Main scan function. Checks all tracked wallets for sell→buy patterns.
    Returns list of new alpha recycle signals.
    """
    logger.info("🔄 Scanning alpha recycling...")

    recycler_state = _load_recycler_state()
    known_wallets = _load_discovered_wallets()
    now = time.time()
    new_signals = []

    for wallet in known_wallets:
        wallet_data = recycler_state.get(wallet, {})
        last_sell = wallet_data.get("last_sell")
        next_buy = wallet_data.get("next_buy")

        # Check recent transactions
        events = _check_wallet_transactions(wallet, lookback_ledgers=30)

        # Look for new sells (winner exits)
        for event in events:
            if event["direction"] == "out" and event["type"] in ("sell", "payment"):
                currency = event["currency"]
                issuer = event["issuer"]
                token_key = f"{currency}:{issuer}"
                symbol = _get_token_symbol(currency, issuer)

                # Record the sell if not already tracked
                if not last_sell or event["ts"] > last_sell.get("time", 0):
                    # We can't easily determine PnL without full position history
                    # Mark as potential winner — will be confirmed if they rebuy
                    recycler_state[wallet] = {
                        "last_sell": {
                            "token": symbol,
                            "currency": currency,
                            "issuer": issuer,
                            "token_key": token_key,
                            "time": event["ts"],
                            "pnl_pct": None,  # Unknown without entry price
                        },
                        "next_buy": None,
                        "updated": now,
                    }
                    logger.info(
                        f"  📤 {wallet[:10]}... sold {symbol} — watching for next buy"
                    )

        # Check if wallet has a pending "watching for buy" state
        if last_sell and not next_buy:
            sell_time = last_sell.get("time", 0)
            elapsed = now - sell_time

            # Still within the buy window?
            if elapsed < BUY_WINDOW_SEC:
                # Look for a new buy in recent events
                for event in events:
                    if event["direction"] == "in" and event["type"] in ("buy", "payment"):
                        if event["ts"] > sell_time:  # Buy happened after the sell
                            buy_currency = event["currency"]
                            buy_issuer = event["issuer"]
                            buy_token_key = f"{buy_currency}:{buy_issuer}"
                            buy_symbol = _get_token_symbol(buy_currency, buy_issuer)

                            # Check if bot already holds this token
                            if not _is_token_held_by_bot(buy_token_key, bot_state):
                                signal = {
                                    "wallet": wallet,
                                    "sold_token": last_sell.get("token", ""),
                                    "bought_token": buy_symbol,
                                    "bought_currency": buy_currency,
                                    "bought_issuer": buy_issuer,
                                    "bought_token_key": buy_token_key,
                                    "sell_time": sell_time,
                                    "buy_time": event["ts"],
                                    "delay_sec": event["ts"] - sell_time,
                                    "context": f"recycled_from_{last_sell.get('token', 'unknown')}",
                                    "ts": now,
                                    "signal_type": "alpha_recycler",
                                }

                                new_signals.append(signal)

                                # Update state
                                recycler_state[wallet]["next_buy"] = {
                                    "token": buy_symbol,
                                    "currency": buy_currency,
                                    "issuer": buy_issuer,
                                    "token_key": buy_token_key,
                                    "time": event["ts"],
                                }

                                logger.warning(
                                    f"🔁 ALPHA RECYCLE: {wallet[:10]}... sold "
                                    f"{last_sell.get('token', '?')} → just bought {buy_symbol}"
                                )

                                # Save signal to file
                                _save_signal_to_file(signal)

                                # Inject into bot_state if available
                                if bot_state is not None:
                                    if "signals" not in bot_state:
                                        bot_state["signals"] = {}
                                    bot_state["signals"]["alpha_recycler"] = signal

                            break  # Only track first buy after sell
            else:
                # Window expired — clear the watch
                if wallet in recycler_state:
                    recycler_state[wallet]["next_buy"] = None
                    recycler_state[wallet]["last_sell"] = None
                    logger.debug(f"  ⏰ Watch expired for {wallet[:10]}...")

    _save_recycler_state(recycler_state)

    if new_signals:
        logger.info(f"✅ Found {len(new_signals)} alpha recycle signal(s)")
    else:
        logger.debug("No new alpha recycle signals")

    return new_signals


def _save_signal_to_file(signal: Dict):
    """Append signal to alpha_recycler_signals.json."""
    os.makedirs(STATE_DIR, exist_ok=True)
    try:
        if os.path.exists(SIGNALS_FILE):
            with open(SIGNALS_FILE) as f:
                data = json.load(f)
        else:
            data = {"signals": [], "last_updated": 0}

        data["signals"].append(signal)
        # Keep last 50 signals
        data["signals"] = data["signals"][-50:]
        data["last_updated"] = time.time()

        tmp = SIGNALS_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, SIGNALS_FILE)
    except Exception as e:
        logger.error(f"Error saving alpha recycler signal: {e}")


def get_alpha_recycler_boost(symbol: str, issuer: str) -> int:
    """
    Get score boost for a token based on alpha recycler activity.
    Returns +25 if an alpha recycler signal matches this token, 0 otherwise.
    Called by scoring.py.
    """
    signals_file = SIGNALS_FILE
    if not os.path.exists(signals_file):
        return 0

    try:
        with open(signals_file) as f:
            data = json.load(f)

        now = time.time()
        token_key = f"{symbol}:{issuer}"

        # Check recent signals (within 30 min)
        for sig in data.get("signals", []):
            if sig.get("bought_token_key") == token_key:
                age = now - sig.get("ts", 0)
                if age < 1800:  # 30 min TTL
                    return 25
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("Alpha Recycler — test mode")
    signals = scan_alpha_recycling()
    print(f"New signals: {len(signals)}")
    for sig in signals:
        print(f"  🔁 {sig['wallet'][:10]}... : {sig['sold_token']} → {sig['bought_token']}")
