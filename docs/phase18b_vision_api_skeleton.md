# Phase 18B：Vision API Skeleton

本文档记录 `edgeinfer-rk3588` 在 Phase 18B 中新增的 Vision Detect API skeleton。

---

## 1. 背景

Phase 18 已经将项目路线重新对齐到原始多模型推理服务框架设计。

当前项目已经完成 LLM Serving milestone，但原始总设计要求：

```text
YOLOv11 实时检测
Qwen2.5 / Qwen3 文本生成
VLM 图文问答
统一 API
多模型调度
自动化 Benchmark
```

因此，Phase 18B 开始补齐 Vision Serving 主线。

---

## 2. 本阶段目标

Phase 18B 的目标不是直接接入真实 RKNN runtime，而是先冻结 Vision Detect API 合约。

新增接口：

```text
POST /v1/vision/detect
```

当前使用：

```text
fake-vision backend
```

这样可以先完成：

```text
1. API route；
2. request schema；
3. response schema；
4. object-detection model 解析；
5. model_not_vision 错误响应；
6. invalid_image_path 错误响应；
7. host-side client test；
8. 为后续 RKNN YOLO backend 预留结构。
```

---

## 3. 新增文件

```text
server/api/vision_api.py
server/runtime/fake_vision_backend.py
scripts/host/test_vision_detect_client.py
docs/phase18b_vision_api_skeleton.md
```

更新：

```text
server/main.py
README.md
docs/README.md
```

---

## 4. Request

第一版使用 JSON 请求，暂不使用 multipart upload。

```http
POST /v1/vision/detect
Content-Type: application/json
```

示例：

```json
{
  "model": "YOLOv11n-INT8-Baseline",
  "image_path": "/tmp/test.jpg",
  "confidence_threshold": 0.25,
  "iou_threshold": 0.45
}
```

字段：

| 字段 | 说明 |
| --- | --- |
| `model` | 可选；不填时自动选择第一个 `task=object-detection` 模型 |
| `image_path` | 必填；Phase 18B skeleton 只校验非空 |
| `confidence_threshold` | 可选；默认 0.25 |
| `iou_threshold` | 可选；默认 0.45 |

---

## 5. Response

示例：

```json
{
  "id": "visiondet-xxxxxxxxxxxx",
  "object": "vision.detection",
  "created": 1780000000,
  "model": "YOLOv11n-INT8-Baseline",
  "objects": [],
  "latency_ms": {
    "preprocess": 0.0,
    "inference": 0.0,
    "postprocess": 0.0,
    "total": 0.0
  },
  "edgeinfer": {
    "backend": "fake-vision",
    "runtime": "phase18b-skeleton",
    "image_path": "/tmp/test.jpg",
    "thresholds": {
      "confidence": 0.25,
      "iou": 0.45
    },
    "note": "Phase 18B API skeleton. Real RKNN YOLO backend will be integrated in later phases.",
    "vision": {
      "total_requests": 1,
      "completed_requests": 1,
      "failed_requests": 0,
      "last_error": null,
      "last_latency_ms": 0.0,
      "last_started_at": 1780000000.0,
      "last_finished_at": 1780000000.0,
      "current_model": null
    }
  }
}
```

说明：

```text
objects 当前为空列表是预期行为；
Phase 18B 不执行真实 YOLO 推理；
latency_ms 字段用于冻结未来真实 RKNN backend 的返回结构。
```

---

## 6. 错误响应

### 6.1 model_not_found

当指定不存在的模型：

```text
HTTP 404
code = model_not_found
```

### 6.2 model_not_vision

当把 LLM 模型传给 `/v1/vision/detect`：

```text
HTTP 400
code = model_not_vision
```

### 6.3 invalid_image_path

当 `image_path` 为空：

```text
HTTP 400
code = invalid_image_path
```

---

## 7. Host 测试

新增：

```text
scripts/host/test_vision_detect_client.py
```

执行：

```bash
python3 scripts/host/test_vision_detect_client.py
```

覆盖：

```text
1. 指定 object-detection model 成功；
2. 默认 object-detection model 成功；
3. LLM model 触发 model_not_vision；
4. 空 image_path 触发 invalid_image_path。
```

---

## 8. 当前限制

Phase 18B 仍有以下限制：

```text
1. 不加载 RKNN；
2. 不读取真实图片；
3. 不执行 YOLO preprocess；
4. 不执行 YOLO inference；
5. 不执行 YOLO decode / NMS；
6. 不支持 multipart upload；
7. 不支持 /v1/vision/stream；
8. 不输出真实 bbox。
```

这些限制是刻意保留的，目的是先稳定 API contract。

---

## 9. 后续阶段

### Phase 18C

建议接入真实图片读取和基础预处理：

```text
image_path existence check
OpenCV / PIL load
input size metadata
preprocess_ms
```

### Phase 18D

建议接入 RKNN YOLO backend：

```text
server/runtime/rknn_backend.py
RKNN load
RKNN inference
raw outputs
```

### Phase 18E

建议接入 YOLO postprocess：

```text
decode
confidence filter
NMS
bbox scale back
objects output
```

### Phase 19

建立 Vision Detect Benchmark：

```text
scripts/host/benchmark_vision_detect.py
CSV / Markdown report
```

---

## 10. 阶段结论

Phase 18B 完成后，项目从单一 LLM Serving 子系统重新迈向多模型 Serving 框架：

```text
/v1/chat/completions 已存在；
/v1/vision/detect API contract 开始建立；
后续可以逐步把 fake-vision 替换为真实 RKNN YOLO backend。
```
