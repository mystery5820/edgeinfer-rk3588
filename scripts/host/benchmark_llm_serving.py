#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[2]

DEFAULT_BOARD_URL = os.environ.get("EDGEINFER_BOARD_URL", "http://192.168.43.7:8000").rstrip("/")
DEFAULT_MODEL_ID = os.environ.get("EDGEINFER_MODEL_ID", "qwen3-4b-rkllm-all-npu")
DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("EDGEINFER_LLM_BENCH_TIMEOUT", "180"))
DEFAULT_REPEAT = int(os.environ.get("EDGEINFER_LLM_BENCH_REPEAT", "1"))
DEFAULT_MAX_TOKENS = int(os.environ.get("EDGEINFER_LLM_BENCH_MAX_TOKENS", "48"))


PROMPTS: list[tuple[str, str]] = [
    (
        "rk3588_intro",
        "请用一句话介绍 RK3588。",
    ),
    (
        "edge_ai_value",
        "请用两句话说明端侧 LLM Serving 的价值。",
    ),
]


CSV_FIELDS = [
    "timestamp",
    "board_url",
    "model_id",
    "backend_mode",
    "worker_enabled",
    "worker_started",
    "prompt_name",
    "repeat_idx",
    "max_tokens",
    "http_status",
    "ok",
    "client_latency_ms",
    "edgeinfer_latency_ms",
    "llm_last_latency_ms",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "finish_reason",
    "edgeinfer_backend",
    "assistant_chars",
    "error",
]


def json_bytes(data: Dict[str, Any]) -> bytes:
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def request_json(
    method: str,
    url: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
    timeout_s: float,
) -> tuple[int, Dict[str, Any], float]:
    data = json_bytes(payload) if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}

    req = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )

    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        elapsed_ms = round((time.time() - start) * 1000.0, 3)
        raise RuntimeError(f"request failed: {url}: {exc}") from exc

    elapsed_ms = round((time.time() - start) * 1000.0, 3)

    try:
        body = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"non-json response from {url}, HTTP {status}: {raw!r}") from exc

    return status, body, elapsed_ms


def get_health(board_url: str, timeout_s: float) -> Dict[str, Any]:
    status, body, _ = request_json(
        "GET",
        f"{board_url}/v1/health",
        timeout_s=timeout_s,
    )
    if status != 200:
        raise RuntimeError(f"health check failed: HTTP {status}: {body!r}")
    return body


def get_metrics(board_url: str, timeout_s: float) -> Dict[str, Any]:
    status, body, _ = request_json(
        "GET",
        f"{board_url}/v1/metrics",
        timeout_s=timeout_s,
    )
    if status != 200:
        raise RuntimeError(f"metrics check failed: HTTP {status}: {body!r}")
    return body


def parse_backend_snapshot(metrics: Dict[str, Any]) -> Dict[str, Any]:
    rkllm_backend = metrics.get("rkllm_backend") or {}
    worker_runtime = rkllm_backend.get("worker_runtime") or {}
    llm = metrics.get("llm") or {}

    return {
        "backend_mode": str(rkllm_backend.get("mode", "")),
        "worker_enabled": bool(rkllm_backend.get("worker_enabled", False)),
        "worker_started": worker_runtime.get("started"),
        "llm_last_latency_ms": llm.get("last_latency_ms"),
    }


def extract_response_metrics(body: Dict[str, Any]) -> Dict[str, Any]:
    choices = body.get("choices") or []
    choice = choices[0] if choices else {}
    message = choice.get("message") or {}
    content = message.get("content") if isinstance(message, dict) else ""
    if not isinstance(content, str):
        content = ""

    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    edgeinfer = body.get("edgeinfer") if isinstance(body.get("edgeinfer"), dict) else {}

    return {
        "edgeinfer_latency_ms": edgeinfer.get("latency_ms"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "finish_reason": choice.get("finish_reason"),
        "edgeinfer_backend": edgeinfer.get("backend"),
        "assistant_chars": len(content),
    }


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * pct / 100.0
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def numeric_value(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}

    for row in rows:
        if not row.get("ok"):
            continue
        key = (
            str(row.get("backend_mode", "")),
            str(row.get("edgeinfer_backend", "")),
            str(row.get("prompt_name", "")),
        )
        groups.setdefault(key, []).append(row)

    summaries: list[dict[str, Any]] = []
    for (backend_mode, edgeinfer_backend, prompt_name), items in sorted(groups.items()):
        client_latencies = [
            v for v in (numeric_value(item.get("client_latency_ms")) for item in items)
            if v is not None
        ]
        backend_latencies = [
            v for v in (numeric_value(item.get("edgeinfer_latency_ms")) for item in items)
            if v is not None
        ]
        completion_tokens = [
            v for v in (numeric_value(item.get("completion_tokens")) for item in items)
            if v is not None
        ]

        summaries.append(
            {
                "backend_mode": backend_mode,
                "edgeinfer_backend": edgeinfer_backend,
                "prompt_name": prompt_name,
                "count": len(items),
                "client_avg_ms": round(statistics.mean(client_latencies), 3) if client_latencies else 0.0,
                "client_p50_ms": round(statistics.median(client_latencies), 3) if client_latencies else 0.0,
                "client_p95_ms": round(percentile(client_latencies, 95), 3) if client_latencies else 0.0,
                "backend_avg_ms": round(statistics.mean(backend_latencies), 3) if backend_latencies else 0.0,
                "backend_p50_ms": round(statistics.median(backend_latencies), 3) if backend_latencies else 0.0,
                "backend_p95_ms": round(percentile(backend_latencies, 95), 3) if backend_latencies else 0.0,
                "completion_tokens_avg": round(statistics.mean(completion_tokens), 3) if completion_tokens else 0.0,
            }
        )

    return summaries


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in CSV_FIELDS})


