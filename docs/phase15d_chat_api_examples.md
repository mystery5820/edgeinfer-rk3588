# Phase 15D：Chat API Request / Response Examples

本文档整理 `edgeinfer-rk3588` 当前 OpenAI-like `/v1/chat/completions` 的请求与响应示例，便于 API 调用方、README 展示、SDK 使用说明和后续测试复盘。

本文档基于当前 host-side client 示例输出整理：

```bash
python3 scripts/host/test_openai_chat_client.py
```

测试环境：

```text
BOARD_URL=http://192.168.43.7:8000
MODEL_ID=qwen3-4b-rkllm-all-npu
backend_mode=oneshot
```

---

## 1. Health 示例

请求：

```bash
curl -s http://192.168.43.7:8000/v1/health | python3 -m json.tool
```

响应示例：

```json
{
  "status": "ok",
  "service": "edgeinfer-rk3588-serving",
  "phase": "phase9-serving-framework-mvp",
  "legacy_services_should_be_disabled": [
    "qwen-web-chat.service",
    "yolov5-web.service"
  ]
}
```

说明：

```text
status=ok 表示 FastAPI Serving 服务可访问；
legacy_services_should_be_disabled 用于提醒旧 demo 服务应保持禁用，避免占用 RKNPU / DRM / IOVA 资源。
```

---

## 2. 非流式成功请求示例

### 2.1 请求

```bash
curl -s http://192.168.43.7:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-4b-rkllm-all-npu",
    "messages": [
      {
        "role": "system",
        "content": "你是 EdgeInfer-RK3588 端侧推理助手。"
      },
      {
        "role": "user",
        "content": "请用一句话介绍 RK3588。"
      }
    ],
    "max_tokens": 48,
    "n": 1,
    "top_p": 1.0,
    "response_format": {
      "type": "text"
    }
  }' | python3 -m json.tool
```

### 2.2 响应要点

测试输出摘要：

```text
backend: rkllm-runner
latency_ms: 26268.544
usage.prompt_tokens: 27
usage.completion_tokens: 43
usage.total_tokens: 70
assistant_content_length: 83
finish_reason: stop
```

示例回答：

```text
RK3588 是瑞芯微推出的一款高性能 AIoT SoC，搭载四核 Cortex-A76 和四核 Cortex-A55 CPU，并内置 NPU 支持端侧 AI 推理。
```

说明：

```text
1. backend=rkllm-runner 表示当前是 one-shot runner；
2. usage 为 Phase 12A estimated usage，不是真实 tokenizer 精确值；
3. finish_reason 当前可靠返回 stop；
4. latency_ms 为 edgeinfer metadata 中记录的后端耗时。
```

---

## 3. stop sequences 示例

### 3.1 请求

```bash
curl -s http://192.168.43.7:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-4b-rkllm-all-npu",
    "messages": [
      {
        "role": "system",
        "content": "你是 EdgeInfer-RK3588 端侧推理助手。"
      },
      {
        "role": "user",
        "content": "请用一句话介绍 RK3588。"
      }
    ],
    "max_tokens": 48,
    "stop": ["RK3588", "瑞芯微"]
  }' | python3 -m json.tool
```

### 3.2 响应要点

测试输出摘要：

```text
backend: rkllm-runner
latency_ms: 16753.068
usage.prompt_tokens: 27
usage.completion_tokens: 0
usage.total_tokens: 27
stop.requested: ["RK3588", "瑞芯微"]
stop.matched: "RK3588"
assistant_content_length: 0
```

说明：

```text
1. 模型输出一开始命中 stop sequence；
2. API 层截断了命中的 stop 内容；
3. 因此 assistant content 为空；
4. edgeinfer.stop.matched 记录实际命中的 stop sequence。
```

---

## 4. one-shot stream=true 拒绝示例

### 4.1 请求

```bash
curl -s http://192.168.43.7:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-4b-rkllm-all-npu",
    "messages": [
      {
        "role": "user",
        "content": "请用一句话介绍 RK3588。"
      }
    ],
    "max_tokens": 64,
    "stream": true
  }' | python3 -m json.tool
```

### 4.2 响应示例

```json
{
  "detail": {
    "error": {
      "code": "stream_backend_not_supported",
      "message": "stream=true currently requires rkllm-persistent-worker backend",
      "type": "edgeinfer_error",
      "retryable": false
    }
  }
}
```

说明：

```text
1. one-shot backend 只能返回完整文本；
2. stream=true 当前需要 rkllm-persistent-worker backend；
3. 如需 SSE streaming，应先启用 worker mode。
```

---

## 5. n>1 拒绝示例

### 5.1 请求

```json
{
  "model": "qwen3-4b-rkllm-all-npu",
  "messages": [
    {
      "role": "user",
      "content": "请用一句话介绍 RK3588。"
    }
  ],
  "max_tokens": 16,
  "n": 2
}
```

### 5.2 响应示例

```json
{
  "detail": {
    "error": {
      "code": "n_not_supported",
      "message": "n values other than 1 are not supported in Phase 9 MVP",
      "type": "edgeinfer_error",
      "retryable": false
    }
  }
}
```

说明：

```text
当前 LLM backend 一次只生成一个 candidate，因此仅支持 n=1。
```

---

## 6. top_p!=1 拒绝示例

### 6.1 请求

