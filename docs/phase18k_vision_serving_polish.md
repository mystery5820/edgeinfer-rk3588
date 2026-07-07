# Phase 18K：Vision Serving Polish and Examples

本文档记录 Phase 18K：对 Vision Serving 进行使用示例、响应字段说明和阶段性收尾整理。

---

## 1. 阶段背景

Phase 18B 到 Phase 18J 已经完成了 Vision Serving 的主要工程链路：

```text
Phase 18B：/v1/vision/detect API skeleton
Phase 18C：image_path 输入与 image metadata probe
Phase 18D：RKNN YOLO dryrun backend
Phase 18E：RKNN YOLO inference probe
Phase 18F：YOLO postprocess detect probe
Phase 18G：COCO class_name 与 original-image bbox
Phase 18H：persistent RKNN YOLO worker
Phase 18I：VisionRequestQueue 与 reject_when_busy
Phase 18J：默认 FP 模型与 direct resize metadata cleanup
```

此时 Vision Serving 已经从“接口骨架”推进到“可用的端侧视觉检测服务”。

Phase 18K 的重点不是继续堆功能，而是把接口使用方式、字段语义、演示脚本和文档索引补齐。

---

## 2. 当前 Vision Serving 能力

当前 `/v1/vision/detect` 支持：

```text
1. 默认模型检测；
2. 指定模型检测；
3. image_path 输入；
4. RKNN YOLO FP 模型真实推理；
5. persistent worker 复用；
6. busy 时返回 429 vision_backend_busy；
7. response 中返回 original-image bbox；
8. response 中保留 model-input bbox；
9. /v1/metrics 暴露 vision queue 状态。
```

默认模型：

```text
YOLOv11n-FP-Baseline
```

默认 runtime：

```text
phase18j-vision-default-model-metadata-cleanup
```

---

## 3. 快速演示脚本

新增：

```text
scripts/host/demo_vision_detect.sh
```

用法：

```bash
bash scripts/host/demo_vision_detect.sh
```

可选环境变量：

```bash
EDGEINFER_BOARD_URL=http://192.168.43.7:8000
EDGEINFER_VISION_TEST_IMAGE_PATH=/home/linaro/edgeinfer-rk3588-board/datasets/coco128/images/train2017/000000000089.jpg
EDGEINFER_VISION_TEST_MODEL=YOLOv11n-FP-Baseline
```

示例：

```bash
EDGEINFER_BOARD_URL=http://192.168.43.7:8000 \
EDGEINFER_VISION_TEST_MODEL=YOLOv11n-FP-Baseline \
bash scripts/host/demo_vision_detect.sh
```

脚本会依次执行：

```text
1. GET /
2. GET /v1/health
3. GET /v1/models
4. POST /v1/vision/detect，不传 model，验证默认模型；
5. POST /v1/vision/detect，显式指定模型；
6. GET /v1/metrics，查看 vision queue。
```

---

## 4. 默认模型检测

请求：

```bash
curl -s http://192.168.43.7:8000/v1/vision/detect \
  -H "Content-Type: application/json" \
  -d '{
    "image_path": "/home/linaro/edgeinfer-rk3588-board/datasets/coco128/images/train2017/000000000089.jpg"
  }' | python3 -m json.tool
```

预期重点：

```text
model = YOLOv11n-FP-Baseline
edgeinfer.backend = rknn-yolo-worker
edgeinfer.runtime = phase18j-vision-default-model-metadata-cleanup
objects 非空
```

---

## 5. 指定模型检测

请求：

```bash
curl -s http://192.168.43.7:8000/v1/vision/detect \
  -H "Content-Type: application/json" \
  -d '{
    "model": "YOLOv11n-FP-Baseline",
    "image_path": "/home/linaro/edgeinfer-rk3588-board/datasets/coco128/images/train2017/000000000089.jpg",
    "confidence_threshold": 0.25,
    "iou_threshold": 0.45
  }' | python3 -m json.tool
```

---

## 6. 响应字段说明

典型响应结构：

```json
{
  "id": "visiondet-...",
  "object": "vision.detection",
  "created": 1783392145,
  "model": "YOLOv11n-FP-Baseline",
  "image": {},
  "objects": [],
  "latency_ms": {},
  "edgeinfer": {}
}
```

### 6.1 image

`image` 描述输入图像与预处理 metadata。

关键字段：

```text
path：板端图片路径；
format：图片格式；
width / height：原始图像尺寸；
channels：通道数；
size_bytes：文件大小；
preprocess：预处理计划与坐标变换说明。
```

### 6.2 image.preprocess

Phase 18J 后，worker 模式中的 preprocess metadata 与真实 direct resize 行为一致。

