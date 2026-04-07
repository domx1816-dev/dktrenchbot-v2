"""
safety_controller.py — Emergency stop and pause system for DKTrenchBot v2.

File-based control: creating a file activates the state, deleting it clears it.
- state/PAUSED          → bot pauses new entries, manages exits only
- state/EMERGENCY_STOP  → bot halts all activity immediately

CLI:
    python3 safety_controller.py status
    python3 safety_controller.py pause
    python3 safety_controller.py resume
    python3 safety_controller.py emergency-stop
    python3 safety_controller.py reset
"""

import argparse
import json
import os
import sys
import time
from typing import Dict

from config import STATE_DIR

PAUSE_FILE = os.path.join(STATE_DIR, "PAUSED")
KILL_FILE = os.path.join(STATE_DIR, "EMERGENCY_STOP")
ALERT_LOG_FILE = os.path.join(STATE_DIR, "safety_alerts.json")

# Drawdown thresholds
MIN_BALANCE_XRP = 20.0       # emergency stop if balance falls below this
CONSEC_LOSS_PAUSE = 3        # pause after N consecutive losses all > this XRP
CONSEC_LOSS_THRESHOLD = 5.0  # each loss must exceed this XRP to count
SINGLE_LOSS_PAUSE = 10.0     # pause + alert if single loss exceeds this XRP


def _write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def _log_alert(event: str, reason: str) -> None:
    alerts = []
    if os.path.exists(ALERT_LOG_FILE):
        try:
            with open(ALERT_LOG_FILE) as f:
                alerts = json.load(f)
        except Exception:
            pass
    alerts.append({
        "ts": time.time(),
        "ts_human": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "event": event,
        "reason": reason,
    })
    alerts = alerts[-200:]  # keep last 200 alerts
    tmp = ALERT_LOG_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(alerts, f, indent=2)
    os.replace(tmp, ALERT_LOG_FILE)


class SafetyController:
    """
    Emergency stop and pause system.
    File-based: state survives process restarts.
    """

    PAUSE_FILE = PAUSE_FILE
    KILL_FILE = KILL_FILE

    def is_paused(self) -> bool:
        """Returns True if PAUSED file exists."""
        return os.path.exists(PAUSE_FILE)

    def is_emergency_stopped(self) -> bool:
        """Returns True if EMERGENCY_STOP file exists."""
        return os.path.exists(KILL_FILE)

    def pause(self, reason: str = "manual") -> None:
        """Create PAUSED file with reason."""
        content = json.dumps({
            "ts": time.time(),
            "ts_human": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "reason": reason,
        }, indent=2)
        _write_file(PAUSE_FILE, content)
        _log_alert("PAUSED", reason)
        print(f"⏸️  Bot PAUSED: {reason}")

    def resume(self) -> None:
        """Remove PAUSED file."""
        if os.path.exists(PAUSE_FILE):
            os.remove(PAUSE_FILE)
            _log_alert("RESUMED", "manual resume")
            print("▶️  Bot RESUMED — new entries re-enabled")
        else:
            print("ℹ️  Bot was not paused")

    def emergency_stop(self, reason: str = "manual") -> None:
        """Create EMERGENCY_STOP file. Bot will halt on next cycle check."""
        content = json.dumps({
            "ts": time.time(),
            "ts_human": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "reason": reason,
        }, indent=2)
        _write_file(KILL_FILE, content)
        _log_alert("EMERGENCY_STOP", reason)
        print(f"🛑 EMERGENCY STOP activated: {reason}")

    def reset_emergency(self) -> None:
        """Remove EMERGENCY_STOP file (requires explicit operator action)."""
        if os.path.exists(KILL_FILE):
            os.remove(KILL_FILE)
            _log_alert("EMERGENCY_CLEARED", "manual reset")
            print("✅ Emergency stop CLEARED — bot can resume on next restart")
        else:
            print("ℹ️  No emergency stop active")

    def check_drawdown_kill(self, bot_state: Dict) -> bool:
        """
        Check drawdown conditions and auto-trigger pause/stop as needed.

        Auto-triggers:
          - balance < MIN_BALANCE_XRP XRP → emergency stop
          - 3+ consecutive losses > CONSEC_LOSS_THRESHOLD XRP each → pause
          - single loss > SINGLE_LOSS_PAUSE XRP → pause + alert

        Returns True if any action was taken.
        """
        triggered = False
        perf = bot_state.get("performance", {})
        history = bot_state.get("trade_history", [])

        # --- Balance check ---
        balance_xrp = bot_state.get("_cycle_wallet_xrp", 0.0)
        if balance_xrp > 0 and balance_xrp < MIN_BALANCE_XRP:
            if not self.is_emergency_stopped():
                reason = f"balance_critical_{balance_xrp:.1f}XRP_below_{MIN_BALANCE_XRP}XRP"
                self.emergency_stop(reason)
                triggered = True

        # --- Consecutive losses ---
        consec = perf.get("consecutive_losses", 0)
        if consec >= CONSEC_LOSS_PAUSE:
            # Verify each loss was > threshold
            recent_losses = [
                t for t in history[-consec:]
                if float(t.get("pnl_xrp", 0) or 0) < -CONSEC_LOSS_THRESHOLD
            ]
            if len(recent_losses) >= CONSEC_LOSS_PAUSE and not self.is_paused():
                reason = f"{consec}_consecutive_losses_over_{CONSEC_LOSS_THRESHOLD}XRP_each"
                self.pause(reason)
                triggered = True

        # --- Single large loss ---
        if history:
            last_trade = history[-1]
            last_pnl = float(last_trade.get("pnl_xrp", 0) or 0)
            if last_pnl < -SINGLE_LOSS_PAUSE and not self.is_paused():
                reason = f"single_loss_{abs(last_pnl):.2f}XRP_exceeds_{SINGLE_LOSS_PAUSE}XRP_threshold"
                self.pause(reason)
                triggered = True

        return triggered

    def check_cycle(self, bot_state: Dict) -> str:
        """
        Called at the top of every run_cycle().
        Returns: 'ok', 'paused', 'stopped'

        Also auto-checks drawdown conditions.
        """
        # Run drawdown checks first (may activate pause/stop)
        self.check_drawdown_kill(bot_state)

        if self.is_emergency_stopped():
            return "stopped"
        if self.is_paused():
            return "paused"
        return "ok"

    def get_status(self) -> Dict:
        """Return current status dict."""
        paused = self.is_paused()
        stopped = self.is_emergency_stopped()

        pause_reason = ""
        stop_reason = ""

        if paused and os.path.exists(PAUSE_FILE):
            try:
                pause_reason = json.loads(open(PAUSE_FILE).read()).get("reason", "")
            except Exception:
                pause_reason = "unknown"

        if stopped and os.path.exists(KILL_FILE):
            try:
                stop_reason = json.loads(open(KILL_FILE).read()).get("reason", "")
            except Exception:
                stop_reason = "unknown"

        status = "ok"
        if stopped:
            status = "EMERGENCY_STOPPED"
        elif paused:
            status = "PAUSED"

        return {
            "status": status,
            "is_paused": paused,
            "is_emergency_stopped": stopped,
            "pause_reason": pause_reason,
            "stop_reason": stop_reason,
            "pause_file": PAUSE_FILE,
            "kill_file": KILL_FILE,
        }


