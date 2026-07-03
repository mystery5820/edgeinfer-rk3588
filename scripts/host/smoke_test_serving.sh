#!/usr/bin/env bash
set -euo pipefail

BOARD_URL="${EDGEINFER_BOARD_URL:-http://192.168.43.7:8000}"
MODEL_ID="${EDGEINFER_MODEL_ID:-qwen3-4b-rkllm-all-npu}"

RUN_CHAT="${EDGEINFER_SMOKE_CHAT:-1}"
RUN_BUSY="${EDGEINFER_SMOKE_BUSY:-1}"
RUN_MAX_TOKENS_COMPAT="${EDGEINFER_SMOKE_MAX_TOKENS_COMPAT:-1}"
EXPECT_BACKEND="${EDGEINFER_EXPECT_BACKEND:-}"
EXPECT_BACKEND_MODE="${EDGEINFER_EXPECT_BACKEND_MODE:-}"

TMP_DIR="$(mktemp -d /tmp/edgeinfer_smoke_XXXXXX)"
trap 'rm -rf "${TMP_DIR}"' EXIT

echo "=== EdgeInfer RK3588 Serving Smoke Test ==="
echo "BOARD_URL=${BOARD_URL}"
echo "MODEL_ID=${MODEL_ID}"
echo "RUN_CHAT=${RUN_CHAT}"
echo "RUN_BUSY=${RUN_BUSY}"
echo "RUN_MAX_TOKENS_COMPAT=${RUN_MAX_TOKENS_COMPAT}"
echo "EXPECT_BACKEND=${EXPECT_BACKEND:-<not checked>}"
echo "EXPECT_BACKEND_MODE=${EXPECT_BACKEND_MODE:-<auto>}"
echo

curl_json() {
  local method="$1"
  local url="$2"
  local data_file="${3:-}"

  local out_file="${TMP_DIR}/response.json"
  local code_file="${TMP_DIR}/status.txt"

  if [ -n "${data_file}" ]; then
    curl -sS -o "${out_file}" -w "%{http_code}" \
      -X "${method}" "${url}" \
      -H "Content-Type: application/json" \
      -d @"${data_file}" > "${code_file}"
  else
    curl -sS -o "${out_file}" -w "%{http_code}" \
      -X "${method}" "${url}" > "${code_file}"
  fi

  local code
  code="$(cat "${code_file}")"

  echo "HTTP ${code}"
  python3 -m json.tool "${out_file}" || cat "${out_file}"
  echo

  if [ "${code}" -lt 200 ] || [ "${code}" -ge 300 ]; then
    echo "ERROR: request failed with HTTP ${code}: ${url}" >&2
    return 1
  fi
}

assert_backend() {
  local json_file="$1"
  local expected_backend="$2"
  local label="$3"

  if [ -z "${expected_backend}" ]; then
    return 0
  fi

  local actual_backend
  actual_backend="$(
    python3 -c '
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(data.get("edgeinfer", {}).get("backend", ""))
' "${json_file}"
  )"

  if [ "${actual_backend}" != "${expected_backend}" ]; then
    echo "ERROR: ${label} backend mismatch: expected ${expected_backend}, got ${actual_backend}" >&2
    exit 1
  fi

  echo "backend check OK: ${label}: ${actual_backend}"
}


infer_expected_backend_mode() {
  if [ -n "${EXPECT_BACKEND_MODE}" ]; then
    echo "${EXPECT_BACKEND_MODE}"
    return 0
  fi

  case "${EXPECT_BACKEND}" in
    rkllm-runner)
      echo "oneshot"
      ;;
    rkllm-persistent-worker)
      echo "worker"
      ;;
    fake)
      echo "fake"
      ;;
    *)
      echo ""
      ;;
  esac
}

