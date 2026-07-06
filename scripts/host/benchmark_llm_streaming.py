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
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BOARD_URL = os.environ.get("EDGEINFER_BOARD_URL", "http://192.168.43.7:8000").rstrip("/")
DEFAULT_MODEL_ID = os.environ.get("EDGEINFER_MODEL_ID", "qwen3-4b-rkllm-all-npu")

FIELDNAMES = [
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
    "header_latency_ms",
    "time_to_first_event_ms",
    "time_to_first_content_ms",
    "total_stream_latency_ms",
    "event_count",
    "content_event_count",
    "assistant_chars",
    "finish_reason",
    "done_received",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "edgeinfer_backend",
    "error",
]


PROMPTS = [
    (
        "rk3588_intro",
        "请用一句话介绍 RK3588。",
    ),
    (
        "edge_ai_value",
        "请用两句话说明端侧 LLM Streaming Serving 的价值。",
    ),
]


def now_ts() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def ms_since(start: float) -> float:
    return (time.monotonic() - start) * 1000.0


def fmt_ms(value: Optional[float]) -> str:
    if value is None:
        return ""
    return f"{value:.3f}"


def url_join(base: str, path: str) -> str:
    return base.rstrip("/") + "/" + path.lstrip("/")


def request_json(method: str, board_url: str, path: str, payload: Optional[Dict[str, Any]] = None, timeout: float = 10.0) -> Dict[str, Any]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        url_join(board_url, path),
        data=data,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    return json.loads(body)


def get_metrics(board_url: str, timeout: float) -> Dict[str, Any]:
    try:
        return request_json("GET", board_url, "/v1/metrics", timeout=timeout)
    except Exception as exc:
        return {"error": str(exc)}


def backend_info(metrics: Dict[str, Any]) -> Dict[str, Any]:
    rkllm = metrics.get("rkllm_backend") if isinstance(metrics.get("rkllm_backend"), dict) else {}
    worker_runtime = rkllm.get("worker_runtime") if isinstance(rkllm.get("worker_runtime"), dict) else {}
    return {
        "backend_mode": rkllm.get("mode"),
        "worker_enabled": rkllm.get("worker_enabled"),
        "worker_started": worker_runtime.get("started"),
    }


