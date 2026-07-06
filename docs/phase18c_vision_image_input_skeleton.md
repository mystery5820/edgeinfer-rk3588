# Phase 18C：Vision Image Input / Preprocess Skeleton

本文档记录 Phase 18C 对 `/v1/vision/detect` 的增强：从纯 fake response 升级为真实 `image_path` 校验、图片头解析、图片 metadata 返回和 preprocess metadata skeleton。

---

## 1. 背景

Phase 18B 已经完成 `/v1/vision/detect` API skeleton，但它不读取图片，只返回固定 schema。

Phase 18C 的目标是在不引入 OpenCV / Pillow / NumPy 板端依赖的前提下，让 Vision API 具备真实图片输入感知能力。

板端 serving venv 当前缺少：

```text
cv2
PIL
numpy
```

因此本阶段选择纯 Python 图片头解析方式，支持：

```text
JPEG
PNG
BMP
```

---

## 2. 本阶段目标

Phase 18C 完成：

```text
1. image_path 存在性校验；
2. 图片格式探测；
3. width / height / channels / size_bytes 解析；
4. letterbox metadata 计算；
5. load_image_ms 和 preprocess_ms 计时；
6. image_not_found 错误响应；
7. invalid_image_file 错误响应；
8. host-side vision detect client test 更新。
```

仍不做：

```text
1. OpenCV 真实 resize；
2. RKNN runtime 加载；
3. YOLO inference；
4. decode / NMS；
5. bbox 输出；
6. multipart upload。
```

---

## 3. 新增 / 更新文件

新增：

```text
server/vision/image_probe.py
docs/phase18c_vision_image_input_skeleton.md
```

更新：

```text
server/api/vision_api.py
server/runtime/fake_vision_backend.py
scripts/host/test_vision_detect_client.py
README.md
docs/README.md
```

---

## 4. API Request

```http
POST /v1/vision/detect
Content-Type: application/json
```

示例：

```json
{
  "model": "YOLOv11n-INT8-Baseline",
  "image_path": "/home/linaro/edgeinfer-rk3588-board/datasets/coco128/images/train2017/000000000089.jpg",
  "confidence_threshold": 0.25,
  "iou_threshold": 0.45
}
```

---

## 5. API Response

示例结构：

```json
{
  "id": "visiondet-xxxxxxxxxxxx",
  "object": "vision.detection",
  "created": 1780000000,
  "model": "YOLOv11n-INT8-Baseline",
  "image": {
    "path": "/home/linaro/edgeinfer-rk3588-board/datasets/coco128/images/train2017/000000000089.jpg",
    "format": "jpeg",
    "width": 640,
    "height": 480,
    "channels": 3,
    "size_bytes": 123456,
    "preprocess": {
      "method": "letterbox-metadata-only",
      "target_width": 640,
      "target_height": 640,
      "scale": 1.0,
      "resized_width": 640,
      "resized_height": 480,
      "pad_left": 0,
      "pad_right": 0,
      "pad_top": 80,
      "pad_bottom": 80
    }
  },
  "objects": [],
  "latency_ms": {
    "load_image": 0.2,
    "preprocess": 0.01,
    "inference": 0.0,
    "postprocess": 0.0,
    "total": 0.4
  },
  "edgeinfer": {
    "backend": "fake-vision",
    "runtime": "phase18c-image-input-skeleton"
  }
}
```

说明：

```text
objects 仍为空是预期行为；
当前还没有执行 RKNN YOLO inference；
preprocess 是 metadata skeleton，不是真实 pixel resize。
```

---

## 6. 错误响应

### 6.1 image_not_found

图片不存在：

```text
HTTP 404
code = image_not_found
```

### 6.2 invalid_image_file

图片存在但格式不支持或头信息损坏：

```text
HTTP 400
code = invalid_image_file
```

### 6.3 invalid_image_path

image_path 为空：

```text
HTTP 400
code = invalid_image_path
```

### 6.4 model_not_vision

LLM 模型用于 Vision Detect：

```text
HTTP 400
code = model_not_vision
```

---

## 7. 测试图片

默认 host 测试使用板端已有 COCO128 图片：

```text
/home/linaro/edgeinfer-rk3588-board/datasets/coco128/images/train2017/000000000089.jpg
```

可通过环境变量覆盖：

```bash
EDGEINFER_VISION_TEST_IMAGE_PATH=/path/on/board/test.jpg \
python3 scripts/host/test_vision_detect_client.py
```

注意：

```text
image_path 是板端路径，不是 host 路径。
```

---

## 8. Host 测试

执行：

```bash
python3 scripts/host/test_vision_detect_client.py
```

覆盖：

```text
1. 指定 object-detection model 成功；
2. 默认 object-detection model 成功；
3. image metadata 字段检查；
4. latency_ms 字段检查；
5. LLM model 触发 model_not_vision；
6. 空 image_path 触发 invalid_image_path；
7. 不存在图片触发 image_not_found。
```

---

## 9. 为什么不引入 OpenCV / PIL

当前板端 serving venv 未安装：

```text
cv2
PIL
numpy
```

如果在服务启动时直接 import 这些库，可能导致 `edgeinfer-serving.service` 启动失败。

因此 Phase 18C 采用纯 Python 图片头解析：

```text
JPEG: 解析 SOF marker
PNG: 解析 IHDR
BMP: 解析 DIB header
```

这样可以在不改变板端环境的情况下，先推进 Vision API 输入链路。

---

## 10. 后续阶段

### Phase 18D：RKNN YOLO Backend Dry Integration

建议下一步开始设计真实 backend，但仍保持可回退：

```text
server/runtime/rknn_yolo_backend.py
runtime selection: fake-vision / rknn-yolo
lazy import rknnlite
model path validation
RKNN load / release lifecycle
```

### Phase 18E：YOLO Inference + Postprocess

接入：

```text
preprocess pixels
rknn.inference
postprocess_yolo_outputs
objects output
```

---

## 11. 阶段结论

Phase 18C 让 `/v1/vision/detect` 从 API skeleton 前进到真实图片输入 skeleton：

```text
有真实 image_path；
有图片 metadata；
有 preprocess metadata；
有 load/preprocess latency；
有 image_not_found / invalid_image_file 错误边界；
仍未接真实 RKNN YOLO。
```

这为下一步 RKNN YOLO backend 接入打好了输入链路基础。
