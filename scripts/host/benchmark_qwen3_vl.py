#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple


DEFAULT_BOARD_URL = os.environ.get("EDGEINFER_BOARD_URL", "http://192.168.43.7:8000").rstrip("/")
DEFAULT_MODEL = os.environ.get("EDGEINFER_QWEN3_VL_MODEL", "qwen3-vl-2b-instruct-rkllm-v123")
DEFAULT_OUTPUT_DIR = Path(os.environ.get("EDGEINFER_BENCHMARK_OUTPUT_DIR", "benchmarks"))

DEFAULT_CASES: List[Dict[str, Any]] = [
    {
        "case_id": "pizza_caption",
        "task": "vision-language",
        "image_path": "/home/linaro/qwen3-vl-2b-npu/Pizza.jpg",
        "prompt": "<image> Describe this image in one sentence.",
        "max_new_tokens": 64,
    },
    {
        "case_id": "pizza_detail",
        "task": "vision-language",
        "image_path": "/home/linaro/qwen3-vl-2b-npu/Pizza.jpg",
        "prompt": "<image> Describe this image in detail.",
        "max_new_tokens": 128,
    },
    {
        "case_id": "singapore_caption",
        "task": "image-captioning",
        "image_path": "/home/linaro/qwen3-vl-2b-npu/Singapore.jpg",
        "prompt": "<image> Describe this image in one sentence.",
        "max_new_tokens": 64,
    },
    {
        "case_id": "moon_vqa",
        "task": "visual-question-answering",
        "image_path": "/home/linaro/qwen3-vl-2b-npu/Moon.jpg",
        "prompt": "<image> What is the main object or scene in this image?",
        "max_new_tokens": 64,
    },
    {
        "case_id": "chinese_wall_caption",
        "task": "vision-language",
        "image_path": "/home/linaro/qwen3-vl-2b-npu/ChineseWall.jpg",
        "prompt": "<image> Describe the landmark or scene in this image.",
        "max_new_tokens": 96,
    },
]


