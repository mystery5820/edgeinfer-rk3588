#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from server.vision.coco_classes import coco_class_name
from server.vision.yolo_postprocess import postprocess_yolo_outputs


EDGEINFER_JSON_PREFIX = "__EDGEINFER_JSON__ "


def emit(payload: dict) -> None:
    print(EDGEINFER_JSON_PREFIX + json.dumps(payload, ensure_ascii=False), flush=True)


def summarize_outputs(outputs):
    import numpy as np

    shapes = []
    dtypes = []

    for out in outputs or []:
        arr = np.asarray(out)
        shapes.append([int(x) for x in arr.shape])
        dtypes.append(str(arr.dtype))

    return shapes, dtypes


def clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def refine_detection(
    det: Dict[str, object],
    *,
    original_width: int,
    original_height: int,
    input_width: int,
    input_height: int,
) -> Dict[str, object]:
    box_input = [float(x) for x in (det.get("box") or det.get("bbox") or [0.0, 0.0, 0.0, 0.0])]
    if len(box_input) != 4:
        box_input = [0.0, 0.0, 0.0, 0.0]

    scale_x = float(original_width) / max(float(input_width), 1.0)
    scale_y = float(original_height) / max(float(input_height), 1.0)

    x1 = clip(box_input[0] * scale_x, 0.0, float(original_width))
    y1 = clip(box_input[1] * scale_y, 0.0, float(original_height))
    x2 = clip(box_input[2] * scale_x, 0.0, float(original_width))
    y2 = clip(box_input[3] * scale_y, 0.0, float(original_height))

    cls_id = int(det.get("class_id", -1))
    score = float(det.get("score", det.get("confidence", 0.0)))

    return {
        "bbox": [x1, y1, x2, y2],
        "bbox_input": box_input,
        "score": score,
        "class_id": cls_id,
        "class_name": coco_class_name(cls_id),
        "box_format": "xyxy",
        "coordinate_space": "original_image",
        "bbox_input_coordinate_space": "model_input_640x640",
    }


def create_runtime(model_path: Path):
    from rknnlite.api import RKNNLite

    rknn = RKNNLite()

    load_started = time.time()
    ret = rknn.load_rknn(str(model_path))
    load_ms = (time.time() - load_started) * 1000.0
    if ret != 0:
        raise RuntimeError(f"load_rknn failed, ret={ret}")

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
        raise RuntimeError(f"init_runtime failed, ret={ret}")

    return rknn, load_ms, init_ms, core_mask_name


