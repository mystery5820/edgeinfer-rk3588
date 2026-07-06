# Phase 15A：OpenAI-compatible API 兼容性矩阵

本文档整理 `edgeinfer-rk3588` 当前 `/v1/chat/completions` 的 OpenAI-compatible API 支持状态、显式拒绝项、错误码和后续扩展方向。

本文档基于当前代码与验证脚本整理，主要涉及：

```text
server/api/chat_api.py
scripts/host/test_openai_chat_client.py
scripts/host/smoke_test_serving.sh
docs/phase9_openai_compat.md
docs/phase10_streaming_sse.md
docs/phase12_estimated_usage.md
docs/phase12b_finish_reason_length_research.md
```

---

## 1. 总体结论

当前项目已经实现 OpenAI-like Chat Completions 的 MVP 兼容能力：

```text
1. 支持 /v1/chat/completions；
2. 支持 messages；
3. 支持 max_tokens；
4. 保留内部 max_new_tokens；
5. 支持 stop sequences；
6. 支持 response_format={"type":"text"}；
7. 支持 estimated usage；
8. 支持 worker 模式 stream=true SSE；
9. 支持 OpenAI Python SDK base_url 示例；
10. 对当前无法可靠支持的能力进行显式拒绝。
```

当前策略不是“假装完全兼容 OpenAI API”，而是：

```text
能可靠支持的字段明确支持；
暂不能支持的字段明确拒绝；
暂不能可靠判断的语义明确文档化。
```

---

## 2. Chat Completions 字段兼容矩阵

| 字段 | 当前状态 | 行为 | 错误码 / 备注 |
| --- | --- | --- | --- |
| `model` | 支持 | 使用模型注册表中的 model id | 当前主线为 `qwen3-4b-rkllm-all-npu` |
| `messages` | 支持 | 按 chat messages 构造 prompt | 当前主要覆盖 system/user |
| `max_tokens` | 支持 | OpenAI 风格输出 token 限制字段 | 映射到内部 `max_new_tokens` |
| `max_new_tokens` | 支持 | 项目内部保留字段 | 兼容历史调用 |
| `max_tokens` + `max_new_tokens` | 部分支持 | 两者相同则接受，不同则拒绝 | `token_limit_conflict` |
| `stop` | 支持 | 支持字符串或字符串列表 | 非空校验，命中后截断输出 |
| `stream=false` | 支持 | 普通 JSON 响应 | one-shot / worker 均支持 |
| `stream=true` | 条件支持 | worker 模式支持 SSE | one-shot 返回 `stream_backend_not_supported` |
| `n=1` | 支持 | 单候选输出 | 默认能力 |
| `n>1` | 不支持 | 显式拒绝 | 当前单后端不生成多个候选 |
| `top_p=1.0` | 支持 | 默认值，等同不启用 nucleus sampling | 当前未完整下传到底层 |
| `top_p!=1.0` | 不支持 | 显式拒绝 | `top_p_not_supported` |
| `response_format={"type":"text"}` | 支持 | 普通文本输出 | Phase 9 MVP 支持 |
| `response_format={"type":"json_object"}` | 不支持 | 显式拒绝 | `response_format_not_supported` |
| `temperature` | 接口层保留/有限支持 | 当前未作为重点兼容项验证 | 后续可继续 polish |
| `tools` / `tool_calls` | 不支持 | 当前无工具调用协议 | 后续扩展方向 |
| `function_call` | 不支持 | 当前无函数调用协议 | 后续扩展方向 |
| `logprobs` | 不支持 | RKLLM 当前未暴露 | 后续视 runtime 能力决定 |
| `seed` | 不支持 | 当前未实现确定性采样控制 | 后续视 runtime 能力决定 |

---

## 3. 响应字段兼容矩阵

| 响应字段 | 当前状态 | 说明 |
| --- | --- | --- |
| `id` | 支持 | 返回 chat completion id |
| `object` | 支持 | 非流式为 `chat.completion`，流式为 `chat.completion.chunk` |
| `created` | 支持 | Unix timestamp |
| `model` | 支持 | 回显请求模型 |
| `choices` | 支持 | 当前单 choice |
| `choices[].index` | 支持 | 当前为 0 |
| `choices[].message.role` | 支持 | `assistant` |
| `choices[].message.content` | 支持 | 模型生成内容 |
| `choices[].delta.role` | 支持 | SSE 首 chunk |
| `choices[].delta.content` | 支持 | SSE 内容 chunk |
| `choices[].finish_reason` | 支持 `stop` | 当前可靠返回 `stop` |
| `finish_reason=length` | 暂不支持 | Phase 12B 已调研，不做不可靠实现 |
| `usage` | 支持 estimated | Phase 12A 实现，非精确 tokenizer |
| `edgeinfer` | 支持 | 项目扩展 metadata |
| `edgeinfer.backend` | 支持 | 标识 `rkllm-runner` / `rkllm-persistent-worker` |
| `edgeinfer.latency_ms` | 支持 | 后端耗时 |
| `edgeinfer.stop` | 支持 | stop requested / matched |
| `edgeinfer.usage` | 支持 | 标注 estimated 与 method |

---

## 4. 错误码矩阵

