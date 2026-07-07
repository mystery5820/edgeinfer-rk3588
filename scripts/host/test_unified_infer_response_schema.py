#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Tuple


BASE_URL = os.environ.get("EDGEINFER_BASE_URL", "http://192.168.43.7:8000").rstrip("/")
IMAGE_PATH = os.environ.get(
    "EDGEINFER_TEST_IMAGE_PATH",
    "/home/linaro/edgeinfer-rk3588-board/datasets/coco128/images/train2017/000000000089.jpg",
)
VISION_MODEL = os.environ.get("EDGEINFER_TEST_VISION_MODEL", "YOLOv11n-FP-Baseline")
EXPECT_BACKEND = os.environ.get("EDGEINFER_EXPECT_VISION_BACKEND")


def _read_json(resp: Any) -> Dict[str, Any]:
    body = resp.read().decode("utf-8", errors="replace")
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"response is not JSON: {body[:500]}") from exc


def get_json(path: str) -> Dict[str, Any]:
    req = urllib.request.Request(BASE_URL + path, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status != 200:
            raise AssertionError(f"GET {path} returned {resp.status}")
        return _read_json(resp)


def post_json(path: str, payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL + path,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return resp.status, _read_json(resp)
    except urllib.error.HTTPError as exc:
        return exc.code, _read_json(exc)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def require_keys(obj: Dict[str, Any], keys: list[str], context: str) -> None:
    missing = [key for key in keys if key not in obj]
    require(not missing, f"{context} missing keys: {missing}")


def main() -> int:
    started = time.time()

    tasks = get_json("/v1/infer/tasks")
    require(tasks.get("object") == "edgeinfer.infer.tasks", "unexpected /v1/infer/tasks object")
    require("object-detection" in tasks.get("tasks", {}), "object-detection task missing")
    require("vision-language" in tasks.get("tasks", {}), "vision-language task missing")

    status, response = post_json(
        "/v1/infer",
        {
            "task": "object-detection",
            "model": VISION_MODEL,
            "input": {
                "image_path": IMAGE_PATH,
            },
            "parameters": {
                "confidence_threshold": 0.25,
                "iou_threshold": 0.45,
            },
        },
    )
    require(status == 200, f"object-detection returned HTTP {status}: {response}")

    require_keys(
        response,
        ["id", "object", "created", "task", "model", "output", "edgeinfer"],
        "unified inference response",
    )
    require(response["object"] == "edgeinfer.inference", "unexpected response object")
    require(response["task"] == "object-detection", "unexpected task")
    require(isinstance(response["created"], int), "created must be int")

    output = response["output"]
    require(isinstance(output, dict), "output must be dict")
    require_keys(output, ["summary", "data", "raw"], "output")

    summary = output["summary"]
    data = output["data"]
    raw = output["raw"]
    require(isinstance(summary, dict), "output.summary must be dict")
    require(isinstance(data, dict), "output.data must be dict")
    require(isinstance(raw, dict), "output.raw must be dict")

    require(summary.get("type") == "object-detection", "summary.type must be object-detection")
    require(isinstance(summary.get("num_objects"), int), "summary.num_objects must be int")
    require(isinstance(summary.get("classes"), list), "summary.classes must be list")
    require(summary.get("coordinate_space") == "original_image", "coordinate_space should be original_image")
    require(summary.get("box_format") == "xyxy", "box_format should be xyxy")

    require("objects" in data, "output.data.objects missing")
    require(isinstance(data["objects"], list), "output.data.objects must be list")

    # Compatibility fields for Phase 19A-style simple clients.
    require(output.get("model") == VISION_MODEL, "compat output.model mismatch")
    require("objects" in output, "compat output.objects missing")
    require(isinstance(output["objects"], list), "compat output.objects must be list")
    require("image" in output, "compat output.image missing")
    require("edgeinfer" in output, "compat output.edgeinfer missing")

    edgeinfer = response["edgeinfer"]
    require(isinstance(edgeinfer, dict), "edgeinfer must be dict")
    require(edgeinfer.get("runtime") == "phase19b-unified-response-adapter-polish", "unexpected runtime")

    dispatch = edgeinfer.get("dispatch")
    require(isinstance(dispatch, dict), "edgeinfer.dispatch must be dict")
    require(dispatch.get("task") == "object-detection", "dispatch.task mismatch")
    require(dispatch.get("adapter") == "vision-detect", "dispatch.adapter mismatch")
    require(dispatch.get("source_endpoint") == "/v1/vision/detect", "dispatch.source_endpoint mismatch")
    require(dispatch.get("backend"), "dispatch.backend missing")

    if EXPECT_BACKEND:
        require(
            dispatch.get("backend") == EXPECT_BACKEND,
            f"expected backend {EXPECT_BACKEND}, got {dispatch.get('backend')}",
        )

    status, vlm_response = post_json(
        "/v1/infer",
        {
            "task": "vision-language",
            "model": "future-vlm-model",
            "input": {
                "image_path": IMAGE_PATH,
                "text": "What is in this image?",
            },
        },
    )
    require(status == 501, f"vision-language placeholder should return 501, got {status}")
    require(
        vlm_response.get("detail", {}).get("error", {}).get("code") == "vlm_backend_not_ready",
        f"unexpected VLM error payload: {vlm_response}",
    )

    status, unsupported = post_json(
        "/v1/infer",
        {
            "task": "audio-transcription",
            "input": {},
        },
    )
    require(status == 400, f"unsupported task should return 400, got {status}")
    require(
        unsupported.get("detail", {}).get("error", {}).get("code") == "unsupported_task",
        f"unexpected unsupported task payload: {unsupported}",
    )

    elapsed = time.time() - started
    print(f"=== unified infer response schema test passed in {elapsed:.3f}s ===")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        raise
