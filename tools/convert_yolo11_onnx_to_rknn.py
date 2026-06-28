#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import shutil
import time
from pathlib import Path

from rknn.api import RKNN


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resolve_path(path_value: str) -> Path:
    p = Path(path_value)
    if p.is_absolute():
        return p
    return PROJECT_ROOT / p


def main():
    parser = argparse.ArgumentParser(description="Convert YOLOv11 ONNX to RKNN INT8 for RK3588.")
    parser.add_argument(
        "--onnx",
        default="models/vision/yolo11/onnx/yolo11n_baseline_640.onnx",
        help="Input ONNX model path.",
    )
    parser.add_argument(
        "--dataset",
        default="models/vision/yolo11/configs/yolo11_calib.txt",
        help="Calibration dataset txt path.",
    )
    parser.add_argument(
        "--output",
        default="models/vision/yolo11/rknn/yolo11n_baseline_i8_rk3588.rknn",
        help="Output RKNN model path.",
    )
    parser.add_argument(
        "--report",
        default="models/vision/yolo11/reports/yolo11n_baseline_i8_rk3588_convert_info.json",
        help="Output conversion report path.",
    )
    args = parser.parse_args()

    onnx_path = resolve_path(args.onnx)
    dataset_path = resolve_path(args.dataset)
    output_path = resolve_path(args.output)
    report_path = resolve_path(args.report)

    if not onnx_path.exists():
        raise FileNotFoundError(f"ONNX not found: {onnx_path}")

    if not dataset_path.exists():
        raise FileNotFoundError(f"Calibration dataset not found: {dataset_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists():
        backup_path = output_path.with_suffix(".prev.rknn")
        shutil.copy2(output_path, backup_path)
        print(f"Existing RKNN backed up to: {backup_path}")

    print("========== YOLOv11 ONNX -> RKNN INT8 ==========")
    print(f"ONNX    : {onnx_path}")
    print(f"Dataset : {dataset_path}")
    print(f"Output  : {output_path}")
    print("Target  : rk3588")
    print("Quant   : INT8")
    print("===============================================")

    rknn = RKNN(verbose=True)

    start = time.time()

    print("--> Config")
    ret = rknn.config(
        mean_values=[[0, 0, 0]],
        std_values=[[255, 255, 255]],
        target_platform="rk3588",
    )
    if ret != 0:
        raise RuntimeError(f"rknn.config failed: {ret}")

    print("--> Load ONNX")
    ret = rknn.load_onnx(model=str(onnx_path))
    if ret != 0:
        raise RuntimeError(f"rknn.load_onnx failed: {ret}")

    print("--> Build RKNN")
    ret = rknn.build(
        do_quantization=True,
        dataset=str(dataset_path),
    )
    if ret != 0:
        raise RuntimeError(f"rknn.build failed: {ret}")

    print("--> Export RKNN")
    ret = rknn.export_rknn(str(output_path))
    if ret != 0:
        raise RuntimeError(f"rknn.export_rknn failed: {ret}")

    rknn.release()

    elapsed = time.time() - start

    info = {
        "task": "convert_yolo11n_baseline_onnx_to_rknn_int8",
        "source_onnx": str(onnx_path.relative_to(PROJECT_ROOT)),
        "calibration_dataset": str(dataset_path.relative_to(PROJECT_ROOT)),
        "output_rknn": str(output_path.relative_to(PROJECT_ROOT)),
        "target_platform": "rk3588",
        "quantization": "INT8",
        "mean_values": [[0, 0, 0]],
        "std_values": [[255, 255, 255]],
        "elapsed_sec": round(elapsed, 3),
        "output_size_mb": round(output_path.stat().st_size / 1024 / 1024, 3),
    }

    with report_path.open("w", encoding="utf-8") as f:
        json.dump(info, f, indent=2, ensure_ascii=False)

    print("========== Conversion Finished ==========")
    print(f"RKNN   : {output_path}")
    print(f"Size   : {info['output_size_mb']} MB")
    print(f"Report : {report_path}")
    print("=========================================")


if __name__ == "__main__":
    main()
