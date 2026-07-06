#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def emit(payload: dict, rc: int = 0) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return rc


def summarize_outputs(outputs):
    import numpy as np

    shapes = []
    dtypes = []
    stats = []

    for idx, out in enumerate(outputs or []):
        arr = np.asarray(out)
        shapes.append([int(x) for x in arr.shape])
        dtypes.append(str(arr.dtype))

        item = {
            "index": idx,
            "shape": [int(x) for x in arr.shape],
            "dtype": str(arr.dtype),
            "size": int(arr.size),
        }

        if arr.size > 0:
            # Use float64 conversion only for compact summary stats, never dump raw tensors.
            arr64 = arr.astype("float64", copy=False)
            item.update(
                {
                    "min": float(arr64.min()),
                    "max": float(arr64.max()),
                    "mean": float(arr64.mean()),
                }
            )

        stats.append(item)

    return shapes, dtypes, stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe RKNN YOLO inference and return output metadata.")
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--image-path", required=True)
    parser.add_argument("--input-width", type=int, default=640)
    parser.add_argument("--input-height", type=int, default=640)
    parser.add_argument("--runtime", default="rknnlite", choices=["rknnlite"])
    args = parser.parse_args()

    model_path = Path(args.model_path)
    image_path = Path(args.image_path)

    if not model_path.exists():
        return emit(
            {
                "ok": False,
                "error": f"RKNN model not found: {model_path}",
                "model_path": str(model_path),
            },
            rc=2,
        )

    if not image_path.exists():
        return emit(
            {
                "ok": False,
                "error": f"image not found: {image_path}",
                "image_path": str(image_path),
            },
            rc=3,
        )

    started = time.time()
    rknn = None

    try:
        import_started = time.time()
        import cv2
        import numpy as np
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
                rc=4,
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
                rc=5,
            )

        preprocess_started = time.time()
        img = cv2.imread(str(image_path))
        if img is None:
            return emit(
                {
                    "ok": False,
                    "runtime": "rknnlite",
                    "error": f"cv2 failed to read image: {image_path}",
                    "image_path": str(image_path),
                },
                rc=6,
            )

        original_shape = [int(x) for x in img.shape]
        img = cv2.resize(img, (args.input_width, args.input_height), interpolation=cv2.INTER_LINEAR)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.uint8)
        input_tensor = np.expand_dims(img, axis=0)
        preprocess_ms = (time.time() - preprocess_started) * 1000.0

        inference_started = time.time()
        outputs = rknn.inference(inputs=[input_tensor])
        inference_ms = (time.time() - inference_started) * 1000.0

        output_shapes, output_dtypes, output_stats = summarize_outputs(outputs)

        release_started = time.time()
        rknn.release()
        rknn = None
        release_ms = (time.time() - release_started) * 1000.0

        backend_init_ms = import_ms + create_ms + load_ms + init_ms
        total_ms = (time.time() - started) * 1000.0

        return emit(
            {
                "ok": True,
                "runtime": "rknnlite",
                "model_path": str(model_path),
                "model_size_mb": round(model_path.stat().st_size / 1024 / 1024, 3),
                "image_path": str(image_path),
                "original_image_shape": original_shape,
                "input_tensor_shape": [int(x) for x in input_tensor.shape],
                "input_tensor_dtype": str(input_tensor.dtype),
                "input_tensor_layout": "NHWC",
                "import_ms": round(import_ms, 3),
                "create_ms": round(create_ms, 3),
                "load_rknn_ms": round(load_ms, 3),
                "init_runtime_ms": round(init_ms, 3),
                "backend_init_ms": round(backend_init_ms, 3),
                "preprocess_ms": round(preprocess_ms, 3),
                "inference_ms": round(inference_ms, 3),
                "release_ms": round(release_ms, 3),
                "total_ms": round(total_ms, 3),
                "core_mask": core_mask_name,
                "num_outputs": len(outputs or []),
                "output_shapes": output_shapes,
                "output_dtypes": output_dtypes,
                "output_stats": output_stats,
            }
        )
    except Exception as exc:
        return emit(
            {
                "ok": False,
                "runtime": "rknnlite",
                "error": repr(exc),
                "model_path": str(model_path),
                "image_path": str(image_path),
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
