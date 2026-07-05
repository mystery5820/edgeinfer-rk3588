# Phase 9 OpenAI-like Chat API 兼容说明

本文档记录 EdgeInfer-RK3588 Phase 9 Serving Framework 当前 `/v1/chat/completions` 接口对 OpenAI Chat Completions 风格 API 的兼容范围、请求字段、响应字段、错误响应和当前限制。

更新说明：Phase 10 已在 RKLLM persistent worker 模式下新增 `stream=true` SSE 流式输出能力；默认 one-shot 模式仍拒绝 `stream=true`。完整设计与验证记录见 `docs/phase10_streaming_sse.md`。

当前目标不是完整复刻 OpenAI API，而是在 RK3588 板端 RKLLM 后端能力范围内，提供一个足够接近 OpenAI Chat Completions 的最小可用接口，便于后续接入 Web UI、脚本客户端和 OpenAI SDK 风格调用。

---

## 1. 接口概览

当前 Chat API：

```text
POST /v1/chat/completions
```

默认地址：

```text
http://192.168.43.7:8000/v1/chat/completions
```

当前推荐模型：

```text
qwen3-4b-rkllm-all-npu
```

该接口当前由 FastAPI 实现，后端实际调用 RKLLM runner 或 RKLLM persistent worker。两种后端模式下，HTTP API 的请求字段和响应格式保持一致。

---

## 2. 最小请求示例

### 2.1 OpenAI 风格 max_tokens

```bash
curl -sS http://192.168.43.7:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-4b-rkllm-all-npu",
    "messages": [
      {"role": "system", "content": "你是 EdgeInfer-RK3588 端侧推理助手。"},
      {"role": "user", "content": "请用一句话介绍 RK3588。"}
    ],
    "max_tokens": 64
  }' | python3 -m json.tool
```

### 2.2 项目内部原始 max_new_tokens

```bash
curl -sS http://192.168.43.7:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-4b-rkllm-all-npu",
    "messages": [
      {"role": "user", "content": "请用一句话介绍 RK3588。"}
    ],
    "max_new_tokens": 64
  }' | python3 -m json.tool
```

---

## 3. 支持的请求字段

### 3.1 model

类型：

```text
string，可选
```

默认值：

```text
qwen3-4b-rkllm-all-npu
```

当前推荐使用：

```text
qwen3-4b-rkllm-all-npu
```

如果模型不存在，接口返回 HTTP 404，错误码为：

```text
model_not_found
```

如果模型存在但不是 LLM 任务，接口返回 HTTP 400，错误码为：

```text
model_not_llm
```

---

### 3.2 messages

类型：

```text
array，必填
```

当前支持的 role：

```text
system
user
assistant
```

示例：

```json
[
  {"role": "system", "content": "你是 EdgeInfer-RK3588 端侧推理助手。"},
  {"role": "user", "content": "请用一句话介绍 RK3588。"}
]
```

当前 Phase 9 的 prompt 渲染逻辑会把 messages 转换为简单文本格式：

```text
System: ...
User: ...
Assistant: ...
Assistant:
```

注意：当前还不是完整的模型官方 chat template 实现，而是 Phase 9 Serving MVP 的统一 prompt 渲染策略。

---

### 3.3 max_tokens

类型：

```text
integer，可选，范围 1-256
```

这是 OpenAI 风格的输出 token 限制字段。Phase 9 已支持该字段，并会映射为后端实际使用的 `max_new_tokens`。

示例：

```json
{
  "max_tokens": 64
}
```

---

### 3.4 max_new_tokens

类型：

```text
integer，可选，范围 1-256
```

这是本项目早期使用的内部字段，仍然保持兼容。

示例：

```json
{
  "max_new_tokens": 64
}
```

---

### 3.5 max_tokens 与 max_new_tokens 的兼容规则

允许只传 `max_tokens`：

```json
{
  "max_tokens": 64
}
```

允许只传 `max_new_tokens`：

```json
{
  "max_new_tokens": 64
}
```

允许两者同时传入且值相同：

```json
{
  "max_tokens": 64,
  "max_new_tokens": 64
}
```

不允许两者同时传入且值不同：

```json
{
  "max_tokens": 64,
  "max_new_tokens": 32
}
```

这种情况下返回 HTTP 400：

```json
{
  "detail": {
    "error": {
      "code": "token_limit_conflict",
      "message": "max_tokens and max_new_tokens cannot both be set to different values",
      "type": "edgeinfer_error",
      "retryable": false
    }
  }
}
```

---

### 3.6 stop

类型：

```text
string 或 string array，可选
```

支持单个 stop sequence：

```json
{
  "stop": "
User:"
}
```

支持多个 stop sequence：

```json
{
  "stop": ["
User:", "</s>"]
}
```

当前实现方式：

```text
RKLLM 后端完成生成后，由 Python API 层对生成文本进行后处理截断。
如果多个 stop sequence 都出现，使用最早出现的位置截断。
截断后的响应 content 不包含 stop sequence 本身。
```

如果 stop 为空字符串，或者数组里包含非字符串 / 空字符串，返回 HTTP 400：