def format_markdown_table(headers: list[str], rows: Iterable[Iterable[Any]]) -> str:
    out = []
    out.append("| " + " | ".join(headers) + " |")
    out.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        out.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(out)


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    health: Dict[str, Any],
    metrics_before: Dict[str, Any],
    metrics_after: Dict[str, Any],
    rows: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    csv_path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    success_count = sum(1 for row in rows if row.get("ok"))
    failure_count = len(rows) - success_count

    summary_table = format_markdown_table(
        [
            "backend_mode",
            "edgeinfer_backend",
            "prompt_name",
            "count",
            "client_avg_ms",
            "client_p50_ms",
            "client_p95_ms",
            "backend_avg_ms",
            "backend_p50_ms",
            "backend_p95_ms",
            "completion_tokens_avg",
        ],
        (
            [
                item["backend_mode"],
                item["edgeinfer_backend"],
                item["prompt_name"],
                item["count"],
                item["client_avg_ms"],
                item["client_p50_ms"],
                item["client_p95_ms"],
                item["backend_avg_ms"],
                item["backend_p50_ms"],
                item["backend_p95_ms"],
                item["completion_tokens_avg"],
            ]
            for item in summaries
        ),
    )

    rows_table = format_markdown_table(
        [
            "backend_mode",
            "prompt_name",
            "repeat_idx",
            "http_status",
            "ok",
            "client_latency_ms",
            "edgeinfer_latency_ms",
            "completion_tokens",
            "finish_reason",
            "edgeinfer_backend",
        ],
        (
            [
                row.get("backend_mode", ""),
                row.get("prompt_name", ""),
                row.get("repeat_idx", ""),
                row.get("http_status", ""),
                row.get("ok", ""),
                row.get("client_latency_ms", ""),
                row.get("edgeinfer_latency_ms", ""),
                row.get("completion_tokens", ""),
                row.get("finish_reason", ""),
                row.get("edgeinfer_backend", ""),
            ]
            for row in rows
        ),
    )

    content = f"""# Phase 14B LLM Serving Benchmark Report

This report was generated by:

```bash
scripts/host/benchmark_llm_serving.py
```

## 1. Configuration

```text
board_url: {args.board_url}
model_id: {args.model_id}
repeat: {args.repeat}
max_tokens: {args.max_tokens}
timeout_seconds: {args.timeout}
csv_path: {csv_path}
```

## 2. Health

```json
{json.dumps(health, ensure_ascii=False, indent=2)}
```

## 3. Metrics before benchmark

```json
{json.dumps(metrics_before, ensure_ascii=False, indent=2)}
```

## 4. Summary

```text
total_requests: {len(rows)}
success_count: {success_count}
failure_count: {failure_count}
```

{summary_table}

## 5. Raw request rows

{rows_table}

## 6. Metrics after benchmark

```json
{json.dumps(metrics_after, ensure_ascii=False, indent=2)}
```

## 7. Notes

- `client_latency_ms` is measured on the host side around the full HTTP request.
- `edgeinfer_latency_ms` is reported by the server backend metadata when available.
- `usage` is estimated usage from Phase 12A, not tokenizer-accurate usage.
- Run this script separately in one-shot and worker modes if you want a controlled comparison.
- For worker mode, enable it before running this script and disable it after the run.
"""

    path.write_text(content, encoding="utf-8")


