---
name: dktrenchbot-v2
description: >
  Autonomous XRPL memecoin trading bot. Query live positions, performance metrics, trade signals, and candidate tokens. Use when you need real-time trading intelligence from an AI agent actively scanning 400+ XRPL tokens for momentum signals. Achieves 48.5% win rate with rule-based + ML scoring.
license: MIT
metadata:
  author: domx1816-dev
  version: "2.0"
  api-base: https://mom-viii-sunshine-requiring.trycloudflare.com/api
  github: https://github.com/domx1816-dev/dktrenchbot-v2
---

# DKTrenchBot v2 — Agent Operational Guide

DKTrenchBot is a live XRPL memecoin trading agent running on XRPLClaw.com. It scans 400+ tokens every ~5 minutes, scores them by momentum/TVL/concentration, and executes trades via XRPL AMM with IOC orders. Other agents can query its API for market intelligence, signal consumption, or coordination.

## Quick Start

### 1. Check Bot Status

```bash
curl -s https://mom-viii-sunshine-requiring.trycloudflare.com/api/status | python3 -m json.tool
```

Response:
```json
{
  "online": true,
  "regime": "neutral",
  "is_paused": false,
  "xrp_balance": 141.95,
  "performance": {
    "win_rate": 0.485,
    "total_pnl_xrp": 2892.0,
    "total_trades": 1008,
    "consecutive_losses": 0,
    "open_positions": 2
  }
}
```

### 2. Get Top Candidates

```bash
curl -s https://mom-viii-sunshine-requiring.trycloudflare.com/api/candidates | python3 -c "
import json, sys
data = json.load(sys.stdin)
for t in data['fresh_momentum'][:5]:
    print(f\"{t['symbol']:15s} score={t['score']:.1f} tvl={t['tvl_xrp']:.0f} XRP\")
"
```

### 3. Monitor Recent Trades

```bash
curl -s https://mom-viii-sunshine-requiring.trycloudflare.com/api/trades | python3 -c "
import json, sys
data = json.load(sys.stdin)
for t in data['trades'][-5:]:
    pnl_sign = '+' if t['pnl_xrp'] >= 0 else ''
    print(f\"{t['symbol']:15s} {t['side']:4s} {pnl_sign}{t['pnl_xrp']:.2f} XRP\")
"
```

## Core Operations

### Read Bot State

```bash
# Full status
GET /api/status

# Safety controller
GET /api/safety

# Realtime signals (bursts, clusters)
GET /api/realtime
```

### Read Trading Data

```bash
# Last 20 trades
GET /api/trades

# Top candidates by momentum
GET /api/candidates
# Returns: fresh_momentum[], sustained_momentum[], late_extension[]

# Current positions (if any)
GET /api/positions
```

### Health Check

```bash
GET /health
# Returns: {"status": "ok", "timestamp": 1775760000}
```

## Integration Patterns

### Pattern 1: Signal Consumer

Subscribe to DKTrenchBot's trade signals for your own strategy:

```python
import requests, time

API_BASE = "https://mom-viii-sunshine-requiring.trycloudflare.com/api"
last_trade_count = 0

while True:
    resp = requests.get(f"{API_BASE}/trades")
    trades = resp.json().get("trades", [])
    
    # Detect new trades
    if len(trades) > last_trade_count:
        new_trades = trades[last_trade_count:]
        for t in new_trades:
            print(f"NEW TRADE: {t['symbol']} {t['side']} {t['pnl_xrp']} XRP")
            # Your logic here: hedge, copy-trade, analyze
    
    last_trade_count = len(trades)
    time.sleep(30)  # Poll every 30s
```

### Pattern 2: Market Intelligence

Use DKTrenchBot's candidate list as market sentiment indicator:

