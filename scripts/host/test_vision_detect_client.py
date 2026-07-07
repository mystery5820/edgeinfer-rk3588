#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


BOARD_URL = os.environ.get("EDGEINFER_BOARD_URL", "http://192.168.43.7:8000").rstrip("/")
TIMEOUT_SECONDS = float(os.environ.get("EDGEINFER_TIMEOUT_SECONDS", "120"))
VISION_TEST_IMAGE_PATH = os.environ.get(
    "EDGEINFER_VISION_TEST_IMAGE_PATH",
    "/home/linaro/edgeinfer-rk3588-board/datasets/coco128/images/train2017/000000000089.jpg",
)
EXPECTED_BACKEND = os.environ.get("EDGEINFER_EXPECT_VISION_BACKEND", "fake-vision").strip()
VISION_TEST_MODEL = os.environ.get("EDGEINFER_VISION_TEST_MODEL", "").strip()
EXPECTED_DEFAULT_MODEL = os.environ.get("EDGEINFER_EXPECT_DEFAULT_VISION_MODEL", "YOLOv11n-FP-Baseline").strip()


def expected_runtime() -> str:
    if EXPECTED_BACKEND == "rknn-yolo-worker":
        return "phase18j-vision-default-model-metadata-cleanup"
    if EXPECTED_BACKEND == "rknn-yolo-detect-probe":
        return "phase18g-vision-detect-output-refinement"
    if EXPECTED_BACKEND == "rknn-yolo-inference-probe":
        return "phase18e-rknn-yolo-inference-probe"
    if EXPECTED_BACKEND == "rknn-yolo-dryrun":
        return "phase18d-rknn-yolo-dryrun"
    return "phase18c-image-input-skeleton"


def default_test_model() -> str:
    if VISION_TEST_MODEL:
        return VISION_TEST_MODEL
    if EXPECTED_BACKEND in {"rknn-yolo-detect-probe", "rknn-yolo-worker"}:
        return "YOLOv11n-FP-Baseline"
    return ""


def url(path: str) -> str:
    return BOARD_URL + "/" + path.lstrip("/")


