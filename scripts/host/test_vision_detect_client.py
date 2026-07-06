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


def expected_runtime() -> str:
    if EXPECTED_BACKEND == "rknn-yolo-dryrun":
        return "phase18d-rknn-yolo-dryrun"
    return "phase18c-image-input-skeleton"


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
    data = request_json("GET", "/v1/models")
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
    if EXPECTED_BACKEND == "rknn-yolo-dryrun":
        required.append("backend_init")

    for key in required:
        if key not in latency:
            raise AssertionError(f"missing latency_ms.{key}: {latency!r}")
        value = latency[key]
        if not isinstance(value, (int, float)) or value < 0:
            raise AssertionError(f"latency_ms.{key} must be non-negative number, got {value!r}")


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


def assert_success_response(data: Dict[str, Any], model_id: Optional[str] = None) -> None:
    if data.get("object") != "vision.detection":
        raise AssertionError(f"unexpected object: {data.get('object')!r}")
    if model_id is not None and data.get("model") != model_id:
        raise AssertionError(f"unexpected model: {data.get('model')!r}, expected {model_id!r}")
    if not isinstance(data.get("objects"), list):
        raise AssertionError(f"objects must be a list: {data!r}")
    assert_latency(data.get("latency_ms") or {})
    assert_image(data.get("image") or {})

    edgeinfer = data.get("edgeinfer") or {}
    if edgeinfer.get("backend") != EXPECTED_BACKEND:
        raise AssertionError(f"expected backend {EXPECTED_BACKEND!r}, got {edgeinfer!r}")
    if edgeinfer.get("runtime") != expected_runtime():
        raise AssertionError(f"expected runtime {expected_runtime()!r}, got {edgeinfer!r}")

    if EXPECTED_BACKEND == "rknn-yolo-dryrun":
        model_runtime = edgeinfer.get("model_runtime")
        if not isinstance(model_runtime, dict):
            raise AssertionError(f"missing model_runtime for rknn dryrun: {edgeinfer!r}")
        if model_runtime.get("backend") != "rknn-yolo-dryrun":
            raise AssertionError(f"unexpected model_runtime backend: {model_runtime!r}")
        probe = model_runtime.get("probe")
        if not isinstance(probe, dict) or probe.get("ok") is not True:
            raise AssertionError(f"RKNN probe did not succeed: {model_runtime!r}")


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
    assert_success_response(data, model_id=model_id)
    print("vision detect image metadata success check OK")
    return model_id


def test_default_model_success() -> None:
    print("=== 2. vision detect default model success ===")
    payload = {
        "image_path": VISION_TEST_IMAGE_PATH,
    }
    data = request_json("POST", "/v1/vision/detect", payload)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    assert_success_response(data)
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