# Module-level singleton
_controller: SafetyController = SafetyController()


def get_safety_controller() -> SafetyController:
    return _controller


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DKTrenchBot Safety Controller")
    parser.add_argument("action", nargs="?", default="status",
                        choices=["status", "pause", "resume", "emergency-stop", "reset"],
                        help="Action to perform")
    parser.add_argument("--reason", default="manual CLI command",
                        help="Reason for pause/stop")
    args = parser.parse_args()

    ctrl = SafetyController()

    if args.action == "status":
        s = ctrl.get_status()
        print(f"\n=== DKTrenchBot Safety Status ===")
        print(f"  Status:    {s['status']}")
        if s["is_paused"]:
            print(f"  Pause:     {s['pause_reason']}")
        if s["is_emergency_stopped"]:
            print(f"  Stop:      {s['stop_reason']}")
        print(f"  Pause file:  {PAUSE_FILE}  ({'EXISTS' if s['is_paused'] else 'absent'})")
        print(f"  Kill file:   {KILL_FILE}  ({'EXISTS' if s['is_emergency_stopped'] else 'absent'})")

        # Load recent alerts
        if os.path.exists(ALERT_LOG_FILE):
            try:
                alerts = json.load(open(ALERT_LOG_FILE))
                recent = alerts[-5:]
                if recent:
                    print(f"\n  Recent alerts:")
                    for a in recent:
                        print(f"    [{a['ts_human']}] {a['event']}: {a['reason']}")
            except Exception:
                pass
        print()

    elif args.action == "pause":
        ctrl.pause(args.reason)

    elif args.action == "resume":
        ctrl.resume()

    elif args.action == "emergency-stop":
        confirm = input("⚠️  Confirm EMERGENCY STOP? This halts all bot activity. [yes/N]: ")
        if confirm.strip().lower() == "yes":
            ctrl.emergency_stop(args.reason)
        else:
            print("Cancelled.")

    elif args.action == "reset":
        ctrl.reset_emergency()
        ctrl.resume()
        print("✅ All safety states cleared")
