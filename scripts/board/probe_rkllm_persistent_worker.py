#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import os
import select
import subprocess
import sys
import time
from dataclasses import dataclass


DEFAULT_BIN = "/home/linaro/edgeinfer-rk3588-board/tools/rkllm_enhanced/rkllm_enhanced_no_template"
DEFAULT_MODEL = "/userdata/edgeinfer-assets/models/llm/rkllm_outputs/Qwen3-4B-w8a8-npu.rkllm"


@dataclass
class ProbeResult:
    name: str
    latency_ms: float
    text: str


def set_nonblocking(fd: int) -> None:
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)


def read_available(proc: subprocess.Popen[bytes], timeout_s: float) -> str:
    assert proc.stdout is not None
    fd = proc.stdout.fileno()
    end = time.time() + timeout_s
    chunks: list[bytes] = []

    while time.time() < end:
        if proc.poll() is not None:
            break

        remaining = max(0.0, end - time.time())
        rlist, _, _ = select.select([fd], [], [], min(0.2, remaining))
        if not rlist:
            continue

        try:
            data = os.read(fd, 65536)
        except BlockingIOError:
            continue

        if not data:
            break

        chunks.append(data)

    return b"".join(chunks).decode("utf-8", errors="replace")


def read_until(
    proc: subprocess.Popen[bytes],
    *,
    markers: tuple[str, ...],
    timeout_s: float,
    label: str,
) -> str:
    assert proc.stdout is not None
    fd = proc.stdout.fileno()
    end = time.time() + timeout_s
    chunks: list[bytes] = []

    while time.time() < end:
        if proc.poll() is not None:
            leftover = b"".join(chunks).decode("utf-8", errors="replace")
            raise RuntimeError(
                f"process exited while waiting for {label}, "
                f"returncode={proc.returncode}, partial={leftover[-1000:]}"
            )

        remaining = max(0.0, end - time.time())
        rlist, _, _ = select.select([fd], [], [], min(0.2, remaining))
        if not rlist:
            continue

        try:
            data = os.read(fd, 65536)
        except BlockingIOError:
            continue

        if not data:
            continue

        chunks.append(data)
        text = b"".join(chunks).decode("utf-8", errors="replace")
        if any(marker in text for marker in markers):
            return text

    text = b"".join(chunks).decode("utf-8", errors="replace")
    raise TimeoutError(f"timeout waiting for {label}, markers={markers!r}, partial={text[-1000:]}")


def clean_response(raw: str) -> str:
    text = raw

    if "LLM:" in text:
        text = text.split("LLM:", 1)[1]

    if "<|im_end|>" in text:
        text = text.split("<|im_end|>", 1)[0]

    if "\nYou:" in text:
        text = text.split("\nYou:", 1)[0]

    if "\r\nYou:" in text:
        text = text.split("\r\nYou:", 1)[0]

    for token in ("<|im_end|>", "</think>", "<think>"):
        text = text.replace(token, "")

    return " ".join(text.strip().split())


def send_prompt(
    proc: subprocess.Popen[bytes],
    *,
    name: str,
    prompt: str,
    timeout_s: float,
) -> ProbeResult:
    assert proc.stdin is not None

    prompt_line = " ".join(prompt.replace("\r", " ").replace("\n", " ").split())

    start = time.time()
    proc.stdin.write((prompt_line + "\n").encode("utf-8"))
    proc.stdin.flush()

    raw = read_until(
        proc,
        markers=("<|im_end|>", "\nYou:", "\r\nYou:"),
        timeout_s=timeout_s,
        label=f"{name} response",
    )
    latency_ms = (time.time() - start) * 1000.0

    return ProbeResult(
        name=name,
        latency_ms=round(latency_ms, 3),
        text=clean_response(raw),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bin", default=DEFAULT_BIN)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--ctx", type=int, default=1024)
    parser.add_argument("--max-new", type=int, default=64)
    parser.add_argument("--startup-timeout", type=float, default=60.0)
    parser.add_argument("--request-timeout", type=float, default=90.0)
    args = parser.parse_args()

    cmd = [
        args.bin,
        args.model,
        str(args.ctx),
        str(args.max_new),
    ]

    print("=== RKLLM persistent worker probe ===")
    print("cmd:", " ".join(cmd))
    print()

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
    )

    assert proc.stdout is not None
    set_nonblocking(proc.stdout.fileno())

    try:
        startup_start = time.time()
        startup_log = read_until(
            proc,
            markers=("You:",),
            timeout_s=args.startup_timeout,
            label="initial prompt",
        )
        startup_ms = round((time.time() - startup_start) * 1000.0, 3)

        print("startup_ms:", startup_ms)
        print("loading_count_startup:", startup_log.count("loading rkllm model"))
        print()

        prompt1 = "/no_think 已知事实：RK3588 是瑞芯微 Rockchip 推出的高性能 AIoT SoC，采用四核 Cortex-A76 加四核 Cortex-A55 架构，内置 NPU。请用一句话介绍 RK3588。"
        prompt2 = "/no_think 已知事实：RK3588 内置 NPU，可用于端侧 AI 推理。请用一句话说明 RK3588 为什么适合端侧 AI。"

        r1 = send_prompt(proc, name="first", prompt=prompt1, timeout_s=args.request_timeout)
        print("first_latency_ms:", r1.latency_ms)
        print("first_text:", r1.text)
        print()

        # Drain the next "You:" prompt if it has already been printed.
        _ = read_available(proc, timeout_s=0.5)

        r2 = send_prompt(proc, name="second", prompt=prompt2, timeout_s=args.request_timeout)
        print("second_latency_ms:", r2.latency_ms)
        print("second_text:", r2.text)
        print()

        print("summary:")
        print("  startup_ms:", startup_ms)
        print("  first_latency_ms:", r1.latency_ms)
        print("  second_latency_ms:", r2.latency_ms)
        print("  second_is_faster:", r2.latency_ms < r1.latency_ms)

        return 0

    finally:
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass

        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
