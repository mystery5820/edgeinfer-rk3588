#!/usr/bin/env bash
set -euo pipefail

BOARD_URL="${EDGEINFER_BOARD_URL:-http://192.168.43.7:8000}"
MODEL_ID="${EDGEINFER_MODEL_ID:-qwen3-4b-rkllm-all-npu}"

RUN_CHAT="${EDGEINFER_SMOKE_CHAT:-1}"
RUN_BUSY="${EDGEINFER_SMOKE_BUSY:-1}"

TMP_DIR="$(mktemp -d /tmp/edgeinfer_smoke_XXXXXX)"
trap 'rm -rf "${TMP_DIR}"' EXIT

echo "=== EdgeInfer RK3588 Serving Smoke Test ==="
echo "BOARD_URL=${BOARD_URL}"
echo "MODEL_ID=${MODEL_ID}"
echo "RUN_CHAT=${RUN_CHAT}"
echo "RUN_BUSY=${RUN_BUSY}"
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

echo "=== 1. health ==="
curl_json GET "${BOARD_URL}/v1/health"

echo "=== 2. models ==="
curl_json GET "${BOARD_URL}/v1/models"

echo "=== 3. metrics before chat ==="
curl_json GET "${BOARD_URL}/v1/metrics"

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
else
  echo "=== 4. single chat completion skipped ==="
fi

echo "=== 5. metrics after single chat ==="
curl_json GET "${BOARD_URL}/v1/metrics"

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
else
  echo "=== 6. busy rejection test skipped ==="
fi

echo "=== 7. metrics after busy test ==="
curl_json GET "${BOARD_URL}/v1/metrics"

echo "=== Smoke test passed ==="
