#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

BOARD_URL = os.environ.get("EDGEINFER_BOARD_URL", "http://192.168.43.7:8000").rstrip("/")
MODEL_ID = os.environ.get("EDGEINFER_MODEL_ID", "qwen3-4b-rkllm-all-npu")
TIMEOUT_SECONDS = float(os.environ.get("EDGEINFER_OPENAI_CLIENT_TIMEOUT", "120"))


def _json_dumps(data: Dict[str, Any]) -> bytes:
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def request_json(
    method: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    expected_status: Optional[int] = None,
) -> Tuple[int, Dict[str, Any]]:
    url = f"{BOARD_URL}{path}"
    data = _json_dumps(payload) if payload is not None else None

    headers = {}
    if payload is not None:
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"request failed: {url}: {exc}") from exc

    try:
        body = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"non-json response from {url}, HTTP {status}: {raw!r}") from exc

    if expected_status is not None and status != expected_status:
        raise AssertionError(
            f"{method} {path} expected HTTP {expected_status}, got {status}: "
            f"{json.dumps(body, ensure_ascii=False)}"
        )

    return status, body


def get_error_code(body: Dict[str, Any]) -> str:
    return str(body.get("detail", {}).get("error", {}).get("code", ""))


def get_assistant_content(body: Dict[str, Any]) -> str:
    choices = body.get("choices") or []
    if not choices:
        raise AssertionError("response has no choices")

    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str):
        raise AssertionError(f"assistant content is not a string: {content!r}")

    return content


def print_chat_summary(label: str, body: Dict[str, Any]) -> None:
    content = get_assistant_content(body)
    edgeinfer = body.get("edgeinfer", {})
    backend = edgeinfer.get("backend")
    latency_ms = edgeinfer.get("latency_ms")
    stop_info = edgeinfer.get("stop")

    print(f"--- {label} ---")
    print(f"backend: {backend}")
    print(f"latency_ms: {latency_ms}")
    if stop_info is not None:
        print(f"stop: {json.dumps(stop_info, ensure_ascii=False)}")
    print(f"assistant_content_length: {len(content)}")
    print(f"assistant_content: {content}")
    print()


def assert_backend_present(body: Dict[str, Any]) -> None:
    backend = body.get("edgeinfer", {}).get("backend")
    if not backend:
        raise AssertionError("response edgeinfer.backend is missing")


def test_health() -> None:
    print("=== 1. health ===")
    _, body = request_json("GET", "/v1/health", expected_status=200)
    print(json.dumps(body, ensure_ascii=False, indent=2))
    print()


def test_max_tokens_chat() -> None:
    print("=== 2. chat with max_tokens ===")
    payload = {
        "model": MODEL_ID,
        "messages": [
            {
                "role": "system",
                "content": "你是 EdgeInfer-RK3588 端侧推理助手。",
            },
            {
                "role": "user",
                "content": "请用一句话介绍 RK3588。",
            },
        ],
        "max_tokens": 48,
    }

    _, body = request_json("POST", "/v1/chat/completions", payload, expected_status=200)
    assert_backend_present(body)
    print_chat_summary("max_tokens chat", body)


def test_stop_sequences() -> None:
    print("=== 3. chat with stop sequences ===")
    stop_sequences = ["RK3588", "瑞芯微"]
    payload = {
        "model": MODEL_ID,
        "messages": [
            {
                "role": "system",
                "content": "你是 EdgeInfer-RK3588 端侧推理助手。",
            },
            {
                "role": "user",
                "content": "请用一句话介绍 RK3588。",
            },
        ],
        "max_tokens": 48,
        "stop": stop_sequences,
    }

    _, body = request_json("POST", "/v1/chat/completions", payload, expected_status=200)
    assert_backend_present(body)
    content = get_assistant_content(body)

    leaked = [seq for seq in stop_sequences if seq in content]
    if leaked:
        raise AssertionError(f"stop sequences leaked into assistant content: {leaked!r}")

    stop_info = body.get("edgeinfer", {}).get("stop")
    if not isinstance(stop_info, dict):
        raise AssertionError(f"edgeinfer.stop is missing or invalid: {stop_info!r}")

    requested = stop_info.get("requested")
    if requested != stop_sequences:
        raise AssertionError(
            f"edgeinfer.stop.requested mismatch: expected {stop_sequences!r}, got {requested!r}"
        )

    print_chat_summary("stop sequences chat", body)


def test_stream_rejected() -> None:
    print("=== 4. stream=true rejection ===")
    payload = {
        "model": MODEL_ID,
        "messages": [
            {
                "role": "user",
                "content": "请用一句话介绍 RK3588。",
            }
        ],
        "max_tokens": 16,
        "stream": True,
    }

    status, body = request_json("POST", "/v1/chat/completions", payload, expected_status=400)
    code = get_error_code(body)
    if code != "stream_not_supported":
        raise AssertionError(f"expected stream_not_supported, got {code!r}: {body!r}")

    print(f"HTTP {status}")
    print(json.dumps(body, ensure_ascii=False, indent=2))
    print("stream rejection check OK")
    print()


def main() -> int:
    started = time.time()

    print("=== EdgeInfer OpenAI-like Chat Client Test ===")
    print(f"BOARD_URL={BOARD_URL}")
    print(f"MODEL_ID={MODEL_ID}")
    print(f"TIMEOUT_SECONDS={TIMEOUT_SECONDS}")
    print()

    try:
        test_health()
        test_max_tokens_chat()
        test_stop_sequences()
        test_stream_rejected()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    elapsed = time.time() - started
    print(f"=== OpenAI-like chat client test passed in {elapsed:.3f}s ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
