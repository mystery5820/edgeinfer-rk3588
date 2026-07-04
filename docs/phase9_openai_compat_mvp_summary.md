# Phase 9 OpenAI Chat Compatibility MVP 阶段总结

## 1. 阶段定位

本阶段完成了 EdgeInfer RK3588 项目中 Phase 9 的 OpenAI Chat API 兼容性收口工作，使现有 RK3588 端侧 Qwen3-4B RKLLM 推理服务能够以接近 OpenAI Chat Completions 的方式被外部程序调用。

本阶段不是重新实现完整 OpenAI API，而是在当前端侧推理服务能力范围内，完成一套稳定、明确、可验证的 MVP 兼容层：

- 保留项目内部 `max_new_tokens` 参数；
- 兼容 OpenAI 风格 `max_tokens` 参数；
- 支持常见的 `stop` 截断语义；
- 对尚未真正支持的参数进行显式校验和拒绝；
- 保证 one-shot 与 worker 两种 RKLLM 后端行为一致；
- 通过 host 侧 smoke test 和 Python 客户端测试形成稳定验收闭环。

当前稳定 tag：

```text
phase9-openai-compat-mvp
```

对应提交：

```text
ad58445 validate response_format in chat api
```

上一阶段稳定 tag：

```text
phase9-serving-worker-mvp
```

对应提交：

```text
487f97d document phase9 serving operations
```

---

## 2. 当前核心服务能力

Phase 9 当前服务入口为统一 Serving API，运行在 RK3588 板端：

```text
http://192.168.43.7:8000
```

主要接口包括：

```text
GET  /v1/health
GET  /v1/models
GET  /v1/metrics
POST /v1/chat/completions
```

其中 `/v1/chat/completions` 是本阶段重点完善的接口，用于对接 OpenAI-like Chat Completions 风格请求。

---

## 3. 当前默认模型

当前主要验证模型为：

```text
qwen3-4b-rkllm-all-npu
```

模型定位：

```text
Qwen3-4B W8A8 RKLLM all_npu
```

其运行特征：

- 使用 RKLLM runtime；
- 面向 RK3588 NPU 推理；
- 作为当前 LLM Serving 的推荐模型；
- 支持 one-shot runner 模式；
- 支持 persistent worker 模式。

---

## 4. 后端模式

当前服务支持两种 RKLLM 后端模式。

### 4.1 one-shot 模式

默认模式：

```text
EDGEINFER_RKLLM_BACKEND_MODE 未设置
```

后端名称：

```text
rkllm-runner
```

特点：

- 每次请求启动一次 RKLLM runner；
- 实现简单；
- 便于调试；
- 启动开销较大；
- 当前默认恢复状态为 one-shot。

### 4.2 worker 模式

启用方式：

```bash
./scripts/board/enable_edgeinfer_worker_mode.sh
```

后端名称：

```text
rkllm-persistent-worker
```

特点：

- 通过 persistent no-history worker 复用 RKLLM runtime；
- 减少重复初始化开销；
- 支持指标暴露；
- 当前仍保持单并发策略；
- 请求仍然通过 busy rejection 防止并发冲突。

关闭方式：

```bash
./scripts/board/disable_edgeinfer_worker_mode.sh
```

---

## 5. OpenAI-like Chat 参数兼容状态

### 5.1 `model`

当前支持通过 `model` 指定模型 ID。

典型值：

```json
{
  "model": "qwen3-4b-rkllm-all-npu"
}
```

如果模型不存在，返回：

```text
model_not_found
```

如果模型不是 LLM 任务，返回：

```text
model_not_llm
```

### 5.2 `messages`

支持 OpenAI Chat 风格 messages：

```json
[
  {"role": "system", "content": "你是 EdgeInfer-RK3588 端侧推理助手。"},
  {"role": "user", "content": "请用一句话介绍 RK3588。"}
]
```

当前支持角色：

```text
system
user
assistant
```

服务端会将 messages 渲染为内部 prompt：

```text
System: ...
User: ...
Assistant: ...
Assistant:
```

### 5.3 `max_new_tokens`

项目内部原始参数：

```json
{
  "max_new_tokens": 128
}
```

当前约束：

```text
1 <= max_new_tokens <= 256
```

### 5.4 `max_tokens`

OpenAI 风格兼容参数：

```json
{
  "max_tokens": 128
}
```

当前约束：

```text
1 <= max_tokens <= 256
```

兼容规则：

- 只传 `max_tokens`：接受；
- 只传 `max_new_tokens`：接受；
- 两者同时传且值相同：接受；
- 两者同时传且值不同：返回 HTTP 400。

冲突错误码：

```text
token_limit_conflict
```

### 5.5 `stop`

支持 OpenAI 风格 stop sequences：

```json
{
  "stop": ["RK3588", "瑞芯微"]
}
```

支持类型：

