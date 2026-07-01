#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${EDGEINFER_BOARD_DIR:-/home/linaro/edgeinfer-rk3588-board}"
TOOL_DIR="${PROJECT_DIR}/tools/rkllm_enhanced"
RUNTIME_LIB_DIR="${PROJECT_DIR}/third_party/rkllm_runtime/lib"

SRC="${TOOL_DIR}/rkllm_enhanced_no_template.cpp"
OUT_SRC="${TOOL_DIR}/rkllm_enhanced_no_template_no_history.cpp"
OUT_BIN="${TOOL_DIR}/rkllm_enhanced_no_template_no_history"

echo "=== build RKLLM no-history binary ==="
echo "PROJECT_DIR=${PROJECT_DIR}"
echo "TOOL_DIR=${TOOL_DIR}"
echo "RUNTIME_LIB_DIR=${RUNTIME_LIB_DIR}"
echo

if [ ! -f "${SRC}" ]; then
  echo "ERROR: source not found: ${SRC}" >&2
  exit 1
fi

if [ ! -d "${RUNTIME_LIB_DIR}" ]; then
  echo "ERROR: runtime lib dir not found: ${RUNTIME_LIB_DIR}" >&2
  exit 1
fi

python3 - <<PY
from pathlib import Path

src = Path("${SRC}")
dst = Path("${OUT_SRC}")

text = src.read_text(encoding="utf-8")

old = """        // keep_history=0 on the very first turn (fresh KV cache),
        // keep_history=1 on subsequent turns (extend existing context).
        ip.keep_history = (turn > 0) ? 1 : 0;
"""

new = """        // no-history mode:
        // keep every request isolated even when the RKLLM process stays alive.
        ip.keep_history = 0;
"""

if old not in text:
    raise SystemExit("ERROR: target keep_history block not found")

text = text.replace(old, new)

old2 = """        rkllm_run(g_handle, &inp, &ip, nullptr);
        g_running.store(false);
        turn++;
"""

new2 = """        rkllm_run(g_handle, &inp, &ip, nullptr);
        g_running.store(false);

        // Clear KV cache after each request to avoid cross-request contamination.
        // nullptr ranges mean clearing the whole cache.
        rkllm_clear_kv_cache(g_handle, 0, nullptr, nullptr);

        turn++;
"""

if old2 not in text:
    raise SystemExit("ERROR: target rkllm_run block not found")

text = text.replace(old2, new2)

dst.write_text(text, encoding="utf-8")
print(f"generated {dst}")
PY

echo
echo "=== patch check ==="
grep -n "keep_history\\|rkllm_clear_kv_cache\\|no-history" "${OUT_SRC}"

echo
echo "=== compile ==="
g++ -O2 -std=c++17 \
  "${OUT_SRC}" \
  -o "${OUT_BIN}" \
  -I"${TOOL_DIR}/include" \
  -L"${RUNTIME_LIB_DIR}" \
  -lrkllmrt \
  -Wl,-rpath,"${RUNTIME_LIB_DIR}" \
  -lpthread \
  -ldl

chmod 755 "${OUT_BIN}"

echo
echo "=== binary ==="
ls -lh "${OUT_BIN}"

echo
echo "=== ldd ==="
ldd "${OUT_BIN}" || true

echo
echo "=== runpath ==="
readelf -d "${OUT_BIN}" | grep -E "RPATH|RUNPATH" || true

echo
echo "=== done ==="
