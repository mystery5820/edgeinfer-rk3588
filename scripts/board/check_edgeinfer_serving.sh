#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="edgeinfer-serving.service"

echo "=== service enabled state ==="
systemctl is-enabled "${SERVICE_NAME}" 2>/dev/null || true

echo
echo "=== service active state ==="
systemctl is-active "${SERVICE_NAME}" 2>/dev/null || true

echo
echo "=== service status ==="
systemctl status "${SERVICE_NAME}" --no-pager -l 2>/dev/null || true

echo
echo "=== port 8000 ==="
ss -ltnp 2>/dev/null | grep ":8000" || true

echo
echo "=== uvicorn processes ==="
ps -ef | grep -E "uvicorn|server.main" | grep -v grep || true

echo
echo "=== legacy services ==="
systemctl is-enabled qwen-web-chat.service 2>/dev/null || true
systemctl is-active qwen-web-chat.service 2>/dev/null || true
systemctl is-enabled yolov5-web.service 2>/dev/null || true
systemctl is-active yolov5-web.service 2>/dev/null || true

echo
echo "=== local health check ==="
curl -s http://127.0.0.1:8000/v1/health | python3 -m json.tool 2>/dev/null || true
