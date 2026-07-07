#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple


BOARD_URL = os.environ.get("EDGEINFER_BOARD_URL", "http://192.168.43.7:8000").rstrip("/")
VISION_MODEL = os.environ.get("EDGEINFER_VISION_MODEL", "YOLOv11n-FP-Baseline")
LLM_MODEL = os.environ.get("EDGEINFER_LLM_MODEL", "qwen3-4b-rkllm-all-npu")
IMAGE_PATH = os.environ.get(
    "EDGEINFER_IMAGE_PATH",
    "/home/linaro/edgeinfer-rk3588-board/datasets/coco128/images/train2017/000000000089.jpg",
)
TIMEOUT_SECONDS = float(os.environ.get("EDGEINFER_NPU_GUARD_TIMEOUT_SECONDS", "180"))
LLM_LONG_MAX_NEW = int(os.environ.get("EDGEINFER_NPU_GUARD_LLM_LONG_MAX_NEW", "96"))
LLM_SHORT_MAX_NEW = int(os.environ.get("EDGEINFER_NPU_GUARD_LLM_SHORT_MAX_NEW", "8"))


def _read_json_response(resp) -> Any:
    text = resp.read().decode("utf-8", errors="replace")
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def get_json(path: str, *, timeout: float = 10.0) -> Tuple[int, Any]:
    url = f"{BOARD_URL}{path}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), _read_json_response(resp)
    except urllib.error.HTTPError as exc:
        return int(exc.code), _read_json_response(exc)


def post_json(path: str, payload: Dict[str, Any], *, timeout: float = TIMEOUT_SECONDS) -> Tuple[int, Any]:
    url = f"{BOARD_URL}{path}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), _read_json_response(resp)
    except urllib.error.HTTPError as exc:
        return int(exc.code), _read_json_response(exc)


def error_code(body: Any) -> Optional[str]:
    if not isinstance(body, dict):
        return None
    detail = body.get("detail")
    if not isinstance(detail, dict):
        return None
    err = detail.get("error")
    if not isinstance(err, dict):
        return None
    code = err.get("code")
    return code if isinstance(code, str) else None


def npu_snapshot() -> Dict[str, Any]:
    status, body = get_json("/v1/metrics")
    if status != 200 or not isinstance(body, dict):
        raise AssertionError(f"metrics failed: status={status}, body={body!r}")
    snap = body.get("npu_resource")
    if not isinstance(snap, dict):
        raise AssertionError(f"metrics missing npu_resource: {body!r}")
    return snap


def print_json(title: str, value: Any) -> None:
    print(title)
    print(json.dumps(value, ensure_ascii=False, indent=2))


class BackgroundPost:
    def __init__(self, path: str, payload: Dict[str, Any], *, timeout: float = TIMEOUT_SECONDS):
        self.path = path
        self.payload = payload
        self.timeout = timeout
        self.status: Optional[int] = None
        self.body: Any = None
        self.error: Optional[BaseException] = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        try:
            self.status, self.body = post_json(self.path, self.payload, timeout=self.timeout)
        except BaseException as exc:
            self.error = exc

    def start(self) -> None:
        self.thread.start()

    def join(self) -> None:
        self.thread.join(timeout=self.timeout + 10)
        if self.thread.is_alive():
            raise AssertionError(f"background request still running: {self.path}")
        if self.error is not None:
            raise AssertionError(f"background request failed: {self.error!r}")


def wait_npu_owner(owner: str, *, timeout: float = 10.0) -> Dict[str, Any]:
    deadline = time.time() + timeout
    last: Dict[str, Any] = {}
    while time.time() < deadline:
        last = npu_snapshot()
        if last.get("busy") is True and last.get("current_owner") == owner:
            return last
        time.sleep(0.05)
    raise AssertionError(f"NPU owner {owner!r} not observed, last snapshot={last!r}")


