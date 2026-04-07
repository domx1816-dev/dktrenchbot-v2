#!/bin/bash
# watchdog.sh — auto-restarts DKBot and tg_signal_listener, singleton-safe
cd /home/agent/workspace/trading-bot-v2

while true; do
    # ── DKBot singleton guard ─────────────────────────────────────────────
    # Only match bot.py running from the trading-bot-v2 directory
    BOT_PIDS=()
    while IFS= read -r pid; do
        cwd=$(readlink /proc/$pid/cwd 2>/dev/null)
        if [[ "$cwd" == "/home/agent/workspace/trading-bot-v2" ]]; then
            BOT_PIDS+=("$pid")
        fi
    done < <(pgrep -f "bot\.py" | grep -v "bot/bot\.py")

    COUNT=${#BOT_PIDS[@]}

    if [[ $COUNT -eq 0 ]]; then
        echo "[$(date -u +%H:%M:%S)] bot.py not running — starting..." >> watchdog.log
        nohup python3 -u bot.py >> bot.log 2>&1 &
    elif [[ $COUNT -gt 1 ]]; then
        NEWEST=${BOT_PIDS[-1]}
        for pid in "${BOT_PIDS[@]}"; do
            if [[ $pid -ne $NEWEST ]]; then
                echo "[$(date -u +%H:%M:%S)] Duplicate DKBot (PID $pid) — killing" >> watchdog.log
                kill -9 "$pid" 2>/dev/null
            fi
        done
    fi

    # ── TG signal listener singleton guard ───────────────────────────────
    TG_PIDS=($(pgrep -f "tg_signal_listener"))
    TG_COUNT=${#TG_PIDS[@]}

    if [[ $TG_COUNT -eq 0 ]]; then
        echo "[$(date -u +%H:%M:%S)] tg_signal_listener not running — starting..." >> watchdog.log
        nohup python3 tg_signal_listener.py >> tg_listener.log 2>&1 &
    elif [[ $TG_COUNT -gt 1 ]]; then
        TG_NEWEST=${TG_PIDS[-1]}
        for pid in "${TG_PIDS[@]}"; do
            if [[ $pid -ne $TG_NEWEST ]]; then kill -9 "$pid" 2>/dev/null; fi
        done
    fi

    # ── TG scanner listener singleton guard ──────────────────────────────
    TSC_PIDS=($(pgrep -f "tg_scanner_listener"))
    TSC_COUNT=${#TSC_PIDS[@]}

    if [[ $TSC_COUNT -eq 0 ]]; then
        echo "[$(date -u +%H:%M:%S)] tg_scanner_listener not running — starting..." >> watchdog.log
        nohup python3 tg_scanner_listener.py >> tg_scanner.log 2>&1 &
    elif [[ $TSC_COUNT -gt 1 ]]; then
        TSC_NEWEST=${TSC_PIDS[-1]}
        for pid in "${TSC_PIDS[@]}"; do
            if [[ $pid -ne $TSC_NEWEST ]]; then kill -9 "$pid" 2>/dev/null; fi
        done
    fi

    # ── AMM launch watcher singleton guard ───────────────────────────────
    AMM_PIDS=($(pgrep -f "amm_launch_watcher"))
    AMM_COUNT=${#AMM_PIDS[@]}

    if [[ $AMM_COUNT -eq 0 ]]; then
        echo "[$(date -u +%H:%M:%S)] amm_launch_watcher not running — starting..." >> watchdog.log
        nohup python3 amm_launch_watcher.py >> amm_watcher.log 2>&1 &
    elif [[ $AMM_COUNT -gt 1 ]]; then
        AMM_NEWEST=${AMM_PIDS[-1]}
        for pid in "${AMM_PIDS[@]}"; do
            if [[ $pid -ne $AMM_NEWEST ]]; then kill -9 "$pid" 2>/dev/null; fi
        done
    fi

    sleep 30
done
