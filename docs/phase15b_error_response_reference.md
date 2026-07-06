# Phase 15B：Error Response Reference

本文档整理 `edgeinfer-rk3588` 当前 OpenAI-like API 的错误响应结构、错误码、HTTP 状态码、触发条件和验证入口。

本文档面向：

```text
1. API 调用方；
2. 后续 SDK 示例；
3. host smoke test；
4. README 对外说明；
5. 后续错误码稳定性维护。
```

---

## 1. 错误响应总体结构

当前 Chat Completions API 的结构化错误通常采用 FastAPI `HTTPException` 返回，核心结构为：

```json
{
  "detail": {
    "error": {
      "code": "error_code",
      "message": "human readable message",
      "retryable": false
    }
  }
}
```

部分错误可能附带更多字段，具体以实际 API 返回为准。

调用方建议优先读取：

```text
detail.error.code
detail.error.message
detail.error.retryable
```

其中：

```text
code：稳定的程序判断字段；
message：给人看的解释；
retryable：调用方是否可以稍后重试。
```

---

## 2. 错误码总表

| 错误码 | HTTP | retryable | 分类 | 触发条件 |
| --- | ---: | --- | --- | --- |
| `token_limit_conflict` | 400 | false | 请求参数错误 | `max_tokens` 与 `max_new_tokens` 同时传入且值不同 |
| `invalid_stop` | 400 | false | 请求参数错误 | `stop` 不是非空字符串或非空字符串列表 |
| `top_p_not_supported` | 400 | false | 当前能力不支持 | `top_p != 1.0` |
| `response_format_not_supported` | 400 | false | 当前能力不支持 | `response_format.type != text` |
| `n_not_supported` | 400 | false | 当前能力不支持 | `n != 1` |
| `stream_backend_not_supported` | 400 | false | 当前 backend 不支持 | one-shot backend 收到 `stream=true` |
| `model_not_found` | 404 | false | 模型错误 | 请求模型 ID 不存在 |
| `model_not_llm` | 400 | false | 模型错误 | 请求模型不是 text-generation / LLM 类型 |
| `llm_backend_busy` | 429 | true | 资源忙 | 单 LLM backend 正在处理请求 |
| `llm_timeout` | 504 | true | 后端超时 | LLM 请求超过超时限制 |
| `rkllm_runtime_error` | 502 | true/视情况 | 后端运行时错误 | RKLLM runner / worker 执行失败 |

说明：

```text
1. 400 多数代表请求参数或当前能力不支持；
2. 404 代表模型不存在；
3. 429 代表后端忙，调用方可稍后重试；
4. 502/504 代表后端执行链路异常或超时；
5. retryable 字段应作为客户端重试策略的主要依据。
```

---

## 3. HTTP 400：请求参数与能力不支持

### 3.1 token_limit_conflict

触发条件：

```text
同时传入 max_tokens 和 max_new_tokens，且两者值不同。
```