def run_detection(
    *,
    rknn,
    image_path: Path,
    input_width: int,
    input_height: int,
    conf_thres: float,
    iou_thres: float,
) -> Dict[str, object]:
    import cv2
    import numpy as np

    if not image_path.exists():
        raise FileNotFoundError(f"image not found: {image_path}")

    preprocess_started = time.time()
    img = cv2.imread(str(image_path))
    if img is None:
        raise RuntimeError(f"cv2 failed to read image: {image_path}")

    original_height = int(img.shape[0])
    original_width = int(img.shape[1])
    original_shape = [int(x) for x in img.shape]

    img = cv2.resize(img, (input_width, input_height), interpolation=cv2.INTER_LINEAR)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = img.astype(np.uint8)
    input_tensor = np.expand_dims(img, axis=0)
    preprocess_ms = (time.time() - preprocess_started) * 1000.0

    inference_started = time.time()
    outputs = rknn.inference(inputs=[input_tensor])
    inference_ms = (time.time() - inference_started) * 1000.0

    output_shapes, output_dtypes = summarize_outputs(outputs)

    postprocess_started = time.time()
    raw_detections = postprocess_yolo_outputs(
        outputs=outputs,
        conf_thres=conf_thres,
        iou_thres=iou_thres,
        box_format="xywh",
        input_size=(input_width, input_height),
    )
    detections = [
        refine_detection(
            det,
            original_width=original_width,
            original_height=original_height,
            input_width=input_width,
            input_height=input_height,
        )
        for det in raw_detections[:100]
    ]
    postprocess_ms = (time.time() - postprocess_started) * 1000.0

    return {
        "original_image_shape": original_shape,
        "original_image_width": original_width,
        "original_image_height": original_height,
        "input_tensor_shape": [int(x) for x in input_tensor.shape],
        "input_tensor_dtype": str(input_tensor.dtype),
        "input_tensor_layout": "NHWC",
        "coordinate_space": "original_image",
        "bbox_input_coordinate_space": "model_input_640x640",
        "coordinate_transform": "direct_resize_scale_back",
        "preprocess_ms": round(preprocess_ms, 3),
        "inference_ms": round(inference_ms, 3),
        "postprocess_ms": round(postprocess_ms, 3),
        "num_outputs": len(outputs or []),
        "output_shapes": output_shapes,
        "output_dtypes": output_dtypes,
        "num_detections": len(detections),
        "detections": detections,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Persistent RKNN YOLO worker.")
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--input-width", type=int, default=640)
    parser.add_argument("--input-height", type=int, default=640)
    parser.add_argument("--runtime", default="rknnlite", choices=["rknnlite"])
    args = parser.parse_args()

    model_path = Path(args.model_path)

    if not model_path.exists():
        emit(
            {
                "type": "ready",
                "ok": False,
                "error": f"RKNN model not found: {model_path}",
                "model_path": str(model_path),
            }
        )
        return 2

    started = time.time()
    rknn = None

    try:
        import_started = time.time()
        import cv2  # noqa: F401
        import numpy as np  # noqa: F401
        from rknnlite.api import RKNNLite  # noqa: F401
        import_ms = (time.time() - import_started) * 1000.0

        create_started = time.time()
        rknn, load_ms, init_ms, core_mask_name = create_runtime(model_path)
        create_runtime_ms = (time.time() - create_started) * 1000.0

        startup_ms = (time.time() - started) * 1000.0

        emit(
            {
                "type": "ready",
                "ok": True,
                "runtime": "rknnlite",
                "backend": "rknn-yolo-worker",
                "model_path": str(model_path),
                "model_size_mb": round(model_path.stat().st_size / 1024 / 1024, 3),
                "input_width": args.input_width,
                "input_height": args.input_height,
                "import_ms": round(import_ms, 3),
                "load_rknn_ms": round(load_ms, 3),
                "init_runtime_ms": round(init_ms, 3),
                "create_runtime_ms": round(create_runtime_ms, 3),
                "startup_ms": round(startup_ms, 3),
                "core_mask": core_mask_name,
            }
        )

        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
            except json.JSONDecodeError as exc:
                emit(
                    {
                        "type": "response",
                        "id": None,
                        "ok": False,
                        "error": f"invalid JSON request: {exc}",
                    }
                )
                continue

            if request.get("command") == "stop":
                emit({"type": "stopped", "ok": True})
                break

            request_id = request.get("id")
            request_started = time.time()

            try:
                image_path = Path(str(request.get("image_path") or ""))
                conf_thres = float(request.get("conf_thres", 0.25))
                iou_thres = float(request.get("iou_thres", 0.45))

                result = run_detection(
                    rknn=rknn,
                    image_path=image_path,
                    input_width=args.input_width,
                    input_height=args.input_height,
                    conf_thres=conf_thres,
                    iou_thres=iou_thres,
                )

                total_ms = (time.time() - request_started) * 1000.0

                emit(
                    {
                        "type": "response",
                        "id": request_id,
                        "ok": True,
                        "runtime": "rknnlite",
                        "backend": "rknn-yolo-worker",
                        "model_path": str(model_path),
                        "model_size_mb": round(model_path.stat().st_size / 1024 / 1024, 3),
                        "image_path": str(image_path),
                        "conf_thres": conf_thres,
                        "iou_thres": iou_thres,
                        "total_ms": round(total_ms, 3),
                        "core_mask": core_mask_name,
                        **result,
                    }
                )
            except Exception as exc:
                total_ms = (time.time() - request_started) * 1000.0
                emit(
                    {
                        "type": "response",
                        "id": request_id,
                        "ok": False,
                        "runtime": "rknnlite",
                        "backend": "rknn-yolo-worker",
                        "model_path": str(model_path),
                        "error": repr(exc),
                        "total_ms": round(total_ms, 3),
                    }
                )

        return 0

    except Exception as exc:
        emit(
            {
                "type": "ready",
                "ok": False,
                "runtime": "rknnlite",
                "backend": "rknn-yolo-worker",
                "model_path": str(model_path),
                "error": repr(exc),
            }
        )
        return 1
    finally:
        if rknn is not None:
            try:
                rknn.release()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
