#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
from pathlib import Path
from datetime import datetime


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SCAN_DIRS = [
    PROJECT_ROOT / "experiments" / "yolo11_prune",
    PROJECT_ROOT / "models" / "vision",
]

EXT_GROUPS = {
    "PyTorch weights": [".pt", ".pth"],
    "ONNX models": [".onnx"],
    "RKNN models": [".rknn"],
    "Config files": [".yaml", ".yml", ".json", ".txt"],
    "Reports": [".csv", ".md", ".log"],
    "Images": [".jpg", ".jpeg", ".png"],
}


def human_size(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024


def collect_files(scan_dirs):
    files = []

    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue

        for path in scan_dir.rglob("*"):
            if path.is_file():
                files.append(path)

    return files


def classify_file(path: Path):
    suffix = path.suffix.lower()

    for group, exts in EXT_GROUPS.items():
        if suffix in exts:
            return group

    return "Others"


def print_group(group_name, items):
    print("\n" + "=" * 100)
    print(group_name)
    print("=" * 100)

    if not items:
        print("No files found.")
        return

    for path in sorted(items, key=lambda p: p.stat().st_size, reverse=True):
        stat = path.stat()
        size = human_size(stat.st_size)
        mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        rel = path.relative_to(PROJECT_ROOT)
        print(f"{size:>12}  {mtime}  {rel}")


def main():
    parser = argparse.ArgumentParser(description="Scan YOLOv11 related assets.")
    parser.add_argument(
        "--scan-dir",
        action="append",
        help="Extra directory to scan. Can be used multiple times."
    )
    args = parser.parse_args()

    scan_dirs = list(DEFAULT_SCAN_DIRS)

    if args.scan_dir:
        scan_dirs.extend(Path(p).expanduser().resolve() for p in args.scan_dir)

    print("=" * 100)
    print("YOLOv11 Asset Scanner")
    print("=" * 100)

    print("\nScan directories:")
    for d in scan_dirs:
        print(f"  - {d}")

    all_files = collect_files(scan_dirs)

    grouped = {group: [] for group in EXT_GROUPS}
    grouped["Others"] = []

    for path in all_files:
        grouped[classify_file(path)].append(path)

    for group in [
        "RKNN models",
        "ONNX models",
        "PyTorch weights",
        "Config files",
        "Reports",
        "Images",
        "Others",
    ]:
        print_group(group, grouped[group])

    print("\n" + "=" * 100)
    print("Summary")
    print("=" * 100)
    print(f"Total files scanned: {len(all_files)}")

    for group, items in grouped.items():
        total_size = sum(p.stat().st_size for p in items)
        print(f"{group:18}: {len(items):4d} files, {human_size(total_size)}")


if __name__ == "__main__":
    main()
