#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-edgeinfer-serving.service}"
DROPIN_DIR="/etc/systemd/system/${SERVICE_NAME}.d"
DROPIN_FILE="${DROPIN_DIR}/vision-rknn-worker.conf"
BOARD_DIR="${BOARD_DIR:-/home/linaro/edgeinfer-rk3588-board}"

echo "=== Enable EdgeInfer Vision RKNN persistent worker backend ==="
echo "SERVICE_NAME=${SERVICE_NAME}"
echo "BOARD_DIR=${BOARD_DIR}"
echo "DROPIN_FILE=${DROPIN_FILE}"

sudo mkdir -p "${DROPIN_DIR}"
sudo rm -f \
  "${DROPIN_DIR}/vision-rknn-detect-probe.conf" \
  "${DROPIN_DIR}/vision-rknn-inference-probe.conf" \
  "${DROPIN_DIR}/vision-rknn-dryrun.conf"

cat <<EOF | sudo tee "${DROPIN_FILE}" >/dev/null
[Service]
Environment=EDGEINFER_VISION_BACKEND_MODE=rknn-yolo-worker
Environment=EDGEINFER_RKNN_YOLO_PYTHON=/usr/bin/python3
Environment=EDGEINFER_RKNN_YOLO_WORKER_STARTUP_TIMEOUT_SECONDS=60
Environment=EDGEINFER_RKNN_YOLO_WORKER_REQUEST_TIMEOUT_SECONDS=60
EOF

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
