#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-edgeinfer-serving.service}"
DROPIN_DIR="/etc/systemd/system/${SERVICE_NAME}.d"

echo "=== Disable EdgeInfer Vision RKNN worker/probe backends ==="
echo "SERVICE_NAME=${SERVICE_NAME}"
echo "DROPIN_DIR=${DROPIN_DIR}"

sudo rm -f \
  "${DROPIN_DIR}/vision-rknn-worker.conf" \
  "${DROPIN_DIR}/vision-rknn-detect-probe.conf" \
  "${DROPIN_DIR}/vision-rknn-inference-probe.conf" \
  "${DROPIN_DIR}/vision-rknn-dryrun.conf"

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