```json
{
  "model": "qwen3-4b-rkllm-all-npu",
  "messages": [
    {
      "role": "user",
      "content": "请用一句话介绍 RK3588。"
    }
  ],
  "max_tokens": 16,
  "top_p": 0.9
}
```

### 6.2 响应示例

```json
{
  "detail": {
    "error": {
      "code": "top_p_not_supported",
      "message": "top_p values other than 1.0 are not supported in Phase 9 MVP",
      "type": "edgeinfer_error",
      "retryable": false
    }
  }
}
```

说明：

```text
当前尚未可靠下传 top_p 采样语义到底层 RKLLM runtime，因此只支持 top_p=1.0。
```

---

## 7. response_format=json_object 拒绝示例

### 7.1 请求

```json
{
  "model": "qwen3-4b-rkllm-all-npu",
  "messages": [
    {
      "role": "user",
      "content": "请用一句话介绍 RK3588。"
    }
  ],
  "max_tokens": 16,
  "response_format": {
    "type": "json_object"
  }
}
```

### 7.2 响应示例

```json
{
  "detail": {
    "error": {
      "code": "response_format_not_supported",
      "message": "response_format values other than {'type': 'text'} are not supported in Phase 9 MVP",
      "type": "edgeinfer_error",
      "retryable": false
    }
  }
}
```

说明：

```text
当前不支持可靠 JSON mode，因此 json_object 会显式拒绝。
```

---

## 8. invalid_stop 拒绝示例

### 8.1 请求

```json
{
  "model": "qwen3-4b-rkllm-all-npu",
  "messages": [
    {
      "role": "user",
      "content": "请用一句话介绍 RK3588。"
    }
  ],
  "max_tokens": 16,
  "stop": ""
}
```

### 8.2 响应示例

```json
{
  "detail": {
    "error": {
      "code": "invalid_stop",
      "message": "stop must be a non-empty string or a list of non-empty strings",
      "type": "edgeinfer_error",
      "retryable": false
    }
  }
}
```

说明：

```text
stop 必须是非空字符串，或非空字符串列表。
```

---

## 9. model_not_found 拒绝示例

### 9.1 请求

```json
{
  "model": "__edgeinfer_missing_model__",
  "messages": [
    {
      "role": "user",
      "content": "hello"
    }
  ],
  "max_tokens": 16
}
```

### 9.2 响应示例

```json
{
  "detail": {
    "error": {
      "code": "model_not_found",
      "message": "'model not found: __edgeinfer_missing_model__'",
      "type": "edgeinfer_error",
      "retryable": false
    }
  }
}
```

说明：

```text
调用方应先通过 /v1/models 获取可用模型 ID。
```

---

## 10. model_not_llm 拒绝示例

### 10.1 请求

示例中将视觉模型传给 `/v1/chat/completions`：

```json
{
  "model": "YOLOv11n-INT8-Baseline",
  "messages": [
    {
      "role": "user",
      "content": "hello"
    }
  ],
  "max_tokens": 16
}
```

### 10.2 响应示例

```json
{
  "detail": {
    "error": {
      "code": "model_not_llm",
      "message": "model is not an llm model: YOLOv11n-INT8-Baseline",
      "type": "edgeinfer_error",
      "retryable": false
    }
  }
}
```

说明：

```text
/v1/chat/completions 只接受 LLM 模型；
视觉模型后续应走独立 vision endpoint。
```

---

## 11. worker stream=true SSE 示例

当前文档中的实际日志来自 one-shot 模式，因此只覆盖了 one-shot stream=true 拒绝。

worker 模式下可使用：

```bash
ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/enable_edgeinfer_worker_mode.sh"

curl -N http://192.168.43.7:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-4b-rkllm-all-npu",
    "messages": [
      {
        "role": "user",
        "content": "请用一句话介绍 RK3588。"
      }
    ],
    "max_tokens": 64,
    "stream": true
  }'

ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/disable_edgeinfer_worker_mode.sh"
```

SSE 语义：

```text
1. 首 chunk: delta.role=assistant；
2. 中间 chunk: delta.content；
3. final chunk: finish_reason=stop；
4. final chunk: usage；
5. 最后 data: [DONE]。
```

---

## 12. OpenAI Python SDK 示例入口

当前 SDK 示例位于：

```text
examples/openai_sdk_chat_completion.py
examples/openai_sdk_streaming_chat.py
scripts/host/check_openai_sdk_examples.py
```

普通非流式：

```bash
python3 examples/openai_sdk_chat_completion.py
```

worker stream 示例：

```bash
EDGEINFER_EXPECT_STREAM=1 python3 scripts/host/check_openai_sdk_examples.py
```

---

## 13. 当前测试结论

本轮实际执行结果：

```text
OpenAI-like chat client test passed in 43.569s
```

覆盖：

```text
1. health；
2. max_tokens chat；
3. stop sequences；
4. stream_backend_not_supported；
5. n_not_supported；
6. top_p_not_supported；
7. response_format_not_supported；
8. invalid_stop；
9. model_not_found；
10. model_not_llm。
```

---

## 14. 注意事项

```text
1. 本文档示例来自一次实际 one-shot 测试；
2. latency_ms、usage、assistant 内容会随运行状态和模型输出变化；
3. usage 是 estimated usage；
4. 错误响应中的 edgeinfer.llm metrics 会随服务运行状态变化；
5. 本文档中错误响应示例省略了部分 edgeinfer metrics，以突出 error.code / message / retryable。
```
