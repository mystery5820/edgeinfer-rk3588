#!/usr/bin/env bash
set -euo pipefail

MODEL_NAME="${1:-Qwen2.5-0.5B-Instruct}"
MAX_NEW_TOKENS="${2:-512}"
MAX_CONTEXT="${3:-2048}"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${PROJECT_ROOT}/third_party/rkllm_runtime"
DEMO_BIN="${RUNTIME_DIR}/llm_demo"

case "${MODEL_NAME}" in
  Qwen2.5-0.5B-Instruct)
    MODEL_PATH="${PROJECT_ROOT}/models/llm/rkllm_outputs/qwen2_5_0_5b_instruct_w8a8_opt1_ctx2048_rk3588.rkllm"
    ;;
  Qwen2.5-1.5B-Instruct)
    MODEL_PATH="${PROJECT_ROOT}/models/llm/rkllm_outputs/qwen2_5_1_5b_instruct_w8a8_opt1_ctx2048_rk3588.rkllm"
    ;;
  *)
    echo "ERROR: unsupported model: ${MODEL_NAME}" >&2
    echo "Supported models:" >&2
    echo "  Qwen2.5-0.5B-Instruct" >&2
    echo "  Qwen2.5-1.5B-Instruct" >&2
    exit 1
    ;;
esac

if [ ! -x "${DEMO_BIN}" ]; then
  echo "ERROR: llm_demo not found or not executable: ${DEMO_BIN}" >&2
  echo "Hint: create third_party/rkllm_runtime as a symlink to the RKLLM runtime directory on board." >&2
  exit 1
fi

if [ ! -f "${MODEL_PATH}" ]; then
  echo "ERROR: model file not found: ${MODEL_PATH}" >&2
  echo "Hint: sync or symlink the RKLLM model under models/llm/rkllm_outputs." >&2
  exit 1
fi

export LD_LIBRARY_PATH="${RUNTIME_DIR}/lib:${LD_LIBRARY_PATH:-}"
export RKLLM_LOG_LEVEL="${RKLLM_LOG_LEVEL:-1}"

echo "Project root : ${PROJECT_ROOT}"
echo "Runtime dir  : ${RUNTIME_DIR}"
echo "Demo binary  : ${DEMO_BIN}"
echo "Model name   : ${MODEL_NAME}"
echo "Model path   : ${MODEL_PATH}"
echo "Max tokens   : ${MAX_NEW_TOKENS}"
echo "Max context  : ${MAX_CONTEXT}"
echo

"${DEMO_BIN}" "${MODEL_PATH}" "${MAX_NEW_TOKENS}" "${MAX_CONTEXT}"
