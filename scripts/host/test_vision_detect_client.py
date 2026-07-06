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
TIMEOUT_SECONDS = float(os.environ.get("EDGEINFER_TIMEOUT_SECONDS", "30"))


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
    required = ["preprocess", "inference", "postprocess", "total"]
    for key in required:
        if key not in latency:
            raise AssertionError(f"missing latency_ms.{key}: {latency!r}")
        value = latency[key]
        if not isinstance(value, (int, float)) or value < 0:
            raise AssertionError(f"latency_ms.{key} must be non-negative number, got {value!r}")


def test_vision_detect_success() -> str:
    print("=== 1. vision detect skeleton success ===")
    model_id = find_model("object-detection")
    payload = {
        "model": model_id,
        "image_path": "/tmp/edgeinfer_phase18b_fake_input.jpg",
        "confidence_threshold": 0.25,
        "iou_threshold": 0.45,
    }
    data = request_json("POST", "/v1/vision/detect", payload)
    print(json.dumps(data, ensure_ascii=False, indent=2))

    if data.get("object") != "vision.detection":
        raise AssertionError(f"unexpected object: {data.get('object')!r}")
    if data.get("model") != model_id:
        raise AssertionError(f"unexpected model: {data.get('model')!r}, expected {model_id!r}")
    if not isinstance(data.get("objects"), list):
        raise AssertionError(f"objects must be a list: {data!r}")
    assert_latency(data.get("latency_ms") or {})

    edgeinfer = data.get("edgeinfer") or {}
    if edgeinfer.get("backend") != "fake-vision":
        raise AssertionError(f"expected fake-vision backend, got {edgeinfer!r}")
    if edgeinfer.get("runtime") != "phase18b-skeleton":
        raise AssertionError(f"expected phase18b-skeleton runtime, got {edgeinfer!r}")

    print("vision detect skeleton success check OK")
    return model_id


def test_default_model_success() -> None:
    print("=== 2. vision detect default model success ===")
    payload = {
        "image_path": "/tmp/edgeinfer_phase18b_fake_input.jpg",
    }
    data = request_json("POST", "/v1/vision/detect", payload)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    if data.get("object") != "vision.detection":
        raise AssertionError(f"unexpected object: {data.get('object')!r}")
    if not data.get("model"):
        raise AssertionError(f"default vision model was not resolved: {data!r}")
    assert_latency(data.get("latency_ms") or {})
    print("vision default model success check OK")


def test_model_not_vision() -> None:
    print("=== 3. model_not_vision rejection ===")
    llm_model = find_model("text-generation")
    body = request_expect_error(
        "POST",
        "/v1/vision/detect",
        {
            "model": llm_model,
            "image_path": "/tmp/edgeinfer_phase18b_fake_input.jpg",
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


def main() -> int:
    started = time.time()
    print("=== EdgeInfer Vision Detect Skeleton Client Test ===")
    print(f"BOARD_URL={BOARD_URL}")
    print(f"TIMEOUT_SECONDS={TIMEOUT_SECONDS}")
    print()

    model_id = test_vision_detect_success()
    print()
    test_default_model_success()
    print()
    test_model_not_vision()
    print()
    test_invalid_image_path(model_id)
    print()

    elapsed = time.time() - started
    print(f"=== Vision detect skeleton client test passed in {elapsed:.3f}s ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
