# Phase 19B：Unified Inference Response and Adapter Polish

## 1. 目标

Phase 19B 在 Phase 19A `/v1/infer` task dispatch 的基础上，进一步规范统一推理响应结构。

本阶段不替换已有接口：

- `/v1/chat/completions`
- `/v1/vision/detect`

也不接入真实 VLM 模型。

本阶段只增强：

- `/v1/infer`
- unified adapter result
- output.summary / output.data / output.raw
- response schema test
- docs polish

## 2. 背景

Phase 19A 已完成：

- `/v1/infer`
- `/v1/infer/tasks`
- text-generation / chat-completion adapter
- object-detection adapter
- VLM first-class placeholder tasks
- unsupported task error
- `vlm_backend_not_ready`

但 Phase 19A 的 `/v1/infer` 响应仍偏初始结构：

```json
{
  "object": "edgeinfer.inference",
  "task": "object-detection",
  "model": "YOLOv11n-FP-Baseline",
  "output": {
    "...": "原 /v1/vision/detect 响应"
  },
  "edgeinfer": {
    "route": "/v1/vision/detect",
    "backend": "rknn-yolo-worker",
    "runtime": "phase19a-unified-inference-vlm-ready",
    "task_adapter": "vision-detect"
  }
}
```

这种结构可以工作，但还不适合后续扩展 LLM / Vision / VLM / 全局调度。

## 3. Phase 19B 统一响应结构

Phase 19B 后，`/v1/infer` 成功响应统一为：

```json
{
  "id": "infer-xxxxxxxxxxxx",
  "object": "edgeinfer.inference",
  "created": 1783421697,
  "task": "object-detection",
  "model": "YOLOv11n-FP-Baseline",
  "output": {
    "summary": {},
    "data": {},
    "raw": {}
  },
  "edgeinfer": {
    "runtime": "phase19b-unified-response-adapter-polish",
    "dispatch": {
      "task": "object-detection",
      "adapter": "vision-detect",
      "source_endpoint": "/v1/vision/detect",
      "backend": "rknn-yolo-worker",
      "source_runtime": "phase18j-vision-default-model-metadata-cleanup"
    }
  }
}
```

字段含义：

| 字段 | 含义 |
|---|---|
| `output.summary` | 面向用户、前端、日志的简要结果 |
| `output.data` | 标准化后的核心任务输出 |
| `output.raw` | 原任务后端完整响应，方便调试和回归 |
| `edgeinfer.dispatch` | 统一入口到具体 adapter/backend 的分发信息 |

## 4. Object Detection 输出

`task=object-detection` 的 summary 示例：

```json
{
  "type": "object-detection",
  "num_objects": 8,
  "classes": ["oven", "knife", "microwave"],
  "coordinate_space": "original_image",
  "box_format": "xyxy",
  "latency_ms": {},
  "image": {
    "path": "/home/linaro/.../000000000089.jpg",
    "format": "jpeg",
    "width": 640,
    "height": 480
  }
}
```

核心数据放在：

```json
{
  "output": {
    "data": {
      "objects": []
    }
  }
}
```

完整 `/v1/vision/detect` 原始响应保留在：

```json
{
  "output": {
    "raw": {}
  }
}
```

为了不破坏 Phase 19A 的简单客户端，Phase 19B 暂时保留：

```json
{
  "output": {
    "objects": []
  }
}
```

该字段是兼容字段，后续新代码应优先读取：

```text
output.data.objects
```

## 5. Text Generation / Chat Completion 输出

`text-generation` 和 `chat-completion` 同样会被包装成：

```json
{
  "output": {
    "summary": {
      "type": "text-generation",
      "num_choices": 1,
      "finish_reason": "stop",
      "text_preview": "...",
      "usage": {}
    },
    "data": {
      "choices": [],
      "usage": {}
    },
    "raw": {}
  }
}
```

Phase 19B 仍不包装 streaming response。

如果需要 streaming，请继续使用：

```text
/v1/chat/completions
```

## 6. VLM 行为

VLM 任务仍然是一等任务，但真实后端尚未接入。

以下任务仍返回：

```text
HTTP 501
error.code = vlm_backend_not_ready
backend = vlm-placeholder
```

包括：

- `vision-language`
- `image-captioning`
- `visual-question-answering`
- `multimodal-chat`

## 7. 新增文件

```text
server/runtime/unified_adapters.py
scripts/host/test_unified_infer_response_schema.py
docs/phase19b_unified_response_adapter_polish.md
```

## 8. 修改文件

```text
server/api/infer_api.py
server/runtime/vlm_placeholder_backend.py
server/main.py
README.md
docs/README.md
```

## 9. 验证命令

本地编译：

```bash
python3 -m compileall server scripts/host/test_unified_infer_response_schema.py
```

部署到板端：

```bash
./scripts/host/deploy_serving_to_board.sh
```

启用 Vision worker：

```bash
ssh linaro@192.168.43.7 '
cd /home/linaro/edgeinfer-rk3588-board
./scripts/board/enable_edgeinfer_vision_rknn_worker.sh
'
```

运行 Phase 19B schema 测试：

```bash
EDGEINFER_EXPECT_VISION_BACKEND=rknn-yolo-worker \
python3 scripts/host/test_unified_infer_response_schema.py
```

保留 Phase 19A 回归：

```bash
EDGEINFER_EXPECT_VISION_BACKEND=rknn-yolo-worker \
python3 scripts/host/test_unified_infer_client.py
```

Vision 回归：

```bash
EDGEINFER_EXPECT_VISION_BACKEND=rknn-yolo-worker \
python3 scripts/host/test_vision_detect_client.py
```

Vision busy rejection 回归：

```bash
python3 scripts/host/test_vision_busy_rejection.py
```

## 10. 阶段结论

Phase 19B 将 `/v1/infer` 从“任务分发入口”升级为“统一推理响应入口”。

这为后续阶段打基础：

- Phase 19C：LLM unified adapter 系统验证
- Phase 19D：VLM API skeleton
- Phase 20：Global Multi-Model NPU Resource Guard