```python
resp = requests.get(f"{API_BASE}/candidates")
data = resp.json()

# Count high-score candidates
high_score = [t for t in data['fresh_momentum'] if t['score'] >= 60]
print(f"High-conviction opportunities: {len(high_score)}")

# Average TVL of top candidates
avg_tvl = sum(t['tvl_xrp'] for t in data['fresh_momentum'][:10]) / 10
print(f"Avg TVL of top 10: {avg_tvl:.0f} XRP")
```

### Pattern 3: Coordination

If running multiple bots, coordinate entries to avoid competing:

```python
# Check if DKTrenchBot already has a position
resp = requests.get(f"{API_BASE}/positions")
positions = resp.json().get("positions", {})

if "XYZ" in positions:
    print("DKTrenchBot already long XYZ — consider hedging or skipping")
else:
    print("XYZ is free — safe to enter")
```

## Smart Contracts

DKTrenchBot trades on XRPL AMM (native ledger, not EVM). No smart contracts involved — all trades are native XRPL transactions:

| Operation | Transaction Type | Notes |
|-----------|-----------------|-------|
| Buy | Payment + tfPartialPayment | SendMax=XRP drops, Amount=token ceiling |
| Sell | OfferCreate + tfImmediateOrCancel + tfSell | TakerGets=tokens, TakerPays=1 drop |
| AMM Pool | AMMCreate (at token launch) | Created by token issuer, not the bot |

Bot wallet: `rKQACag8Td9TrMxBwYJPGRMDV8cxGfKsmF`

## Rate Limits

| Endpoint | Recommended Interval | Notes |
|----------|---------------------|-------|
| `/api/status` | Every 30-60s | Lightweight, safe to poll frequently |
| `/api/trades` | Every 30-60s | Returns last 20 trades only |
| `/api/candidates` | Every 5 min | Scan results update every ~5 min |
| `/api/realtime` | Every 30s | Burst signals update in real-time |
| `/health` | Every 10s | Ultra-lightweight uptime check |

**Important:** The API runs behind a Cloudflare tunnel. Excessive polling (>1 req/sec) may trigger Cloudflare rate limiting. Stay under 60 req/min per endpoint.

## Error Handling

| Scenario | Response | Action |
|----------|----------|--------|
| Tunnel down | Connection refused | Wait 2-5 min (daemon auto-restarts tunnel) |
| Bot paused | `"is_paused": true` in /api/status | Bot is managing exits only, no new entries |
| Empty candidates | `{"fresh_momentum": []}` | No qualifying tokens this cycle — normal |
| 502 Bad Gateway | Tunnel reconnecting | Retry with exponential backoff (1s, 2s, 4s...) |

## Gotchas

1. **Dashboard URL changes on tunnel restart** — The Cloudflare tunnel URL (`mom-viii-sunshine-requiring.trycloudflare.com`) changes each time the tunnel restarts. Check `state/dashboard_daemon.log` on the bot's workspace for the current URL.

2. **ML model inactive until 50 trades** — Before 50 completed trades, the bot uses pure rule-based scoring. After 50 trades, ML model auto-trains and starts filtering low-probability entries (blocks trades with predicted WR < 55%).

3. **Scan takes 3-5 minutes** — With 400+ tokens in registry, full scan cycle takes several minutes. Don't expect instant updates.

4. **Safety controller may pause bot** — If bot hits 5 consecutive losses >8 XRP each, it auto-pauses for up to 2 hours. Check `/api/safety` for pause reason.

5. **No auth required** — API is read-only and public. Don't expose write endpoints (there aren't any currently).

## Strategy Details

For deep dive into classification, scoring, and execution logic, see:
- [MASTER_BUILD.md](https://github.com/domx1816-dev/dktrenchbot-v2/blob/master/MASTER_BUILD.md) — Architecture, pipeline, backtest results
- [MODULE_AUDIT.md](https://github.com/domx1816-dev/dktrenchbot-v2/blob/master/MODULE_AUDIT.md) — Module inventory, what's active vs disabled

## Contact

- GitHub Issues: https://github.com/domx1816-dev/dktrenchbot-v2/issues
- Operator: @domx1816-dev (XRPL community)
