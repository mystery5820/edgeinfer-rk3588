#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
from pathlib import Path

try:
    import yaml
except ImportError:
    raise SystemExit("PyYAML is not installed. Please run: pip install pyyaml")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / "configs" / "model_registry.yaml"


def load_registry(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Model registry not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or "models" not in data:
        raise ValueError("Invalid model_registry.yaml: missing 'models' field")

    return data["models"]


def resolve_path(path_value):
    if path_value is None:
        return None
    p = Path(path_value)
    if p.is_absolute():
        return p
    return PROJECT_ROOT / p


def check_one_model(model):
    name = model.get("name", "unknown")
    source_dir = resolve_path(model.get("source_dir"))
    runtime_model = resolve_path(model.get("runtime_model"))

    results = []

    if source_dir is not None:
        results.append(("source_dir", source_dir, source_dir.exists()))
    else:
        results.append(("source_dir", None, False))

    if runtime_model is not None:
        results.append(("runtime_model", runtime_model, runtime_model.exists()))
    else:
        results.append(("runtime_model", None, model.get("task") == "object-detection"))

    return name, results


def main():
    parser = argparse.ArgumentParser(description="Check registered model assets.")
    parser.add_argument(
        "--registry",
        default=str(REGISTRY_PATH),
        help="Path to model_registry.yaml"
    )
    args = parser.parse_args()

    models = load_registry(Path(args.registry))

    failed = 0

    print("=" * 100)
    print("Asset Check")
    print("=" * 100)

    for model in models:
        name, results = check_one_model(model)
        print(f"\n[{name}]")

        for field, path, ok in results:
            status = "OK" if ok else "MISSING"
            path_text = str(path) if path is not None else "null"
            print(f"  {field:14} {status:8} {path_text}")

            if not ok:
                failed += 1

    print("\n" + "=" * 100)

    if failed == 0:
        print("All registered assets are valid.")
    else:
        print(f"Found {failed} missing asset(s). Please check configs/model_registry.yaml.")

    raise SystemExit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