assert_metrics_backend() {
  local json_file="$1"
  local label="$2"
  local require_worker_started="${3:-0}"

  local expected_mode
  expected_mode="$(infer_expected_backend_mode)"

  if [ -z "${expected_mode}" ] || [ "${expected_mode}" = "fake" ]; then
    return 0
  fi

  python3 -c '
import json
import sys
from pathlib import Path

json_file = Path(sys.argv[1])
expected_mode = sys.argv[2]
label = sys.argv[3]
require_worker_started = sys.argv[4] == "1"

data = json.loads(json_file.read_text(encoding="utf-8"))
backend = data.get("rkllm_backend", {})
actual_mode = backend.get("mode")
worker_enabled = backend.get("worker_enabled")
worker_runtime = backend.get("worker_runtime")

if actual_mode != expected_mode:
    print(
        f"ERROR: {label} metrics backend mode mismatch: "
        f"expected {expected_mode!r}, got {actual_mode!r}",
        file=sys.stderr,
    )
    sys.exit(1)

if expected_mode == "oneshot":
    if worker_enabled is not False:
        print(
            f"ERROR: {label} expected worker_enabled=false in oneshot mode, "
            f"got {worker_enabled!r}",
            file=sys.stderr,
        )
        sys.exit(1)
    if worker_runtime is not None:
        print(
            f"ERROR: {label} expected worker_runtime=null in oneshot mode, "
            f"got {worker_runtime!r}",
            file=sys.stderr,
        )
        sys.exit(1)
elif expected_mode == "worker":
    if worker_enabled is not True:
        print(
            f"ERROR: {label} expected worker_enabled=true in worker mode, "
            f"got {worker_enabled!r}",
            file=sys.stderr,
        )
        sys.exit(1)
    if not isinstance(worker_runtime, dict):
        print(
            f"ERROR: {label} expected worker_runtime object in worker mode, "
            f"got {worker_runtime!r}",
            file=sys.stderr,
        )
        sys.exit(1)
    if require_worker_started:
        if worker_runtime.get("started") is not True:
            print(
                f"ERROR: {label} expected worker_runtime.started=true after chat, "
                f"got {worker_runtime.get('started')!r}",
                file=sys.stderr,
            )
            sys.exit(1)
        if int(worker_runtime.get("request_count") or 0) < 1:
            print(
                f"ERROR: {label} expected worker request_count >= 1 after chat, "
                f"got {worker_runtime.get('request_count')!r}",
                file=sys.stderr,
            )
            sys.exit(1)
        if int(worker_runtime.get("failed_request_count") or 0) != 0:
            print(
                f"ERROR: {label} expected failed_request_count=0, "
                f"got {worker_runtime.get('failed_request_count')!r}",
                file=sys.stderr,
            )
            sys.exit(1)
else:
    print(f"ERROR: unsupported expected backend mode: {expected_mode!r}", file=sys.stderr)
    sys.exit(1)

runtime_state = None
if isinstance(worker_runtime, dict):
    runtime_state = worker_runtime.get("started")
print(
    f"metrics backend check OK: {label}: "
    f"mode={actual_mode}, worker_enabled={worker_enabled}, worker_started={runtime_state}"
)
' "${json_file}" "${expected_mode}" "${label}" "${require_worker_started}"
}

echo "=== 1. health ==="
curl_json GET "${BOARD_URL}/v1/health"

echo "=== 2. models ==="
curl_json GET "${BOARD_URL}/v1/models"

echo "=== 3. metrics before chat ==="
curl_json GET "${BOARD_URL}/v1/metrics"
assert_metrics_backend "${TMP_DIR}/response.json" "metrics before chat" "0"

if [ "${RUN_CHAT}" = "1" ]; then
  echo "=== 4. single chat completion ==="

  CHAT_REQ="${TMP_DIR}/chat_req.json"
  cat > "${CHAT_REQ}" <<JSON
{
  "model": "${MODEL_ID}",
  "messages": [
    {"role": "system", "content": "你是 EdgeInfer-RK3588 端侧推理助手。"},
    {"role": "user", "content": "已知事实：RK3588 是瑞芯微 Rockchip 推出的高性能 AIoT SoC，采用四核 Cortex-A76 加四核 Cortex-A55 架构，内置 NPU。请用一句话介绍 RK3588。"}
  ],
  "max_new_tokens": 64
}
JSON

  curl_json POST "${BOARD_URL}/v1/chat/completions" "${CHAT_REQ}"
  assert_backend "${TMP_DIR}/response.json" "${EXPECT_BACKEND}" "single chat"

  if [ "${RUN_MAX_TOKENS_COMPAT}" = "1" ]; then
    echo "=== 4b. max_tokens compatibility ==="

    MAX_TOKENS_REQ="${TMP_DIR}/max_tokens_req.json"
    MAX_TOKENS_CONFLICT_REQ="${TMP_DIR}/max_tokens_conflict_req.json"
    MAX_TOKENS_CONFLICT_OUT="${TMP_DIR}/max_tokens_conflict_out.json"
    MAX_TOKENS_CONFLICT_CODE="${TMP_DIR}/max_tokens_conflict_code.txt"

    cat > "${MAX_TOKENS_REQ}" <<JSON
{
  "model": "${MODEL_ID}",
  "messages": [
    {"role": "system", "content": "你是 EdgeInfer-RK3588 端侧推理助手。"},
    {"role": "user", "content": "请用一句话介绍 RK3588。"}
  ],
  "max_tokens": 32
}
JSON

    curl_json POST "${BOARD_URL}/v1/chat/completions" "${MAX_TOKENS_REQ}"
    assert_backend "${TMP_DIR}/response.json" "${EXPECT_BACKEND}" "max_tokens compatibility"

    cat > "${MAX_TOKENS_CONFLICT_REQ}" <<JSON
{
  "model": "${MODEL_ID}",
  "messages": [
    {"role": "user", "content": "请用一句话介绍 RK3588。"}
  ],
  "max_new_tokens": 16,
  "max_tokens": 17
}
JSON

    echo "--- max_tokens conflict request ---"
    curl -sS -o "${MAX_TOKENS_CONFLICT_OUT}" -w "%{http_code}" \
      -X POST "${BOARD_URL}/v1/chat/completions" \
      -H "Content-Type: application/json" \
      -d @"${MAX_TOKENS_CONFLICT_REQ}" > "${MAX_TOKENS_CONFLICT_CODE}"

    MAX_TOKENS_CONFLICT_CODE_VALUE="$(cat "${MAX_TOKENS_CONFLICT_CODE}")"
    echo "conflict HTTP ${MAX_TOKENS_CONFLICT_CODE_VALUE}"
    python3 -m json.tool "${MAX_TOKENS_CONFLICT_OUT}" || cat "${MAX_TOKENS_CONFLICT_OUT}"
    echo

    if [ "${MAX_TOKENS_CONFLICT_CODE_VALUE}" != "400" ]; then
      echo "ERROR: expected max_tokens conflict to return HTTP 400, got ${MAX_TOKENS_CONFLICT_CODE_VALUE}" >&2
      exit 1
    fi

    if ! grep -q "token_limit_conflict" "${MAX_TOKENS_CONFLICT_OUT}"; then
      echo "ERROR: max_tokens conflict response does not contain token_limit_conflict" >&2
      exit 1
    fi

    echo "max_tokens conflict check OK"
  else
    echo "=== 4b. max_tokens compatibility skipped ==="
  fi