| 错误码 | HTTP | 触发条件 | 当前验证入口 |
| --- | ---: | --- | --- |
| `token_limit_conflict` | 400 | `max_tokens` 与 `max_new_tokens` 同时传入且值不同 | `smoke_test_serving.sh` |
| `invalid_stop` | 400 | `stop` 不是非空字符串或非空字符串列表 | API 校验逻辑 |
| `top_p_not_supported` | 400 | `top_p != 1.0` | `test_openai_chat_client.py` / `smoke_test_serving.sh` |
| `response_format_not_supported` | 400 | `response_format.type != text` | `test_openai_chat_client.py` / `smoke_test_serving.sh` |
| `stream_backend_not_supported` | 400 | one-shot backend 收到 `stream=true` | `test_openai_chat_client.py` / `smoke_test_serving.sh` |
| `llm_backend_busy` | 429 | 单 LLM backend 忙时新请求被拒绝 | Phase 9 busy metrics validation |

说明：当前错误策略偏保守：能明确识别的问题返回结构化错误；暂不可靠支持的 OpenAI 参数显式拒绝；后续扩展时应继续保持错误码稳定。

---

## 5. stream=true SSE 当前语义

### 5.1 one-shot 模式

one-shot 模式不支持 `stream=true`。

```text
HTTP 400
error.code = stream_backend_not_supported
```

原因：one-shot runner 只有完整文本返回，不具备增量 token/chunk 输出能力。

### 5.2 worker 模式

worker 模式支持 `stream=true` SSE：

```text
1. 首 chunk 返回 delta.role=assistant；
2. 中间 chunk 返回 delta.content；
3. final chunk 返回 finish_reason=stop；
4. final chunk 携带 usage；
5. 最后返回 data: [DONE]。
```

当前测试覆盖：

```text
scripts/host/test_openai_chat_client.py
scripts/host/smoke_test_serving.sh
examples/openai_sdk_streaming_chat.py
```

---

## 6. usage 当前语义

Phase 12A 已实现 estimated usage：

```json
{
  "usage": {
    "prompt_tokens": 67,
    "completion_tokens": 42,
    "total_tokens": 109
  },
  "edgeinfer": {
    "usage": {
      "estimated": true,
      "method": "simple_mixed_text_heuristic_v1"
    }
  }
}
```

约束：

```text
1. usage 是估算值；
2. 不来自真实 tokenizer；
3. 不用于严格计费；
4. 不用于 quota；
5. 不用于判断 finish_reason=length；
6. stream 模式仅 final chunk 携带 usage。
```

---

## 7. finish_reason 当前语义

当前可靠返回：

```text
finish_reason=stop
```

暂不返回：

```text
finish_reason=length
```

原因：

```text
1. RKLLM one-shot runner 未暴露 stop_reason；
2. persistent worker 未暴露 generated_tokens；
3. API 层无法判断是否命中 max_new_tokens；
4. estimated usage 不能用于判断 length；
5. worker 实际 max_new_tokens 可能与请求 max_tokens 不完全等价。
```

---

## 8. API 示例

### 8.1 非流式请求

```bash
curl -s http://192.168.43.7:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-4b-rkllm-all-npu",
    "messages": [
      {"role": "user", "content": "请用一句话介绍 RK3588。"}
    ],
    "max_tokens": 64,
    "top_p": 1.0,
    "response_format": {"type": "text"}
  }' | python3 -m json.tool
```

### 8.2 stop sequences

```bash
curl -s http://192.168.43.7:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-4b-rkllm-all-npu",
    "messages": [
      {"role": "user", "content": "请用一句话介绍 RK3588。"}
    ],
    "max_tokens": 64,
    "stop": ["RK3588", "瑞芯微"]
  }' | python3 -m json.tool
```

### 8.3 worker stream=true

```bash
ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/enable_edgeinfer_worker_mode.sh"

curl -N http://192.168.43.7:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-4b-rkllm-all-npu",
    "messages": [
      {"role": "user", "content": "请用一句话介绍 RK3588。"}
    ],
    "max_tokens": 64,
    "stream": true
  }'

ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/disable_edgeinfer_worker_mode.sh"
```

---

## 9. 后续改进方向

Phase 15 后续可继续分解为：

```text
Phase 15B：统一错误响应文档
Phase 15C：请求 / 响应 JSON examples
Phase 15D：OpenAI SDK compatibility notes
Phase 15E：temperature 参数语义验证
Phase 15F：stream first-token latency benchmark
```

更长期的功能扩展：

```text
1. 真实 tokenizer usage；
2. RKLLM wrapper 暴露 stop_reason；
3. finish_reason=length；
4. stream first-token latency；
5. JSON mode；
6. tool calls；
7. 多模型路由；
8. VLM endpoint。
```

---

## 10. 阶段结论

当前 OpenAI-compatible API 已达到项目 MVP 展示要求：

```text
1. 常用 Chat Completions 调用可用；
2. OpenAI Python SDK base_url 可接入；
3. stream=true 在 worker 模式下可用；
4. usage 有 estimated 字段；
5. 错误码有结构化返回；
6. 不支持的能力没有假装支持，而是显式拒绝。
```

后续重点应是逐步 polish API 文档、错误码稳定性、SDK 示例和更细的兼容能力，而不是一次性追求完整 OpenAI API 覆盖。