```text
string
list[string]
null
```

行为：

- 模型生成完成后，在服务端对输出文本进行 stop sequence 截断；
- 返回体中通过 `edgeinfer.stop.requested` 暴露请求 stop；
- 返回体中通过 `edgeinfer.stop.matched` 暴露实际命中的 stop；
- 如果 stop 非空字符串或非空字符串数组，返回 HTTP 400。

错误码：

```text
invalid_stop
```

### 5.6 `stream`

当前只支持：

```json
{
  "stream": false
}
```

如果传入：

```json
{
  "stream": true
}
```

返回 HTTP 400。

错误码：

```text
stream_not_supported
```

说明：

当前还没有实现 SSE 流式输出。Phase 9 MVP 中选择显式拒绝，避免外部客户端误以为服务支持流式响应。

### 5.7 `n`

当前只支持：

```json
{
  "n": 1
}
```

如果传入：

```json
{
  "n": 2
}
```

返回 HTTP 400。

错误码：

```text
n_not_supported
```

说明：

当前端侧 RKLLM 服务只支持单路生成，不返回多个 choices。显式校验 `n` 可以避免外部客户端误以为服务会生成多候选回答。

### 5.8 `top_p`

当前只支持：

```json
{
  "top_p": 1.0
}
```

如果传入非 `1.0`，例如：

```json
{
  "top_p": 0.9
}
```

返回 HTTP 400。

错误码：

```text
top_p_not_supported
```

说明：

当前 `top_p` 尚未真正下传到 RKLLM runtime 参数，因此只兼容外部客户端默认携带的 `top_p=1.0`。对非默认值显式拒绝，避免产生“参数已生效”的误解。

### 5.9 `response_format`

当前支持：

```json
{
  "response_format": {
    "type": "text"
  }
}
```

如果传入 JSON 模式，例如：

```json
{
  "response_format": {
    "type": "json_object"
  }
}
```

返回 HTTP 400。

错误码：

```text
response_format_not_supported
```

说明：

当前 RKLLM 服务没有实现结构化 JSON 输出约束，因此仅接受 `text` 类型。这样可以兼容部分外部客户端默认设置，同时对 JSON mode 做明确拒绝。

### 5.10 `temperature`

当前请求模型中保留：

```json
{
  "temperature": 0.7
}
```

但 Phase 9 MVP 中尚未真正下传到 RKLLM runtime 参数，不应依赖其改变输出随机性。

---

## 6. 错误响应格式

当前错误响应统一使用：

```json
{
  "detail": {
    "error": {
      "code": "...",
      "message": "...",
      "type": "edgeinfer_error",
      "retryable": false
    },
    "edgeinfer": {
      "model": "...",
      "backend": "...",
      "llm": {}
    }
  }
}
```

常见错误码：

```text
stream_not_supported
token_limit_conflict
invalid_stop
n_not_supported
top_p_not_supported
response_format_not_supported
model_not_found
model_not_llm
llm_backend_busy
llm_timeout
rkllm_runtime_error
```

其中 busy rejection 使用 HTTP 429：

```text
llm_backend_busy
```

这表明当前服务仍然采取单并发策略：当 LLM 后端正在处理请求时，新的请求直接拒绝，而不是进入排队等待。

---

## 7. 验证脚本体系

### 7.1 部署脚本

```bash
./scripts/host/deploy_serving_to_board.sh
```

用途：

- 将 host 侧服务代码同步到 RK3588 板端；
- 在板端执行 compileall；
- 重启 `edgeinfer-serving.service`；
- 检查服务状态、端口和健康接口；
- 确认旧 demo 服务处于 disabled / inactive 状态。

### 7.2 smoke test

```bash
./scripts/host/smoke_test_serving.sh
```

覆盖内容：

- `/v1/health`
- `/v1/models`
- `/v1/metrics`
- 单次 chat completion；
- `max_tokens` 兼容；
- `max_tokens` 与 `max_new_tokens` 冲突校验；
- `stop` sequence 截断；
- `n>1` 拒绝；
- `top_p!=1.0` 拒绝；
- `response_format.type=json_object` 拒绝；
- busy rejection；
- metrics 状态校验。

### 7.3 双模式验证脚本

```bash
EDGEINFER_VALIDATE_DEPLOY=1 ./scripts/host/validate_serving_modes.sh
```

覆盖内容：

- 可选部署；
- 强制恢复 one-shot 模式；
- 验证 one-shot backend；
- 启用 worker 模式；
- 验证 worker backend；
- 最终清理并恢复默认 one-shot 模式。

### 7.4 OpenAI-like Python 客户端测试

```bash
./scripts/host/test_openai_chat_client.py
```

特点：

- 只使用 Python 标准库；
- 不依赖 OpenAI SDK；
- 不依赖 requests；
- 用于验证外部客户端调用体验。

覆盖内容：

