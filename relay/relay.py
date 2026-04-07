#!/usr/bin/env python3
"""
Agent-to-Agent Learning Relay
------------------------------
Shared API for DKTrenchBot and Predator to exchange signals,
trade outcomes, warnings and learnings.

Endpoints:
  POST /signal          — post a live signal
  POST /trade           — post a completed trade result
  POST /warning         — post a market warning
  POST /learning        — post a strategy insight
  GET  /signals         — get latest signals from all agents
  GET  /trades          — get recent trade history from all agents
  GET  /warnings        — get active warnings
  GET  /learnings       — get accumulated learnings
  GET  /status          — relay health + connected agents
"""

import json
import os
import time
import hashlib
from datetime import datetime, timezone
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)

# API keys: agent_name -> key
API_KEYS = {
    "DKTrench":  "dk-7x9m2p-trench",
    "Predator":  "pred-4k8n1q-hunter",
}

MAX_SIGNALS   = 100
MAX_TRADES    = 200
MAX_WARNINGS  = 50
MAX_LEARNINGS = 100


def _load(filename):
    path = os.path.join(DATA_DIR, filename)
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return []


def _save(filename, data):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _auth(req):
    """Authenticate request. Returns agent_name or None."""
    key = req.headers.get("X-API-Key") or req.json.get("api_key", "") if req.is_json else ""
    for agent, k in API_KEYS.items():
        if k == key:
            return agent
    return None


def _ts():
    return datetime.now(timezone.utc).isoformat()


# ─── POST /signal ──────────────────────────────────────────────────────────────
@app.route("/signal", methods=["POST"])
def post_signal():
    agent = _auth(request)
    if not agent:
        return jsonify({"error": "unauthorized"}), 401

    data = request.json or {}
    signals = _load("signals.json")

    entry = {
        "ts":       _ts(),
        "agent":    agent,
        "symbol":   data.get("symbol", ""),
        "score":    data.get("score", 0),
        "chart":    data.get("chart", ""),
        "tvl":      data.get("tvl", 0),
        "pct":      data.get("pct", 0),
        "regime":   data.get("regime", "neutral"),
        "note":     data.get("note", ""),
    }
    signals.insert(0, entry)
    signals = signals[:MAX_SIGNALS]
    _save("signals.json", signals)
    return jsonify({"ok": True, "entry": entry})


# ─── POST /trade ───────────────────────────────────────────────────────────────
@app.route("/trade", methods=["POST"])
def post_trade():
    agent = _auth(request)
    if not agent:
        return jsonify({"error": "unauthorized"}), 401

    data = request.json or {}
    trades = _load("trades.json")

    entry = {
        "ts":         _ts(),
        "agent":      agent,
        "symbol":     data.get("symbol", ""),
        "action":     data.get("action", ""),      # entry / exit / partial
        "xrp":        data.get("xrp", 0),
        "pnl_pct":    data.get("pnl_pct", None),
        "exit_reason":data.get("exit_reason", ""),
        "score":      data.get("score", 0),
        "chart":      data.get("chart", ""),
        "note":       data.get("note", ""),
    }
    trades.insert(0, entry)
    trades = trades[:MAX_TRADES]
    _save("trades.json", trades)
    return jsonify({"ok": True, "entry": entry})


# ─── POST /warning ─────────────────────────────────────────────────────────────
@app.route("/warning", methods=["POST"])
def post_warning():
    agent = _auth(request)
    if not agent:
        return jsonify({"error": "unauthorized"}), 401

    data = request.json or {}
    warnings = _load("warnings.json")

    entry = {
        "ts":      _ts(),
        "agent":   agent,
        "symbol":  data.get("symbol", ""),
        "message": data.get("message", ""),
        "level":   data.get("level", "info"),   # info / caution / danger
    }
    warnings.insert(0, entry)
    warnings = warnings[:MAX_WARNINGS]
    _save("warnings.json", warnings)
    return jsonify({"ok": True, "entry": entry})


