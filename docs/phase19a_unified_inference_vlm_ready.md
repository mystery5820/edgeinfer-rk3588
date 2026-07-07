# Phase 19A：Unified Inference API with VLM-Ready Task Dispatch

Phase 19A 新增统一推理入口 `/v1/infer`，并在 task dispatch 设计中提前纳入 VLM。

## 1. 背景

Phase 18K 后，项目已有：

```text
/v1/chat/completions
/v1/vision/detect
```

Phase 19A 在现有接口上方增加统一入口：

```text
/v1/infer
```

该入口不替换旧接口，而是通过 `task` 分发到已有能力或未来能力。

## 2. 支持和预留的任务

```text
text-generation
chat-completion
object-detection
vision-language
image-captioning
visual-question-answering
multimodal-chat
```

其中：

```text
text-generation / chat-completion -> LLM adapter
object-detection -> Vision adapter
vision-language / image-captioning / visual-question-answering / multimodal-chat -> VLM placeholder
```

VLM 是计划内任务，不是 unknown task。未接入真实 VLM backend 前返回：

```text
HTTP 501
error.code = vlm_backend_not_ready
backend = vlm-placeholder
```

## 3. 新增接口

```text
GET  /v1/infer/tasks
POST /v1/infer
```

查看任务列表：

```bash
curl -s http://192.168.43.7:8000/v1/infer/tasks | python3 -m json.tool
```

## 4. Object Detection 示例

```bash
curl -s http://192.168.43.7:8000/v1/infer \
  -H "Content-Type: application/json" \
  -d '{
    "task": "object-detection",
    "model": "YOLOv11n-FP-Baseline",
    "input": {
      "image_path": "/home/linaro/edgeinfer-rk3588-board/datasets/coco128/images/train2017/000000000089.jpg"
    },
    "parameters": {
      "confidence_threshold": 0.25,
      "iou_threshold": 0.45
    }
  }' | python3 -m json.tool
```

内部路由：

```text
/v1/infer -> object-detection -> vision adapter -> /v1/vision/detect
```

## 5. Text Generation 示例

```bash
curl -s http://192.168.43.7:8000/v1/infer \
  -H "Content-Type: application/json" \
  -d '{
    "task": "text-generation",
    "input": {
      "messages": [
        {
          "role": "user",
          "content": "你好，请用一句话介绍 edgeinfer-rk3588。"
        }
      ]
    },
    "parameters": {
      "max_tokens": 64,
      "temperature": 0.7
    }
  }' | python3 -m json.tool
```

Phase 19A 暂不包装 streaming。`stream=true` 仍建议使用 `/v1/chat/completions`。

## 6. VLM Placeholder 示例

```bash
curl -s http://192.168.43.7:8000/v1/infer \
  -H "Content-Type: application/json" \
  -d '{
    "task": "vision-language",
    "model": "future-vlm-model",
    "input": {
      "image_path": "/home/linaro/test.jpg",
      "text": "这张图片里有什么？"
    }
  }' | python3 -m json.tool
```

当前返回：

```text
HTTP 501
error.code = vlm_backend_not_ready
backend = vlm-placeholder
runtime = phase19a-unified-inference-vlm-ready
```

## 7. 测试脚本

新增：

```text
scripts/host/test_unified_infer_client.py
```

运行：

```bash
EDGEINFER_EXPECT_VISION_BACKEND=rknn-yolo-worker \
python3 scripts/host/test_unified_infer_client.py
```

测试内容：

```text
GET /v1/infer/tasks
POST /v1/infer object-detection
POST /v1/infer VLM planned tasks -> 501 vlm_backend_not_ready
POST /v1/infer unsupported task -> 400 unsupported_task
```

可选 LLM 测试：

```bash
EDGEINFER_RUN_UNIFIED_TEXT=1 \
python3 scripts/host/test_unified_infer_client.py
```

## 8. 阶段边界

Phase 19A 不实现真实 VLM，不替换现有接口，不做全局资源调度，不包装 streaming，也不引入 multipart/base64 图片输入。

## 9. 结论

Phase 19A 后，项目从 LLM 与 Vision 两条独立 API，进一步升级为：

```text
统一入口 /v1/infer
task-based dispatch
LLM adapter
Vision adapter
VLM placeholder
VLM-ready API schema
```
