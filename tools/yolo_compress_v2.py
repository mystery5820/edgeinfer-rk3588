#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import shutil
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXP_ROOT = PROJECT_ROOT / "experiments" / "yolo11_compress_v2"

CONFIG_DIR = EXP_ROOT / "configs"
WEIGHTS_DIR = EXP_ROOT / "weights"
REPORTS_DIR = EXP_ROOT / "reports"
RUNS_DIR = EXP_ROOT / "runs"

BASELINE_PT = WEIGHTS_DIR / "yolo11n_baseline.pt"
DATA_YAML = CONFIG_DIR / "coco128_local.yaml"

OLD_BASELINE_PT = PROJECT_ROOT / "experiments" / "yolo11_prune" / "weights" / "yolo11n.pt"
OLD_DATA_YAML = PROJECT_ROOT / "experiments" / "yolo11_prune" / "datasets" / "coco128_local.yaml"


def ensure_dirs():
    for d in [
        EXP_ROOT,
        CONFIG_DIR,
        WEIGHTS_DIR,
        REPORTS_DIR,
        RUNS_DIR,
        EXP_ROOT / "onnx_exports",
        EXP_ROOT / "rknn_exports",
        EXP_ROOT / "logs",
    ]:
        d.mkdir(parents=True, exist_ok=True)


def ensure_assets():
    ensure_dirs()

    if not BASELINE_PT.exists():
        if OLD_BASELINE_PT.exists():
            shutil.copy2(OLD_BASELINE_PT, BASELINE_PT)
            print(f"Copied baseline: {OLD_BASELINE_PT} -> {BASELINE_PT}")
        else:
            raise FileNotFoundError(f"Baseline not found: {BASELINE_PT}")

    if not DATA_YAML.exists():
        if OLD_DATA_YAML.exists():
            shutil.copy2(OLD_DATA_YAML, DATA_YAML)
            print(f"Copied data yaml: {OLD_DATA_YAML} -> {DATA_YAML}")
        else:
            raise FileNotFoundError(f"Data yaml not found: {DATA_YAML}")


def check_env():
    import torch
    import ultralytics
    from ultralytics import YOLO

    ensure_assets()

    print("========== YOLO Compress V2 Check ==========")
    print(f"Project root : {PROJECT_ROOT}")
    print(f"Experiment   : {EXP_ROOT}")
    print(f"Baseline pt  : {BASELINE_PT}")
    print(f"Data yaml    : {DATA_YAML}")
    print(f"torch        : {torch.__version__}")
    print(f"cuda         : {torch.cuda.is_available()}")
    print(f"ultralytics  : {ultralytics.__version__}")

    YOLO(str(BASELINE_PT))
    print("YOLO baseline load: OK")
    print("============================================")


def smoke_train(epochs, imgsz, batch):
    import torch
    from ultralytics import YOLO

    ensure_assets()

    run_name = f"yolo11n_cpu_smoke_e{epochs}_img{imgsz}_b{batch}"
    run_dir = RUNS_DIR / run_name
    output_pt = WEIGHTS_DIR / f"{run_name}.pt"
    report_json = REPORTS_DIR / f"{run_name}_train_info.json"

    print("========== YOLOv11 CPU Smoke Train ==========")
    print(f"Baseline : {BASELINE_PT}")
    print(f"Data     : {DATA_YAML}")
    print(f"Run name : {run_name}")
    print(f"Epochs   : {epochs}")
    print(f"Image sz : {imgsz}")
    print(f"Batch    : {batch}")
    print(f"CUDA     : {torch.cuda.is_available()}")
    print("=============================================")

    model = YOLO(str(BASELINE_PT))

    start = time.time()

    model.train(
        data=str(DATA_YAML),
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        device="cpu",
        workers=0,
        project=str(RUNS_DIR),
        name=run_name,
        exist_ok=True,
        cache=False,
        verbose=True,
    )

    elapsed = time.time() - start

    best_pt = run_dir / "weights" / "best.pt"
    last_pt = run_dir / "weights" / "last.pt"

    if best_pt.exists():
        shutil.copy2(best_pt, output_pt)
        copied_from = best_pt
    elif last_pt.exists():
        shutil.copy2(last_pt, output_pt)
        copied_from = last_pt
    else:
        raise FileNotFoundError(f"No best.pt or last.pt found under {run_dir}")

    info = {
        "task": "cpu_smoke_train",
        "baseline_pt": str(BASELINE_PT.relative_to(PROJECT_ROOT)),
        "data_yaml": str(DATA_YAML.relative_to(PROJECT_ROOT)),
        "epochs": epochs,
        "imgsz": imgsz,
        "batch": batch,
        "device": "cpu",
        "run_dir": str(run_dir.relative_to(PROJECT_ROOT)),
        "copied_from": str(copied_from.relative_to(PROJECT_ROOT)),
        "output_pt": str(output_pt.relative_to(PROJECT_ROOT)),
        "elapsed_sec": round(elapsed, 3),
    }

    with report_json.open("w", encoding="utf-8") as f:
        json.dump(info, f, indent=2, ensure_ascii=False)

    print("========== Smoke Train Finished ==========")
    print(f"Output pt : {output_pt}")
    print(f"Report    : {report_json}")
    print(f"Elapsed   : {elapsed:.1f} sec")
    print("==========================================")


def main():
    parser = argparse.ArgumentParser(description="YOLOv11 compression V2 pipeline scaffold.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check")

    p_train = sub.add_parser("smoke-train")
    p_train.add_argument("--epochs", type=int, default=1)
    p_train.add_argument("--imgsz", type=int, default=320)
    p_train.add_argument("--batch", type=int, default=2)

    args = parser.parse_args()

    if args.command == "check":
        check_env()
    elif args.command == "smoke-train":
        smoke_train(args.epochs, args.imgsz, args.batch)


if __name__ == "__main__":
    main()
