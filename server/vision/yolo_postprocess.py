#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Dict, List, Sequence, Tuple

import numpy as np


def xywh_to_xyxy(boxes: np.ndarray) -> np.ndarray:
    """Convert boxes from cx, cy, w, h to x1, y1, x2, y2."""
    out = boxes.copy()
    out[:, 0] = boxes[:, 0] - boxes[:, 2] / 2.0
    out[:, 1] = boxes[:, 1] - boxes[:, 3] / 2.0
    out[:, 2] = boxes[:, 0] + boxes[:, 2] / 2.0
    out[:, 3] = boxes[:, 1] + boxes[:, 3] / 2.0
    return out


def box_iou(box: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    """Calculate IoU between one box and many boxes."""
    x1 = np.maximum(box[0], boxes[:, 0])
    y1 = np.maximum(box[1], boxes[:, 1])
    x2 = np.minimum(box[2], boxes[:, 2])
    y2 = np.minimum(box[3], boxes[:, 3])

    inter_w = np.maximum(0.0, x2 - x1)
    inter_h = np.maximum(0.0, y2 - y1)
    inter = inter_w * inter_h

    area1 = np.maximum(0.0, box[2] - box[0]) * np.maximum(0.0, box[3] - box[1])
    area2 = np.maximum(0.0, boxes[:, 2] - boxes[:, 0]) * np.maximum(0.0, boxes[:, 3] - boxes[:, 1])

    union = area1 + area2 - inter
    return inter / np.maximum(union, 1e-6)


def nms(
    boxes: np.ndarray,
    scores: np.ndarray,
    iou_thres: float = 0.45,
) -> List[int]:
    """Class-agnostic NMS."""
    if len(boxes) == 0:
        return []

    order = scores.argsort()[::-1]
    keep = []

    while order.size > 0:
        i = int(order[0])
        keep.append(i)

        if order.size == 1:
            break

        ious = box_iou(boxes[i], boxes[order[1:]])
        order = order[1:][ious <= iou_thres]

    return keep


def normalize_yolo_output(output: np.ndarray) -> np.ndarray:
    """
    Normalize common YOLO output layouts to [num_boxes, channels].

    Supported:
    - [1, 84, 8400] -> [8400, 84]
    - [84, 8400]    -> [8400, 84]
    - [1, 8400, 84] -> [8400, 84]
    - [8400, 84]    -> [8400, 84]
    - [1, 84, 4]    -> [4, 84], used by unit test
    """
    pred = np.asarray(output)
    pred = np.squeeze(pred)

    if pred.ndim != 2:
        raise ValueError(f"Unsupported YOLO output shape after squeeze: {pred.shape}")

    dim0, dim1 = pred.shape

    def looks_like_channel_dim(x: int) -> bool:
        # YOLO channels = 4 bbox channels + class scores.
        # Common values: 84 for COCO, but allow smaller synthetic tests.
        return 6 <= x <= 256

    # [channels, boxes] -> [boxes, channels]
    if looks_like_channel_dim(dim0) and not looks_like_channel_dim(dim1):
        pred = pred.T

    # Synthetic small case, e.g. [84, 4]
    elif looks_like_channel_dim(dim0) and dim1 < 6:
        pred = pred.T

    # Ambiguous small case; prefer treating the larger dim as channels.
    elif looks_like_channel_dim(dim0) and looks_like_channel_dim(dim1) and dim0 >= dim1:
        pred = pred.T

    # [boxes, channels], keep as is
    elif looks_like_channel_dim(dim1):
        pass

    else:
        raise ValueError(f"Cannot infer YOLO output layout: {pred.shape}")

    if pred.shape[1] < 6:
        raise ValueError(f"Invalid YOLO output channel size after normalize: {pred.shape}")

    return pred


def postprocess_yolo_outputs(
    outputs: Sequence[np.ndarray],
    conf_thres: float = 0.25,
    iou_thres: float = 0.45,
    box_format: str = "xywh",
    input_size: Tuple[int, int] = (640, 640),
    class_names: Sequence[str] = None,
) -> List[Dict]:
    """
    Generic YOLO postprocess for one-output YOLOv8 / YOLOv11 style models.
    """
    if outputs is None or len(outputs) == 0:
        return []

    pred = normalize_yolo_output(np.asarray(outputs[0]))

    boxes = pred[:, :4].astype(np.float32)
    cls_scores = pred[:, 4:].astype(np.float32)

    class_ids = np.argmax(cls_scores, axis=1)
    scores = cls_scores[np.arange(cls_scores.shape[0]), class_ids]

    mask = scores >= conf_thres
    boxes = boxes[mask]
    scores = scores[mask]
    class_ids = class_ids[mask]

    if len(boxes) == 0:
        return []

    if box_format == "xywh":
        boxes = xywh_to_xyxy(boxes)
    elif box_format != "xyxy":
        raise ValueError(f"Unsupported box_format: {box_format}")

    width, height = input_size
    boxes[:, [0, 2]] = np.clip(boxes[:, [0, 2]], 0, width)
    boxes[:, [1, 3]] = np.clip(boxes[:, [1, 3]], 0, height)

    keep = nms(boxes, scores, iou_thres=iou_thres)

    detections = []
    for idx in keep:
        cls_id = int(class_ids[idx])
        cls_name = class_names[cls_id] if class_names and cls_id < len(class_names) else str(cls_id)

        detections.append({
            "box": [float(x) for x in boxes[idx].tolist()],
            "score": float(scores[idx]),
            "class_id": cls_id,
            "class_name": cls_name,
        })

    return detections
