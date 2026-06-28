#!/usr/bin/env bash
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}"

MODEL_NAME="${1:-YOLOv11n-INT8-Baseline}"
IMAGE_DIR="${2:-datasets/coco128/images/train2017}"
OUTPUT_PATH="${3:-results/benchmark/yolo11_board_benchmark.csv}"

mkdir -p results/benchmark

echo "========================================"
echo "EdgeInfer RK3588 YOLOv11 Board Benchmark"
echo "========================================"
echo "Project root : ${PROJECT_ROOT}"
echo "Model        : ${MODEL_NAME}"
echo "Image dir    : ${IMAGE_DIR}"
echo "Output       : ${OUTPUT_PATH}"
echo "========================================"

python3 tools/benchmark_yolo11_rknn.py \
  --model "${MODEL_NAME}" \
  --runtime rknnlite \
  --image-dir "${IMAGE_DIR}" \
  --limit 50 \
  --repeat 5 \
  --output "${OUTPUT_PATH}"

python3 tools/summarize_yolo_benchmark.py \
  --input "${OUTPUT_PATH}" \
  --output "${OUTPUT_PATH%.csv}_report.md"

echo
echo "Benchmark finished."
echo "CSV report: ${OUTPUT_PATH}"
echo "Markdown report: ${OUTPUT_PATH%.csv}_report.md"
