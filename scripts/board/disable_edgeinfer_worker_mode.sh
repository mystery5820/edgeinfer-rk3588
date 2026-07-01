#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${EDGEINFER_SERVICE_NAME:-edgeinfer-serving.service}"
DROPIN_DIR="/etc/systemd/system/${SERVICE_NAME}.d"
DROPIN_FILE="${DROPIN_DIR}/worker-mode.conf"
OLD_TEST_FILE="${DROPIN_DIR}/worker-test.conf"

echo "=== disable EdgeInfer RKLLM worker mode ==="
echo "SERVICE_NAME=${SERVICE_NAME}"
echo "DROPIN_FILE=${DROPIN_FILE}"
echo "OLD_TEST_FILE=${OLD_TEST_FILE}"
echo

if [ -f "${DROPIN_FILE}" ]; then
  sudo rm -f "${DROPIN_FILE}"
  echo "removed ${DROPIN_FILE}"
else
  echo "not found: ${DROPIN_FILE}"
fi

if [ -f "${OLD_TEST_FILE}" ]; then
  sudo rm -f "${OLD_TEST_FILE}"
  echo "removed ${OLD_TEST_FILE}"
else
  echo "not found: ${OLD_TEST_FILE}"
fi

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
