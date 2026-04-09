"""
dashboard_server.py — FastAPI backend for live bot monitoring.
Replaces static Cloudflare Pages dashboard with real-time API.

Run: uvicorn dashboard_server:app --host 0.0.0.0 --port 5000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import threading
import time
import json
import os
from datetime import datetime

app = FastAPI(title="DKTrenchBot Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔥 SHARED STATE — hooked into bot via update functions
STATE = {
    "running": False,
    "balance": 0.0,
    "pnl": 0.0,
    "trades": 0,
    "wins": 0,
    "losses": 0,
    "logs": [],
    "positions": [],
    "started_at": None,
    "uptime_seconds": 0,
}


def log(msg: str):
    """Append a log message (max 200 entries)."""
    ts = datetime.utcnow().strftime("%H:%M:%S")
    entry = f"[{ts}] {msg}"
    print(entry)
    STATE["logs"].append(entry)
    STATE["logs"] = STATE["logs"][-200:]


def update_stats(balance=None, pnl=None, trades=None, win=None, loss=None):
    """Update bot statistics."""
    if balance is not None:
        STATE["balance"] = round(balance, 4)
    if pnl is not None:
        STATE["pnl"] = round(pnl, 4)
    if trades is not None:
        STATE["trades"] = trades
    if win is True:
        STATE["wins"] += 1
    if loss is True:
        STATE["losses"] += 1


def update_position(token: str, entry: float, current: float, size_xrp: float = 0):
    """Add or update an open position."""
    pct = ((current - entry) / entry * 100) if entry > 0 else 0
    # Remove old entry for this token
    STATE["positions"] = [p for p in STATE["positions"] if p["token"] != token]
    STATE["positions"].append({
        "token": token,
        "entry": round(entry, 8),
        "current": round(current, 8),
        "pnl_pct": round(pct, 2),
        "size_xrp": round(size_xrp, 2),
    })


def remove_position(token: str):
    """Remove a closed position."""
    STATE["positions"] = [p for p in STATE["positions"] if p["token"] != token]


def set_running(running: bool):
    """Set bot running state."""
    STATE["running"] = running
    if running and STATE["started_at"] is None:
        STATE["started_at"] = time.time()
    elif not running:
        STATE["started_at"] = None


def reset_stats():
    """Reset all stats for a fresh start."""
    STATE.update({
        "running": False,
        "balance": 0.0,
        "pnl": 0.0,
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "logs": [],
        "positions": [],
        "started_at": None,
        "uptime_seconds": 0,
    })
    log("📊 Stats reset — fresh start")


# ---------- API Endpoints ----------

@app.get("/stats")
def get_stats():
    winrate = (STATE["wins"] / max(STATE["trades"], 1)) * 100
    uptime = 0
    if STATE["started_at"]:
        uptime = int(time.time() - STATE["started_at"])
    
    # Get ML phase
    ml_phase = "logging"
    import os, json
    meta_file = os.path.join(os.path.dirname(__file__), "state", "ml_meta.json")
    state_file = os.path.join(os.path.dirname(__file__), "state", "state.json")
    trades_current = 0
    if os.path.exists(state_file):
        try:
            with open(state_file) as f:
                st = json.load(f)
            trades_current = len(st.get("trade_history", []))
        except: pass
    if os.path.exists(meta_file):
        try:
            with open(meta_file) as f:
                meta = json.load(f)
            ml_phase = meta.get("phase", "logging")
        except: pass
    elif trades_current >= 200:
        ml_phase = "xgboost"
    elif trades_current >= 50:
        ml_phase = "logistic"
    
    return {
        "balance": STATE["balance"],
        "pnl": STATE["pnl"],
        "trades": STATE["trades"],
        "wins": STATE["wins"],
        "losses": STATE["losses"],
        "winRate": round(winrate, 1),
        "running": STATE["running"],
        "uptime": uptime,
        "positions_count": len(STATE["positions"]),
        "ml_phase": ml_phase,
    }


@app.get("/logs")
def get_logs(limit: int = 50):
    return STATE["logs"][-limit:]


@app.get("/positions")
def get_positions():
    return STATE["positions"]


@app.post("/start")
def start_bot():
    set_running(True)
    log("🟢 BOT STARTED")
    return {"status": "started"}


@app.post("/stop")
def stop_bot():
    set_running(False)
    log("🔴 BOT STOPPED")
    return {"status": "stopped"}


@app.post("/kill")
def kill_bot():
    set_running(False)
    log("☠️ EMERGENCY STOP ACTIVATED")
    return {"status": "killed"}


@app.post("/reset")
def reset():
    reset_stats()
    return {"status": "reset"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)

# Serve dashboard HTML
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

@app.get("/")
def dashboard():
    return FileResponse(os.path.join(os.path.dirname(__file__), "dashboard", "index.html"))

@app.post("/update_stats")
def api_update_stats(data: dict):
    if "balance" in data: STATE["balance"] = round(data["balance"], 4)
    if "pnl" in data: STATE["pnl"] = round(data["pnl"], 4)
    if "trades" in data: STATE["trades"] = data["trades"]
    if "wins" in data: STATE["wins"] = data["wins"]
    if "losses" in data: STATE["losses"] = data["losses"]
    return {"status": "ok"}

@app.post("/update_position")
def api_update_position(data: dict):
    update_position(data.get("token",""), data.get("entry",0), data.get("current",0), data.get("size_xrp",0))
    return {"status": "ok"}

@app.post("/remove_position")
def api_remove_position(data: dict):
    remove_position(data.get("token",""))
    return {"status": "ok"}

@app.get("/shadow_trades")
def get_shadow_trades():
    """Return shadow ML trade data."""
    import os, json
    shadow_file = os.path.join(os.path.dirname(__file__), "state", "shadow_state.json")
    if not os.path.exists(shadow_file):
        return {"total": 0, "trades": [], "win_rate": 0, "total_pnl": 0, "open": 0}
    try:
        with open(shadow_file) as f:
            data = json.load(f)
        trades = data.get("trades", [])
        closed = [t for t in trades if t.get("status") == "CLOSED"]
        open_pos = [t for t in trades if t.get("status") == "OPEN"]
        wins = [t for t in closed if (t.get("pnl") or 0) > 0]
        total_pnl = sum(t.get("pnl", 0) for t in closed)
        win_rate = (len(wins) / max(len(closed), 1)) * 100
        return {
            "total": len(trades),
            "trades": trades[-20:],  # Last 20
            "win_rate": round(win_rate, 1),
            "total_pnl": round(total_pnl, 4),
            "open": len(open_pos),
        }
    except Exception:
        return {"total": 0, "trades": [], "win_rate": 0, "total_pnl": 0, "open": 0}

@app.get("/ml_status")
def get_ml_status():
    """Return ML model status."""
    import os, json
    state_file = os.path.join(os.path.dirname(__file__), "state", "state.json")
    meta_file = os.path.join(os.path.dirname(__file__), "state", "ml_meta.json")
    features_file = os.path.join(os.path.dirname(__file__), "state", "ml_features.jsonl")
    
    trades_current = 0
    if os.path.exists(state_file):
        try:
            with open(state_file) as f:
                st = json.load(f)
            trades_current = len(st.get("trade_history", []))
        except: pass
    
    phase = "logging"
    trades_needed = 50
    if os.path.exists(meta_file):
        try:
            with open(meta_file) as f:
                meta = json.load(f)
            phase = meta.get("phase", "logging")
            trades_needed = meta.get("trades_needed", 50)
        except: pass
    elif trades_current >= 200:
        phase = "xgboost"
        trades_needed = 200
    elif trades_current >= 50:
        phase = "logistic"
        trades_needed = 50
    
    features_logged = 0
    if os.path.exists(features_file):
        try:
            with open(features_file) as f:
                features_logged = sum(1 for _ in f)
        except: pass
    
    return {
        "phase": phase,
        "trades_current": trades_current,
        "trades_needed": trades_needed,
        "features_logged": features_logged,
    }


# ── Compatibility endpoints for external dashboard ─────────────────────────

@app.get("/api/status")
def api_status():
    """Bot health + basic stats (compatible with external dashboard)."""
    import os, subprocess
    state_file = os.path.join(os.path.dirname(__file__), "state", "state.json")
    regime_file = os.path.join(os.path.dirname(__file__), "state", "regime.json")
    
    perf = STATE.copy()
    win_rate = perf["wins"] / max(perf["trades"], 1)
    
    # Check if bot is running
    try:
        result = subprocess.run(
            ["pgrep", "-f", "python3 bot.py"],
            capture_output=True, text=True, timeout=5
        )
        is_running = bool(result.stdout.strip())
    except Exception:
        is_running = False
    
    regime = "unknown"
    if os.path.exists(regime_file):
        try:
            with open(regime_file) as f:
                regime = json.load(f).get("regime", "unknown")
        except Exception:
            pass
    
    paused = os.path.exists(os.path.join(os.path.dirname(__file__), "state", "PAUSED"))
    stopped = os.path.exists(os.path.join(os.path.dirname(__file__), "state", "EMERGENCY_STOP"))
    
    return {
        "online": is_running,
        "last_updated": time.time(),
        "xrp_balance": perf["balance"],
        "performance": {
            "win_rate": win_rate,
            "total_pnl_xrp": perf["pnl"],
            "total_trades": perf["trades"],
            "consecutive_losses": 0,  # Would need to pull from state.json
            "open_positions": len(perf["positions"]),
        },
        "regime": regime,
        "is_paused": paused,
        "is_stopped": stopped,
    }


@app.get("/api/trades")
def api_trades():
    """Last 20 trades."""
    import os
    exec_log_file = os.path.join(os.path.dirname(__file__), "state", "execution_log.json")
    try:
        with open(exec_log_file) as f:
            exec_log = json.load(f)
        trade_list = exec_log.get("trades", [])
        recent = trade_list[-20:] if isinstance(trade_list, list) else []
        return {"trades": recent}
    except Exception:
        return {"trades": []}


@app.get("/api/candidates")
def api_candidates():
    """Top scan candidates."""
    import os
    scan_file = os.path.join(os.path.dirname(__file__), "state", "scan_results.json")
    try:
        with open(scan_file) as f:
            scan = json.load(f)
        return {
            "fresh_momentum": scan.get("fresh_momentum", [])[:10],
            "sustained_momentum": scan.get("sustained_momentum", [])[:10],
            "late_extension": scan.get("late_extension", [])[:5],
            "scan_time": scan.get("scan_time", 0),
        }
    except Exception:
        return {"fresh_momentum": [], "sustained_momentum": [], "late_extension": []}


@app.get("/api/safety")
def api_safety():
    """Safety controller status."""
    import os
    state_dir = os.path.join(os.path.dirname(__file__), "state")
    paused = os.path.exists(os.path.join(state_dir, "PAUSED"))
    stopped = os.path.exists(os.path.join(state_dir, "EMERGENCY_STOP"))
    
    pause_reason = ""
    if paused:
        try:
            with open(os.path.join(state_dir, "PAUSED")) as f:
                pause_reason = json.load(f).get("reason", "unknown")
        except Exception:
            pass
    
    return {
        "is_paused": paused,
        "is_stopped": stopped,
        "pause_reason": pause_reason,
    }


@app.get("/api/realtime")
def api_realtime():
    """Recent realtime signals."""
    import os
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
    return {"signals": signals[-20:]}


@app.get("/api/ecosystem")
def api_ecosystem():
    """Machine-readable project map for agent discovery."""
    return {
        "name": "DKTrenchBot v2",
        "version": "2.0",
        "description": "Autonomous XRPL memecoin trading agent",
        "type": "trading_bot",
        "networks": {
            "xrpl_mainnet": {
                "chainId": 0,
                "rpc": "https://rpc.xrplclaw.com",
                "explorer": "https://xrpscan.com"
            }
        },
        "bot_wallet": "rKQACag8Td9TrMxBwYJPGRMDV8cxGfKsmF",
        "api": {
            "rest": "https://mom-viii-sunshine-requiring.trycloudflare.com/api",
            "endpoints": ["/status", "/trades", "/candidates", "/safety", "/realtime", "/health"]
        },
        "docs": {
            "llms_txt": "https://github.com/domx1816-dev/dktrenchbot-v2/blob/master/llms.txt",
            "skill_md": "https://github.com/domx1816-dev/dktrenchbot-v2/blob/master/SKILL.md",
            "master_build": "https://github.com/domx1816-dev/dktrenchbot-v2/blob/master/MASTER_BUILD.md"
        },
        "github": "https://github.com/domx1816-dev/dktrenchbot-v2",
        "strategy": {
            "win_rate_target": 0.485,
            "backtest_pnl_xrp": 2892,
            "backtest_trades": 1008,
            "profit_factor": 6.39
        }
    }
