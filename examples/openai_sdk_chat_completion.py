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

    completion = client.chat.completions.create(
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
        stream=False,
    )

    print("=== EdgeInfer OpenAI SDK chat completion example ===")
    print(f"base_url: {BASE_URL}")
    print(f"model: {MODEL_ID}")
    print(f"id: {completion.id}")
    print(f"object: {completion.object}")
    print(f"created: {completion.created}")

    choice = completion.choices[0]
    print(f"finish_reason: {choice.finish_reason}")
    print("assistant:")
    print(choice.message.content)

    edgeinfer = getattr(completion, "edgeinfer", None)
    if edgeinfer is not None:
        print()
        print("edgeinfer:")
        print(edgeinfer)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
