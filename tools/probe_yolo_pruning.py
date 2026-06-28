#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
from pathlib import Path

import torch
import torch_pruning as tp
from ultralytics import YOLO


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def count_params(model):
    return sum(p.numel() for p in model.parameters())


def resolve_path(p):
    path = Path(p)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--imgsz", type=int, default=320)
    parser.add_argument("--ratio", type=float, default=0.10)
    args = parser.parse_args()

    input_pt = resolve_path(args.input)

    print("========== YOLO Pruning Probe ==========")
    print(f"Input : {input_pt}")
    print(f"ImgSz : {args.imgsz}")
    print(f"Ratio : {args.ratio}")
    print("========================================")

    yolo = YOLO(str(input_pt))
    model = yolo.model
    model.cpu()
    model.train()

    example_inputs = torch.randn(1, 3, args.imgsz, args.imgsz)

    params_before = count_params(model)

    print(f"Params before: {params_before}")

    DG = tp.DependencyGraph().build_dependency(
        model,
        example_inputs=example_inputs,
    )

    candidates = []

    for name, module in model.named_modules():
        if not isinstance(module, torch.nn.Conv2d):
            continue

        if name.startswith("model.23"):
            continue

        if module.groups != 1:
            continue

        if module.out_channels < 16:
            continue

        candidates.append((name, module))

    print(f"Candidate Conv2d layers: {len(candidates)}")

    success = False

    for name, conv in candidates:
        out_channels = conv.out_channels
        prune_num = max(1, int(out_channels * args.ratio))

        weight = conv.weight.detach()
        score = weight.abs().mean(dim=(1, 2, 3))
        idxs = torch.argsort(score)[:prune_num].tolist()

        print(f"\nTry layer: {name}")
        print(f"  out_channels: {out_channels}")
        print(f"  prune_num   : {prune_num}")

        try:
            group = DG.get_pruning_group(
                conv,
                tp.prune_conv_out_channels,
                idxs=idxs,
            )

            ok = DG.check_pruning_group(group)
            print(f"  group check : {ok}")

            if not ok:
                continue

            group.prune()

            params_after = count_params(model)
            reduction = params_before - params_after

            print("========== Probe Success ==========")
            print(f"Layer        : {name}")
            print(f"Params before: {params_before}")
            print(f"Params after : {params_after}")
            print(f"Reduction    : {reduction}")
            print(f"Reduction %  : {reduction / params_before * 100:.4f}%")

            model.eval()
            with torch.no_grad():
                _ = model(torch.randn(1, 3, args.imgsz, args.imgsz))

            print("Forward check: OK")
            print("===================================")

            success = True
            break

        except Exception as e:
            print(f"  failed: {type(e).__name__}: {e}")

    if not success:
        raise RuntimeError("No valid manual pruning group found.")


if __name__ == "__main__":
    main()
