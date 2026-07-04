#!/usr/bin/env python3
from __future__ import annotations

import os
import sys


BOARD_URL = os.environ.get("EDGEINFER_BOARD_URL", "http://192.168.43.7:8000").rstrip("/")
BASE_URL = os.environ.get("EDGEINFER_OPENAI_BASE_URL", f"{BOARD_URL}/v1")
MODEL_ID = os.environ.get("EDGEINFER_MODEL_ID", "qwen3-4b-rkllm-all-npu")
API_KEY = os.environ.get("EDGEINFER_OPENAI_API_KEY", "edgeinfer-local")


def main() -> int:
    try:
        from openai import OpenAI
    except ImportError:
        print(
            "ERROR: missing dependency: openai\n"
            "Install it with: python3 -m pip install openai",
            file=sys.stderr,
        )
        return 1

    client = OpenAI(
        base_url=BASE_URL,
        api_key=API_KEY,
    )

    print("=== EdgeInfer OpenAI SDK streaming chat example ===")
    print(f"base_url: {BASE_URL}")
    print(f"model: {MODEL_ID}")
    print()
    print("assistant:")
    print("", end="", flush=True)

    stream = client.chat.completions.create(
        model=MODEL_ID,
        messages=[
            {
                "role": "system",
                "content": "你是 EdgeInfer-RK3588 端侧推理助手。",
            },
            {
                "role": "user",
                "content": "请用一句话介绍 RK3588。",
            },
        ],
        max_tokens=64,
        stream=True,
    )

    content_parts: list[str] = []
    final_finish_reason = None

    for chunk in stream:
        if not chunk.choices:
            continue

        choice = chunk.choices[0]
        delta = choice.delta

        content = getattr(delta, "content", None)
        if content:
            content_parts.append(content)
            print(content, end="", flush=True)

        if choice.finish_reason is not None:
            final_finish_reason = choice.finish_reason

    print()
    print()
    print(f"finish_reason: {final_finish_reason}")
    print(f"assistant_content_length: {len(''.join(content_parts))}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
