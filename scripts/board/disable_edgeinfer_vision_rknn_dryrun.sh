#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-edgeinfer-serving.service}"
DROPIN_FILE="/etc/systemd/system/${SERVICE_NAME}.d/vision-rknn-dryrun.conf"

echo "=== Disable EdgeInfer Vision RKNN dryrun backend ==="
echo "SERVICE_NAME=${SERVICE_NAME}"
echo "DROPIN_FILE=${DROPIN_FILE}"

if [ -f "${DROPIN_FILE}" ]; then
  sudo rm -f "${DROPIN_FILE}"
  echo "removed: ${DROPIN_FILE}"
else
  echo "drop-in not found, nothing to remove"
fi

sudo systemctl daemon-reload
sudo systemctl restart "${SERVICE_NAME}"
sleep 2

echo
echo "=== service active state ==="
systemctl is-active "${SERVICE_NAME}"

echo
echo "=== effective env ==="
systemctl show "${SERVICE_NAME}" -p Environment | tr ' ' '\n' | grep -E "EDGEINFER_VISION_BACKEND_MODE|EDGEINFER_RKNN_YOLO" || true

echo
echo "=== health ==="
curl -s http://127.0.0.1:8000/v1/health | python3 -m json.tool
