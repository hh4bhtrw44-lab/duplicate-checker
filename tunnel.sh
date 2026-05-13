#!/bin/bash
# Tunnel script - maintains SSH tunnel via serveo.net
APP_DIR="/home/sandbox/.openclaw/workspace/duplicate-checker"
LOG_DIR="${APP_DIR}/logs"

mkdir -p "$LOG_DIR"

# Kill any existing tunnel
pkill -f "serveo\.net" 2>/dev/null

# Start SSH tunnel
/usr/bin/ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes -R 80:localhost:5000 serveo.net > "${LOG_DIR}/tunnel.log" 2>&1 &

TUNNEL_PID=$!
echo "$TUNNEL_PID" > "${LOG_DIR}/tunnel.pid"

# Wait and extract the URL
sleep 6
URL=$(grep -oP 'https://[a-z0-9-]+\.serveousercontent\.com' "${LOG_DIR}/tunnel.log" | head -1)

if [ -n "$URL" ]; then
    echo "TUNNEL_URL=$URL"
else
    echo "TUNNEL_NOT_READY"
fi
