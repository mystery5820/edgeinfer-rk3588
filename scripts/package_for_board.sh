#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}"

PACKAGE_NAME="edgeinfer-rk3588-board"
DIST_ROOT="${PROJECT_ROOT}/dist"
PACKAGE_DIR="${DIST_ROOT}/${PACKAGE_NAME}"
IMAGE_LIMIT="${IMAGE_LIMIT:-20}"

echo "========================================"
echo "Packaging EdgeInfer for RK3588 board"
echo "========================================"
echo "Project root : ${PROJECT_ROOT}"
echo "Package dir  : ${PACKAGE_DIR}"
echo "Image limit  : ${IMAGE_LIMIT}"
echo "========================================"

rm -rf "${PACKAGE_DIR}"
mkdir -p "${PACKAGE_DIR}"

mkdir -p \
  "${PACKAGE_DIR}/configs" \
  "${PACKAGE_DIR}/tools" \
  "${PACKAGE_DIR}/server" \
  "${PACKAGE_DIR}/scripts" \
  "${PACKAGE_DIR}/docs" \
  "${PACKAGE_DIR}/models/vision/yolo11/rknn" \
  "${PACKAGE_DIR}/datasets/coco128/images/train2017" \
  "${PACKAGE_DIR}/results/benchmark"

echo "[1/6] Copy configs..."
cp configs/*.yaml "${PACKAGE_DIR}/configs/"

echo "[2/6] Copy tools..."
cp tools/benchmark_yolo11_rknn.py "${PACKAGE_DIR}/tools/"
cp tools/summarize_yolo_benchmark.py "${PACKAGE_DIR}/tools/"
cp tools/list_models.py "${PACKAGE_DIR}/tools/"
cp tools/check_assets.py "${PACKAGE_DIR}/tools/"

echo "[3/6] Copy server modules..."
cp -r server/* "${PACKAGE_DIR}/server/"

echo "[4/6] Copy scripts and docs..."
cp scripts/run_board_yolo_benchmark.sh "${PACKAGE_DIR}/scripts/" 2>/dev/null || true

cp docs/phase3_yolo11_benchmark.md "${PACKAGE_DIR}/docs/" 2>/dev/null || true
cp docs/phase3_yolo11_benchmark_postprocess.md "${PACKAGE_DIR}/docs/" 2>/dev/null || true
cp docs/phase3_yolo11_postprocess.md "${PACKAGE_DIR}/docs/" 2>/dev/null || true
cp docs/phase4_board_deploy_package.md "${PACKAGE_DIR}/docs/" 2>/dev/null || true

echo "[5/6] Copy RKNN models..."
cp models/vision/yolo11/rknn/yolo11n_baseline_i8_rk3588.rknn \
  "${PACKAGE_DIR}/models/vision/yolo11/rknn/"


echo "[6/6] Copy sample images..."
if [ -d datasets/coco128/images/train2017 ]; then
  find datasets/coco128/images/train2017 \
    -maxdepth 1 \
    -type f \
    \( -name "*.jpg" -o -name "*.jpeg" -o -name "*.png" \) \
    | sort \
    | head -n "${IMAGE_LIMIT}" \
    | while IFS= read -r img; do
        cp "$img" "${PACKAGE_DIR}/datasets/coco128/images/train2017/"
      done
else
  echo "Warning: datasets/coco128/images/train2017 not found, skip sample images."
fi

echo "Clean Python cache files..."
find "${PACKAGE_DIR}" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "${PACKAGE_DIR}" -type f -name "*.pyc" -delete

echo "Create README_BOARD.md..."
{
  echo "# EdgeInfer RK3588 Board Package"
  echo
  echo "This package is used to run YOLOv11 RKNN benchmark on RK3588 board."
  echo
  echo "## Check assets"
  echo
  echo "python3 tools/list_models.py"
  echo "python3 tools/check_assets.py"
  echo
  echo "## Run baseline"
  echo
  echo "bash scripts/run_board_yolo_benchmark.sh YOLOv11n-INT8-Baseline"
  echo
  echo "## Output"
  echo
  echo "Benchmark results will be saved to results/benchmark/."
} > "${PACKAGE_DIR}/README_BOARD.md"

{
  echo "numpy"
  echo "pyyaml"
  echo "opencv-python"
} > "${PACKAGE_DIR}/requirements_board.txt"

echo
echo "Package file list:"
find "${PACKAGE_DIR}" -maxdepth 4 -type f | sort

cd "${DIST_ROOT}"
tar -czf "${PACKAGE_NAME}.tar.gz" "${PACKAGE_NAME}"

echo
echo "========================================"
echo "Package created:"
echo "${PACKAGE_DIR}"
echo "${DIST_ROOT}/${PACKAGE_NAME}.tar.gz"
echo "========================================"
