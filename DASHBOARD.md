# DKTrenchBot Dashboard

**Live URL**: https://atmospheric-acoustic-advocate-respect.trycloudflare.com

## Architecture

```
Browser → Cloudflare Tunnel → localhost:5000 (FastAPI dashboard_server.py)
                                              ↓
                                        Bot state files (JSON)
```

## Components

1. **dashboard_server.py** — FastAPI server on port 5000
   - Serves static HTML at `/`
   - API endpoints at `/api/*`
   - Reads bot state from `state/*.json` files

2. **dashboard/index.html** — Static frontend (dark theme, auto-refresh every 10s)

3. **Cloudflare Tunnel** — Exposes port 5000 publicly via trycloudflare.com

## Start/Stop

```bash
# Start dashboard server
cd /home/agent/workspace/trading-bot-v2
uvicorn dashboard_server:app --host 0.0.0.0 --port 5000 &

# Start Cloudflare tunnel
/tmp/cloudflared tunnel --url http://localhost:5000 --no-autoupdate &

# Stop both
pkill -f "uvicorn dashboard_server"
pkill -f "cloudflared tunnel"
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/status` | Bot health, balance, performance stats |
| `GET /api/trades` | Last 20 trades |
| `GET /api/candidates` | Top scan candidates by momentum |
| `GET /api/safety` | Safety controller status (paused/stopped) |
| `GET /api/realtime` | Recent realtime signals (bursts, clusters) |
| `GET /health` | Health check |

## Notes

- The tunnel URL changes each time cloudflared restarts
- For a permanent URL, set up a Cloudflare Pages project or use a custom domain
- No authentication — keep the URL private or add auth middleware
