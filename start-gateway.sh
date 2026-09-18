#!/bin/bash
# eltdx-TQ Gateway 启动脚本
LOG_FILE="/tmp/eltdx-tq-gateway.log"
PID_FILE="/tmp/eltdx-tq-gateway.pid"

# 如果已经在运行，先停止
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Stopping old process (PID: $OLD_PID)..."
        kill "$OLD_PID" 2>/dev/null
        sleep 2
    fi
fi

# 启动网关
echo "Starting eltdx-TQ Gateway on port 17709..."
nohup /tmp/eltdx-venv/bin/python3 /vol4/1000/ydyp/gateway/eltdx-tq-gateway.py >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

sleep 3
if kill -0 $(cat "$PID_FILE") 2>/dev/null; then
    echo "Gateway started successfully (PID: $(cat $PID_FILE))"
    echo "Health check: $(curl -s http://127.0.0.1:17709/health)"
else
    echo "Failed to start gateway"
    echo "Log: $(tail -20 $LOG_FILE)"
fi
