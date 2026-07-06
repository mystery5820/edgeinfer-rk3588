# Phase 18F：YOLO Postprocess Integration

本文档记录 Phase 18F：在 `/v1/vision/detect` 调用链中执行真实 RKNNLite inference，并接入 YOLO postprocess，返回 detection objects。

---

## 1. 背景

Phase 18E 已经完成：

```text
真实图片读取
NHWC uint8 tensor 构造
RKNNLite inference
output_shapes / output_dtypes / output_stats
```

Phase 18F 在此基础上接入：

```text
server.vision.yolo_postprocess.postprocess_yolo_outputs
confidence_threshold
iou_threshold
objects 输出
```

---

## 2. 前置验证结论

现有 `server/vision/yolo_postprocess.py` 已支持：

```text
[1, 84, 8400] -> [8400, 84]
xywh -> xyxy
confidence filter
class-agnostic NMS
```

`tools/benchmark_yolo11_rknn.py` 已经使用同一个 `postprocess_yolo_outputs`。

FP 模型 3 张图预览结果：

```text
000000000009.jpg: num_detections = 5
000000000025.jpg: num_detections = 1
000000000030.jpg: num_detections = 2
Avg inference_ms ≈ 146 ms
Avg postprocess_ms ≈ 12 ms
Avg e2e_ms ≈ 172 ms
Avg detections ≈ 2.67
```

因此 Phase 18F 优先用 `YOLOv11n-FP-Baseline` 验证真实 objects 输出。

---

## 3. 本阶段目标

Phase 18F 完成：

```text
1. 新增 rknn-yolo-detect-probe backend；
2. 新增 board subprocess detect probe；
3. 在 subprocess 中运行 cv2 / numpy / rknnlite；
4. 调用 rknn.inference；
5. 调用 postprocess_yolo_outputs；
6. 返回 num_detections；
7. 返回 detections；
8. API 将 detections 规范化为 objects；
9. 对外返回 bbox / confidence / class_id / class_name。
```

---

## 4. 新增文件

```text
scripts/board/probe_rknn_yolo_detect.py
scripts/board/enable_edgeinfer_vision_rknn_detect_probe.sh
scripts/board/disable_edgeinfer_vision_rknn_detect_probe.sh
docs/phase18f_yolo_postprocess_integration.md
```

更新：

```text
server/runtime/rknn_yolo_backend.py
server/api/vision_api.py
scripts/host/test_vision_detect_client.py
README.md
docs/README.md
```

---

## 5. Backend 模式

默认：

```text
fake-vision
```

Phase 18D dryrun：

```text
EDGEINFER_VISION_BACKEND_MODE=rknn-yolo-dryrun
```

Phase 18E inference probe：

```text
EDGEINFER_VISION_BACKEND_MODE=rknn-yolo-inference-probe
```

Phase 18F detect probe：

```text
EDGEINFER_VISION_BACKEND_MODE=rknn-yolo-detect-probe
```

---

## 6. 启用方式

板端执行：

```bash
cd /home/linaro/edgeinfer-rk3588-board
./scripts/board/enable_edgeinfer_vision_rknn_detect_probe.sh
```

恢复 fake backend：

```bash
cd /home/linaro/edgeinfer-rk3588-board
./scripts/board/disable_edgeinfer_vision_rknn_detect_probe.sh
```

---

## 7. API Response 变化

启用 Phase 18F 后，`/v1/vision/detect` 返回真实 objects：

```json
{
  "object": "vision.detection",
  "model": "YOLOv11n-FP-Baseline",
  "objects": [
    {
      "class_id": 0,
      "class_name": "0",
      "confidence": 0.83,
      "bbox": [100.0, 120.0, 300.0, 480.0],
      "box_format": "xyxy"
    }
  ],
  "edgeinfer": {
    "backend": "rknn-yolo-detect-probe",
    "runtime": "phase18f-yolo-postprocess-integration",
    "model_runtime": {
      "output_summary": {
        "num_outputs": 1,
        "output_shapes": [[1, 84, 8400]],
        "num_detections": 5
      }
    }
  }
}
```

说明：

```text
class_name 暂时可能是 class_id 字符串；
后续可接入 COCO label names。
```

---

## 8. Host 测试

默认 fake backend：

```bash
python3 scripts/host/test_vision_detect_client.py
```

Phase 18F detect probe backend：

```bash
EDGEINFER_EXPECT_VISION_BACKEND=rknn-yolo-detect-probe \
python3 scripts/host/test_vision_detect_client.py
```

测试脚本在 detect probe 模式下会优先使用：

```text
YOLOv11n-FP-Baseline
```

因为当前 FP 模型是已验证可产生 detections 的模型。

---

## 9. 当前限制

Phase 18F 仍是 probe backend，不建议直接作为默认线上模式：

```text
1. 每次请求都会新建 subprocess；
2. 每次请求都会重新 import cv2 / rknnlite；
3. 每次请求都会 load/init/release RKNN；
4. class_name 暂无 COCO 标签；
5. 还没有持久 worker；
6. 还没有 camera stream。
```

---

## 10. 后续阶段

### Phase 18G：Vision Backend Stabilization

下一步建议：

```text
1. 对 FP detect probe 做稳定性测试；
2. 加入 COCO class names；
3. 改善 bbox / preprocess 对齐说明；
4. 设计 persistent RKNN worker；
5. 为 vision 加入 queue / reject_when_busy；
6. 最终将稳定 backend 设为正式 vision backend。
```

---

## 11. 阶段结论

Phase 18F 完成后，Vision Serving 将首次具备完整链路：

```text
/v1/vision/detect
  -> image_path
  -> cv2 preprocess
  -> RKNNLite inference
  -> YOLO postprocess
  -> objects
```

这意味着项目已经从“视觉 API 框架”进入“真实视觉检测服务”阶段。
