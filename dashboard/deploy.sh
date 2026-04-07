#!/bin/bash
# Auto-deploy dashboard to Cloudflare Pages every 60s
export CLOUDFLARE_API_TOKEN=cfut_GXa99ala6yjfDGgfE2eR2a4t1IK30icR8Gq3JjAs16660743

DASHBOARD_DIR="/home/agent/workspace/trading-bot-v2/dashboard"
PROJECT="dktrenchbot"
LOG="/home/agent/workspace/trading-bot-v2/dashboard/deploy.log"

echo "[$(date -u '+%H:%M:%S')] Deploy loop started" >> "$LOG"

while true; do
    # Regenerate HTML
    cd /home/agent/workspace/trading-bot-v2
    python3 dashboard/generate.py --once 2>/dev/null || python3 -c "
import sys; sys.path.insert(0,'dashboard')
import generate; generate.build()
print('Built')
" 2>> "$LOG"

    # Deploy to Cloudflare Pages
    RESULT=$(cd "$DASHBOARD_DIR" && npx wrangler pages deploy . --project-name "$PROJECT" 2>&1 | tail -3)
    echo "[$(date -u '+%H:%M:%S')] $RESULT" >> "$LOG"

    sleep 60
done
