"""
wallet_cluster.py — Wallet Clustering on Realtime Stream (Audit #2)

Goal: Alert when 2+ known smart wallets enter the same token on the live stream.

Algorithm:
1. Load known_wallets = list(config.TRACKED_WALLETS) + discovered_wallets from state/discovered_wallets.json
2. Subscribe to XRPL websocket stream: wss://rpc.xrplclaw.com/ (CLIO supports account subscriptions)
3. For each known wallet, watch for incoming Payments (TrustSet doesn't help — watch Payments to token issuers)
4. Maintain in-memory dict: token_wallet_map[token] = set of wallets seen in last 10 min
5. If token_wallet_map[token] has >= 2 distinct known wallets entering within 10 min → CLUSTER_ALERT
6. Emit cluster_alert to bot_state["signals"]["wallet_cluster"] and log it prominently
7. The scoring module (scoring.py) should read this signal and boost the token's score significantly (+30 points)
8. Clean up old entries (10 min TTL on each wallet entry per token)
9. Graceful reconnect on disconnect

Note on XRPL websocket: CLIO supports `subscribe` with `accounts` field.
Send: {"command":"subscribe","accounts":[wallet1, wallet2, ...]}
"""

import json
import os
import time
import logging
import threading
import websocket
from typing import Dict, List, Set, Optional, Callable
from collections import defaultdict

logger = logging.getLogger("wallet_cluster")

STATE_DIR = os.path.join(os.path.dirname(__file__), "state")
SIGNALS_FILE = os.path.join(STATE_DIR, "cluster_signals.json")
WS_URL = "wss://rpc.xrplclaw.com/"

# Time-to-live for wallet entries per token (seconds)
ENTRY_TTL_SEC = 600  # 10 minutes

# Minimum wallets to trigger cluster alert
CLUSTER_THRESHOLD = 2

# Reconnect delay (seconds)
RECONNECT_DELAY = 5


