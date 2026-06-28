#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean, median


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resolve_path(path_value: str) -> Path:
    p = Path(path_value)
    if p.is_absolute():
        return p
    return PROJECT_ROOT / p


def percentile(values, p):
    if not values:
        return 0.0

    values = sorted(values)
    k = (len(values) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(values) - 1)

    if f == c:
        return values[f]

    return values[f] + (values[c] - values[f]) * (k - f)


def load_rows(csv_path: Path):
    if not csv_path.exists():
        raise FileNotFoundError(f"Benchmark CSV not found: {csv_path}")

    rows = []

    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            if row.get("ok") != "true":
                continue

            rows.append(row)

    return rows


def to_float(row, key):
    try:
        return float(row.get(key, 0.0))
    except ValueError:
        return 0.0


def summarize_group(rows):
    metrics = [
        "preprocess_ms",
        "inference_ms",
        "postprocess_ms",
        "end_to_end_ms",
        "fps",
    ]

    summary = {
        "count": len(rows),
        "model_size_mb": to_float(rows[0], "model_size_mb") if rows else 0.0,
    }

    for metric in metrics:
        values = [to_float(r, metric) for r in rows]

        summary[f"{metric}_avg"] = mean(values) if values else 0.0
        summary[f"{metric}_p50"] = median(values) if values else 0.0
        summary[f"{metric}_p95"] = percentile(values, 95) if values else 0.0

    return summary


def write_markdown(grouped, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        f.write("# YOLOv11 Benchmark Summary\n\n")
        f.write("该报告由 `tools/summarize_yolo_benchmark.py` 自动生成。\n\n")

        f.write("## Summary Table\n\n")
        f.write("| Model | Runtime | Samples | Model Size MB | Preprocess Avg ms | Inference Avg ms | E2E Avg ms | E2E P50 ms | E2E P95 ms | FPS Avg |\n")
        f.write("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|\n")

        for (model, runtime), rows in sorted(grouped.items()):
            s = summarize_group(rows)
            f.write(
                f"| {model} | {runtime} | {s['count']} | "
                f"{s['model_size_mb']:.3f} | "
                f"{s['preprocess_ms_avg']:.3f} | "
                f"{s['inference_ms_avg']:.3f} | "
                f"{s['end_to_end_ms_avg']:.3f} | "
                f"{s['end_to_end_ms_p50']:.3f} | "
                f"{s['end_to_end_ms_p95']:.3f} | "
                f"{s['fps_avg']:.2f} |\n"
            )

        f.write("\n## Notes\n\n")
        f.write("- dryrun 模式不代表真实 RK3588 NPU 性能。\n")
        f.write("- dryrun 主要用于验证模型注册表、图片读取、预处理和 CSV 输出流程。\n")
        f.write("- 真正的 inference_ms 需要在 RK3588 板端使用 rknnlite runtime 测试。\n")
        f.write("- 当前后处理仍是占位，后续需要加入 YOLO decode 和 NMS。\n")


def main():
    parser = argparse.ArgumentParser(description="Summarize YOLOv11 benchmark CSV.")
    parser.add_argument(
        "--input",
        default="results/benchmark/yolo11_benchmark.csv",
        help="Input benchmark CSV path."
    )
    parser.add_argument(
        "--output",
        default="results/benchmark/yolo11_benchmark_report.md",
        help="Output markdown report path."
    )
    args = parser.parse_args()

    input_path = resolve_path(args.input)
    output_path = resolve_path(args.output)

    rows = load_rows(input_path)

    if not rows:
        raise SystemExit("No valid benchmark rows found.")

    grouped = defaultdict(list)

    for row in rows:
        key = (row.get("model_name", "unknown"), row.get("runtime", "unknown"))
        grouped[key].append(row)

    write_markdown(grouped, output_path)

    print(f"Loaded rows: {len(rows)}")
    print(f"Groups     : {len(grouped)}")
    print(f"Report saved to: {output_path}")


if __name__ == "__main__":
    main()
