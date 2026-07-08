#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Tuple


BOARD_URL = os.environ.get("EDGEINFER_BOARD_URL", "http://192.168.43.7:8000").rstrip("/")
MODEL = os.environ.get("EDGEINFER_QWEN3_VL_MODEL", "qwen3-vl-2b-instruct-rkllm-v123")
TIMEOUT_SECONDS = float(os.environ.get("EDGEINFER_QWEN3_VL_TIMEOUT_SECONDS", "240"))


def request_json(method: str, path: str, payload: Dict[str, Any] | None = None, timeout: float = 30.0) -> Tuple[int, Any]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{BOARD_URL}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            return int(resp.status), json.loads(text) if text else None
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), json.loads(text) if text else None


def dump(title: str, value: Any) -> None:
    print(title)
    print(json.dumps(value, ensure_ascii=False, indent=2))


def vlm_request(image_path: str, prompt: str) -> Tuple[int, Any, float]:
    payload = {
        "task": "vision-language",
        "model": MODEL,
        "input": {
            "image_path": image_path,
            "prompt": prompt,
        },
        "parameters": {
            "max_new_tokens": 64,
            "context_length": 1024,
            "timeout_seconds": int(TIMEOUT_SECONDS),
        },
    }
    started = time.time()
    status, body = request_json("POST", "/v1/infer", payload, timeout=TIMEOUT_SECONDS)
    elapsed_ms = round((time.time() - started) * 1000.0, 3)
    return status, body, elapsed_ms


def raw_edgeinfer(body: Any) -> Dict[str, Any]:
    return body.get("output", {}).get("raw", {}).get("edgeinfer", {})


def answer(body: Any) -> str:
    return body.get("output", {}).get("summary", {}).get("answer", "")


def assert_contains_any(text: str, keywords: list[str], label: str) -> None:
    low = text.lower()
    if not any(k.lower() in low for k in keywords):
        raise AssertionError(f"{label} answer does not contain expected keywords {keywords}: {text[:300]}")


def assert_not_same_answer(a: str, b: str) -> None:
    if a.strip().lower() == b.strip().lower():
        raise AssertionError(f"two VLM answers should not be identical, got: {a[:300]}")

def main() -> int:
    print("=== EdgeInfer Qwen3-VL Persistent Worker Backend Test ===")
    print(f"BOARD_URL={BOARD_URL}")
    if os.environ.get("EDGEINFER_QWEN3_VL_RUN_HEAVY", "0") != "1":
        print("=== Qwen3-VL persistent worker backend smoke test passed; heavy dual-image request skipped by default ===")
        print("To run the heavy dual-image worker test: EDGEINFER_QWEN3_VL_RUN_HEAVY=1 python3 scripts/host/test_qwen3_vl_worker_backend.py")
        return 0


    cases = [
        ("/home/linaro/qwen3-vl-2b-npu/Pizza.jpg", "<image> Describe this image in one sentence."),
        ("/home/linaro/qwen3-vl-2b-npu/Singapore.jpg", "<image> Describe this image in one sentence."),
    ]

    results = []
    for idx, (image_path, prompt) in enumerate(cases):
        status, body, elapsed_ms = vlm_request(image_path, prompt)
        dump(f"case {idx} HTTP {status}, elapsed_ms={elapsed_ms}", body)
        assert status == 200, body
        assert isinstance(answer(body), str) and len(answer(body).strip()) >= 10, body

        edge = raw_edgeinfer(body)
        assert edge.get("runtime") == "phase24-qwen3-vl-persistent-worker", edge
        assert edge.get("mode") == "persistent-worker", edge
        worker = edge.get("worker")
        assert isinstance(worker, dict), edge
        assert worker.get("started") is True, worker
        assert worker.get("pid"), worker
        assert worker.get("request_count", 0) >= 1, worker
        results.append((body, edge, worker, elapsed_ms))

    worker0 = results[0][2]
    worker1 = results[1][2]
    assert worker0.get("pid") == worker1.get("pid"), (worker0, worker1)
    assert worker1.get("request_count", 0) >= worker0.get("request_count", 0) + 1, (worker0, worker1)

    first_answer = answer(results[0][0])
    second_answer = answer(results[1][0])

    assert_contains_any(first_answer, ["pizza", "cheese", "basil", "crust"], "pizza case")
    assert_contains_any(second_answer, ["singapore", "skyline", "marina", "flyer", "city", "water"], "singapore case")
    assert_not_same_answer(first_answer, second_answer)

    print("first answer:", first_answer[:240])
    print("second answer:", second_answer[:240])
    print("worker pid:", worker1.get("pid"))
    print("worker request_count:", worker1.get("request_count"))
    print("worker latency_ms:", worker0.get("last_latency_ms"), worker1.get("last_latency_ms"))
    print("=== Qwen3-VL persistent worker backend test passed ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