def build_payload(model_id: str, prompt: str, max_tokens: int) -> Dict[str, Any]:
    return {
        "model": model_id,
        "messages": [
            {
                "role": "system",
                "content": "你是 EdgeInfer-RK3588 端侧推理助手。回答应简洁、稳定。",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "max_tokens": max_tokens,
        "n": 1,
        "top_p": 1.0,
        "response_format": {"type": "text"},
    }


def run_benchmark(args: argparse.Namespace) -> int:
    board_url = args.board_url.rstrip("/")

    print("=== EdgeInfer LLM Serving Benchmark ===")
    print(f"board_url={board_url}")
    print(f"model_id={args.model_id}")
    print(f"repeat={args.repeat}")
    print(f"max_tokens={args.max_tokens}")
    print(f"timeout={args.timeout}")

    health = get_health(board_url, args.timeout)
    metrics_before = get_metrics(board_url, args.timeout)
    backend_snapshot = parse_backend_snapshot(metrics_before)

    backend_mode = backend_snapshot.get("backend_mode") or "unknown"
    output_csv = Path(args.output_csv) if args.output_csv else ROOT / "results" / "benchmark" / f"llm_serving_benchmark_{backend_mode}.csv"
    output_report = Path(args.output_report) if args.output_report else ROOT / "results" / "benchmark" / f"llm_serving_benchmark_{backend_mode}_report.md"

    rows: list[dict[str, Any]] = []

    for prompt_name, prompt in PROMPTS:
        for repeat_idx in range(1, args.repeat + 1):
            print()
            print(f"--- request prompt={prompt_name} repeat={repeat_idx}/{args.repeat} ---")
            metrics_before_request = get_metrics(board_url, args.timeout)
            snapshot = parse_backend_snapshot(metrics_before_request)

            row: dict[str, Any] = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "board_url": board_url,
                "model_id": args.model_id,
                "backend_mode": snapshot.get("backend_mode", ""),
                "worker_enabled": snapshot.get("worker_enabled", ""),
                "worker_started": snapshot.get("worker_started", ""),
                "prompt_name": prompt_name,
                "repeat_idx": repeat_idx,
                "max_tokens": args.max_tokens,
            }

            try:
                status, body, client_latency_ms = request_json(
                    "POST",
                    f"{board_url}/v1/chat/completions",
                    payload=build_payload(args.model_id, prompt, args.max_tokens),
                    timeout_s=args.timeout,
                )
                row["http_status"] = status
                row["client_latency_ms"] = client_latency_ms

                if status == 200:
                    row["ok"] = True
                    row.update(extract_response_metrics(body))
                    print(
                        "OK "
                        f"client_latency_ms={row.get('client_latency_ms')} "
                        f"edgeinfer_latency_ms={row.get('edgeinfer_latency_ms')} "
                        f"completion_tokens={row.get('completion_tokens')} "
                        f"backend={row.get('edgeinfer_backend')}"
                    )
                else:
                    row["ok"] = False
                    row["error"] = json.dumps(body, ensure_ascii=False)
                    print(f"HTTP {status}: {row['error']}")

            except Exception as exc:
                row["ok"] = False
                row["error"] = str(exc)
                print(f"ERROR: {exc}", file=sys.stderr)

            metrics_after_request = get_metrics(board_url, args.timeout)
            row["llm_last_latency_ms"] = (
                metrics_after_request.get("llm", {}) or {}
            ).get("last_latency_ms")

            rows.append(row)
            if args.sleep > 0:
                time.sleep(args.sleep)

    metrics_after = get_metrics(board_url, args.timeout)
    summaries = summarize(rows)

    write_csv(output_csv, rows)
    write_report(
        output_report,
        args=args,
        health=health,
        metrics_before=metrics_before,
        metrics_after=metrics_after,
        rows=rows,
        summaries=summaries,
        csv_path=output_csv,
    )

    print()
    print("=== benchmark completed ===")
    print(f"csv: {output_csv}")
    print(f"report: {output_report}")

    failures = [row for row in rows if not row.get("ok")]
    if failures:
        print(f"WARNING: {len(failures)} request(s) failed", file=sys.stderr)
        return 2

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark EdgeInfer LLM Serving chat completions.")
    parser.add_argument("--board-url", default=DEFAULT_BOARD_URL)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--repeat", type=int, default=DEFAULT_REPEAT)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--sleep", type=float, default=0.5)
    parser.add_argument("--output-csv", default=os.environ.get("EDGEINFER_LLM_BENCH_OUTPUT_CSV", ""))
    parser.add_argument("--output-report", default=os.environ.get("EDGEINFER_LLM_BENCH_OUTPUT_REPORT", ""))
    args = parser.parse_args()

    if args.repeat < 1:
        raise SystemExit("--repeat must be >= 1")
    if args.max_tokens < 1:
        raise SystemExit("--max-tokens must be >= 1")

    args.output_csv = args.output_csv or ""
    args.output_report = args.output_report or ""

    return args


def main() -> int:
    return run_benchmark(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
