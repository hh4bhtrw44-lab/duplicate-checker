#!/bin/bash
# =========================================
# Serveo 隧道守护脚本 - 自动重连
# =========================================
TUNNEL_LOG="/home/sandbox/.openclaw/workspace/duplicate-checker/logs/tunnel.log"
PID_FILE="/tmp/serveo_tunnel.pid"

# Kill any existing tunnel
pkill -f "serveo.net" 2>/dev/null
rm -f "$PID_FILE"

echo "================================================"
echo "  🚇 启动 Serveo 隧道守护进程"
echo "  时间: $(date)"
echo "================================================"

# Loop with auto-reconnect
while true; do
    echo "[$(date)] 正在连接 serveo.net ..." >> "$TUNNEL_LOG"
    
    /usr/bin/ssh \
        -o StrictHostKeyChecking=no \
        -o ServerAliveInterval=30 \
        -o ServerAliveCountMax=3 \
        -o ExitOnForwardFailure=yes \
        -o ConnectTimeout=10 \
        -R 80:localhost:5000 \
        serveo.net \
        2>&1 | while read line; do
            echo "[$(date)] $line" >> "$TUNNEL_LOG"
            # Extract URL if present
            echo "$line" | grep -oP 'https://[a-z0-9-]+\.serveousercontent\.com' >> /tmp/latest_tunnel_url.txt
        done
    
    echo "[$(date)] ⚠️ 隧道断开，5秒后重连..." >> "$TUNNEL_LOG"
    sleep 5
done
