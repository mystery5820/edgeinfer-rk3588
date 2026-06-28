#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
import sys
import time
from pathlib import Path
from typing import List, Tuple

import numpy as np

try:
    import yaml
except ImportError:
    raise SystemExit("PyYAML is not installed. Please run: pip install pyyaml")

try:
    import cv2
except ImportError:
    raise SystemExit("OpenCV is not installed. Please run: pip install opencv-python")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from server.vision.yolo_postprocess import postprocess_yolo_outputs


REGISTRY_PATH = PROJECT_ROOT / "configs" / "model_registry.yaml"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


def load_registry():
    with REGISTRY_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("models", [])


def find_model(model_name: str):
    for model in load_registry():
        if model.get("name") == model_name:
            return model
    raise ValueError(f"Model not found in registry: {model_name}")


def resolve_path(path_value: str) -> Path:
    p = Path(path_value)
    if p.is_absolute():
        return p
    return PROJECT_ROOT / p


def human_size_mb(path: Path) -> float:
    return path.stat().st_size / 1024 / 1024


def discover_images(image_dir: Path, limit: int) -> List[Path]:
    if not image_dir.exists():
        raise FileNotFoundError(f"Image directory not found: {image_dir}")

    images = []
    for p in sorted(image_dir.rglob("*")):
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
            images.append(p)
            if len(images) >= limit:
                break

    if not images:
        raise FileNotFoundError(f"No images found in: {image_dir}")

    return images


def preprocess_image(image_path: Path, input_size: Tuple[int, int], add_batch: bool) -> np.ndarray:
    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError(f"Failed to read image: {image_path}")

    width, height = input_size
    img = cv2.resize(img, (width, height), interpolation=cv2.INTER_LINEAR)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = img.astype(np.uint8)

    if add_batch:
        img = np.expand_dims(img, axis=0)

    return img


def make_fake_yolo_output() -> np.ndarray:
    """
    Fake YOLO output for dry-run mode.
    Shape: [1, 84, 4]
    It should produce 2 detections after NMS.
    """
    num_classes = 80
    num_boxes = 4
    channels = 4 + num_classes

    pred = np.zeros((1, channels, num_boxes), dtype=np.float32)

    pred[0, 0:4, 0] = [100, 100, 80, 80]
    pred[0, 4 + 0, 0] = 0.95

    pred[0, 0:4, 1] = [105, 105, 80, 80]
    pred[0, 4 + 0, 1] = 0.80

    pred[0, 0:4, 2] = [300, 300, 60, 60]
    pred[0, 4 + 2, 2] = 0.90

    pred[0, 0:4, 3] = [500, 500, 50, 50]
    pred[0, 4 + 1, 3] = 0.10

    return pred


class DryRunRuntime:
    name = "dryrun"

    def infer(self, input_tensor):
        return [make_fake_yolo_output()]

    def release(self):
        pass


class RKNNLiteRuntime:
    name = "rknnlite"

    def __init__(self, model_path: Path):
        from rknnlite.api import RKNNLite

        self.RKNNLite = RKNNLite
        self.rknn = RKNNLite()

        ret = self.rknn.load_rknn(str(model_path))
        if ret != 0:
            raise RuntimeError(f"RKNNLite load_rknn failed, ret={ret}")

        core_mask = getattr(RKNNLite, "NPU_CORE_0_1_2", getattr(RKNNLite, "NPU_CORE_AUTO", None))

        if core_mask is not None:
            ret = self.rknn.init_runtime(core_mask=core_mask)
        else:
            ret = self.rknn.init_runtime()

        if ret != 0:
            raise RuntimeError(f"RKNNLite init_runtime failed, ret={ret}")

    def infer(self, input_tensor):
        return self.rknn.inference(inputs=[input_tensor])

    def release(self):
        self.rknn.release()


class RKNNApiRuntime:
    name = "rknnapi"

    def __init__(self, model_path: Path):
        from rknn.api import RKNN

        self.rknn = RKNN()

        ret = self.rknn.load_rknn(str(model_path))
        if ret != 0:
            raise RuntimeError(f"RKNN API load_rknn failed, ret={ret}")

        ret = self.rknn.init_runtime()
        if ret != 0:
            raise RuntimeError(f"RKNN API init_runtime failed, ret={ret}")

    def infer(self, input_tensor):
        return self.rknn.inference(inputs=[input_tensor])

    def release(self):
        self.rknn.release()


def create_runtime(runtime_name: str, model_path: Path):
    if runtime_name == "dryrun":
        return DryRunRuntime()

    if runtime_name == "rknnlite":
        return RKNNLiteRuntime(model_path)

    if runtime_name == "rknnapi":
        return RKNNApiRuntime(model_path)

    if runtime_name == "auto":
        errors = []

        try:
            return RKNNLiteRuntime(model_path)
        except Exception as e:
            errors.append(f"rknnlite failed: {e}")

        try:
            return RKNNApiRuntime(model_path)
        except Exception as e:
            errors.append(f"rknnapi failed: {e}")

        error_text = "\n".join(errors)
        raise RuntimeError(
            "No available RKNN runtime. "
            "Use --runtime dryrun on PC, or run this script on RK3588 board.\n"
            + error_text
        )

    raise ValueError(f"Unknown runtime: {runtime_name}")


