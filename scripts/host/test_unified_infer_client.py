#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

BOARD_URL = os.environ.get("EDGEINFER_BOARD_URL", "http://192.168.43.7:8000").rstrip("/")
TIMEOUT_SECONDS = float(os.environ.get("EDGEINFER_TEST_TIMEOUT_SECONDS", "120"))
IMAGE_PATH = os.environ.get(
    "EDGEINFER_VISION_TEST_IMAGE_PATH",
    "/home/linaro/edgeinfer-rk3588-board/datasets/coco128/images/train2017/000000000089.jpg",
)
VISION_MODEL = os.environ.get("EDGEINFER_VISION_TEST_MODEL", "YOLOv11n-FP-Baseline")
RUN_TEXT = os.environ.get("EDGEINFER_RUN_UNIFIED_TEXT", "0") == "1"


def post_json(path: str, payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BOARD_URL + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"raw": body}
        return exc.code, parsed


def get_json(path: str) -> Tuple[int, Dict[str, Any]]:
    with urllib.request.urlopen(BOARD_URL + path, timeout=TIMEOUT_SECONDS) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def print_json(title: str, data: Dict[str, Any]) -> None:
    print(title)
    print(json.dumps(data, ensure_ascii=False, indent=2))


def error_code(body: Dict[str, Any]) -> Optional[str]:
    detail = body.get("detail", body)
    if isinstance(detail, dict):
        error = detail.get("error")
        if isinstance(error, dict):
            return error.get("code")
    return None


def assert_task_list() -> None:
    status, body = get_json("/v1/infer/tasks")
    print_json("=== 1. unified infer task list ===", body)
    if status != 200:
        raise AssertionError(f"expected 200 from /v1/infer/tasks, got {status}")
    tasks = body.get("tasks")
    if not isinstance(tasks, dict):
        raise AssertionError(f"missing tasks map: {body!r}")
    for task in [
        "text-generation",
        "object-detection",
        "vision-language",
        "image-captioning",
        "visual-question-answering",
        "multimodal-chat",
    ]:
        if task not in tasks:
            raise AssertionError(f"missing task {task!r}: {tasks!r}")


def assert_object_detection() -> None:
    payload = {
        "task": "object-detection",
        "model": VISION_MODEL,
        "input": {"image_path": IMAGE_PATH},
        "parameters": {"confidence_threshold": 0.25, "iou_threshold": 0.45},
    }
    status, body = post_json("/v1/infer", payload)
    print_json("=== 2. unified object-detection ===", body)

    if status != 200:
        raise AssertionError(f"expected 200 from unified object-detection, got {status}: {body!r}")
    if body.get("object") != "edgeinfer.inference":
        raise AssertionError(f"unexpected object: {body!r}")
    if body.get("task") != "object-detection":
        raise AssertionError(f"unexpected task: {body!r}")

    output = body.get("output")
    if not isinstance(output, dict):
        raise AssertionError(f"missing output: {body!r}")
    if output.get("model") != VISION_MODEL:
        raise AssertionError(f"expected vision model {VISION_MODEL!r}, got {output.get('model')!r}")
    if not isinstance(output.get("objects"), list):
        raise AssertionError(f"objects must be a list: {output!r}")

    edgeinfer = body.get("edgeinfer") or {}
    if edgeinfer.get("route") != "/v1/vision/detect":
        raise AssertionError(f"expected vision route: {edgeinfer!r}")
    if edgeinfer.get("task_adapter") != "vision-detect":
        raise AssertionError(f"expected vision adapter: {edgeinfer!r}")

    print("unified object-detection check OK")


def assert_vlm_placeholder(task: str, input_payload: Dict[str, Any]) -> None:
    payload = {
        "task": task,
        "model": "future-vlm-model",
        "input": input_payload,
        "parameters": {"max_tokens": 64},
    }
    status, body = post_json("/v1/infer", payload)
    print_json(f"=== VLM placeholder: {task} ===", body)

    if status != 501:
        raise AssertionError(f"expected HTTP 501 for {task}, got {status}: {body!r}")
    if error_code(body) != "vlm_backend_not_ready":
        raise AssertionError(f"expected vlm_backend_not_ready for {task}: {body!r}")

    detail = body.get("detail") or {}
    edgeinfer = detail.get("edgeinfer") or {}
    if edgeinfer.get("backend") != "vlm-placeholder":
        raise AssertionError(f"expected vlm-placeholder backend: {body!r}")

    print(f"{task} placeholder check OK")


def assert_vlm_placeholders() -> None:
    assert_vlm_placeholder("vision-language", {"image_path": IMAGE_PATH, "text": "这张图片里有什么？"})
    assert_vlm_placeholder("image-captioning", {"image_path": IMAGE_PATH})
    assert_vlm_placeholder("visual-question-answering", {"image_path": IMAGE_PATH, "question": "图中有什么物体？"})
    assert_vlm_placeholder(
        "multimodal-chat",
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "请描述这张图。"},
                        {"type": "image_path", "image_path": IMAGE_PATH},
                    ],
                }
            ]
        },
    )


def assert_unsupported_task() -> None:
    status, body = post_json("/v1/infer", {"task": "audio-transcription", "input": {"audio_path": "/tmp/test.wav"}})
    print_json("=== unsupported task ===", body)

    if status != 400:
        raise AssertionError(f"expected HTTP 400 for unsupported task, got {status}: {body!r}")
    if error_code(body) != "unsupported_task":
        raise AssertionError(f"expected unsupported_task: {body!r}")

    print("unsupported task check OK")


def assert_text_generation_optional() -> None:
    payload = {
        "task": "text-generation",
        "input": {"messages": [{"role": "user", "content": "用一句话介绍 edgeinfer-rk3588。"}]},
        "parameters": {"max_tokens": 64, "temperature": 0.7},
    }
    status, body = post_json("/v1/infer", payload)
    print_json("=== optional unified text-generation ===", body)

    if status != 200:
        raise AssertionError(f"expected 200 from unified text-generation, got {status}: {body!r}")
    if body.get("task") not in {"text-generation", "chat-completion"}:
        raise AssertionError(f"unexpected text task output: {body!r}")

    print("optional unified text-generation check OK")


def main() -> int:
    started = time.time()
    print("=== EdgeInfer Unified Infer Client Test ===")
    print(f"BOARD_URL={BOARD_URL}")
    print(f"IMAGE_PATH={IMAGE_PATH}")
    print(f"VISION_MODEL={VISION_MODEL}")
    print(f"RUN_TEXT={RUN_TEXT}")
    print()

    assert_task_list()
    assert_object_detection()
    assert_vlm_placeholders()
    assert_unsupported_task()

    if RUN_TEXT:
        assert_text_generation_optional()
    else:
        print("skip optional text-generation test; set EDGEINFER_RUN_UNIFIED_TEXT=1 to enable it")

    print(f"=== unified infer client test passed in {time.time() - started:.3f}s ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