def build_payload(model_id: str, prompt: str, max_tokens: int) -> Dict[str, Any]:
    return {
        "model": model_id,
        "messages": [
            {
                "role": "system",
                "content": "你是 EdgeInfer-RK3588 端侧推理助手。",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "max_tokens": max_tokens,
        "stream": True,
    }


def parse_sse_data_line(line: bytes) -> Optional[str]:
    text = line.decode("utf-8", errors="replace").strip()
    if not text.startswith("data:"):
        return None
    return text[len("data:"):].strip()


def extract_error_code(body: str) -> str:
    try:
        data = json.loads(body)
    except Exception:
        return body[:500]
    detail = data.get("detail") if isinstance(data, dict) else None
    if isinstance(detail, dict):
        error = detail.get("error")
        if isinstance(error, dict):
            return str(error.get("code") or error)
    return str(data)[:500]


def run_stream_once(
    *,
    board_url: str,
    model_id: str,
    prompt_name: str,
    prompt: str,
    repeat_idx: int,
    max_tokens: int,
    timeout: float,
    info: Dict[str, Any],
) -> Dict[str, Any]:
    payload = build_payload(model_id, prompt, max_tokens)
    request_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url_join(board_url, "/v1/chat/completions"),
        data=request_body,
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )

    row: Dict[str, Any] = {
        "timestamp": now_ts(),
        "board_url": board_url,
        "model_id": model_id,
        "backend_mode": info.get("backend_mode"),
        "worker_enabled": info.get("worker_enabled"),
        "worker_started": info.get("worker_started"),
        "prompt_name": prompt_name,
        "repeat_idx": repeat_idx,
        "max_tokens": max_tokens,
        "http_status": "",
        "ok": False,
        "header_latency_ms": "",
        "time_to_first_event_ms": "",
        "time_to_first_content_ms": "",
        "total_stream_latency_ms": "",
        "event_count": 0,
        "content_event_count": 0,
        "assistant_chars": 0,
        "finish_reason": "",
        "done_received": False,
        "prompt_tokens": "",
        "completion_tokens": "",
        "total_tokens": "",
        "edgeinfer_backend": "",
        "error": "",
    }

    started = time.monotonic()
    first_event_ms: Optional[float] = None
    first_content_ms: Optional[float] = None
    content_parts: List[str] = []
    final_payload: Optional[Dict[str, Any]] = None
    finish_reason = ""

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            row["http_status"] = resp.status
            row["header_latency_ms"] = fmt_ms(ms_since(started))

            for raw_line in resp:
                data = parse_sse_data_line(raw_line)
                if data is None:
                    continue

                if first_event_ms is None:
                    first_event_ms = ms_since(started)
                    row["time_to_first_event_ms"] = fmt_ms(first_event_ms)

                if data == "[DONE]":
                    row["done_received"] = True
                    break

                row["event_count"] = int(row["event_count"]) + 1

                try:
                    payload = json.loads(data)
                except json.JSONDecodeError as exc:
                    row["error"] = f"invalid_sse_json: {exc}: {data[:200]}"
                    break

                if isinstance(payload.get("error"), dict):
                    row["error"] = f"sse_error_event: {payload['error']}"
                    break

                choices = payload.get("choices")
                if not isinstance(choices, list) or not choices:
                    row["error"] = f"sse_event_without_choices: {payload}"
                    break

                choice = choices[0]
                if not isinstance(choice, dict):
                    row["error"] = f"invalid_choice: {choice!r}"
                    break

                delta = choice.get("delta") or {}
                if isinstance(delta, dict):
                    content = delta.get("content")
                    if isinstance(content, str) and content:
                        if first_content_ms is None:
                            first_content_ms = ms_since(started)
                            row["time_to_first_content_ms"] = fmt_ms(first_content_ms)
                        content_parts.append(content)
                        row["content_event_count"] = int(row["content_event_count"]) + 1

                if choice.get("finish_reason") is not None:
                    finish_reason = str(choice.get("finish_reason"))
                    final_payload = payload

                edgeinfer = payload.get("edgeinfer")
                if isinstance(edgeinfer, dict) and edgeinfer.get("backend"):
                    row["edgeinfer_backend"] = edgeinfer.get("backend")

            row["total_stream_latency_ms"] = fmt_ms(ms_since(started))

    except urllib.error.HTTPError as exc:
        row["http_status"] = exc.code
        row["total_stream_latency_ms"] = fmt_ms(ms_since(started))
        error_body = exc.read().decode("utf-8", errors="replace")
        row["error"] = extract_error_code(error_body)
        return row
    except Exception as exc:
        row["total_stream_latency_ms"] = fmt_ms(ms_since(started))
        row["error"] = repr(exc)
        return row

    text = "".join(content_parts)
    row["assistant_chars"] = len(text)
    row["finish_reason"] = finish_reason

    if final_payload:
        usage = final_payload.get("usage")
        if isinstance(usage, dict):
            row["prompt_tokens"] = usage.get("prompt_tokens", "")
            row["completion_tokens"] = usage.get("completion_tokens", "")
            row["total_tokens"] = usage.get("total_tokens", "")

        edgeinfer = final_payload.get("edgeinfer")
        if isinstance(edgeinfer, dict) and edgeinfer.get("backend"):
            row["edgeinfer_backend"] = edgeinfer.get("backend")

    if text.lstrip().startswith("LLM:") or "LLM:" in text[:16]:
        row["error"] = f"worker_prefix_leaked: {text[:80]!r}"

    row["ok"] = (
        row["http_status"] == 200
        and row["done_received"] is True
        and row["content_event_count"] > 0
        and row["finish_reason"] == "stop"
        and not row["error"]
    )

    return row


def numeric(row: Dict[str, Any], key: str) -> Optional[float]:
    value = row.get(key)
    if value in ("", None):
        return None
    try:
        return float(value)
    except Exception:
        return None


def summarize_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("prompt_name")), []).append(row)

    summary: List[Dict[str, Any]] = []
    for prompt_name, items in grouped.items():
        ok_items = [row for row in items if row.get("ok") is True]
        first_content = [numeric(row, "time_to_first_content_ms") for row in ok_items]
        first_content = [x for x in first_content if x is not None]
        total = [numeric(row, "total_stream_latency_ms") for row in ok_items]
        total = [x for x in total if x is not None]
        chars = [numeric(row, "assistant_chars") for row in ok_items]
        chars = [x for x in chars if x is not None]
        chunks = [numeric(row, "content_event_count") for row in ok_items]
        chunks = [x for x in chunks if x is not None]

        summary.append(
            {
                "prompt_name": prompt_name,
                "runs": len(items),
                "ok_runs": len(ok_items),
                "first_content_avg_ms": statistics.mean(first_content) if first_content else None,
                "first_content_p50_ms": statistics.median(first_content) if first_content else None,
                "total_avg_ms": statistics.mean(total) if total else None,
                "total_p50_ms": statistics.median(total) if total else None,
                "assistant_chars_avg": statistics.mean(chars) if chars else None,
                "content_chunks_avg": statistics.mean(chunks) if chunks else None,
            }
        )

    return summary


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in FIELDNAMES})


