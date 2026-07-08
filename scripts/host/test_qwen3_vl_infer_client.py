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
IMAGE_PATH = os.environ.get("EDGEINFER_QWEN3_VL_IMAGE_PATH", "/home/linaro/qwen3-vl-2b-npu/Pizza.jpg")
TIMEOUT_SECONDS = float(os.environ.get("EDGEINFER_QWEN3_VL_TIMEOUT_SECONDS", "240"))


def _json(resp) -> Any:
    text = resp.read().decode("utf-8", errors="replace")
    return json.loads(text) if text else None


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
            return int(resp.status), _json(resp)
    except urllib.error.HTTPError as exc:
        return int(exc.code), _json(exc)


def dump(title: str, value: Any) -> None:
    print(title)
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main() -> int:
    print("=== EdgeInfer Qwen3-VL Infer Client Test ===")
    print(f"BOARD_URL={BOARD_URL}")
    print(f"MODEL={MODEL}")
    print(f"IMAGE_PATH={IMAGE_PATH}")

    status, tasks_body = request_json("GET", "/v1/infer/tasks")
    dump(f"/v1/infer/tasks HTTP {status}", tasks_body)
    assert status == 200, tasks_body

    tasks = tasks_body.get("tasks", {})
    for task in ("vision-language", "image-captioning", "visual-question-answering", "multimodal-chat"):
        info = tasks.get(task)
        assert isinstance(info, dict), tasks
        assert info.get("status") == "adapter", info
        assert info.get("backend") == "qwen3-vl-rkllm-rknn-runner", info

    payload = {
        "task": "vision-language",
        "model": MODEL,
        "input": {
            "image_path": IMAGE_PATH,
            "prompt": "<image> Describe this image in one sentence.",
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
    dump(f"/v1/infer vision-language HTTP {status}, elapsed_ms={elapsed_ms}", body)
    assert status == 200, body
    assert body.get("task") == "vision-language", body

    output = body.get("output", {})
    summary = output.get("summary", {})
    data = output.get("data", {})
    raw = output.get("raw", {})
    answer = summary.get("answer")
    assert isinstance(answer, str) and len(answer.strip()) >= 10, summary
    assert data.get("answer") == answer, data
    assert raw.get("answer") == answer, raw

    edgeinfer = body.get("edgeinfer", {})
    assert edgeinfer.get("backend") == "qwen3-vl-rkllm-rknn-runner", edgeinfer
    assert edgeinfer.get("source_runtime") == "phase22-qwen3-vl-rk3588-backend", edgeinfer
    assert edgeinfer.get("dispatch", {}).get("adapter") == "qwen3-vl", edgeinfer

    status, metrics = request_json("GET", "/v1/metrics")
    npu = metrics.get("npu_resource", {}) if isinstance(metrics, dict) else {}
    dump("/v1/metrics npu_resource", npu)
    assert status == 200, metrics
    assert npu.get("busy") is False, npu

    print("VLM answer:", answer)
    print("=== Qwen3-VL infer client test passed ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
