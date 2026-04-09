#!/bin/bash
# Supervisor script for DKTrenchBot dashboard
# Checks if dashboard server and Cloudflare tunnel are running, restarts if needed.
# Run every 2 minutes via cron.

DASHBOARD_DIR="/home/agent/workspace/trading-bot-v2"
TUNNEL_BIN="/tmp/cloudflared"
LOG="$DASHBOARD_DIR/state/dashboard_supervisor.log"

log() {
    echo "[$(date -u '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG"
}

# Check dashboard server (port 5000)
if ! curl -s http://localhost:5000/health > /dev/null 2>&1; then
    log "Dashboard server not responding — restarting..."
    pkill -f "uvicorn dashboard_server" 2>/dev/null
    sleep 1
    cd "$DASHBOARD_DIR" && nohup uvicorn dashboard_server:app --host 0.0.0.0 --port 5000 > state/dashboard_server.log 2>&1 &
    log "Dashboard server restarted (PID: $!)"
    sleep 3
fi

# Check Cloudflare tunnel
if ! pgrep -f "cloudflared tunnel" > /dev/null 2>&1; then
    log "Cloudflare tunnel not running — restarting..."
    pkill -f "cloudflared tunnel" 2>/dev/null
    sleep 1
    $TUNNEL_BIN tunnel --url http://localhost:5000 --no-autoupdate > /tmp/tunnel.log 2>&1 &
    sleep 5
    TUNNEL_URL=$(grep -o "https://[^ ]*\.trycloudflare\.com" /tmp/tunnel.log | head -1)
    log "Tunnel restarted: $TUNNEL_URL"
    
    # Update dashboard HTML with new URL
    if [ -n "$TUNNEL_URL" ]; then
        sed -i "s|const API_BASE = 'https://[^']*'|const API_BASE = '$TUNNEL_URL'|" "$DASHBOARD_DIR/dashboard/index.html"
        log "Updated dashboard HTML with new tunnel URL"
    fi
else
    log "Dashboard OK — all services running"
fi
