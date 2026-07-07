#!/usr/bin/env bash
set -euo pipefail

BOARD_URL="${EDGEINFER_BOARD_URL:-http://192.168.43.7:8000}"
IMAGE_PATH="${EDGEINFER_VISION_TEST_IMAGE_PATH:-/home/linaro/edgeinfer-rk3588-board/datasets/coco128/images/train2017/000000000089.jpg}"
MODEL_ID="${EDGEINFER_VISION_TEST_MODEL:-YOLOv11n-FP-Baseline}"

echo "=== EdgeInfer Vision Detect Demo ==="
echo "BOARD_URL=${BOARD_URL}"
echo "IMAGE_PATH=${IMAGE_PATH}"
echo "MODEL_ID=${MODEL_ID}"
echo

echo "=== 1. service root ==="
curl -s "${BOARD_URL}/" | python3 -m json.tool
echo

echo "=== 2. health ==="
curl -s "${BOARD_URL}/v1/health" | python3 -m json.tool
echo

echo "=== 3. models: object-detection only ==="
MODELS_JSON="$(mktemp)"
curl -s "${BOARD_URL}/v1/models" > "${MODELS_JSON}"
python3 - "${MODELS_JSON}" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for model in data.get("models", []):
    if model.get("task") == "object-detection":
        print(json.dumps(model, ensure_ascii=False, indent=2))
PY
rm -f "${MODELS_JSON}"
echo

echo "=== 4. default vision detect: no model field ==="
curl -s "${BOARD_URL}/v1/vision/detect" \
  -H "Content-Type: application/json" \
  -d "{
    \"image_path\": \"${IMAGE_PATH}\",
    \"confidence_threshold\": 0.25,
    \"iou_threshold\": 0.45
  }" | python3 -m json.tool
echo

echo "=== 5. explicit model vision detect ==="
curl -s "${BOARD_URL}/v1/vision/detect" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"${MODEL_ID}\",
    \"image_path\": \"${IMAGE_PATH}\",
    \"confidence_threshold\": 0.25,
    \"iou_threshold\": 0.45
  }" | python3 -m json.tool
echo

echo "=== 6. metrics: vision queue ==="
METRICS_JSON="$(mktemp)"
curl -s "${BOARD_URL}/v1/metrics" > "${METRICS_JSON}"
python3 - "${METRICS_JSON}" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(json.dumps(data.get("vision"), ensure_ascii=False, indent=2))
PY
rm -f "${METRICS_JSON}"
echo

echo "=== demo completed ==="
