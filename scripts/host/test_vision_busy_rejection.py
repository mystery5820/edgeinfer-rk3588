#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import queue
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Tuple


BOARD_URL = os.environ.get("EDGEINFER_BOARD_URL", "http://192.168.43.7:8000").rstrip("/")
TIMEOUT_SECONDS = float(os.environ.get("EDGEINFER_TIMEOUT_SECONDS", "120"))
MODEL_ID = os.environ.get("EDGEINFER_VISION_TEST_MODEL", "YOLOv11n-FP-Baseline")
IMAGE_PATH = os.environ.get(
    "EDGEINFER_VISION_TEST_IMAGE_PATH",
    "/home/linaro/edgeinfer-rk3588-board/datasets/coco128/images/train2017/000000000089.jpg",
)
MAX_ATTEMPTS = int(os.environ.get("EDGEINFER_VISION_BUSY_TEST_ATTEMPTS", "5"))


def url(path: str) -> str:
    return BOARD_URL + "/" + path.lstrip("/")


def post_detect() -> Tuple[int, Dict[str, Any]]:
    payload = {
        "model": MODEL_ID,
        "image_path": IMAGE_PATH,
        "confidence_threshold": 0.25,
        "iou_threshold": 0.45,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url("/v1/vision/detect"),
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return int(resp.status), json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), json.loads(body)


def run_pair() -> list[Tuple[int, Dict[str, Any]]]:
    barrier = threading.Barrier(3)
    results: "queue.Queue[Tuple[int, Dict[str, Any]]]" = queue.Queue()

    def worker() -> None:
        barrier.wait()
        results.put(post_detect())

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(2)]
    for t in threads:
        t.start()

    barrier.wait()

    for t in threads:
        t.join(timeout=TIMEOUT_SECONDS + 5)

    out = []
    while not results.empty():
        out.append(results.get())
    return out


def error_code(body: Dict[str, Any]) -> str | None:
    detail = body.get("detail")
    if not isinstance(detail, dict):
        return None
    error = detail.get("error")
    if not isinstance(error, dict):
        return None
    return error.get("code")


def retryable(body: Dict[str, Any]) -> bool | None:
    detail = body.get("detail")
    if not isinstance(detail, dict):
        return None
    error = detail.get("error")
    if not isinstance(error, dict):
        return None
    return error.get("retryable")


def main() -> int:
    print("=== EdgeInfer Vision Busy Rejection Test ===")
    print(f"BOARD_URL={BOARD_URL}")
    print(f"MODEL_ID={MODEL_ID}")
    print(f"IMAGE_PATH={IMAGE_PATH}")
    print(f"MAX_ATTEMPTS={MAX_ATTEMPTS}")
    print()

    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"=== attempt {attempt} ===")
        pair = run_pair()
        pair.sort(key=lambda item: item[0])
        for status, body in pair:
            code = error_code(body)
            edgeinfer = body.get("edgeinfer") or (body.get("detail") or {}).get("edgeinfer") or {}
            backend = edgeinfer.get("backend")
            print(f"HTTP {status}, code={code}, backend={backend}")
            print(json.dumps(body, ensure_ascii=False, indent=2)[:4000])

        statuses = [status for status, _ in pair]
        has_success = any(status == 200 for status in statuses)
        has_busy = any(
            status == 429
            and error_code(body) == "vision_backend_busy"
            and retryable(body) is True
            for status, body in pair
        )

        if has_success and has_busy:
            print("busy rejection check OK")
            return 0

        print("pair did not overlap enough or returned unexpected result; retrying...")
        time.sleep(0.5)

    raise AssertionError("expected one successful vision request and one 429 vision_backend_busy response")


if __name__ == "__main__":
    raise SystemExit(main())
