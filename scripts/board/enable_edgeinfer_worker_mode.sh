#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${EDGEINFER_SERVICE_NAME:-edgeinfer-serving.service}"
DROPIN_DIR="/etc/systemd/system/${SERVICE_NAME}.d"
DROPIN_FILE="${DROPIN_DIR}/worker-mode.conf"

WORKER_MODE="${EDGEINFER_RKLLM_BACKEND_MODE:-worker}"
WORKER_MAX_NEW="${EDGEINFER_RKLLM_WORKER_MAX_NEW:-128}"
WORKER_CTX="${EDGEINFER_RKLLM_WORKER_CTX:-1024}"

echo "=== enable EdgeInfer RKLLM worker mode ==="
echo "SERVICE_NAME=${SERVICE_NAME}"
echo "DROPIN_FILE=${DROPIN_FILE}"
echo "WORKER_MODE=${WORKER_MODE}"
echo "WORKER_MAX_NEW=${WORKER_MAX_NEW}"
echo "WORKER_CTX=${WORKER_CTX}"
echo

sudo mkdir -p "${DROPIN_DIR}"

cat <<EOF | sudo tee "${DROPIN_FILE}"
[Service]
Environment=EDGEINFER_RKLLM_BACKEND_MODE=${WORKER_MODE}
Environment=EDGEINFER_RKLLM_WORKER_MAX_NEW=${WORKER_MAX_NEW}
Environment=EDGEINFER_RKLLM_WORKER_CTX=${WORKER_CTX}
EOF

sudo systemctl daemon-reload
sudo systemctl restart "${SERVICE_NAME}"

sleep 2

echo
echo "=== service environment ==="
systemctl show "${SERVICE_NAME}" -p Environment

echo
echo "=== service status ==="
systemctl is-active "${SERVICE_NAME}"
systemctl is-enabled "${SERVICE_NAME}"

echo
echo "=== health check ==="
curl -sS http://127.0.0.1:8000/v1/health | python3 -m json.tool