```text
health
max_tokens chat
stop sequences chat
stream=true rejection
n>1 rejection
top_p!=1 rejection
response_format json_object rejection
```

---

## 8. 最终验证结论

本阶段最终验证包括：

### 8.1 本地检查

执行过：

```bash
python3 -m py_compile server/api/chat_api.py scripts/host/test_openai_chat_client.py
python3 -m compileall -q server scripts/host
bash -n scripts/host/smoke_test_serving.sh
git diff --check
```

结论：

```text
local checks OK
```

### 8.2 板端 one-shot 模式验证

通过：

```text
EXPECT_BACKEND=rkllm-runner
EXPECT_BACKEND_MODE=oneshot
```

关键结论：

```text
top_p parameter check OK
response_format parameter check OK
=== Smoke test passed ===
```

### 8.3 板端 worker 模式验证

通过：

```text
EXPECT_BACKEND=rkllm-persistent-worker
EXPECT_BACKEND_MODE=worker
```

关键结论：

```text
worker_enabled=true
worker_started=true
top_p parameter check OK
response_format parameter check OK
=== Smoke test passed ===
```

### 8.4 Python 客户端最终验证

最终通过：

```text
response_format rejection check OK
=== OpenAI-like chat client test passed in 40.941s ===
```

---

## 9. 关键提交记录

```text
ad58445 validate response_format in chat api
74b9c3f validate top_p in chat api
8198485 document openai chat client workflow
ebe7e39 support n parameter validation in chat api
76610cc add openai chat client test
edec445 document phase9 openai chat compatibility
0a47354 support stop sequences in chat api
4c4095d support max_tokens alias in chat api
487f97d document phase9 serving operations
2faa037 add serving mode validation script
```

当前 tag：

```text
phase9-openai-compat-mvp
```

---

## 10. 当前限制

当前 Phase 9 MVP 仍有以下限制：

1. 尚未实现 SSE 流式输出；
2. `temperature` 字段存在，但尚未真正下传到 RKLLM runtime；
3. `top_p` 只接受默认值 `1.0`；
4. `response_format` 只接受 `text`，不支持 JSON mode；
5. `usage` 中 token 统计仍为 `null`；
6. `finish_reason` 目前主要为 `stop`，尚未精细区分 `length` 等情况；
7. 当前 LLM 后端仍为单并发策略；
8. busy 时直接返回 HTTP 429，不做请求排队；
9. 尚未接入 OpenAI 官方 SDK 级别自动化兼容测试；
10. 尚未实现工具调用、函数调用、多模态输入等高级 OpenAI API 能力。

---

## 11. Phase 10 建议方向

Phase 9 已经完成 OpenAI Chat Compatibility MVP。下一阶段建议进入 Phase 10，重点可以从以下方向选择。

### 11.1 流式输出

实现：

```text
stream=true
```

目标：

- 支持 SSE；
- 外部客户端能够逐 token 或逐片段接收响应；
- 改善长文本生成时的交互体验。

这是最符合 OpenAI API 兼容路线的下一步。

### 11.2 Token usage 统计

实现：

```json
{
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
  }
}
```

难点：

- 需要 tokenizer；
- 或需要 RKLLM runtime 侧暴露 token 统计；
- 需要保证与实际推理 token 一致或明确标注估算方式。

### 11.3 请求队列

当前 busy 策略为直接拒绝。Phase 10 可以考虑引入轻量队列：

```text
max_queue_size
queue_timeout
request_id
```

目标：

- 提高外部服务调用稳定性；
- 降低客户端短时间并发导致的失败率；
- 为后续 Web UI 或多客户端调用做准备。

### 11.4 Worker 模式增强

可继续增强：

- worker 自动重启策略；
- worker 健康检查；
- worker warmup；
- worker 日志结构化；
- worker 请求超时后的恢复机制。

### 11.5 API SDK 示例

新增示例目录：

```text
examples/openai_compat/
```

可包含：

- Python urllib 标准库示例；
- requests 示例；
- OpenAI SDK base_url 示例；
- curl 示例；
- LangChain / LlamaIndex 接入示例。

---

## 12. 阶段结论

Phase 9 已经从最初的 RK3588 Serving Framework MVP，推进到具备 OpenAI Chat API 基础兼容能力的稳定版本。

当前系统已经具备：

- 板端统一 Serving API；
- RKLLM one-shot 后端；
- RKLLM persistent worker 后端；
- 模型注册表；
- 健康检查；
- 模型列表；
- 指标接口；
- OpenAI-like Chat Completions；
- 参数兼容与显式拒绝策略；
- host 侧部署脚本；
- host 侧双模式验证脚本；
- host 侧 OpenAI-like Python 客户端测试；
- 完整文档；
- 稳定 tag。

当前 tag `phase9-openai-compat-mvp` 可以作为 Phase 9 的稳定收口点。