def request_json(
    *,
    board_url: str,
    path: str,
    payload: Dict[str, Any],
    timeout: float,
) -> Tuple[int, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{board_url}{path}",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            return int(resp.status), json.loads(text) if text else None
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(text) if text else None
        except json.JSONDecodeError:
            body = text
        return int(exc.code), body


def load_cases(path: str | None) -> List[Dict[str, Any]]:
    if not path:
        return list(DEFAULT_CASES)

    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("case file must contain a JSON list")
    return data


def answer_from_body(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    output = body.get("output")
    if not isinstance(output, dict):
        return ""
    summary = output.get("summary")
    if not isinstance(summary, dict):
        return ""
    answer = summary.get("answer")
    return answer if isinstance(answer, str) else ""


def backend_latency_from_body(body: Any) -> Any:
    if not isinstance(body, dict):
        return ""
    output = body.get("output")
    if not isinstance(output, dict):
        return ""
    summary = output.get("summary")
    if not isinstance(summary, dict):
        return ""
    return summary.get("latency_ms", "")


def edgeinfer_field(body: Any, key: str) -> str:
    if not isinstance(body, dict):
        return ""
    edgeinfer = body.get("edgeinfer")
    if not isinstance(edgeinfer, dict):
        return ""
    value = edgeinfer.get(key)
    return str(value) if value is not None else ""


def error_code_from_body(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    detail = body.get("detail")
    if not isinstance(detail, dict):
        return ""
    error = detail.get("error")
    if not isinstance(error, dict):
        return ""
    code = error.get("code")
    return str(code) if code is not None else ""


def run_case(
    *,
    board_url: str,
    model: str,
    case: Dict[str, Any],
    repeat_index: int,
    context_length: int,
    timeout_seconds: int,
) -> Dict[str, Any]:
    task = str(case.get("task", "vision-language"))
    image_path = str(case["image_path"])
    prompt = str(case.get("prompt", "<image> Describe this image in one sentence."))
    max_new_tokens = int(case.get("max_new_tokens", 64))

    payload = {
        "task": task,
        "model": str(case.get("model", model)),
        "input": {
            "image_path": image_path,
            "prompt": prompt,
        },
        "parameters": {
            "max_new_tokens": max_new_tokens,
            "context_length": context_length,
            "timeout_seconds": timeout_seconds,
        },
    }

    started = time.time()
    status, body = request_json(
        board_url=board_url,
        path="/v1/infer",
        payload=payload,
        timeout=float(timeout_seconds) + 30.0,
    )
    finished = time.time()

    client_latency_ms = round((finished - started) * 1000.0, 3)
    answer = answer_from_body(body)
    backend_latency_ms = backend_latency_from_body(body)
    success = status == 200 and bool(answer.strip())

    return {
        "case_id": str(case.get("case_id", "case")),
        "repeat_index": repeat_index,
        "task": task,
        "model": payload["model"],
        "image_path": image_path,
        "prompt": prompt,
        "max_new_tokens": max_new_tokens,
        "context_length": context_length,
        "timeout_seconds": timeout_seconds,
        "http_status": status,
        "success": success,
        "client_latency_ms": client_latency_ms,
        "backend_latency_ms": backend_latency_ms,
        "answer_chars": len(answer),
        "answer_preview": answer.replace("\n", " ")[:300],
        "backend": edgeinfer_field(body, "backend"),
        "source_runtime": edgeinfer_field(body, "source_runtime"),
        "error_code": error_code_from_body(body),
        "created_at": int(time.time()),
    }


def write_csv(rows: List[Dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "case_id",
        "repeat_index",
        "task",
        "model",
        "image_path",
        "prompt",
        "max_new_tokens",
        "context_length",
        "timeout_seconds",
        "http_status",
        "success",
        "client_latency_ms",
        "backend_latency_ms",
        "answer_chars",
        "answer_preview",
        "backend",
        "source_runtime",
        "error_code",
        "created_at",
    ]

    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def print_summary(rows: List[Dict[str, Any]]) -> None:
    ok_rows = [r for r in rows if r.get("success") is True]
    print()
    print("=== benchmark summary ===")
    print(f"total_cases={len(rows)}")
    print(f"success_cases={len(ok_rows)}")
    print(f"failed_cases={len(rows) - len(ok_rows)}")
    if ok_rows:
        latencies = [float(r["client_latency_ms"]) for r in ok_rows]
        backend_latencies = [
            float(r["backend_latency_ms"])
            for r in ok_rows
            if str(r.get("backend_latency_ms", "")).strip()
        ]
        print(f"client_latency_ms_avg={sum(latencies) / len(latencies):.3f}")
        print(f"client_latency_ms_min={min(latencies):.3f}")
        print(f"client_latency_ms_max={max(latencies):.3f}")
        if backend_latencies:
            print(f"backend_latency_ms_avg={sum(backend_latencies) / len(backend_latencies):.3f}")
            print(f"backend_latency_ms_min={min(backend_latencies):.3f}")
            print(f"backend_latency_ms_max={max(backend_latencies):.3f}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark Qwen3-VL /v1/infer cases on RK3588.")
    parser.add_argument("--board-url", default=DEFAULT_BOARD_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--cases-json", default=None, help="Optional JSON list of benchmark cases.")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--context-length", type=int, default=1024)
    parser.add_argument("--timeout-seconds", type=int, default=260)
    parser.add_argument("--output", default=None)
    parser.add_argument("--quick", action="store_true", help="Run only the first two built-in cases.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    cases = load_cases(args.cases_json)
    if args.quick:
        cases = cases[:2]

    if args.repeat < 1:
        raise ValueError("--repeat must be >= 1")

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output = Path(args.output) if args.output else DEFAULT_OUTPUT_DIR / f"phase23_qwen3_vl_benchmark_{timestamp}.csv"

    print("=== EdgeInfer Qwen3-VL Benchmark ===")
    print(f"board_url={args.board_url}")
    print(f"model={args.model}")
    print(f"cases={len(cases)}")
    print(f"repeat={args.repeat}")
    print(f"output={output}")

    rows: List[Dict[str, Any]] = []
    for repeat_index in range(args.repeat):
        for case in cases:
            print()
            print(f"=== run case {case.get('case_id')} repeat={repeat_index} ===")
            row = run_case(
                board_url=args.board_url,
                model=args.model,
                case=case,
                repeat_index=repeat_index,
                context_length=args.context_length,
                timeout_seconds=args.timeout_seconds,
            )
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False, indent=2))

    write_csv(rows, output)
    print_summary(rows)
    print()
    print(f"CSV written to: {output}")

    failed = [r for r in rows if r.get("success") is not True]
    if failed:
        print("FAILED CASES:")
        for row in failed:
            print(f"- {row.get('case_id')} status={row.get('http_status')} error={row.get('error_code')}")
        return 1

    print("=== Qwen3-VL benchmark passed ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