典型值：

```json
{
  "method": "resize-nhwc-uint8-worker-postprocess-scale-back",
  "target_width": 640,
  "target_height": 640,
  "scale": null,
  "scale_x": 1.0,
  "scale_y": 1.333333,
  "resized_width": 640,
  "resized_height": 640,
  "pad_left": 0,
  "pad_right": 0,
  "pad_top": 0,
  "pad_bottom": 0,
  "input_tensor_layout": "NHWC",
  "input_tensor_shape": [1, 640, 640, 3],
  "input_tensor_dtype": "uint8",
  "coordinate_transform": "resize_stretch_scale_back_to_original",
  "coordinate_space": "original_image"
}
```

含义：

```text
scale = null：
  表示不是 letterbox 的单一等比例缩放。

scale_x / scale_y：
  表示原图到模型输入的横向、纵向缩放比例。

pad_top / pad_bottom = 0：
  表示没有 letterbox padding。

coordinate_space = original_image：
  表示 objects[].bbox 已经映射回原图坐标。
```

### 6.3 objects

`objects` 是检测结果数组。

每个 object：

```json
{
  "class_id": 69,
  "class_name": "oven",
  "confidence": 0.8935546875,
  "bbox": [140.0, 203.25, 479.0, 478.875],
  "bbox_input": [140.0, 271.0, 479.0, 638.5],
  "box_format": "xyxy",
  "coordinate_space": "original_image"
}
```

字段说明：

```text
class_id：
  COCO 类别 ID。

class_name：
  COCO 类别名称。

confidence：
  检测置信度。

bbox：
  原图坐标系中的检测框，格式为 [x1, y1, x2, y2]。

bbox_input：
  模型输入 640x640 坐标系中的检测框。

box_format：
  当前为 xyxy。

coordinate_space：
  bbox 所在坐标系，目前为 original_image。
```

### 6.4 latency_ms

`latency_ms` 描述请求的主要耗时。

```text
load_image：读取/探测输入图像；
preprocess：图像预处理；
backend_init：worker 首次启动耗时；复用时为 0.0；
inference：RKNN 推理耗时；
postprocess：YOLO 后处理耗时；
total：端到端请求耗时。
```

典型现象：

```text
首次请求：
  backend_init > 0

第二次请求：
  backend_init = 0.0
  worker_reused = true
```

### 6.5 edgeinfer.vision

`edgeinfer.vision` 包含 queue 与 backend 两层：

```json
{
  "queue": {
    "busy": false,
    "queue_policy": "reject_when_busy"
  },
  "backend": {
    "worker": {}
  }
}
```

`queue` 描述 API 层资源保护状态：

```text
max_concurrent
busy
queue_policy
total_requests
accepted_requests
rejected_busy
completed_requests
failed_requests
timeout_requests
last_error
last_latency_ms
current_model
```

`backend` 描述 RKNN YOLO 后端状态，包括 worker pid、request_count、last_probe 等。

---

## 7. Busy Rejection 示例

并发测试脚本：

```bash
python3 scripts/host/test_vision_busy_rejection.py
```

预期：

```text
一个请求 HTTP 200
一个请求 HTTP 429
error.code = vision_backend_busy
retryable = true
```

手动理解：

```text
Vision Serving 目前是单 RKNN worker；
同一时刻只允许一个 vision request 占用 worker；
第二个并发请求不会排队等待，而是立即返回 429；
客户端可根据 retryable=true 延迟重试。
```

---

## 8. Metrics 示例

请求：

```bash
curl -s http://192.168.43.7:8000/v1/metrics \
  | python3 -m json.tool
```

重点字段：

```json
{
  "vision": {
    "busy": false,
    "queue_policy": "reject_when_busy",
    "total_requests": 5,
    "accepted_requests": 4,
    "rejected_busy": 1,
    "completed_requests": 4,
    "failed_requests": 0
  }
}
```

---

## 9. 当前阶段边界

Phase 18K 不引入新的模型，也不改变 RKNN 推理逻辑。

当前仍然是：

```text
1. 单 RKNN YOLO worker；
2. 单并发；
3. busy reject；
4. 输入为板端 image_path；
5. 暂不支持 multipart image upload；
6. 暂不支持 base64 image input；
7. 暂不支持多 vision worker pool；
8. 暂不支持 VLM。
```

---

## 10. 阶段结论

Phase 18K 完成后，Vision Serving 已经具备比较完整的阶段性成果形态：

```text
API 可用；
默认模型合理；
输出字段清晰；
metadata 可信；
worker 可复用；
并发有保护；
文档和 demo 可复现。
```

这标志着 Phase 18 Vision Serving 可以阶段性收口。