示例请求：

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
  "max_new_tokens": 17
}
```

期望响应：

```json
{
  "detail": {
    "error": {
      "code": "token_limit_conflict",
      "message": "max_tokens and max_new_tokens cannot both be set to different values",
      "retryable": false
    }
  }
}
```

客户端处理建议：

```text
只传 max_tokens，或者只传 max_new_tokens；
如果两者都传，必须保持值一致。
```

---

### 3.2 invalid_stop

触发条件：

```text
stop 不是非空字符串，也不是非空字符串列表。
```

示例非法值：

```json
{
  "stop": ""
}
```

或：

```json
{
  "stop": ["RK3588", ""]
}
```

期望错误码：

```text
invalid_stop
```

客户端处理建议：

```text
stop 应传非空字符串，或非空字符串数组。
```

---

### 3.3 top_p_not_supported

触发条件：

```text
top_p != 1.0
```

示例请求：

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

期望错误码：

```text
top_p_not_supported
```

原因：

```text
当前 Phase 15 阶段尚未将 top_p 采样语义可靠下传到底层 RKLLM runtime。
```

客户端处理建议：

```text
保持 top_p=1.0，或者不传 top_p。
```

---

### 3.4 response_format_not_supported

触发条件：

```text
response_format.type 不是 text。
```

示例请求：

```json
{
  "model": "qwen3-4b-rkllm-all-npu",
  "messages": [
    {
      "role": "user",
      "content": "请用 JSON 输出 RK3588 的简介。"
    }
  ],
  "max_tokens": 16,
  "response_format": {
    "type": "json_object"
  }
}
```

期望错误码：

```text
response_format_not_supported
```

原因：

```text
当前不支持可靠 JSON mode，不假装支持 OpenAI 的 json_object 语义。
```

客户端处理建议：

```text
使用 response_format={"type":"text"}，或者不传 response_format。
```

---

### 3.5 n_not_supported

触发条件：

```text
n != 1
```

示例请求：

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

期望错误码：

```text
n_not_supported
```

原因：

```text
当前 LLM backend 一次只生成一个 candidate，不支持 OpenAI API 中的多候选输出。
```

客户端处理建议：

```text
保持 n=1，或者不传 n。
```

---

### 3.6 stream_backend_not_supported

触发条件：

```text
one-shot backend 收到 stream=true 请求。
```

示例请求：

```json
{
  "model": "qwen3-4b-rkllm-all-npu",
  "messages": [
    {
      "role": "user",
      "content": "请用一句话介绍 RK3588。"
    }
  ],
  "max_tokens": 64,
  "stream": true
}
```

期望错误码：

```text
stream_backend_not_supported
```

原因：

```text
one-shot runner 只能返回完整文本，不能返回增量 SSE chunk。
```

客户端处理建议：

```text
1. 默认 one-shot 模式下使用 stream=false；
2. 如需 stream=true，先启用 RKLLM persistent worker mode。
```

---

## 4. HTTP 404：模型不存在

### 4.1 model_not_found

触发条件：

```text
请求的 model id 不存在于 model registry。
```

示例请求：

```json
{
  "model": "not-exist-model",
  "messages": [
    {
      "role": "user",
      "content": "hello"
    }
  ]
}
```

期望错误码：

```text
model_not_found
```

客户端处理建议：

```text
先调用 /v1/models 获取可用模型 ID；
当前推荐模型为 qwen3-4b-rkllm-all-npu。
```

---

## 5. HTTP 400：模型类型不匹配

### 5.1 model_not_llm

触发条件：

```text
请求的模型存在，但不是 text-generation / LLM 类型。
```

典型情况：

```text
误把 object-detection 模型传给 /v1/chat/completions。
```

期望错误码：

```text
model_not_llm
```

客户端处理建议：

```text
/v1/chat/completions 只应使用 LLM 模型；
视觉模型后续应走独立 vision endpoint。
```

---

## 6. HTTP 429：LLM backend busy

### 6.1 llm_backend_busy

触发条件：

```text
当前 LLM 后端正在处理请求，新的并发请求被 reject_when_busy 策略拒绝。
```

期望响应：

```json
{
  "detail": {
    "error": {
      "code": "llm_backend_busy",
      "message": "LLM backend is busy; retry later",
      "retryable": true
    }
  }
}
```

当前策略：

```text
1. max_concurrent_llm=1；
2. queue_policy=reject_when_busy；
3. 不排队等待；
4. 后端忙时立即返回 429；
5. metrics 中 rejected_busy 递增。
```

客户端处理建议：

```text
1. 读取 retryable=true；
2. 稍后重试；
3. 可以实现指数退避；
4. 不应立即高频重试。
```

---

## 7. HTTP 504：LLM timeout

### 7.1 llm_timeout

触发条件：

```text
LLM 请求超过服务端配置的超时时间。
```

期望错误码：

```text
llm_timeout
```

可能原因：

```text
1. 模型生成过慢；
2. max_tokens / max_new_tokens 设置过大；
3. RKLLM runner / worker 卡住；
4. 板端资源异常。
```

客户端处理建议：

```text
1. 降低 max_tokens；
2. 检查 /v1/metrics；
3. 检查 systemd 日志；
4. 稍后重试。
```

---

## 8. HTTP 502：RKLLM runtime error

### 8.1 rkllm_runtime_error

触发条件：

```text
RKLLM runner / worker 执行失败，API 层捕获运行时错误。
```

期望错误码：

```text
rkllm_runtime_error
```

可能原因：

```text
1. RKLLM runtime 进程异常退出；
2. 模型文件路径错误；
3. RKNPU 资源异常；
4. worker stdout/stderr 协议异常；
5. 板端 legacy demo 服务占用资源。
```

客户端处理建议：

```text
1. 调用 /v1/metrics 查看 last_error；
2. 查看 systemd journal；
3. 确认模型文件存在；
4. 确认 legacy AI demo 服务已禁用；
5. 必要时重启 edgeinfer-serving.service。
```

---

## 9. 推荐客户端处理逻辑

客户端可以采用如下策略：

```text
1. 先读取 HTTP status；
2. 再读取 detail.error.code；
3. 根据 retryable 判断是否自动重试；
4. 400/404 一般不自动重试，需要修正请求；
5. 429 可以延迟重试；
6. 502/504 可以有限次数重试，并记录日志；
7. 不要依赖 message 做程序分支，message 主要给人阅读。
```

伪代码：

```python
error = body.get("detail", {}).get("error", {})
code = error.get("code")
retryable = error.get("retryable", False)

