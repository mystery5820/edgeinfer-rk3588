#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

BOARD_URL = os.environ.get("EDGEINFER_BOARD_URL", "http://192.168.43.7:8000").rstrip("/")
BASE_URL = os.environ.get("EDGEINFER_OPENAI_BASE_URL", f"{BOARD_URL}/v1")


def run(cmd: list[str], *, expect_success: bool = True) -> int:
    print()
    print("+ " + " ".join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT, text=True)
    if expect_success and proc.returncode != 0:
        raise RuntimeError(f"command failed with status {proc.returncode}: {' '.join(cmd)}")
    return proc.returncode


def main() -> int:
    print("=== EdgeInfer OpenAI SDK example smoke test ===")
    print(f"ROOT={ROOT}")
    print(f"BOARD_URL={BOARD_URL}")
    print(f"BASE_URL={BASE_URL}")

    try:
        import openai  # noqa: F401
    except ImportError:
        print(
            "SKIP: Python package 'openai' is not installed.\n"
            "Install it with: python3 -m pip install openai",
            file=sys.stderr,
        )
        return 77

    run([sys.executable, "examples/openai_sdk_chat_completion.py"])

    # The streaming example succeeds only when the board service is running in
    # RKLLM persistent worker mode. In default one-shot mode the server should
    # reject stream=true with stream_backend_not_supported, which is already
    # covered by scripts/host/test_openai_chat_client.py.
    if os.environ.get("EDGEINFER_EXPECT_STREAM", "0") == "1":
        run([sys.executable, "examples/openai_sdk_streaming_chat.py"])
    else:
        print()
        print("streaming SDK example skipped by default")
        print("Set EDGEINFER_EXPECT_STREAM=1 after enabling worker mode to run it.")

    print()
    print("=== OpenAI SDK example smoke test completed ===")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