# ─── POST /learning ────────────────────────────────────────────────────────────
@app.route("/learning", methods=["POST"])
def post_learning():
    agent = _auth(request)
    if not agent:
        return jsonify({"error": "unauthorized"}), 401

    data = request.json or {}
    learnings = _load("learnings.json")

    entry = {
        "ts":       _ts(),
        "agent":    agent,
        "insight":  data.get("insight", ""),
        "category": data.get("category", "general"),  # strategy/token/timing/risk
        "impact":   data.get("impact", "medium"),      # low/medium/high
    }
    learnings.insert(0, entry)
    learnings = learnings[:MAX_LEARNINGS]
    _save("learnings.json", learnings)
    return jsonify({"ok": True, "entry": entry})


# ─── GET /signals ──────────────────────────────────────────────────────────────
@app.route("/signals", methods=["GET"])
def get_signals():
    agent = _auth(request)
    if not agent:
        return jsonify({"error": "unauthorized"}), 401

    signals = _load("signals.json")
    limit = int(request.args.get("limit", 20))
    other_only = request.args.get("other_only", "false").lower() == "true"

    if other_only:
        signals = [s for s in signals if s["agent"] != agent]

    return jsonify({
        "agent":   agent,
        "count":   len(signals[:limit]),
        "signals": signals[:limit],
    })


# ─── GET /trades ───────────────────────────────────────────────────────────────
@app.route("/trades", methods=["GET"])
def get_trades():
    agent = _auth(request)
    if not agent:
        return jsonify({"error": "unauthorized"}), 401

    trades = _load("trades.json")
    limit = int(request.args.get("limit", 30))
    other_only = request.args.get("other_only", "false").lower() == "true"

    if other_only:
        trades = [t for t in trades if t["agent"] != agent]

    return jsonify({
        "agent":  agent,
        "count":  len(trades[:limit]),
        "trades": trades[:limit],
    })


# ─── GET /warnings ─────────────────────────────────────────────────────────────
@app.route("/warnings", methods=["GET"])
def get_warnings():
    agent = _auth(request)
    if not agent:
        return jsonify({"error": "unauthorized"}), 401

    warnings = _load("warnings.json")
    return jsonify({"warnings": warnings[:20]})


# ─── GET /learnings ────────────────────────────────────────────────────────────
@app.route("/learnings", methods=["GET"])
def get_learnings():
    agent = _auth(request)
    if not agent:
        return jsonify({"error": "unauthorized"}), 401

    learnings = _load("learnings.json")
    return jsonify({"learnings": learnings[:50]})


# ─── GET /status ───────────────────────────────────────────────────────────────
@app.route("/status", methods=["GET"])
def get_status():
    signals  = _load("signals.json")
    trades   = _load("trades.json")
    warnings = _load("warnings.json")
    learning = _load("learnings.json")

    agents_seen = list(set(
        [s["agent"] for s in signals[:20]] +
        [t["agent"] for t in trades[:20]]
    ))

    return jsonify({
        "status":        "online",
        "ts":            _ts(),
        "agents_seen":   agents_seen,
        "total_signals": len(signals),
        "total_trades":  len(trades),
        "total_warnings":len(warnings),
        "total_learnings":len(learning),
        "last_signal":   signals[0]["ts"] if signals else None,
        "last_trade":    trades[0]["ts"] if trades else None,
    })


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "name":    "Agent-to-Agent Learning Relay",
        "version": "1.0",
        "agents":  list(API_KEYS.keys()),
        "endpoints": [
            "POST /signal", "POST /trade", "POST /warning", "POST /learning",
            "GET /signals", "GET /trades", "GET /warnings", "GET /learnings",
            "GET /status",
        ]
    })


if __name__ == "__main__":
    print("🤝 A2A Relay starting on port 7433...")
    app.run(host="0.0.0.0", port=7433, debug=False)