def assert_npu_busy_response(status: int, body: Any, *, expected_current_owner: str) -> None:
    if status != 429:
        raise AssertionError(f"expected HTTP 429, got {status}, body={body!r}")
    if error_code(body) != "npu_resource_busy":
        raise AssertionError(f"expected npu_resource_busy, got body={body!r}")

    detail = body.get("detail", {}) if isinstance(body, dict) else {}
    edgeinfer = detail.get("edgeinfer", {}) if isinstance(detail, dict) else {}
    snap = edgeinfer.get("npu_resource", {}) if isinstance(edgeinfer, dict) else {}
    if snap.get("current_owner") != expected_current_owner:
        raise AssertionError(
            f"expected current_owner={expected_current_owner!r}, got snapshot={snap!r}"
        )


def test_llm_blocks_vision() -> None:
    print("=== 1. LLM running, Vision should get npu_resource_busy ===")
    llm_payload = {
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "user",
                "content": "请用三句话介绍RK3588的CPU、NPU和端侧AI应用。",
            }
        ],
        "max_new_tokens": LLM_LONG_MAX_NEW,
        "temperature": 0.7,
        "stream": False,
    }
    vision_payload = {
        "model": VISION_MODEL,
        "image_path": IMAGE_PATH,
    }

    bg = BackgroundPost("/v1/chat/completions", llm_payload)
    bg.start()

    snap = wait_npu_owner("chat-completions", timeout=15.0)
    print_json("observed LLM owner:", snap)

    status, body = post_json("/v1/vision/detect", vision_payload, timeout=30.0)
    print_json(f"vision while LLM: HTTP {status}", body)
    assert_npu_busy_response(status, body, expected_current_owner="chat-completions")

    bg.join()
    if bg.status != 200:
        raise AssertionError(f"background LLM expected 200, got {bg.status}, body={bg.body!r}")

    snap = npu_snapshot()
    print_json("after LLM done:", snap)
    if snap.get("busy") is not False:
        raise AssertionError(f"NPU guard not released after LLM: {snap!r}")


def test_vision_blocks_llm() -> None:
    print("=== 2. Vision running, LLM should get npu_resource_busy ===")
    vision_payload = {
        "model": VISION_MODEL,
        "image_path": IMAGE_PATH,
    }
    llm_payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "user", "content": "用一句话介绍RK3588。"}
        ],
        "max_new_tokens": LLM_SHORT_MAX_NEW,
        "temperature": 0.7,
        "stream": False,
    }

    bg = BackgroundPost("/v1/vision/detect", vision_payload, timeout=60.0)
    bg.start()

    try:
        snap = wait_npu_owner("vision-detect", timeout=3.0)
        print_json("observed Vision owner:", snap)
    except AssertionError:
        # Vision can finish quickly on a warm worker. A short sleep usually catches the
        # in-flight request, but keep this fallback message explicit for diagnosis.
        time.sleep(0.05)

    status, body = post_json("/v1/chat/completions", llm_payload, timeout=TIMEOUT_SECONDS)
    print_json(f"LLM while Vision: HTTP {status}", body)
    assert_npu_busy_response(status, body, expected_current_owner="vision-detect")

    bg.join()
    if bg.status != 200:
        raise AssertionError(f"background Vision expected 200, got {bg.status}, body={bg.body!r}")

    snap = npu_snapshot()
    print_json("after Vision done:", snap)
    if snap.get("busy") is not False:
        raise AssertionError(f"NPU guard not released after Vision: {snap!r}")


def main() -> int:
    print("=== EdgeInfer Phase 20 NPU Resource Guard Test ===")
    print(f"BOARD_URL={BOARD_URL}")
    print(f"VISION_MODEL={VISION_MODEL}")
    print(f"LLM_MODEL={LLM_MODEL}")
    print(f"IMAGE_PATH={IMAGE_PATH}")

    initial = npu_snapshot()
    print_json("initial npu_resource:", initial)

    test_llm_blocks_vision()
    test_vision_blocks_llm()

    final = npu_snapshot()
    print_json("final npu_resource:", final)

    print("=== NPU resource guard test passed ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
