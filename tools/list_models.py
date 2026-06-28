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


def print_models(models):
    print("=" * 88)
    print(f"{'Name':32} {'Task':18} {'Backend':8} {'Quant':10} {'Status':10}")
    print("=" * 88)

    for m in models:
        print(
            f"{m.get('name', '-')[:32]:32} "
            f"{m.get('task', '-')[:18]:18} "
            f"{m.get('backend', '-')[:8]:8} "
            f"{str(m.get('quantization', '-'))[:10]:10} "
            f"{m.get('status', '-')[:10]:10}"
        )

    print("=" * 88)
    print(f"Total models: {len(models)}")


def main():
    parser = argparse.ArgumentParser(description="List registered models.")
    parser.add_argument(
        "--registry",
        default=str(REGISTRY_PATH),
        help="Path to model_registry.yaml"
    )
    args = parser.parse_args()

    models = load_registry(Path(args.registry))
    print_models(models)


if __name__ == "__main__":
    main()
