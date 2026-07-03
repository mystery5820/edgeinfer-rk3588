#!/usr/bin/env bash
set -euo pipefail

BOARD_HOST="${EDGEINFER_BOARD_HOST:-linaro@192.168.43.7}"
BOARD_DIR="${EDGEINFER_BOARD_DIR:-/home/linaro/edgeinfer-rk3588-board}"
SERVICE_NAME="${EDGEINFER_SERVICE_NAME:-edgeinfer-serving.service}"
RUN_SMOKE="${EDGEINFER_DEPLOY_SMOKE:-0}"

SYNC_PATHS=(
  server
  configs
  scripts/board
)

echo "=== EdgeInfer RK3588 Serving Deploy ==="
echo "BOARD_HOST=${BOARD_HOST}"
echo "BOARD_DIR=${BOARD_DIR}"
echo "SERVICE_NAME=${SERVICE_NAME}"
echo "RUN_SMOKE=${RUN_SMOKE}"
echo

for path in "${SYNC_PATHS[@]}"; do
  if [ ! -e "${path}" ]; then
    echo "ERROR: missing local path: ${path}" >&2
    exit 1
  fi
done

echo "=== local syntax check ==="
python3 -m compileall -q server
echo "local compileall OK"
echo

echo "=== verify remote directory ==="
ssh "${BOARD_HOST}" "test -d '${BOARD_DIR}' && echo 'remote directory OK: ${BOARD_DIR}'"
echo

echo "=== sync source files to board ==="
tar \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.pytest_cache' \
  --exclude='.mypy_cache' \
  -czf - "${SYNC_PATHS[@]}" \
  | ssh "${BOARD_HOST}" "cd '${BOARD_DIR}' && tar -xzf -"
echo "sync OK"
echo

echo "=== remote compile, restart, and health check ==="
ssh "${BOARD_HOST}" \
  "BOARD_DIR='${BOARD_DIR}' SERVICE_NAME='${SERVICE_NAME}' bash -s" <<'REMOTE'
set -euo pipefail
cd "${BOARD_DIR}"

chmod +x scripts/board/*.sh || true

if [ -f .venv-serving/bin/activate ]; then
  . .venv-serving/bin/activate
fi

python -m compileall -q server
echo "board compileall OK"

sudo systemctl restart "${SERVICE_NAME}"
sleep 2

./scripts/board/check_edgeinfer_serving.sh
REMOTE

echo
if [ "${RUN_SMOKE}" = "1" ]; then
  echo "=== host smoke test ==="
  ./scripts/host/smoke_test_serving.sh
else
  echo "=== host smoke test skipped ==="
  echo "To run it after deploy: EDGEINFER_DEPLOY_SMOKE=1 ./scripts/host/deploy_serving_to_board.sh"
fi

echo

echo "=== deploy completed ==="
