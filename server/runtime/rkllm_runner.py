from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time


SPECIAL_TOKENS = [
    "＜|End of Input|＞",
    "<|End of Input|>",
    "<｜end▁of▁sentence｜>",
    "<|endoftext|>",
    "<|im_end|>",
    "<think>",
    "</think>",
    "<｜Response｜>:",
    "<｜Response｜>",
    "<｜Assistant｜>:",
    "<｜Assistant｜>",
]

STOP_MARKERS = [
    "\"这句话是否",
    "“这句话是否",
    "这句话是否",
    "需要检查",
    "首先，确认",
    "首先，我需要",
    "好的，用户",
    "用户让我",
    "接下来",
    "注：",
    "（注：",
    "注意：",
    "（注意：",
    "（注意",
    "\nYou:",
    "\nUser:",
    "\n<｜User｜>",
]


def clean_output(raw: str) -> str:
    lines: list[str] = []

    for line in raw.splitlines():
        s = line.strip()

        if not s:
            continue

        # Filter RKLLM and wrapper logs.
        if s.startswith(("I rkllm", "W rkllm", "E rkllm")):
            continue
        if s.startswith(("I ", "W ", "E ")):
            continue

        # Filter interactive prompts.
        if s in {"You:", "LLM:"}:
            continue
        if s.startswith("You:"):
            continue

        # Strip LLM callback prefix on each line.
        if s.startswith("LLM:"):
            s = s.split("LLM:", 1)[1].strip()
            if not s:
                continue
            line = s

        # Filter command/menu residues emitted by rkllm_enhanced or Qwen3.
        if s in {"/think", "/no_think", "/now", "/next", "/prev", "/exit", "/", "／"}:
            continue

        # Filter short noisy fragments occasionally emitted by Qwen3.
        if s in {"思科", "嗯", "嗯，", "。", "，"}:
            continue

        lines.append(line)

    text = "\n".join(lines).strip()

    for token in SPECIAL_TOKENS:
        text = text.replace(token, "")

    text = text.strip()
    text = re.sub(r"^[<\s]+", "", text).strip()
    text = re.sub(r"^LLM\s*[:：]\s*", "", text).strip()
    text = re.sub(r"^[:：]\s*", "", text).strip()

    # Remove thinking labels but do not delete real content after them blindly.
    text = text.replace("﹙思考过程﹚", "")
    text = text.replace("（思考过程）", "")
    text = text.replace("(思考过程)", "")
    text = text.strip()

    for marker in STOP_MARKERS:
        idx = text.find(marker)
        if idx > 0:
            text = text[:idx].strip()

    cleaned_lines = []
    for line in text.splitlines():
        s = line.strip()

        if not s:
            continue

        if s.startswith("LLM:"):
            s = s.split("LLM:", 1)[1].strip()

        s = s.replace("<think>", "").replace("</think>", "").strip()

        if not s:
            continue

        if "星期" in s or "2023年" in s:
            continue

        if "您似乎" in s or "遇到问题" in s:
            continue

        if s in {"/think", "/no_think", "/now", "/next", "/prev", "/exit", "/", "／"}:
            continue

        cleaned_lines.append(s)

    rk_lines = [line for line in cleaned_lines if "RK3588" in line]
    if rk_lines:
        return rk_lines[-1].strip()

    if cleaned_lines:
        return cleaned_lines[-1].strip()

    return text.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bin",
        default="/home/linaro/edgeinfer-rk3588-board/tools/rkllm_enhanced/rkllm_enhanced_no_template",
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--ctx", type=int, default=1024)
    parser.add_argument("--max-new", type=int, default=64)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--show-raw", action="store_true")
    args = parser.parse_args()

    cmd = [args.bin, args.model, str(args.ctx), str(args.max_new)]
    start = time.time()

    try:
        proc = subprocess.run(
            cmd,
            input=args.prompt + "\n",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=args.timeout,
        )
    except subprocess.TimeoutExpired as e:
        print("ERROR: rkllm command timeout", file=sys.stderr)
        if e.stdout:
            print(e.stdout, file=sys.stderr)
        if e.stderr:
            print(e.stderr, file=sys.stderr)
        return 124

    latency_ms = (time.time() - start) * 1000.0

    if args.show_raw:
        print("=== RAW_STDOUT_BEGIN ===")
        print(proc.stdout)
        print("=== RAW_STDOUT_END ===")
        print("=== RAW_STDERR_BEGIN ===")
        print(proc.stderr)
        print("=== RAW_STDERR_END ===")

    if proc.returncode != 0:
        print("ERROR: rkllm command failed", file=sys.stderr)
        print(f"returncode={proc.returncode}", file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        print(proc.stdout, file=sys.stderr)
        return proc.returncode

    text = clean_output(proc.stdout)

    print("=== CLEAN_TEXT_BEGIN ===")
    print(text)
    print("=== CLEAN_TEXT_END ===")
    print(f"latency_ms={latency_ms:.2f}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