class WalletClusterMonitor:
    """Monitors known wallets for coordinated token entries."""

    def __init__(self):
        self._ws: Optional[websocket.WebSocketApp] = None
        self._running = False
        self._token_wallet_map: Dict[str, Dict[str, float]] = {}  # token -> {wallet: ts}
        self._cluster_alerts: List[Dict] = []
        self._known_wallets: Set[str] = set()
        self._lock = threading.Lock()
        self._bot_state_ref: Optional[dict] = None  # Reference to bot_state for signal injection
        self._on_alert_callback: Optional[Callable] = None

    def load_known_wallets(self) -> Set[str]:
        """Load tracked wallets from config and discovered_wallets.json."""
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

        self._known_wallets = wallets
        return wallets

    def _cleanup_expired(self):
        """Remove expired wallet entries (older than ENTRY_TTL_SEC)."""
        now = time.time()
        with self._lock:
            for token in list(self._token_wallet_map.keys()):
                self._token_wallet_map[token] = {
                    w: ts for w, ts in self._token_wallet_map[token].items()
                    if now - ts < ENTRY_TTL_SEC
                }
                # Remove empty tokens
                if not self._token_wallet_map[token]:
                    del self._token_wallet_map[token]

    def _record_wallet_entry(self, wallet: str, token_key: str):
        """Record a wallet entering a token."""
        now = time.time()
        with self._lock:
            if token_key not in self._token_wallet_map:
                self._token_wallet_map[token_key] = {}
            self._token_wallet_map[token_key][wallet] = now

        # Check for cluster
        self._check_cluster(token_key)

    def _check_cluster(self, token_key: str):
        """Check if token has enough wallets to trigger cluster alert."""
        now = time.time()
        with self._lock:
            wallets_in_window = self._token_wallet_map.get(token_key, {})
            active_wallets = {
                w for w, ts in wallets_in_window.items()
                if now - ts < ENTRY_TTL_SEC
            }

        if len(active_wallets) >= CLUSTER_THRESHOLD:
            # Parse token key: "SYMBOL:issuer" or "currency:issuer"
            parts = token_key.split(":")
            symbol = parts[0] if parts else token_key

            alert = {
                "token": token_key,
                "symbol": symbol,
                "wallets": list(active_wallets),
                "count": len(active_wallets),
                "ts": now,
                "signal_type": "wallet_cluster",
            }

            # Dedup: don't re-alert same token within 5 minutes
            recent_same = [
                a for a in self._cluster_alerts
                if a["token"] == token_key and now - a["ts"] < 300
            ]
            if not recent_same:
                self._cluster_alerts.append(alert)
                # Keep last 50 alerts
                if len(self._cluster_alerts) > 50:
                    self._cluster_alerts = self._cluster_alerts[-50:]

                logger.warning(
                    f"🚨 CLUSTER ALERT: {symbol} — {len(active_wallets)} smart wallets entered! "
                    f"Wallets: {[w[:10]+'...' for w in active_wallets]}"
                )

                # Save to signals file
                self._save_signals()

                # Inject into bot_state if reference available
                if self._bot_state_ref is not None:
                    if "signals" not in self._bot_state_ref:
                        self._bot_state_ref["signals"] = {}
                    self._bot_state_ref["signals"]["wallet_cluster"] = alert

                # Call callback if registered
                if self._on_alert_callback:
                    try:
                        self._on_alert_callback(alert)
                    except Exception as e:
                        logger.error(f"Cluster alert callback error: {e}")

    def _save_signals(self):
        """Save cluster signals to file."""
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = SIGNALS_FILE + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump({
                    "alerts": self._cluster_alerts[-20:],  # Last 20
                    "last_updated": time.time(),
                }, f, indent=2)
            os.replace(tmp, SIGNALS_FILE)
        except Exception as e:
            logger.error(f"Error saving cluster signals: {e}")

    def _handle_message(self, ws, message: str):
        """Process incoming websocket messages."""
        try:
            data = json.loads(message)

            # Transaction notification
            if data.get("type") == "transaction":
                tx_data = data.get("transaction", {})
                meta = data.get("meta", {})
                tx_type = tx_data.get("TransactionType", "")
                account = tx_data.get("Account", "")

                # Only process transactions from our known wallets
                if account not in self._known_wallets:
                    return

                # Detect token purchases via Payment or OfferCreate
                if tx_type == "Payment":
                    amount = tx_data.get("Amount", {})
                    destination = tx_data.get("Destination", "")

                    # If the payment is a token (not XRP), record it
                    if isinstance(amount, dict):
                        currency = amount.get("currency", "")
                        issuer = amount.get("issuer", "")
                        if currency and issuer:
                            token_key = f"{currency}:{issuer}"
                            self._record_wallet_entry(account, token_key)
                            logger.info(
                                f"  📥 {account[:10]}... bought {currency[:8]} via Payment"
                            )

                elif tx_type == "OfferCreate":
                    # Detect buy offers: TakerPays=XRP, TakerGets=token
                    tp = tx_data.get("TakerPays", {})
                    tg = tx_data.get("TakerGets", {})

                    # Buying token: paying XRP (string), getting token (dict)
                    if isinstance(tp, str) and isinstance(tg, dict):
                        currency = tg.get("currency", "")
                        issuer = tg.get("issuer", "")
                        if currency and issuer:
                            token_key = f"{currency}:{issuer}"
                            self._record_wallet_entry(account, token_key)
                            logger.info(
                                f"  📥 {account[:10]}... bought {currency[:8]} via OfferCreate"
                            )

            elif data.get("type") == "ledgerClosed":
                # Periodic cleanup on ledger close
                self._cleanup_expired()

        except Exception as e:
            logger.debug(f"Message handling error: {e}")

    def _handle_error(self, ws, error):
        logger.error(f"WebSocket error: {error}")

    def _handle_close(self, ws, close_status_code, close_msg):
        logger.info(f"WebSocket closed: {close_status_code} {close_msg}")
        if self._running:
            logger.info(f"Reconnecting in {RECONNECT_DELAY}s...")
            time.sleep(RECONNECT_DELAY)
            self._connect()

    def _handle_open(self, ws):
        logger.info("WebSocket connected — subscribing to accounts...")
        self._subscribe_accounts(ws)

    def _subscribe_accounts(self, ws):
        """Subscribe to account transactions."""
        if not self._known_wallets:
            self.load_known_wallets()

        if not self._known_wallets:
            logger.warning("No known wallets to subscribe to")
            return

        # XRPL has limits on subscription size — batch if needed
        wallet_list = list(self._known_wallets)
        logger.info(f"Subscribing to {len(wallet_list)} wallets...")

        subscribe_msg = {
            "command": "subscribe",
            "accounts": wallet_list,
            "streams": ["ledger"],
        }

        try:
            ws.send(json.dumps(subscribe_msg))
            logger.info("Subscription sent")
        except Exception as e:
            logger.error(f"Subscription error: {e}")

    def _connect(self):
        """Establish WebSocket connection."""
        self._ws = websocket.WebSocketApp(
            WS_URL,
            on_open=self._handle_open,
            on_message=self._handle_message,
            on_error=self._handle_error,
            on_close=self._handle_close,
        )

        try:
            self._ws.run_forever()
        except Exception as e:
            logger.error(f"WebSocket run error: {e}")

    def start(self, bot_state: Optional[dict] = None, on_alert: Optional[Callable] = None):
        """Start the cluster monitor in a background thread."""
        if self._running:
            logger.warning("Cluster monitor already running")
            return

        self._running = True
        self._bot_state_ref = bot_state
        self._on_alert_callback = on_alert
        self.load_known_wallets()

        logger.info(f"Starting wallet cluster monitor ({len(self._known_wallets)} wallets)")

        self._thread = threading.Thread(target=self._connect, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the cluster monitor."""
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        logger.info("Wallet cluster monitor stopped")

    def get_active_clusters(self) -> List[Dict]:
        """Get current active cluster signals."""
        now = time.time()
        clusters = []
        with self._lock:
            for token, wallets_ts in self._token_wallet_map.items():
                active = {w for w, ts in wallets_ts.items() if now - ts < ENTRY_TTL_SEC}
                if len(active) >= CLUSTER_THRESHOLD:
                    clusters.append({
                        "token": token,
                        "wallets": list(active),
                        "count": len(active),
                    })
        return clusters

    def get_cluster_score_boost(self, symbol: str, issuer: str) -> int:
        """
        Get score boost for a token based on cluster activity.
        Returns +30 if cluster detected, 0 otherwise.
        Called by scoring.py.
        """
        token_key = f"{symbol}:{issuer}"
        now = time.time()

        with self._lock:
            wallets_ts = self._token_wallet_map.get(token_key, {})
            active_count = sum(1 for ts in wallets_ts.values() if now - ts < ENTRY_TTL_SEC)

        if active_count >= CLUSTER_THRESHOLD:
            return 30  # Significant boost
        return 0


# Global instance for integration with bot
_monitor: Optional[WalletClusterMonitor] = None


def start_cluster_monitor(bot_state: Optional[dict] = None, on_alert: Optional[Callable] = None):
    """Start the global cluster monitor."""
    global _monitor
    if _monitor is None:
        _monitor = WalletClusterMonitor()
    _monitor.start(bot_state=bot_state, on_alert=on_alert)


def stop_cluster_monitor():
    """Stop the global cluster monitor."""
    global _monitor
    if _monitor:
        _monitor.stop()
        _monitor = None


def get_cluster_boost(symbol: str, issuer: str) -> int:
    """Get cluster score boost for a token (called by scoring.py)."""
    global _monitor
    if _monitor:
        return _monitor.get_cluster_score_boost(symbol, issuer)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("Wallet Cluster Monitor — test mode")
    print("This module runs as a background thread in the main bot.")
    monitor = WalletClusterMonitor()
    wallets = monitor.load_known_wallets()
    print(f"Known wallets: {len(wallets)}")
    for w in list(wallets)[:5]:
        print(f"  - {w}")
