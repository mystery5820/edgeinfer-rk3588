# Phase 18E：RKNN YOLO Inference Probe

本文档记录 Phase 18E：在 `/v1/vision/detect` 调用链中执行一次真实 RKNNLite inference，并返回 output metadata。

---

## 1. 背景

Phase 18D 已经验证：

```text
RKNNLite import
load_rknn
init_runtime
release
```

Phase 18E 继续推进到：

```text
cv2 读取图片
resize 到 640x640
BGR -> RGB
uint8 tensor
expand batch
rknn.inference
返回 output_shapes / output_dtypes / output_stats
```

---

## 2. 前置验证结论

板端 system python3 具备：

```text
cv2
numpy
rknnlite.api
```

Benchmark 前置验证说明模型需要 4D 输入：

```text
[1, 640, 640, 3]
```

不加 batch 时会报：

```text
The input[0] need 4dims input, but 3dims input buffer feed.
```

加 `--add-batch` 后：

```text
YOLOv11n-FP-Baseline:
  num_outputs = 1
  num_detections = 5
  inference_ms ≈ 145 ms

YOLOv11n-INT8-Baseline:
  num_outputs = 1
  num_detections = 0
  inference_ms ≈ 61 ms
```

因此 Phase 18E 固定使用 NHWC + batch：

```text
[1, 640, 640, 3]
```

---

## 3. 本阶段目标

Phase 18E 完成：

```text
1. 新增 rknn-yolo-inference-probe backend；
2. 新增 board subprocess inference probe；
3. 使用 system python3 调用 cv2 / numpy / rknnlite；
4. 构造 NHWC uint8 input tensor；
5. 调用 rknn.inference；
6. 返回 num_outputs；
7. 返回 output_shapes；
8. 返回 output_dtypes；
9. 返回 output_stats；
10. 在 API 中暴露 inference_ms。
```

仍不做：

```text
1. YOLO decode；
2. NMS；
3. bbox 输出；
4. class label 映射；
5. 摄像头实时流。
```

---

## 4. 新增文件

```text
scripts/board/probe_rknn_yolo_inference.py
scripts/board/enable_edgeinfer_vision_rknn_inference_probe.sh
scripts/board/disable_edgeinfer_vision_rknn_inference_probe.sh
docs/phase18e_rknn_yolo_inference_probe.md
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

---

## 6. 启用方式

板端执行：

```bash
cd /home/linaro/edgeinfer-rk3588-board
./scripts/board/enable_edgeinfer_vision_rknn_inference_probe.sh
```

恢复 fake backend：

```bash
cd /home/linaro/edgeinfer-rk3588-board
./scripts/board/disable_edgeinfer_vision_rknn_inference_probe.sh
```

---

## 7. API Response 变化

启用 Phase 18E 后，`/v1/vision/detect` 返回：

```json
{
  "edgeinfer": {
    "backend": "rknn-yolo-inference-probe",
    "runtime": "phase18e-rknn-yolo-inference-probe",
    "model_runtime": {
      "backend": "rknn-yolo-inference-probe",
      "output_summary": {
        "num_outputs": 1,
        "output_shapes": [[1, 84, 8400]],
        "output_dtypes": ["float32"],
        "output_stats": [
          {
            "index": 0,
            "shape": [1, 84, 8400],
            "dtype": "float32",
            "size": 705600,
            "min": 0.0,
            "max": 640.0,
            "mean": 12.3
          }
        ]
      }
    }
  },
  "latency_ms": {
    "load_image": 0.3,
    "preprocess": 0.02,
    "backend_init": 450.0,
    "inference": 60.0,
    "postprocess": 0.0,
    "total": 520.0
  }
}
```

注意：

```text
objects 仍为空；
output_stats 只用于调试；
不会返回原始 tensor。
```

---

## 8. Host 测试

默认 fake backend：

```bash
python3 scripts/host/test_vision_detect_client.py
```

Phase 18E inference probe backend：

```bash
EDGEINFER_EXPECT_VISION_BACKEND=rknn-yolo-inference-probe \
python3 scripts/host/test_vision_detect_client.py
```

---

## 9. 阶段限制

Phase 18E 只是 inference probe：

```text
已经真正执行 rknn.inference；
但还没有 decode YOLO 输出；
因此 objects 仍为空。
```

---

## 10. 后续阶段

### Phase 18F：YOLO Postprocess Integration

下一步接入：

```text
server.vision.yolo_postprocess.postprocess_yolo_outputs
confidence_threshold
iou_threshold
objects 输出
```

需要重点处理：

```text
output layout
box scale back
FP 模型优先
INT8 模型类别分支异常记录
```

---

## 11. 阶段结论

Phase 18E 完成后，Vision Serving 已经具备：

```text
真实图片读取
真实 RKNN 模型加载
真实 RKNN inference
结构化 output metadata
API 可切换 backend
```

这为 Phase 18F 输出真实检测框打下基础。