def write_csv(rows, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "model_name",
        "runtime",
        "image_path",
        "repeat_idx",
        "input_size",
        "add_batch",
        "model_size_mb",
        "conf_thres",
        "iou_thres",
        "preprocess_ms",
        "inference_ms",
        "postprocess_ms",
        "end_to_end_ms",
        "fps",
        "num_outputs",
        "num_detections",
        "ok",
        "error",
    ]

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows):
    valid = [r for r in rows if r["ok"] == "true"]
    if not valid:
        print("No valid benchmark rows.")
        return

    def avg(key):
        return sum(float(r[key]) for r in valid) / len(valid)

    avg_pre = avg("preprocess_ms")
    avg_inf = avg("inference_ms")
    avg_post = avg("postprocess_ms")
    avg_e2e = avg("end_to_end_ms")
    avg_det = avg("num_detections")
    fps = 1000.0 / avg_e2e if avg_e2e > 0 else 0.0

    print("\n========== YOLOv11 Benchmark Summary ==========")
    print(f"Valid samples       : {len(valid)}")
    print(f"Avg preprocess ms   : {avg_pre:.3f}")
    print(f"Avg inference ms    : {avg_inf:.3f}")
    print(f"Avg postprocess ms  : {avg_post:.3f}")
    print(f"Avg e2e ms          : {avg_e2e:.3f}")
    print(f"Estimated FPS       : {fps:.2f}")
    print(f"Avg detections      : {avg_det:.2f}")
    print("===============================================")


def main():
    parser = argparse.ArgumentParser(description="YOLOv11 RKNN benchmark with postprocess.")
    parser.add_argument("--model", default="YOLOv11n-INT8-Baseline")
    parser.add_argument("--image-dir", default="datasets/coco128/images/train2017")
    parser.add_argument("--runtime", default="dryrun", choices=["dryrun", "auto", "rknnlite", "rknnapi"])
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--add-batch", action="store_true")
    parser.add_argument("--conf-thres", type=float, default=0.25)
    parser.add_argument("--iou-thres", type=float, default=0.45)
    parser.add_argument("--output", default="results/benchmark/yolo11_benchmark.csv")
    args = parser.parse_args()

    model = find_model(args.model)
    model_path = resolve_path(model["runtime_model"])
    input_size = tuple(model.get("input_size", [640, 640]))

    if not model_path.exists():
        raise FileNotFoundError(f"RKNN model not found: {model_path}")

    image_dir = resolve_path(args.image_dir)
    images = discover_images(image_dir, args.limit)

    print("========== Benchmark Config ==========")
    print(f"Model       : {args.model}")
    print(f"Runtime     : {args.runtime}")
    print(f"Model path  : {model_path}")
    print(f"Image dir   : {image_dir}")
    print(f"Images      : {len(images)}")
    print(f"Input size  : {input_size}")
    print(f"Add batch   : {args.add_batch}")
    print(f"Conf thres  : {args.conf_thres}")
    print(f"IoU thres   : {args.iou_thres}")
    print("======================================")

    runtime = create_runtime(args.runtime, model_path)

    try:
        if args.runtime != "dryrun":
            print("Running warmup...")
            sample = preprocess_image(images[0], input_size, args.add_batch)
            for _ in range(args.warmup):
                runtime.infer(sample)

        rows = []
        model_size = human_size_mb(model_path)

        print("Running benchmark...")

        for image_path in images:
            for repeat_idx in range(args.repeat):
                row = {
                    "model_name": args.model,
                    "runtime": runtime.name,
                    "image_path": str(image_path.relative_to(PROJECT_ROOT)),
                    "repeat_idx": repeat_idx,
                    "input_size": f"{input_size[0]}x{input_size[1]}",
                    "add_batch": str(args.add_batch).lower(),
                    "model_size_mb": f"{model_size:.3f}",
                    "conf_thres": f"{args.conf_thres:.3f}",
                    "iou_thres": f"{args.iou_thres:.3f}",
                    "preprocess_ms": "0.000",
                    "inference_ms": "0.000",
                    "postprocess_ms": "0.000",
                    "end_to_end_ms": "0.000",
                    "fps": "0.000",
                    "num_outputs": "0",
                    "num_detections": "0",
                    "ok": "false",
                    "error": "",
                }

                try:
                    t0 = time.perf_counter()

                    t_pre0 = time.perf_counter()
                    input_tensor = preprocess_image(image_path, input_size, args.add_batch)
                    t_pre1 = time.perf_counter()

                    t_inf0 = time.perf_counter()
                    outputs = runtime.infer(input_tensor)
                    t_inf1 = time.perf_counter()

                    t_post0 = time.perf_counter()
                    detections = postprocess_yolo_outputs(
                        outputs=outputs,
                        conf_thres=args.conf_thres,
                        iou_thres=args.iou_thres,
                        box_format="xywh",
                        input_size=input_size,
                    )
                    t_post1 = time.perf_counter()

                    t1 = time.perf_counter()

                    preprocess_ms = (t_pre1 - t_pre0) * 1000.0
                    inference_ms = (t_inf1 - t_inf0) * 1000.0
                    postprocess_ms = (t_post1 - t_post0) * 1000.0
                    e2e_ms = (t1 - t0) * 1000.0
                    fps = 1000.0 / e2e_ms if e2e_ms > 0 else 0.0

                    row.update({
                        "preprocess_ms": f"{preprocess_ms:.3f}",
                        "inference_ms": f"{inference_ms:.3f}",
                        "postprocess_ms": f"{postprocess_ms:.3f}",
                        "end_to_end_ms": f"{e2e_ms:.3f}",
                        "fps": f"{fps:.3f}",
                        "num_outputs": str(len(outputs) if outputs is not None else 0),
                        "num_detections": str(len(detections)),
                        "ok": "true",
                    })

                except Exception as e:
                    row["error"] = str(e)

                rows.append(row)

        output_path = resolve_path(args.output)
        write_csv(rows, output_path)
        summarize(rows)

        print(f"\nCSV saved to: {output_path}")

    finally:
        runtime.release()


if __name__ == "__main__":
    main()
