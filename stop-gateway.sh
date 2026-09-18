#!/bin/bash
# eltdx-TQ Gateway 停止脚本
PID_FILE="/tmp/eltdx-tq-gateway.pid"
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        echo "Gateway stopped (PID: $PID)"
    else
        echo "Gateway not running"
    fi
    rm -f "$PID_FILE"
else
    echo "No PID file found"
fi
