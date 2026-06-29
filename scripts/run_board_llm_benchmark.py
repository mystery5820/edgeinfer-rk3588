#!/usr/bin/env python3
import argparse
import csv
import os
import pathlib
import pty
import re
import select
import subprocess
import sys
import time


MODEL_MAP = {
    "Qwen2.5-0.5B-Instruct": "models/llm/rkllm_outputs/qwen2_5_0_5b_instruct_w8a8_opt1_ctx2048_rk3588.rkllm",
    "Qwen2.5-1.5B-Instruct": "models/llm/rkllm_outputs/qwen2_5_1_5b_instruct_w8a8_opt1_ctx2048_rk3588.rkllm",
}


DEFAULT_PROMPTS = [
    ("identity", "请用一句话说明你当前正在运行在哪类硬件平台上。"),
    ("rk3588_intro", "请用三句话介绍 RK3588 的主要特点。"),
    ("edge_ai", "请用三句话说明边缘 AI 推理部署的意义。"),
    ("python_sort", "请用 Python 写一个冒泡排序函数，只输出代码。"),
]


def read_available(fd, timeout=0.2):
    chunks = []
    end_time = time.time() + timeout
    while time.time() < end_time:
        r, _, _ = select.select([fd], [], [], 0.05)
        if not r:
            continue
        try:
            data = os.read(fd, 4096)
        except OSError:
            break
        if not data:
            break
        chunks.append(data.decode("utf-8", errors="ignore"))
    return "".join(chunks)


def read_until(fd, patterns, timeout):
    buf = ""
    end_time = time.time() + timeout
    compiled = [re.compile(p) for p in patterns]
    while time.time() < end_time:
        chunk = read_available(fd, timeout=0.2)
        if chunk:
            buf += chunk
            if any(p.search(buf) for p in compiled):
                return buf
        else:
            time.sleep(0.05)
    return buf


def parse_float(pattern, text):
    m = re.search(pattern, text, re.S)
    return float(m.group(1)) if m else None


def parse_int(pattern, text):
    m = re.search(pattern, text, re.S)
    return int(m.group(1)) if m else None


def parse_metrics(raw):
    metrics = {}

    metrics["model_init_ms"] = parse_float(r"Model init time \(ms\)\s+([0-9.]+)", raw)
    metrics["peak_memory_mb"] = parse_float(r"Peak Memory Usage \(MB\)\s*I rkllm:\s*([0-9.]+)", raw)

    prefill = re.search(
        r"Prefill\s+([0-9.]+)\s+([0-9]+)\s+([0-9.]+)\s+([0-9.]+)",
        raw,
    )
    if prefill:
        metrics["prefill_total_ms"] = float(prefill.group(1))
        metrics["prefill_tokens"] = int(prefill.group(2))
        metrics["prefill_ms_per_token"] = float(prefill.group(3))
        metrics["prefill_tokens_per_second"] = float(prefill.group(4))

    generate = re.search(
        r"Generate\s+([0-9.]+)\s+([0-9]+)\s+([0-9.]+)\s+([0-9.]+)",
        raw,
    )
    if generate:
        metrics["generate_total_ms"] = float(generate.group(1))
        metrics["generate_tokens"] = int(generate.group(2))
        metrics["generate_ms_per_token"] = float(generate.group(3))
        metrics["generate_tokens_per_second"] = float(generate.group(4))

    return metrics


def run_one_prompt(args, prompt_name, prompt_text, raw_dir):
    project_root = pathlib.Path(__file__).resolve().parents[1]
    runtime_dir = project_root / "third_party" / "rkllm_runtime"
    demo_bin = runtime_dir / "llm_demo"
    model_path = project_root / MODEL_MAP[args.model]

    if not demo_bin.exists():
        raise FileNotFoundError(f"llm_demo not found: {demo_bin}")
    if not model_path.exists():
        raise FileNotFoundError(f"model not found: {model_path}")

    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = f"{runtime_dir / 'lib'}:{env.get('LD_LIBRARY_PATH', '')}"
    env["RKLLM_LOG_LEVEL"] = env.get("RKLLM_LOG_LEVEL", "1")

    cmd = [
        str(demo_bin),
        str(model_path),
        str(args.max_new_tokens),
        str(args.max_context),
    ]

    master_fd, slave_fd = pty.openpty()

    proc = subprocess.Popen(
        cmd,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        cwd=str(project_root),
        env=env,
        close_fds=True,
        text=False,
    )
    os.close(slave_fd)

    raw = ""
    try:
        init_text = read_until(master_fd, [r"user:\s*$"], timeout=args.init_timeout)
        raw += init_text

        os.write(master_fd, (prompt_text + "\n").encode("utf-8"))

        answer_text = read_until(master_fd, [r"Peak Memory Usage", r"user:\s*$"], timeout=args.generate_timeout)
        raw += answer_text

        tail_text = read_until(master_fd, [r"user:\s*$"], timeout=5)
        raw += tail_text

    finally:
        try:
            os.write(master_fd, b"\x03")
        except OSError:
            pass
        time.sleep(0.5)
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        os.close(master_fd)

    raw_path = raw_dir / f"{prompt_name}.log"
    raw_path.write_text(raw, encoding="utf-8", errors="ignore")

    metrics = parse_metrics(raw)
    metrics.update(
        {
            "model": args.model,
            "prompt_name": prompt_name,
            "prompt": prompt_text,
            "raw_log": str(raw_path),
        }
    )
    return metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen2.5-0.5B-Instruct", choices=sorted(MODEL_MAP))
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--max-context", type=int, default=2048)
    parser.add_argument("--init-timeout", type=int, default=120)
    parser.add_argument("--generate-timeout", type=int, default=180)
    parser.add_argument("--output-dir", default="benchmark_results/llm_qwen25_0_5b")
    args = parser.parse_args()

    project_root = pathlib.Path(__file__).resolve().parents[1]
    output_dir = project_root / args.output_dir
    raw_dir = output_dir / "raw_logs"
    raw_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for prompt_name, prompt_text in DEFAULT_PROMPTS:
        print(f"\n========== {args.model} / {prompt_name} ==========")
        row = run_one_prompt(args, prompt_name, prompt_text, raw_dir)
        rows.append(row)
        print(f"generate_tps: {row.get('generate_tokens_per_second')}")
        print(f"peak_memory_mb: {row.get('peak_memory_mb')}")

    csv_path = output_dir / "llm_benchmark.csv"
    fieldnames = [
        "model",
        "prompt_name",
        "prompt",
        "model_init_ms",
        "prefill_total_ms",
        "prefill_tokens",
        "prefill_ms_per_token",
        "prefill_tokens_per_second",
        "generate_total_ms",
        "generate_tokens",
        "generate_ms_per_token",
        "generate_tokens_per_second",
        "peak_memory_mb",
        "raw_log",
    ]

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fieldnames})

    print(f"\nCSV saved to: {csv_path}")
    print(f"Raw logs saved to: {raw_dir}")


if __name__ == "__main__":
    main()