else
  echo "=== 4. single chat completion skipped ==="
fi

echo "=== 5. metrics after single chat ==="
curl_json GET "${BOARD_URL}/v1/metrics"
assert_metrics_backend "${TMP_DIR}/response.json" "metrics after single chat" "${RUN_CHAT}"

if [ "${RUN_BUSY}" = "1" ]; then
  echo "=== 6. busy rejection test ==="

  REQ1="${TMP_DIR}/busy_req1.json"
  REQ2="${TMP_DIR}/busy_req2.json"
  OUT1="${TMP_DIR}/busy_out1.json"
  OUT2="${TMP_DIR}/busy_out2.json"
  CODE1="${TMP_DIR}/busy_code1.txt"
  CODE2="${TMP_DIR}/busy_code2.txt"

  cat > "${REQ1}" <<JSON
{
  "model": "${MODEL_ID}",
  "messages": [
    {"role": "system", "content": "你是 EdgeInfer-RK3588 端侧推理助手。"},
    {"role": "user", "content": "请用三句话介绍 RK3588，并说明它为什么适合端侧 AI 推理。"}
  ],
  "max_new_tokens": 96
}
JSON

  cat > "${REQ2}" <<JSON
{
  "model": "${MODEL_ID}",
  "messages": [
    {"role": "system", "content": "你是 EdgeInfer-RK3588 端侧推理助手。"},
    {"role": "user", "content": "请用一句话介绍 RK3588。"}
  ],
  "max_new_tokens": 64
}
JSON

  echo "--- launch first long request in background ---"
  (
    curl -sS -o "${OUT1}" -w "%{http_code}" \
      -X POST "${BOARD_URL}/v1/chat/completions" \
      -H "Content-Type: application/json" \
      -d @"${REQ1}" > "${CODE1}"
  ) &

  PID1=$!

  sleep 2

  echo "--- launch second request while first is running ---"
  curl -sS -o "${OUT2}" -w "%{http_code}" \
    -X POST "${BOARD_URL}/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d @"${REQ2}" > "${CODE2}"

  CODE2_VALUE="$(cat "${CODE2}")"
  echo "second HTTP ${CODE2_VALUE}"
  python3 -m json.tool "${OUT2}" || cat "${OUT2}"
  echo

  if [ "${CODE2_VALUE}" != "429" ]; then
    echo "ERROR: expected second request to return HTTP 429 busy, got ${CODE2_VALUE}" >&2
    wait "${PID1}" || true
    exit 1
  fi

  if ! grep -q "llm_backend_busy" "${OUT2}"; then
    echo "ERROR: second response does not contain llm_backend_busy" >&2
    wait "${PID1}" || true
    exit 1
  fi

  echo "--- wait first request ---"
  wait "${PID1}" || true

  CODE1_VALUE="$(cat "${CODE1}")"
  echo "first HTTP ${CODE1_VALUE}"
  python3 -m json.tool "${OUT1}" || cat "${OUT1}"
  echo

  if [ "${CODE1_VALUE}" != "200" ]; then
    echo "ERROR: expected first request to return HTTP 200, got ${CODE1_VALUE}" >&2
    exit 1
  fi

  assert_backend "${OUT1}" "${EXPECT_BACKEND}" "busy first request"
else
  echo "=== 6. busy rejection test skipped ==="
fi

echo "=== 7. metrics after busy test ==="
curl_json GET "${BOARD_URL}/v1/metrics"
FINAL_REQUIRE_WORKER_STARTED="0"
if [ "${RUN_CHAT}" = "1" ] || [ "${RUN_BUSY}" = "1" ]; then
  FINAL_REQUIRE_WORKER_STARTED="1"
fi
assert_metrics_backend "${TMP_DIR}/response.json" "metrics after busy test" "${FINAL_REQUIRE_WORKER_STARTED}"

echo "=== Smoke test passed ==="
