#!/bin/bash
cd /home/agent/workspace/trading-bot-v2
python3 dashboard_server.py > state/dashboard_stdout.log 2>&1 &
echo "Dashboard PID: $!"