if retryable:
    retry_later()
else:
    raise UserRequestError(code)
```

---

## 10. 当前验证覆盖

当前已有验证入口：

| 错误码 | 验证方式 |
| --- | --- |
| `token_limit_conflict` | `scripts/host/smoke_test_serving.sh` |
| `top_p_not_supported` | `scripts/host/test_openai_chat_client.py` / `scripts/host/smoke_test_serving.sh` |
| `response_format_not_supported` | `scripts/host/test_openai_chat_client.py` / `scripts/host/smoke_test_serving.sh` |
| `stream_backend_not_supported` | `scripts/host/test_openai_chat_client.py` / `scripts/host/smoke_test_serving.sh` |
| `llm_backend_busy` | `scripts/host/smoke_test_serving.sh` / Phase 9 busy validation |
| `invalid_stop` | API 逻辑已实现，后续可补 smoke test |
| `n_not_supported` | API 逻辑已实现，后续可补 Python client assertion |
| `model_not_found` | API 逻辑已实现，后续可补 Python client assertion |
| `model_not_llm` | API 逻辑已实现，后续可补 Python client assertion |
| `llm_timeout` | 异常路径，后续可通过低 timeout 测试 |
| `rkllm_runtime_error` | 异常路径，后续可通过 fake bad model/runtime 测试 |

---

## 11. 后续建议

Phase 15 后续可以继续做：

```text
Phase 15C：补充 error response smoke tests
Phase 15D：整理 request / response examples
Phase 15E：OpenAI SDK compatibility notes
Phase 15F：stream first-token latency benchmark
```

优先级建议：

```text
1. 先补 n_not_supported / model_not_found / model_not_llm 的 host client assertion；
2. 再补 invalid_stop 测试；
3. 暂不强行构造 rkllm_runtime_error；
4. timeout 测试谨慎做，避免拖慢常规 smoke test。
```

---

## 12. 阶段结论

当前错误响应已经具备基本工程可用性：

```text
1. 常见错误有稳定 code；
2. 不支持的 OpenAI 参数会显式拒绝；
3. busy 有 429 和 retryable=true；
4. timeout/runtime error 有独立错误码；
5. 后续应继续补齐错误码测试覆盖和示例文档。
```
