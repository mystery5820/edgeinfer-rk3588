#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import time
from pathlib import Path

import torch
import torch_pruning as tp
from ultralytics import YOLO


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXP_ROOT = PROJECT_ROOT / "experiments" / "yolo11_compress_v2"
REPORTS_DIR = EXP_ROOT / "reports"


def resolve_path(path_value: str) -> Path:
    p = Path(path_value)
    if p.is_absolute():
        return p
    return PROJECT_ROOT / p


def count_params(model) -> int:
    return sum(p.numel() for p in model.parameters())


def add_last_conv_from_module(module, ignored):
    convs = [m for m in module.modules() if isinstance(m, torch.nn.Conv2d)]
    if convs:
        ignored.append(convs[-1])


def get_ignored_layers(model):
    ignored = []

    for module in model.modules():
        name = module.__class__.__name__

        if name == "DFL":
            ignored.append(module)

        if name == "Detect":
            # Do not ignore the whole Detect head.
            # Only ignore its final prediction convs, otherwise all upstream pruning may be blocked.
            for branch_name in ["cv2", "cv3"]:
                if hasattr(module, branch_name):
                    branch = getattr(module, branch_name)
                    for sub in branch:
                        add_last_conv_from_module(sub, ignored)

    return ignored


def run_pruner_step(pruner):
    try:
        groups = pruner.step(interactive=True)
        count = 0
        for group in groups:
            group.prune()
            count += 1
        return count
    except TypeError:
        pruner.step()
        return -1


def prune_yolo(input_pt: Path, output_pt: Path, ratio: float, imgsz: int):
    if not input_pt.exists():
        raise FileNotFoundError(f"Input pt not found: {input_pt}")

    output_pt.parent.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    print("========== YOLOv11 Structured Pruning V2 ==========")
    print(f"Input pt  : {input_pt}")
    print(f"Output pt : {output_pt}")
    print(f"Ratio     : {ratio}")
    print(f"Image sz  : {imgsz}")
    print("===================================================")

    yolo = YOLO(str(input_pt))
    model = yolo.model
    model.cpu()

    # Training mode makes YOLO head return raw feature maps, which is easier for dependency tracing.
    model.train()

    example_inputs = torch.randn(1, 3, imgsz, imgsz)

    ignored_layers = get_ignored_layers(model)
    params_before = count_params(model)

    print(f"Params before : {params_before}")
    print(f"Ignored layers: {len(ignored_layers)}")

    importance = tp.importance.MagnitudeImportance(p=2)

    pruner_kwargs = dict(
        model=model,
        example_inputs=example_inputs,
        importance=importance,
        pruning_ratio=ratio,
        global_pruning=True,
        ignored_layers=ignored_layers,
        iterative_steps=1,
    )

    try:
        pruner = tp.pruner.MagnitudePruner(
            **pruner_kwargs,
            root_module_types=[torch.nn.Conv2d],
        )
    except TypeError:
        pruner = tp.pruner.MagnitudePruner(**pruner_kwargs)

    start = time.time()
    pruned_groups = run_pruner_step(pruner)
    elapsed = time.time() - start

    params_after = count_params(model)
    reduction = params_before - params_after
    reduction_ratio = reduction / params_before if params_before else 0.0

    print(f"Pruned groups  : {pruned_groups}")
    print(f"Params after   : {params_after}")
    print(f"Reduction      : {reduction_ratio * 100:.2f}%")

    if reduction <= 0:
        raise RuntimeError(
            "Pruning did not reduce parameters. "
            "The dependency graph still produced no valid pruning groups."
        )

    model.eval()

    # Quick forward check before saving.
    with torch.no_grad():
        _ = model(torch.randn(1, 3, imgsz, imgsz))

    yolo.model = model
    yolo.save(str(output_pt))

    report = {
        "task": "structured_prune",
        "input_pt": str(input_pt.relative_to(PROJECT_ROOT)),
        "output_pt": str(output_pt.relative_to(PROJECT_ROOT)),
        "pruning_ratio": ratio,
        "imgsz": imgsz,
        "params_before": params_before,
        "params_after": params_after,
        "params_reduction": reduction,
        "params_reduction_ratio": round(reduction_ratio, 6),
        "ignored_layers": len(ignored_layers),
        "pruned_groups": pruned_groups,
        "elapsed_sec": round(elapsed, 3),
    }

    report_path = REPORTS_DIR / f"{output_pt.stem}_prune_info.json"

    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("========== Pruning Finished ==========")
    print(f"Output pt : {output_pt}")
    print(f"Report    : {report_path}")
    print("======================================")


def main():
    parser = argparse.ArgumentParser(description="YOLOv11 structured pruning V2.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--ratio", type=float, default=0.10)
    parser.add_argument("--imgsz", type=int, default=320)
    args = parser.parse_args()

    prune_yolo(
        input_pt=resolve_path(args.input),
        output_pt=resolve_path(args.output),
        ratio=args.ratio,
        imgsz=args.imgsz,
    )


if __name__ == "__main__":
    main()
