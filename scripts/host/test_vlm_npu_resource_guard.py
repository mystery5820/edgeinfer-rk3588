#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Tuple


BOARD_URL = os.environ.get("EDGEINFER_BOARD_URL", "http://192.168.43.7:8000").rstrip("/")
VLM_MODEL = os.environ.get("EDGEINFER_QWEN3_VL_MODEL", "qwen3-vl-2b-instruct-rkllm-v123")
IMAGE_PATH = os.environ.get("EDGEINFER_QWEN3_VL_IMAGE_PATH", "/home/linaro/qwen3-vl-2b-npu/Pizza.jpg")
VISION_MODEL = os.environ.get("EDGEINFER_VISION_MODEL", "YOLOv11n-FP-Baseline")
VLM_TIMEOUT_SECONDS = float(os.environ.get("EDGEINFER_QWEN3_VL_TIMEOUT_SECONDS", "260"))
SLEEP_BEFORE_COMPETING_REQUEST = float(os.environ.get("EDGEINFER_VLM_GUARD_SLEEP_SECONDS", "3"))


def _read_json(resp) -> Any:
    text = resp.read().decode("utf-8", errors="replace")
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def post_json(path: str, payload: Dict[str, Any], *, timeout: float) -> Tuple[int, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{BOARD_URL}{path}",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), _read_json(resp)
    except urllib.error.HTTPError as exc:
        return int(exc.code), _read_json(exc)


def get_json(path: str, *, timeout: float = 30.0) -> Tuple[int, Any]:
    req = urllib.request.Request(f"{BOARD_URL}{path}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), _read_json(resp)
    except urllib.error.HTTPError as exc:
        return int(exc.code), _read_json(exc)


def dump(title: str, value: Any) -> None:
    print(title)
    print(json.dumps(value, ensure_ascii=False, indent=2))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    print("=== EdgeInfer VLM NPU Resource Guard Test ===")
    print(f"BOARD_URL={BOARD_URL}")
    print(f"VLM_MODEL={VLM_MODEL}")
    print(f"VISION_MODEL={VISION_MODEL}")
    print(f"IMAGE_PATH={IMAGE_PATH}")

    vlm_payload = {
        "task": "vision-language",
        "model": VLM_MODEL,
        "input": {
            "image_path": IMAGE_PATH,
            "prompt": "<image> Describe this image in detail.",
        },
        "parameters": {
            "max_new_tokens": 128,
            "context_length": 1024,
            "timeout_seconds": int(VLM_TIMEOUT_SECONDS),
        },
    }

    vision_payload = {
        "model": VISION_MODEL,
        "image_path": IMAGE_PATH,
        "confidence_threshold": 0.25,
        "iou_threshold": 0.45,
    }

    vlm_result: Dict[str, Any] = {}

    def run_vlm() -> None:
        try:
            status, body = post_json("/v1/infer", vlm_payload, timeout=VLM_TIMEOUT_SECONDS)
            vlm_result["status"] = status
            vlm_result["body"] = body
        except Exception as exc:  # pragma: no cover - surfaced in main thread
            vlm_result["exception"] = repr(exc)

    thread = threading.Thread(target=run_vlm, daemon=True)

    print("=== start VLM request in background ===")
    thread.start()
    time.sleep(SLEEP_BEFORE_COMPETING_REQUEST)

    print("=== call vision while VLM should be running ===")
    vision_status, vision_body = post_json("/v1/vision/detect", vision_payload, timeout=60)
    dump(f"/v1/vision/detect during VLM HTTP {vision_status}", vision_body)

    require(vision_status == 429, f"vision request should return 429 while VLM owns NPU, got {vision_status}")

    detail = vision_body.get("detail", {}) if isinstance(vision_body, dict) else {}
    error = detail.get("error", {}) if isinstance(detail, dict) else {}
    edgeinfer = detail.get("edgeinfer", {}) if isinstance(detail, dict) else {}
    npu = edgeinfer.get("npu_resource", {}) if isinstance(edgeinfer, dict) else {}

    require(error.get("code") == "npu_resource_busy", f"unexpected busy error: {vision_body}")
    require(edgeinfer.get("backend") == "npu-resource-guard", f"unexpected busy backend: {edgeinfer}")
    require(npu.get("busy") is True, f"npu_resource should be busy during VLM: {npu}")
    require(npu.get("current_task") == "vision-language", f"current_task mismatch: {npu}")
    require(npu.get("current_model") == VLM_MODEL, f"current_model mismatch: {npu}")
    require(npu.get("current_owner") == "qwen3-vl", f"current_owner mismatch: {npu}")

    print("=== wait VLM request ===")
    thread.join(timeout=VLM_TIMEOUT_SECONDS + 30)
    require(not thread.is_alive(), "VLM request did not finish before timeout")
    require("exception" not in vlm_result, f"VLM thread exception: {vlm_result.get('exception')}")

    vlm_status = vlm_result.get("status")
    vlm_body = vlm_result.get("body")
    dump(f"/v1/infer VLM background HTTP {vlm_status}", vlm_body)

    require(vlm_status == 200, f"VLM request should return 200, got {vlm_status}: {vlm_body}")
    require(isinstance(vlm_body, dict), f"VLM body must be dict: {vlm_body!r}")

    vlm_edgeinfer = vlm_body.get("edgeinfer", {})
    require(vlm_edgeinfer.get("backend") == "qwen3-vl-rkllm-rknn-runner", f"unexpected VLM backend: {vlm_edgeinfer}")
    require(vlm_edgeinfer.get("source_runtime") == "phase22-qwen3-vl-rk3588-backend", f"unexpected VLM runtime: {vlm_edgeinfer}")

    answer = (
        vlm_body.get("output", {})
        .get("summary", {})
        .get("answer", "")
    )
    require(isinstance(answer, str) and len(answer.strip()) >= 10, f"VLM answer missing: {vlm_body}")

    print("VLM answer preview:", answer[:300])

    status, metrics = get_json("/v1/metrics")
    require(status == 200 and isinstance(metrics, dict), f"metrics failed: {status}, {metrics}")
    final_npu = metrics.get("npu_resource", {})
    dump("/v1/metrics npu_resource after test", final_npu)
    require(final_npu.get("busy") is False, f"NPU guard should be released after VLM: {final_npu}")
    require(final_npu.get("rejected_busy", 0) >= 1, f"expected rejected_busy >= 1: {final_npu}")

    print("=== VLM NPU resource guard test passed ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