def format_float(value: Optional[float]) -> str:
    if value is None:
        return ""
    return f"{value:.3f}"


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    rows: List[Dict[str, Any]],
    metrics_before: Dict[str, Any],
    metrics_after: Dict[str, Any],
    output_csv: Path,
) -> None:
    summary = summarize_rows(rows)
    lines: List[str] = []
    lines.append("# LLM Streaming Benchmark Report")
    lines.append("")
    lines.append("## Config")
    lines.append("")
    lines.append(f"- board_url: `{args.board_url}`")
    lines.append(f"- model_id: `{args.model_id}`")
    lines.append(f"- repeat: `{args.repeat}`")
    lines.append(f"- max_tokens: `{args.max_tokens}`")
    lines.append(f"- timeout: `{args.timeout}`")
    lines.append(f"- output_csv: `{output_csv}`")
    lines.append("")
    lines.append("## Metrics before")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(metrics_before, ensure_ascii=False, indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| prompt | runs | ok | first_content_avg_ms | first_content_p50_ms | total_avg_ms | total_p50_ms | chars_avg | content_chunks_avg |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for item in summary:
        lines.append(
            "| {prompt_name} | {runs} | {ok_runs} | {first_avg} | {first_p50} | {total_avg} | {total_p50} | {chars_avg} | {chunks_avg} |".format(
                prompt_name=item["prompt_name"],
                runs=item["runs"],
                ok_runs=item["ok_runs"],
                first_avg=format_float(item["first_content_avg_ms"]),
                first_p50=format_float(item["first_content_p50_ms"]),
                total_avg=format_float(item["total_avg_ms"]),
                total_p50=format_float(item["total_p50_ms"]),
                chars_avg=format_float(item["assistant_chars_avg"]),
                chunks_avg=format_float(item["content_chunks_avg"]),
            )
        )
    lines.append("")
    lines.append("## Raw rows")
    lines.append("")
    lines.append("| prompt | repeat | status | ok | first_event_ms | first_content_ms | total_ms | events | content_chunks | chars | finish_reason | done | error |")
    lines.append("| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |")
    for row in rows:
        lines.append(
            "| {prompt} | {repeat} | {status} | {ok} | {first_event} | {first_content} | {total} | {events} | {chunks} | {chars} | {finish} | {done} | {error} |".format(
                prompt=row.get("prompt_name", ""),
                repeat=row.get("repeat_idx", ""),
                status=row.get("http_status", ""),
                ok=row.get("ok", ""),
                first_event=row.get("time_to_first_event_ms", ""),
                first_content=row.get("time_to_first_content_ms", ""),
                total=row.get("total_stream_latency_ms", ""),
                events=row.get("event_count", ""),
                chunks=row.get("content_event_count", ""),
                chars=row.get("assistant_chars", ""),
                finish=row.get("finish_reason", ""),
                done=row.get("done_received", ""),
                error=str(row.get("error", "")).replace("|", "\\|"),
            )
        )
    lines.append("")
    lines.append("## Metrics after")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(metrics_after, ensure_ascii=False, indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- This benchmark requires RKLLM persistent worker mode.")
    lines.append("- In one-shot mode, `stream=true` is expected to return `stream_backend_not_supported`.")
    lines.append("- `time_to_first_event_ms` measures the first SSE `data:` event.")
    lines.append("- `time_to_first_content_ms` measures the first SSE content delta.")
    lines.append("- `total_stream_latency_ms` measures until `data: [DONE]` or error.")
    lines.append("- `usage` values are estimated usage from Phase 12A.")
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark EdgeInfer LLM streaming SSE latency.")
    parser.add_argument("--board-url", default=DEFAULT_BOARD_URL)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--output-dir", default=str(ROOT / "results" / "benchmark"))
    parser.add_argument("--output-prefix", default="llm_streaming_benchmark")
    parser.add_argument("--allow-non-worker", action="store_true", help="Run even when metrics do not report worker mode.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.board_url = args.board_url.rstrip("/")

    if args.repeat < 1:
        print("ERROR: --repeat must be >= 1", file=sys.stderr)
        return 2
    if args.max_tokens < 1:
        print("ERROR: --max-tokens must be >= 1", file=sys.stderr)
        return 2

    print("=== EdgeInfer LLM Streaming Benchmark ===")
    print(f"board_url={args.board_url}")
    print(f"model_id={args.model_id}")
    print(f"repeat={args.repeat}")
    print(f"max_tokens={args.max_tokens}")
    print(f"timeout={args.timeout}")
    print()

    metrics_before = get_metrics(args.board_url, args.timeout)
    info = backend_info(metrics_before)
    print(f"backend_mode={info.get('backend_mode')}")
    print(f"worker_enabled={info.get('worker_enabled')}")
    print(f"worker_started={info.get('worker_started')}")
    print()

    if info.get("backend_mode") not in {"worker", "persistent", "persistent-worker"} and not args.allow_non_worker:
        print("ERROR: streaming benchmark requires worker backend mode.", file=sys.stderr)
        print("Enable it with:", file=sys.stderr)
        print('  ssh linaro@192.168.43.7 "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/enable_edgeinfer_worker_mode.sh"', file=sys.stderr)
        print("Or pass --allow-non-worker to record the expected rejection.", file=sys.stderr)
        return 2

    rows: List[Dict[str, Any]] = []
    for repeat_idx in range(1, args.repeat + 1):
        for prompt_name, prompt in PROMPTS:
            print(f"--- {prompt_name} repeat={repeat_idx} ---")
            row = run_stream_once(
                board_url=args.board_url,
                model_id=args.model_id,
                prompt_name=prompt_name,
                prompt=prompt,
                repeat_idx=repeat_idx,
                max_tokens=args.max_tokens,
                timeout=args.timeout,
                info=info,
            )
            rows.append(row)
            print(
                "status={status} ok={ok} first_content_ms={first_content} total_ms={total} chunks={chunks} chars={chars} finish={finish} done={done} error={error}".format(
                    status=row.get("http_status"),
                    ok=row.get("ok"),
                    first_content=row.get("time_to_first_content_ms"),
                    total=row.get("total_stream_latency_ms"),
                    chunks=row.get("content_event_count"),
                    chars=row.get("assistant_chars"),
                    finish=row.get("finish_reason"),
                    done=row.get("done_received"),
                    error=row.get("error"),
                )
            )
            print()

    metrics_after = get_metrics(args.board_url, args.timeout)

    output_dir = Path(args.output_dir)
    csv_path = output_dir / f"{args.output_prefix}.csv"
    report_path = output_dir / f"{args.output_prefix}_report.md"

    write_csv(csv_path, rows)
    write_report(
        report_path,
        args=args,
        rows=rows,
        metrics_before=metrics_before,
        metrics_after=metrics_after,
        output_csv=csv_path,
    )

    print(f"wrote: {csv_path}")
    print(f"wrote: {report_path}")

    ok = all(row.get("ok") is True for row in rows)
    if not ok:
        print("ERROR: at least one streaming benchmark row failed", file=sys.stderr)
        return 1

    print("streaming benchmark completed successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