```text
invalid_stop
```

---

### 3.7 n

类型：

```text
integer，可选，当前只支持 1
```

OpenAI Chat Completions 中，`n` 表示为每个输入生成多少个候选回答。当前 Phase 9 MVP 只支持单路 RKLLM 生成，因此只接受：

```json
{
  "n": 1
}
```

如果传入 `n > 1`，接口返回 HTTP 400：

```text
n_not_supported
```

这样可以避免外部客户端误以为服务会返回多个 choices。

---

### 3.8 temperature

类型：

```text
float，可选，范围 0.0-2.0
```

当前请求模型中保留该字段，便于未来兼容 OpenAI 风格参数。

当前 Phase 9 MVP 中，`temperature` 尚未真正下传到 RKLLM runtime 参数，不应依赖它改变输出随机性。

---

### 3.9 top_p

类型：

```text
float，可选，范围 0.0-1.0，当前只支持 1.0
```

当前 Phase 9 MVP 中，`top_p` 尚未真正下传到 RKLLM runtime 参数，因此只接受：

```json
{
  "top_p": 1.0
}
```

如果传入 `top_p` 不等于 `1.0`，接口返回 HTTP 400：

```text
top_p_not_supported
```

这样可以兼容外部客户端默认携带的 `top_p=1.0`，同时避免误以为服务已经支持采样控制。

---

### 3.10 stream

类型：

```text
boolean，可选
```

默认值：

```json
{
  "stream": false
}
```

当前支持状态：

```text
one-shot 模式：
  stream=false：支持，返回普通 JSON
  stream=true ：拒绝，HTTP 400，错误码 stream_backend_not_supported

persistent worker 模式：
  stream=false：支持，返回普通 JSON
  stream=true ：支持，返回 text/event-stream SSE
```

`stream=true` 示例请求：

```json
{
  "model": "qwen3-4b-rkllm-all-npu",
  "messages": [
    {"role": "user", "content": "请用一句话介绍 RK3588。"}
  ],
  "max_tokens": 64,
  "stream": true
}
```

worker 模式下返回 OpenAI-like SSE chunk：

```text
data: {"id":"chatcmpl-...","object":"chat.completion.chunk","created":...,"model":"qwen3-4b-rkllm-all-npu","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}],"edgeinfer":{"backend":"rkllm-persistent-worker","stream":true}}

data: {"id":"chatcmpl-...","object":"chat.completion.chunk","created":...,"model":"qwen3-4b-rkllm-all-npu","choices":[{"index":0,"delta":{"content":"RK"},"finish_reason":null}]}

data: {"id":"chatcmpl-...","object":"chat.completion.chunk","created":...,"model":"qwen3-4b-rkllm-all-npu","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"edgeinfer":{"backend":"rkllm-persistent-worker","stream":true,"stop":{"requested":[],"matched":null}}}

data: [DONE]
```

one-shot 模式下返回 HTTP 400：

```text
stream_backend_not_supported
```

原因：one-shot runner 当前仍通过完整子进程调用一次性获得输出，不能提供真实增量 SSE；persistent worker 使用 stdout pipe 增量读取，Phase 10 已支持真实流式输出。

完整实现说明见：

```text
docs/phase10_streaming_sse.md
```

---

### 3.11 response_format

类型：

```text
object，可选，当前只支持 {"type": "text"}
```

OpenAI Chat Completions 中，`response_format` 用于声明期望的输出格式。当前 Phase 9 MVP 只输出普通文本，因此只接受：

```json
{
  "response_format": {
    "type": "text"
  }
}
```

如果传入 `json_object` 或其他类型，接口返回 HTTP 400：

```text
response_format_not_supported
```

这样可以兼容外部客户端显式声明文本输出，同时避免误以为当前服务已经支持 JSON mode。

---

## 4. 响应格式

成功响应示例：

```json
{
  "id": "chatcmpl-xxxxxxxxxxxx",
  "object": "chat.completion",
  "created": 1783050000,
  "model": "qwen3-4b-rkllm-all-npu",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "RK3588 是瑞芯微推出的高性能 AIoT SoC。"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": null,
    "completion_tokens": null,
    "total_tokens": null
  },
  "edgeinfer": {
    "backend": "rkllm-runner",
    "latency_ms": 21055.646,
    "recommended_model": true,
    "runtime": "rkllm-runtime-v1.3.0",
    "rknpu_driver": "v0.9.8",
    "requirement": "clean RKNPU environment, no old qwen-web-chat or yolov5-web demo services",
    "llm": {
      "max_concurrent": 1,
      "queue_policy": "reject_when_busy"
    },
    "stop": {
      "requested": [],
      "matched": null
    }
  }
}
```

---

## 5. 与 OpenAI Chat Completions 的兼容字段

当前已经支持或部分支持：

```text
model
messages
max_tokens
stop
temperature
stream=false
object
created
choices
choices[].index
choices[].message.role
choices[].message.content
choices[].finish_reason
usage
```

其中需要注意：

