#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
import sys

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from server.vision.yolo_postprocess import postprocess_yolo_outputs


def make_fake_yolo_output():
    """
    Create fake YOLO output in [1, 84, N] layout.

    COCO-style output:
    - 4 box channels
    - 80 class score channels
    """
    num_classes = 80
    num_boxes = 4
    channels = 4 + num_classes

    pred = np.zeros((1, channels, num_boxes), dtype=np.float32)

    # box 0: person, high score
    pred[0, 0:4, 0] = [100, 100, 80, 80]
    pred[0, 4 + 0, 0] = 0.95

    # box 1: overlaps with box 0, lower score, should be removed by NMS
    pred[0, 0:4, 1] = [105, 105, 80, 80]
    pred[0, 4 + 0, 1] = 0.80

    # box 2: different class, should remain
    pred[0, 0:4, 2] = [300, 300, 60, 60]
    pred[0, 4 + 2, 2] = 0.90

    # box 3: low confidence, should be filtered
    pred[0, 0:4, 3] = [500, 500, 50, 50]
    pred[0, 4 + 1, 3] = 0.10

    return pred


def main():
    output = make_fake_yolo_output()

    detections = postprocess_yolo_outputs(
        outputs=[output],
        conf_thres=0.25,
        iou_thres=0.45,
        box_format="xywh",
        input_size=(640, 640),
    )

    print("Detections:")
    for det in detections:
        print(det)

    assert len(detections) == 2, f"Expected 2 detections, got {len(detections)}"

    class_ids = sorted([d["class_id"] for d in detections])
    assert class_ids == [0, 2], f"Expected class ids [0, 2], got {class_ids}"

    print("YOLO postprocess test passed.")


if __name__ == "__main__":
    main()
