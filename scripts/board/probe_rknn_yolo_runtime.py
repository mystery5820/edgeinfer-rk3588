#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def emit(payload: dict, rc: int = 0) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return rc


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe RKNN YOLO runtime load/init/release.")
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--runtime", default="rknnlite", choices=["rknnlite"])
    args = parser.parse_args()

    model_path = Path(args.model_path)
    if not model_path.exists():
        return emit(
            {
                "ok": False,
                "error": f"RKNN model not found: {model_path}",
                "model_path": str(model_path),
            },
            rc=2,
        )

    started = time.time()
    rknn = None

    try:
        import_started = time.time()
        from rknnlite.api import RKNNLite
        import_ms = (time.time() - import_started) * 1000.0

        create_started = time.time()
        rknn = RKNNLite()
        create_ms = (time.time() - create_started) * 1000.0

        load_started = time.time()
        ret = rknn.load_rknn(str(model_path))
        load_ms = (time.time() - load_started) * 1000.0
        if ret != 0:
            return emit(
                {
                    "ok": False,
                    "runtime": "rknnlite",
                    "error": f"load_rknn failed, ret={ret}",
                    "model_path": str(model_path),
                    "load_rknn_ms": round(load_ms, 3),
                },
                rc=3,
            )

        core_mask_name = None
        core_mask = getattr(RKNNLite, "NPU_CORE_0_1_2", None)
        if core_mask is not None:
            core_mask_name = "NPU_CORE_0_1_2"
        else:
            core_mask = getattr(RKNNLite, "NPU_CORE_AUTO", None)
            if core_mask is not None:
                core_mask_name = "NPU_CORE_AUTO"

        init_started = time.time()
        if core_mask is not None:
            ret = rknn.init_runtime(core_mask=core_mask)
        else:
            ret = rknn.init_runtime()
        init_ms = (time.time() - init_started) * 1000.0
        if ret != 0:
            return emit(
                {
                    "ok": False,
                    "runtime": "rknnlite",
                    "error": f"init_runtime failed, ret={ret}",
                    "model_path": str(model_path),
                    "import_ms": round(import_ms, 3),
                    "create_ms": round(create_ms, 3),
                    "load_rknn_ms": round(load_ms, 3),
                    "init_runtime_ms": round(init_ms, 3),
                    "core_mask": core_mask_name,
                },
                rc=4,
            )

        release_started = time.time()
        rknn.release()
        rknn = None
        release_ms = (time.time() - release_started) * 1000.0

        total_ms = (time.time() - started) * 1000.0
        return emit(
            {
                "ok": True,
                "runtime": "rknnlite",
                "model_path": str(model_path),
                "model_size_mb": round(model_path.stat().st_size / 1024 / 1024, 3),
                "import_ms": round(import_ms, 3),
                "create_ms": round(create_ms, 3),
                "load_rknn_ms": round(load_ms, 3),
                "init_runtime_ms": round(init_ms, 3),
                "release_ms": round(release_ms, 3),
                "total_ms": round(total_ms, 3),
                "core_mask": core_mask_name,
            }
        )
    except Exception as exc:
        return emit(
            {
                "ok": False,
                "runtime": "rknnlite",
                "error": repr(exc),
                "model_path": str(model_path),
            },
            rc=1,
        )
    finally:
        if rknn is not None:
            try:
                rknn.release()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