```text
usage 当前字段存在，并返回 estimated integer usage；该数值不是 tokenizer 精确结果，估算方法见 `docs/phase12_estimated_usage.md`。
temperature 当前字段存在并校验范围，但尚未下传控制 RKLLM 采样。
finish_reason 当前统一为 stop，尚未区分 length / content_filter / tool_calls 等情况。
```

---

## 6. EdgeInfer 扩展字段

为了便于端侧工程调试，响应中额外包含：

```text
edgeinfer
```

当前常见字段：

```text
backend              实际使用的后端，例如 rkllm-runner 或 rkllm-persistent-worker
latency_ms           后端生成耗时
recommended_model    是否是当前推荐模型
runtime              RKLLM runtime 信息
rknpu_driver          RKNPU driver 信息
requirement          模型运行要求
llm                  当前 LLM 队列和 busy 状态快照
stop                 stop sequence 处理情况
```

`edgeinfer.stop` 示例：

```json
{
  "requested": ["RK3588", "瑞芯微"],
  "matched": "RK3588"
}
```

含义：

```text
requested  用户请求的 stop sequences
matched    本次实际命中的 stop sequence；如果没有命中则为 null
```

---

## 7. 当前错误响应格式

错误响应统一放在 FastAPI 的 `detail` 字段下：

```json
{
  "detail": {
    "error": {
      "code": "llm_backend_busy",
      "message": "LLM backend is busy; please retry later",
      "type": "edgeinfer_error",
      "retryable": true
    },
    "edgeinfer": {
      "model": "qwen3-4b-rkllm-all-npu",
      "backend": "rkllm-runner",
      "llm": {
        "max_concurrent": 1,
        "busy": true,
        "queue_policy": "reject_when_busy"
      }
    }
  }
}
```

常见错误码：

| HTTP | code | 说明 |
|---:|---|---|
| 400 | stream_backend_not_supported | 当前 backend 不支持 `stream=true`，one-shot 模式下会返回该错误 |
| 400 | token_limit_conflict | `max_tokens` 和 `max_new_tokens` 同时传入且值不同 |
| 400 | invalid_stop | `stop` 不是非空字符串或非空字符串数组 |
| 400 | n_not_supported | 当前只支持 `n=1` |
| 400 | top_p_not_supported | 当前只支持 `top_p=1.0` |
| 400 | response_format_not_supported | 当前只支持 `response_format.type=text` |
| 400 | model_not_llm | 选择的模型不是 LLM 任务 |
| 404 | model_not_found | 模型不存在 |
| 429 | llm_backend_busy | LLM 后端正在处理请求，当前策略为 busy 直接拒绝 |
| 504 | llm_timeout | LLM 请求超时 |
| 502 | rkllm_runtime_error | RKLLM runtime 或 runner 执行失败 |

---

## 8. 当前暂不支持或未完整实现的字段

当前暂不支持或未纳入稳定兼容承诺：

```text
stream=true
presence_penalty
frequency_penalty
logit_bias
logprobs
top_logprobs
seed
user
tools
tool_choice
function_call
parallel_tool_calls
```

说明：

```text
这些字段后续可以逐步加入请求模型、参数校验和测试用例。
其中 `stream=true` 已在 persistent worker 模式实现 SSE；one-shot 模式仍会拒绝。
tools / tool_choice 需要额外设计工具调用协议；
usage token 统计需要 tokenizer 或 RKLLM runtime 侧统计能力支持。
```

---

## 9. one-shot 与 worker 后端行为

当前两种 RKLLM 后端：

```text
rkllm-runner
rkllm-persistent-worker
```

API 兼容行为保持一致：

```text
max_tokens 兼容规则一致
stop 截断规则一致
错误响应格式一致
busy 策略一致
```

区别主要体现在运行机制和性能：

```text
one-shot：每次请求启动 runner 子进程，生命周期简单，但延迟较高。
worker：复用 persistent no-history worker，后续请求延迟更低，但需要额外关注 worker 生命周期。
```

当前仍保持：

```text
max_concurrent=1
queue_policy=reject_when_busy
```

---

## 10. 验证方式

完整双模式验证：

```bash
cd ~/edgeinfer-rk3588

EDGEINFER_VALIDATE_DEPLOY=1 \
./scripts/host/validate_serving_modes.sh
```

该命令会验证：

```text
health
models
metrics
single chat
max_tokens compatibility
max_tokens conflict HTTP 400
stop sequences compatibility
n parameter compatibility
busy rejection HTTP 429
one-shot mode
worker mode
cleanup restore one-shot
```

单独运行 smoke test：

```bash
./scripts/host/smoke_test_serving.sh
```

可以通过环境变量关闭部分兼容测试：

```bash
EDGEINFER_SMOKE_MAX_TOKENS_COMPAT=0 ./scripts/host/smoke_test_serving.sh
EDGEINFER_SMOKE_STOP_COMPAT=0 ./scripts/host/smoke_test_serving.sh
```

---

## 11. 主机侧 OpenAI-like Python 客户端测试

除 `smoke_test_serving.sh` 外，项目还提供主机侧 Python 客户端测试脚本：

```bash
./scripts/host/test_openai_chat_client.py
