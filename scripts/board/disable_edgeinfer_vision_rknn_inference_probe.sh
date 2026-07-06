#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-edgeinfer-serving.service}"
DROPIN_DIR="/etc/systemd/system/${SERVICE_NAME}.d"
INFER_DROPIN_FILE="${DROPIN_DIR}/vision-rknn-inference-probe.conf"
DRYRUN_DROPIN_FILE="${DROPIN_DIR}/vision-rknn-dryrun.conf"

echo "=== Disable EdgeInfer Vision RKNN inference probe backend ==="
echo "SERVICE_NAME=${SERVICE_NAME}"
echo "INFER_DROPIN_FILE=${INFER_DROPIN_FILE}"
echo "DRYRUN_DROPIN_FILE=${DRYRUN_DROPIN_FILE}"

sudo rm -f "${INFER_DROPIN_FILE}" "${DRYRUN_DROPIN_FILE}"

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
