"""
Lightweight read-only API for external dashboards.
Serves bot state as JSON on port 5001.
No auth needed — keep firewall restricted or use Cloudflare tunnel.
"""
from flask import Flask, jsonify, request
import json, os, time, subprocess

app = Flask(__name__)
STATE_DIR = os.path.join(os.path.dirname(__file__), "state")


def read_json(path):
    """Safely read a JSON file, return empty dict on failure."""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


@app.route("/api/status")
def status():
    """Bot health + basic stats."""
    perf = read_json(os.path.join(STATE_DIR, "performance.json"))
    regime = read_json(os.path.join(STATE_DIR, "regime.json"))
    
    # Check if bot process is running
    try:
        result = subprocess.run(
            ["pgrep", "-f", "python3 bot.py"],
            capture_output=True, text=True, timeout=5
        )
        is_running = bool(result.stdout.strip())
    except Exception:
        is_running = False
    
    # Get wallet balance from reconcile state
    reconcile = read_json(os.path.join(STATE_DIR, "reconcile_state.json"))
    xrp_balance = reconcile.get("xrp_balance", 0)
    
    return jsonify({
        "online": is_running,
        "last_updated": time.time(),
        "xrp_balance": xrp_balance,
        "performance": {
            "win_rate": perf.get("win_rate", 0),
            "total_pnl_xrp": perf.get("total_pnl_xrp", 0),
            "total_trades": perf.get("total_trades", 0),
            "consecutive_losses": perf.get("consecutive_losses", 0),
            "open_positions": perf.get("open_positions", 0),
        },
        "regime": regime.get("regime", "unknown"),
        "is_paused": os.path.exists(os.path.join(STATE_DIR, "PAUSED")),
        "is_stopped": os.path.exists(os.path.join(STATE_DIR, "EMERGENCY_STOP")),
    })


@app.route("/api/trades")
def trades():
    """Last 20 trades from execution log."""
    exec_log = read_json(os.path.join(STATE_DIR, "execution_log.json"))
    trade_list = exec_log.get("trades", [])
    recent = trade_list[-20:] if isinstance(trade_list, list) else []
    return jsonify({"trades": recent})


@app.route("/api/candidates")
def candidates():
    """Top scan candidates by momentum."""
    scan = read_json(os.path.join(STATE_DIR, "scan_results.json"))
    fresh = scan.get("fresh_momentum", [])[:10]
    sustained = scan.get("sustained_momentum", [])[:10]
    late = scan.get("late_extension", [])[:5]
    return jsonify({
        "fresh_momentum": fresh,
        "sustained_momentum": sustained,
        "late_extension": late,
        "scan_time": scan.get("scan_time", 0),
    })


@app.route("/api/positions")
def positions():
    """Current open positions."""
    pos_file = os.path.join(STATE_DIR, "positions.json")
    positions = read_json(pos_file)
    return jsonify({"positions": positions})


@app.route("/api/safety")
def safety():
    """Safety controller status."""
    paused = os.path.exists(os.path.join(STATE_DIR, "PAUSED"))
    stopped = os.path.exists(os.path.join(STATE_DIR, "EMERGENCY_STOP"))
    
    pause_reason = ""
    if paused:
        try:
            with open(os.path.join(STATE_DIR, "PAUSED")) as f:
                pause_reason = json.load(f).get("reason", "unknown")
        except Exception:
            pass
    
    return jsonify({
        "is_paused": paused,
        "is_stopped": stopped,
        "pause_reason": pause_reason,
    })


@app.route("/api/realtime")
def realtime():
    """Recent realtime signals (burst, clusters)."""
    # Read last 50 lines of bot log for realtime events
    log_file = os.path.join(os.path.dirname(__file__), "state", "bot_stdout.log")
    signals = []
    try:
        with open(log_file) as f:
            lines = f.readlines()[-50:]
        for line in lines:
            if "BURST" in line or "BUY CLUSTER" in line or "REALTIME" in line:
                signals.append(line.strip())
    except Exception:
        pass
    return jsonify({"signals": signals[-20:]})


@app.route("/health")
def health():
    """Health check — no auth needed."""
    return jsonify({"status": "ok", "timestamp": time.time()})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