def request_json(method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url(path), data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    return json.loads(body)


def request_expect_error(method: str, path: str, payload: Dict[str, Any], expected_status: int) -> Dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url(path),
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            raise AssertionError(f"expected HTTP {expected_status}, got {resp.status}: {body}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}")
        print(body)
        if exc.code != expected_status:
            raise AssertionError(f"expected HTTP {expected_status}, got {exc.code}: {body}")
        return json.loads(body)


def find_model(task: str) -> str:
    requested = default_test_model() if task == "object-detection" else ""
    data = request_json("GET", "/v1/models")
    if requested:
        for model in data.get("models", []):
            if model.get("id") == requested or model.get("name") == requested:
                if model.get("task") != task:
                    raise AssertionError(f"requested model {requested!r} is not task={task!r}: {model!r}")
                return model["id"]
        raise AssertionError(f"requested test model not found: {requested!r}")

    for model in data.get("models", []):
        if model.get("task") == task:
            return model["id"]
    raise AssertionError(f"no model with task={task!r} found in /v1/models")


def assert_error_code(body: Dict[str, Any], expected_code: str) -> None:
    detail = body.get("detail")
    if not isinstance(detail, dict):
        raise AssertionError(f"error response has no detail object: {body!r}")
    error = detail.get("error")
    if not isinstance(error, dict):
        raise AssertionError(f"error response has no error object: {body!r}")
    code = error.get("code")
    if code != expected_code:
        raise AssertionError(f"expected code {expected_code!r}, got {code!r}: {body!r}")


def assert_latency(latency: Dict[str, Any]) -> None:
    required = ["load_image", "preprocess", "inference", "postprocess", "total"]
    if EXPECTED_BACKEND in {"rknn-yolo-dryrun", "rknn-yolo-inference-probe", "rknn-yolo-detect-probe", "rknn-yolo-worker"}:
        required.append("backend_init")

    for key in required:
        if key not in latency:
            raise AssertionError(f"missing latency_ms.{key}: {latency!r}")
        value = latency[key]
        if not isinstance(value, (int, float)) or value < 0:
            raise AssertionError(f"latency_ms.{key} must be non-negative number, got {value!r}")

    if EXPECTED_BACKEND in {"rknn-yolo-inference-probe", "rknn-yolo-detect-probe", "rknn-yolo-worker"} and latency["inference"] <= 0:
        raise AssertionError(f"inference latency should be > 0: {latency!r}")
    if EXPECTED_BACKEND in {"rknn-yolo-detect-probe", "rknn-yolo-worker"} and latency["postprocess"] <= 0:
        raise AssertionError(f"postprocess latency should be > 0 in detect probe: {latency!r}")


def assert_image(image: Dict[str, Any]) -> None:
    required = ["path", "format", "width", "height", "channels", "size_bytes", "preprocess"]
    for key in required:
        if key not in image:
            raise AssertionError(f"missing image.{key}: {image!r}")
    if image["path"] != VISION_TEST_IMAGE_PATH:
        raise AssertionError(f"unexpected image path: {image['path']!r}")
    for key in ["width", "height", "channels", "size_bytes"]:
        value = image[key]
        if not isinstance(value, int) or value <= 0:
            raise AssertionError(f"image.{key} must be positive int, got {value!r}")
    preprocess = image["preprocess"]
    if not isinstance(preprocess, dict):
        raise AssertionError(f"image.preprocess must be object: {image!r}")
    for key in ["method", "target_width", "target_height", "scale"]:
        if key not in preprocess:
            raise AssertionError(f"missing image.preprocess.{key}: {preprocess!r}")


def assert_direct_resize_metadata(image: Dict[str, Any]) -> None:
    preprocess = image.get("preprocess") or {}
    if EXPECTED_BACKEND not in {"rknn-yolo-inference-probe", "rknn-yolo-detect-probe", "rknn-yolo-worker"}:
        return

    expected = {
        "resized_width": 640,
        "resized_height": 640,
        "pad_left": 0,
        "pad_right": 0,
        "pad_top": 0,
        "pad_bottom": 0,
    }

    for key, value in expected.items():
        if preprocess.get(key) != value:
            raise AssertionError(f"expected preprocess.{key}={value!r}, got {preprocess!r}")

    if "scale_x" not in preprocess or "scale_y" not in preprocess:
        raise AssertionError(f"expected direct resize scale_x/scale_y in preprocess: {preprocess!r}")

    if EXPECTED_BACKEND in {"rknn-yolo-detect-probe", "rknn-yolo-worker"}:
        if preprocess.get("coordinate_space") != "original_image":
            raise AssertionError(f"expected preprocess coordinate_space original_image: {preprocess!r}")


def assert_objects(objects: Any, image: Dict[str, Any], require_non_empty: bool) -> None:
    if not isinstance(objects, list):
        raise AssertionError(f"objects must be a list: {objects!r}")
    if require_non_empty and not objects:
        raise AssertionError("expected non-empty objects for Phase 18G FP detect probe")

    width = float(image.get("width", 0) or 0)
    height = float(image.get("height", 0) or 0)
    target_width = float((image.get("preprocess") or {}).get("target_width", 640))
    target_height = float((image.get("preprocess") or {}).get("target_height", 640))

    for obj in objects:
        if not isinstance(obj, dict):
            raise AssertionError(f"object item must be dict: {obj!r}")
        for key in ["class_id", "class_name", "confidence", "bbox"]:
            if key not in obj:
                raise AssertionError(f"missing object.{key}: {obj!r}")

        if not isinstance(obj["bbox"], list) or len(obj["bbox"]) != 4:
            raise AssertionError(f"object.bbox must be 4-number list: {obj!r}")
        x1, y1, x2, y2 = [float(x) for x in obj["bbox"]]
        if not (0 <= x1 <= width and 0 <= x2 <= width and 0 <= y1 <= height and 0 <= y2 <= height):
            raise AssertionError(f"object.bbox must be original-image coordinates: {obj!r}, image={image!r}")

        if not isinstance(obj["confidence"], (int, float)) or obj["confidence"] < 0:
            raise AssertionError(f"invalid object confidence: {obj!r}")

        if EXPECTED_BACKEND in {"rknn-yolo-detect-probe", "rknn-yolo-worker"}:
            if obj.get("coordinate_space") != "original_image":
                raise AssertionError(f"expected original_image coordinate_space: {obj!r}")
            if str(obj.get("class_name")) == str(obj.get("class_id")):
                raise AssertionError(f"class_name should be COCO label, not numeric string: {obj!r}")
            bbox_input = obj.get("bbox_input")
            if not isinstance(bbox_input, list) or len(bbox_input) != 4:
                raise AssertionError(f"expected bbox_input: {obj!r}")
            ix1, iy1, ix2, iy2 = [float(x) for x in bbox_input]
            if not (0 <= ix1 <= target_width and 0 <= ix2 <= target_width and 0 <= iy1 <= target_height and 0 <= iy2 <= target_height):
                raise AssertionError(f"bbox_input must be model-input coordinates: {obj!r}")


def assert_success_response(data: Dict[str, Any], model_id: Optional[str] = None, require_objects: bool = False) -> None:
    if data.get("object") != "vision.detection":
        raise AssertionError(f"unexpected object: {data.get('object')!r}")
    if model_id is not None and data.get("model") != model_id:
        raise AssertionError(f"unexpected model: {data.get('model')!r}, expected {model_id!r}")

    image = data.get("image") or {}
    assert_latency(data.get("latency_ms") or {})
    assert_direct_resize_metadata(data.get("image") or {})
    assert_image(image)
    assert_objects(data.get("objects"), image=image, require_non_empty=require_objects)

    edgeinfer = data.get("edgeinfer") or {}
    if edgeinfer.get("backend") != EXPECTED_BACKEND:
        raise AssertionError(f"expected backend {EXPECTED_BACKEND!r}, got {edgeinfer!r}")
    if edgeinfer.get("runtime") != expected_runtime():
        raise AssertionError(f"expected runtime {expected_runtime()!r}, got {edgeinfer!r}")

    if EXPECTED_BACKEND in {"rknn-yolo-dryrun", "rknn-yolo-inference-probe", "rknn-yolo-detect-probe", "rknn-yolo-worker"}:
        model_runtime = edgeinfer.get("model_runtime")
        if not isinstance(model_runtime, dict):
            raise AssertionError(f"missing model_runtime for rknn backend: {edgeinfer!r}")
        if model_runtime.get("backend") != EXPECTED_BACKEND:
            raise AssertionError(f"unexpected model_runtime backend: {model_runtime!r}")
        probe = model_runtime.get("probe")
        if not isinstance(probe, dict) or probe.get("ok") is not True:
            raise AssertionError(f"RKNN probe did not succeed: {model_runtime!r}")

        if EXPECTED_BACKEND in {"rknn-yolo-inference-probe", "rknn-yolo-detect-probe", "rknn-yolo-worker"}:
            output_summary = model_runtime.get("output_summary")
            if not isinstance(output_summary, dict):
                raise AssertionError(f"missing output_summary: {model_runtime!r}")
            if not isinstance(output_summary.get("num_outputs"), int) or output_summary["num_outputs"] <= 0:
                raise AssertionError(f"expected num_outputs > 0: {output_summary!r}")
            shapes = output_summary.get("output_shapes")
            if not isinstance(shapes, list) or not shapes:
                raise AssertionError(f"expected non-empty output_shapes: {output_summary!r}")

        if EXPECTED_BACKEND in {"rknn-yolo-detect-probe", "rknn-yolo-worker"}:
            output_summary = model_runtime.get("output_summary", {})
            num_detections = output_summary.get("num_detections")
            if require_objects and (not isinstance(num_detections, int) or num_detections <= 0):
                raise AssertionError(f"expected num_detections > 0: {model_runtime!r}")
            if output_summary.get("coordinate_space") != "original_image":
                raise AssertionError(f"expected output coordinate_space original_image: {output_summary!r}")


def test_vision_detect_success() -> str:
    print("=== 1. vision detect image metadata success ===")
    model_id = find_model("object-detection")
    payload = {
        "model": model_id,
        "image_path": VISION_TEST_IMAGE_PATH,
        "confidence_threshold": 0.25,
        "iou_threshold": 0.45,
    }
    data = request_json("POST", "/v1/vision/detect", payload)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    require_objects = EXPECTED_BACKEND in {"rknn-yolo-detect-probe", "rknn-yolo-worker"}
    assert_success_response(data, model_id=model_id, require_objects=require_objects)
    print("vision detect image metadata success check OK")
    return model_id


def test_default_model_success() -> None:
    print("=== 2. vision detect default model success ===")
    payload = {
        "image_path": VISION_TEST_IMAGE_PATH,
    }
    data = request_json("POST", "/v1/vision/detect", payload)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    assert_success_response(data, require_objects=False)
    if not data.get("model"):
        raise AssertionError(f"default vision model was not resolved: {data!r}")
    print("vision default model success check OK")


def test_model_not_vision() -> None:
    print("=== 3. model_not_vision rejection ===")
    llm_model = find_model("text-generation")
    body = request_expect_error(
        "POST",
        "/v1/vision/detect",
        {
            "model": llm_model,
            "image_path": VISION_TEST_IMAGE_PATH,
        },
        expected_status=400,
    )
    assert_error_code(body, "model_not_vision")
    print("model_not_vision rejection check OK")


def test_invalid_image_path(model_id: str) -> None:
    print("=== 4. invalid_image_path rejection ===")
    body = request_expect_error(
        "POST",
        "/v1/vision/detect",
        {
            "model": model_id,
            "image_path": "",
        },
        expected_status=400,
    )
    assert_error_code(body, "invalid_image_path")
    print("invalid_image_path rejection check OK")


def test_image_not_found(model_id: str) -> None:
    print("=== 5. image_not_found rejection ===")
    body = request_expect_error(
        "POST",
        "/v1/vision/detect",
        {
            "model": model_id,
            "image_path": "/tmp/edgeinfer_phase18c_missing_input_000000.jpg",
        },
        expected_status=404,
    )
    assert_error_code(body, "image_not_found")
    print("image_not_found rejection check OK")


def main() -> int:
    started = time.time()
    print("=== EdgeInfer Vision Detect Image Metadata Client Test ===")
    print(f"BOARD_URL={BOARD_URL}")
    print(f"TIMEOUT_SECONDS={TIMEOUT_SECONDS}")
    print(f"VISION_TEST_IMAGE_PATH={VISION_TEST_IMAGE_PATH}")
    print(f"EXPECTED_BACKEND={EXPECTED_BACKEND}")
    print(f"EXPECTED_RUNTIME={expected_runtime()}")
    print(f"VISION_TEST_MODEL={default_test_model() or '<registry-first-object-detection>'}")
    print()

    model_id = test_vision_detect_success()
    print()
    test_default_model_success()
    print()
    test_model_not_vision()
    print()
    test_invalid_image_path(model_id)
    print()
    test_image_not_found(model_id)
    print()

    elapsed = time.time() - started
    print(f"=== Vision detect image metadata client test passed in {elapsed:.3f}s ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
