#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import shutil
import time
from pathlib import Path

import yaml
from ultralytics import YOLO


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXP_ROOT = PROJECT_ROOT / "experiments" / "yolo11_compress_v2"

CONFIG_DIR = EXP_ROOT / "configs"
WEIGHTS_DIR = EXP_ROOT / "weights"
REPORTS_DIR = EXP_ROOT / "reports"
RUNS_DIR = EXP_ROOT / "runs"

DATA_YAML = CONFIG_DIR / "coco128_local.yaml"


VARIANTS = {
    "width0875": {
        "width_multiple": 0.21875,
        "desc": "YOLOv11n width 87.5 percent of baseline width",
    },
    "width075": {
        "width_multiple": 0.18750,
        "desc": "YOLOv11n width 75 percent of baseline width",
    },
}


def ensure_dirs():
    for d in [CONFIG_DIR, WEIGHTS_DIR, REPORTS_DIR, RUNS_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def find_ultralytics_yolo11_yaml():
    import ultralytics

    root = Path(ultralytics.__file__).resolve().parent
    candidates = [
        root / "cfg" / "models" / "11" / "yolo11.yaml",
        root / "cfg" / "models" / "v11" / "yolo11.yaml",
    ]

    for p in candidates:
        if p.exists():
            return p

    raise FileNotFoundError("Cannot find Ultralytics yolo11.yaml in installed package.")


def count_params_from_yolo(yolo):
    return sum(p.numel() for p in yolo.model.parameters())


def create_configs():
    ensure_dirs()

    src = find_ultralytics_yolo11_yaml()
    print(f"Source yaml: {src}")

    with src.open("r", encoding="utf-8") as f:
        base_cfg = yaml.safe_load(f)

    for name, item in VARIANTS.items():
        cfg = dict(base_cfg)

        scales = dict(cfg.get("scales", {}))
        if "n" not in scales:
            raise KeyError("Cannot find scale 'n' in yolo11.yaml")

        depth_multiple = scales["n"][0]
        max_channels = scales["n"][2]

        scales["n"] = [
            depth_multiple,
            item["width_multiple"],
            max_channels,
        ]

        cfg["scales"] = scales
        cfg["scale"] = "n"

        out = CONFIG_DIR / f"yolo11n_{name}.yaml"

        with out.open("w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)

        print(f"Created: {out}")


def train_width(variant, pretrained, epochs, imgsz, batch):
    ensure_dirs()

    if variant not in VARIANTS:
        raise ValueError(f"Unknown variant: {variant}")

    cfg_path = CONFIG_DIR / f"yolo11n_{variant}.yaml"
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config not found: {cfg_path}. Run create-configs first.")

    data_yaml = DATA_YAML
    if not data_yaml.exists():
        raise FileNotFoundError(f"Data yaml not found: {data_yaml}")

    pretrained_path = Path(pretrained)
    if not pretrained_path.is_absolute():
        pretrained_path = PROJECT_ROOT / pretrained_path

    if not pretrained_path.exists():
        raise FileNotFoundError(f"Pretrained pt not found: {pretrained_path}")

    run_name = f"yolo11n_{variant}_finetune_e{epochs}_img{imgsz}_b{batch}"
    run_dir = RUNS_DIR / run_name
    output_pt = WEIGHTS_DIR / f"{run_name}.pt"
    report_json = REPORTS_DIR / f"{run_name}_train_info.json"

    print("========== YOLOv11 Width Compression Train ==========")
    print(f"Variant     : {variant}")
    print(f"Config      : {cfg_path}")
    print(f"Pretrained  : {pretrained_path}")
    print(f"Data        : {data_yaml}")
    print(f"Epochs      : {epochs}")
    print(f"Image size  : {imgsz}")
    print(f"Batch       : {batch}")
    print(f"Output      : {output_pt}")
    print("=====================================================")

    model = YOLO(str(cfg_path))
    params_before_load = count_params_from_yolo(model)

    model = model.load(str(pretrained_path))
    params_after_load = count_params_from_yolo(model)

    start = time.time()

    model.train(
        data=str(data_yaml),
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
        "task": "width_compression_finetune",
        "variant": variant,
        "description": VARIANTS[variant]["desc"],
        "width_multiple": VARIANTS[variant]["width_multiple"],
        "config": str(cfg_path.relative_to(PROJECT_ROOT)),
        "pretrained": str(pretrained_path.relative_to(PROJECT_ROOT)),
        "data_yaml": str(data_yaml.relative_to(PROJECT_ROOT)),
        "epochs": epochs,
        "imgsz": imgsz,
        "batch": batch,
        "device": "cpu",
        "run_dir": str(run_dir.relative_to(PROJECT_ROOT)),
        "copied_from": str(copied_from.relative_to(PROJECT_ROOT)),
        "output_pt": str(output_pt.relative_to(PROJECT_ROOT)),
        "params_before_load": params_before_load,
        "params_after_load": params_after_load,
        "elapsed_sec": round(elapsed, 3),
    }

    with report_json.open("w", encoding="utf-8") as f:
        json.dump(info, f, indent=2, ensure_ascii=False)

    print("========== Width Train Finished ==========")
    print(f"Output pt : {output_pt}")
    print(f"Report    : {report_json}")
    print(f"Elapsed   : {elapsed:.1f} sec")
    print("==========================================")


def main():
    parser = argparse.ArgumentParser(description="YOLOv11 width compression V2.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("create-configs")

    p_train = sub.add_parser("train-width")
    p_train.add_argument("--variant", required=True, choices=list(VARIANTS.keys()))
    p_train.add_argument(
        "--pretrained",
        default="experiments/yolo11_compress_v2/weights/yolo11n_cpu_smoke_e10_img320_b2.pt",
    )
    p_train.add_argument("--epochs", type=int, default=50)
    p_train.add_argument("--imgsz", type=int, default=320)
    p_train.add_argument("--batch", type=int, default=2)

    args = parser.parse_args()

    if args.command == "create-configs":
        create_configs()
    elif args.command == "train-width":
        train_width(
            variant=args.variant,
            pretrained=args.pretrained,
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
        )


if __name__ == "__main__":
    main()
