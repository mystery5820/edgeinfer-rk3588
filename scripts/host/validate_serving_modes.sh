#!/usr/bin/env bash
set -euo pipefail

BOARD_HOST="${EDGEINFER_BOARD_HOST:-linaro@192.168.43.7}"
BOARD_DIR="${EDGEINFER_BOARD_DIR:-/home/linaro/edgeinfer-rk3588-board}"
ONESHOT_BACKEND="${EDGEINFER_ONESHOT_EXPECT_BACKEND:-rkllm-runner}"
WORKER_BACKEND="${EDGEINFER_WORKER_EXPECT_BACKEND:-rkllm-persistent-worker}"
RUN_DEPLOY="${EDGEINFER_VALIDATE_DEPLOY:-0}"

cleanup() {
  local status=$?
  local cleanup_status=0

  set +e
  echo
  echo "=== cleanup: restore default one-shot mode ==="
  ssh "${BOARD_HOST}" "cd '${BOARD_DIR}' && ./scripts/board/disable_edgeinfer_worker_mode.sh"
  cleanup_status=$?

  if [ "${cleanup_status}" -ne 0 ]; then
    echo "ERROR: cleanup failed while disabling worker mode" >&2
    if [ "${status}" -eq 0 ]; then
      status="${cleanup_status}"
    fi
  fi

  if [ "${status}" -eq 0 ]; then
    echo
    echo "=== serving mode validation completed ==="
  else
    echo
    echo "=== serving mode validation failed with status ${status} ===" >&2
  fi

  return "${status}"
}
trap cleanup EXIT

echo "=== EdgeInfer RK3588 Serving Mode Validation ==="
echo "BOARD_HOST=${BOARD_HOST}"
echo "BOARD_DIR=${BOARD_DIR}"
echo "ONESHOT_BACKEND=${ONESHOT_BACKEND}"
echo "WORKER_BACKEND=${WORKER_BACKEND}"
echo "RUN_DEPLOY=${RUN_DEPLOY}"
echo

if [ ! -x scripts/host/smoke_test_serving.sh ]; then
  echo "ERROR: missing executable script: scripts/host/smoke_test_serving.sh" >&2
  exit 1
fi

if [ "${RUN_DEPLOY}" = "1" ]; then
  if [ ! -x scripts/host/deploy_serving_to_board.sh ]; then
    echo "ERROR: missing executable script: scripts/host/deploy_serving_to_board.sh" >&2
    exit 1
  fi

  echo "=== optional deploy before validation ==="
  EDGEINFER_DEPLOY_SMOKE=0 ./scripts/host/deploy_serving_to_board.sh
  echo
fi

echo "=== verify remote directory ==="
ssh "${BOARD_HOST}" "test -d '${BOARD_DIR}' && echo 'remote directory OK: ${BOARD_DIR}'"
echo

echo "=== 1. force default one-shot mode ==="
ssh "${BOARD_HOST}" "cd '${BOARD_DIR}' && ./scripts/board/disable_edgeinfer_worker_mode.sh"
echo

echo "=== 2. validate one-shot mode ==="
EDGEINFER_EXPECT_BACKEND="${ONESHOT_BACKEND}" \
EDGEINFER_EXPECT_BACKEND_MODE="oneshot" \
./scripts/host/smoke_test_serving.sh
echo

echo "=== 3. enable worker mode ==="
ssh "${BOARD_HOST}" "cd '${BOARD_DIR}' && ./scripts/board/enable_edgeinfer_worker_mode.sh"
echo

echo "=== 4. validate worker mode ==="
EDGEINFER_EXPECT_BACKEND="${WORKER_BACKEND}" \
EDGEINFER_EXPECT_BACKEND_MODE="worker" \
./scripts/host/smoke_test_serving.sh
