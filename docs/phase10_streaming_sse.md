# Phase 10：OpenAI-like stream=true SSE 流式输出验证记录

本文档记录 `edgeinfer-rk3588` 项目 Phase 10 中 `/v1/chat/completions` 对 `stream=true` 的支持范围、实现设计、验证方法和当前限制。

Phase 10 的目标不是完整复刻 OpenAI Chat Completions API，而是在 Phase 9 OpenAI-like Chat API MVP 的基础上，优先补齐最关键的流式输出能力，使 RK3588 板端 Qwen3-4B RKLLM persistent worker 模式能够以 Server-Sent Events 形式持续返回增量文本。

---

## 1. 当前结论

Phase 10 当前结论如下：

```text
one-shot 模式：
  stream=false：支持，返回普通 chat.completion JSON
  stream=true ：拒绝，HTTP 400，错误码 stream_backend_not_supported

persistent worker 模式：
  stream=false：支持，返回普通 chat.completion JSON
  stream=true ：支持，返回 text/event-stream SSE
```

因此，`stream=true` 当前是 **worker-only 能力**。默认 one-shot 模式仍保持安全拒绝，避免外部客户端误以为 one-shot runner 可以真实增量输出。

---

## 2. 为什么只在 worker 模式支持 stream=true

Phase 9 中已有两条 RKLLM 推理链路：

```text
one-shot runner:
  FastAPI -> rkllm_backend.py -> rkllm_runner.py -> subprocess.run / communicate -> 一次性返回文本

persistent worker:
  FastAPI -> rkllm_backend.py -> RKLLMPersistentWorker -> Popen stdout pipe -> select + os.read
```

one-shot runner 当前使用 `subprocess.run()` / `proc.communicate()` 等完整等待方式，天然只能在进程退出或输出结束后一次性获得结果，不适合直接实现真实 SSE。

persistent worker 已经使用常驻子进程、stdout pipe、非阻塞 fd 和 `select + os.read`，可以在 RKLLM 生成过程中逐片段读取 stdout。因此 Phase 10 首先选择 worker 模式实现真实 SSE。

---

## 3. RKLLM worker 增量输出调研

在正式改造前，使用临时探针脚本验证了底层 worker 二进制：

```text
tools/rkllm_enhanced/rkllm_enhanced_no_template_no_history
```

会在生成过程中持续向 stdout 输出小片段，而不是最后一次性 flush。

典型观测结果：

```text
--- chunk +2.974s bytes=8 ---
LLM: RK

--- chunk +3.226s bytes=1 ---
3

--- chunk +3.472s bytes=1 ---
5

--- chunk +3.720s bytes=1 ---
8

...

--- chunk +21.453s bytes=10 ---
<|im_end|>
```

这说明底层具备真实流式输出基础，FastAPI 层实现 SSE 是有意义的。

---

## 4. 队列与 busy lease 设计

Phase 9 的 LLM 队列策略是：

```text
max_concurrent=1
queue_policy=reject_when_busy
```

普通非流式请求通过 `llm_queue.run_nowait()` 包裹一次完整异步任务，请求结束后释放锁。

SSE 流式请求不能简单套用原来的 `run_nowait()`，因为 FastAPI handler 返回 `StreamingResponse` 后，真正的模型输出仍在 generator 中继续进行。如果提前释放 busy 状态，新的并发请求可能进入同一个 worker，造成 stdout 混乱。

Phase 10 因此新增了 lease 机制：

```text
LLMRequestQueue.acquire_nowait()
LLMRequestLease.finish_success()
LLMRequestLease.finish_error()
```

流式请求开始时获取 lease，并在 SSE generator 完整结束、异常或客户端断开时释放。这样可以保证整个流式输出期间 `/v1/metrics` 中 `llm.busy=true`，第二个并发 LLM 请求仍会立即返回：

```text
HTTP 429
llm_backend_busy
```

---

## 5. worker generate_stream 设计

`server/runtime/rkllm_worker_backend.py` 新增：

```text
RKLLMPersistentWorker.generate_stream()
```

核心行为：

```text
1. 复用 persistent worker 启动逻辑；
2. 写入 prompt；
3. 用 select + os.read 轮询 stdout；
4. 用 UTF-8 incremental decoder 避免中文多字节被拆坏；
5. 看到 <|im_end|> / You: 等结束标记后停止；
6. 每次读到可输出正文片段就 yield delta；
7. 如果流式请求中断或异常，主动 stop worker，避免下一次请求继承 stale stdout。
```

同时新增开头前缀清洗逻辑，避免 worker 的交互式前缀泄漏：

```text
LLM:
```

早期验证中曾出现过 `"L"`、`"L"`、`"M"`、`":"` 被拆成多个 SSE content chunk 输出的问题。修复后，流式正文从真实内容开始，例如：

```text
R
K3
588
是瑞芯微...
```

---

## 6. backend generate_stream 设计

`server/runtime/rkllm_backend.py` 新增：

```text
RKLLMBackend.supports_stream()
RKLLMBackend.generate_stream()
```

支持规则：

```text
fake backend:
  支持模拟流式输出

worker / persistent / persistent-worker:
  支持真实流式输出

oneshot:
  不支持 stream=true
```

当 one-shot 模式收到 `stream=true` 时，API 层返回：

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

---

## 7. API 层 SSE 响应格式

`server/api/chat_api.py` 新增 `StreamingResponse` 分支。

worker 模式下，请求：

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

响应 media type：

```text
text/event-stream
```

首个 chunk 返回 assistant role：

```text
data: {"id":"chatcmpl-...","object":"chat.completion.chunk","created":...,"model":"qwen3-4b-rkllm-all-npu","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}],"edgeinfer":{"backend":"rkllm-persistent-worker","stream":true}}
```

正文增量 chunk：

```text
data: {"id":"chatcmpl-...","object":"chat.completion.chunk","created":...,"model":"qwen3-4b-rkllm-all-npu","choices":[{"index":0,"delta":{"content":"RK"},"finish_reason":null}]}
```

结束 chunk：

```text
data: {"id":"chatcmpl-...","object":"chat.completion.chunk","created":...,"model":"qwen3-4b-rkllm-all-npu","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"edgeinfer":{"backend":"rkllm-persistent-worker","stream":true,"stop":{"requested":[],"matched":null}}}
```

最终结束标记：

```text
data: [DONE]
```

---

## 8. stop sequences 的流式处理

非流式模式中，stop sequences 会在完整文本生成后统一截断。

流式模式中，Phase 10 在 API 层维护 pending buffer，避免 stop sequence 刚好跨 chunk 被拆开时泄漏。例如 stop sequence 是 `RK3588`，而底层 delta 分成：

```text
R
K3
588
```

API 层不会只看单个 chunk，而是把 pending 和新 delta 合并后检查 stop sequence。如果匹配，则截断最后一次 delta 并结束流。

当前结束原因仍统一返回：

```text
finish_reason = "stop"
```

后续如果实现 token 计数或 max token 判断，可以进一步细分为 `length`。

---

## 9. 验证方法

### 9.1 本地静态检查

```bash
python3 -m py_compile   scripts/host/test_openai_chat_client.py   server/api/chat_api.py   server/runtime/rkllm_backend.py   server/runtime/rkllm_worker_backend.py   server/scheduler/request_queue.py

python3 -m compileall -q server scripts/host

bash -n scripts/host/smoke_test_serving.sh
bash -n scripts/host/validate_serving_modes.sh
bash -n scripts/host/deploy_serving_to_board.sh

git diff --check
```

### 9.2 双模式 smoke test

```bash
EDGEINFER_VALIDATE_DEPLOY=1 ./scripts/host/validate_serving_modes.sh
```

该脚本会自动执行：

```text
1. 部署最新代码到板端；
2. 强制恢复 one-shot；
3. 运行 one-shot smoke test；
4. 启用 worker mode；
5. 运行 worker smoke test；
6. cleanup 恢复默认 one-shot。
```

Phase 10 后，smoke test 新增：

```text
=== 4g. stream parameter compatibility ===
```

one-shot 阶段预期：

```text
stream unsupported HTTP 400
stream backend rejection check OK
```

worker 阶段预期：

```text
stream HTTP 200
stream SSE check OK
```

最终预期：

```text
=== Smoke test passed ===
=== cleanup: restore default one-shot mode ===
=== serving mode validation completed ===
```

### 9.3 OpenAI-like Python client 测试

默认 one-shot 模式：

```bash
./scripts/host/test_openai_chat_client.py
```

预期：

```text
backend_mode: oneshot
stream backend rejection check OK
=== OpenAI-like chat client test passed ...
```

worker 模式：

```bash
ssh linaro@192.168.43.7   "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/enable_edgeinfer_worker_mode.sh"

./scripts/host/test_openai_chat_client.py
```

预期：

```text
backend_mode: worker
HTTP 200
stream SSE check OK
=== OpenAI-like chat client test passed ...
```

测试完成后恢复默认 one-shot：

```bash
ssh linaro@192.168.43.7   "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/disable_edgeinfer_worker_mode.sh"
```

---

## 10. 已验证结果摘要

本阶段已验证：

```text
本地 py_compile 通过
compileall 通过
bash -n 通过
git diff --check 通过
validate_serving_modes.sh 双模式通过
one-shot smoke test 通过
worker smoke test 通过
one-shot stream=true 正确拒绝：HTTP 400 stream_backend_not_supported
worker stream=true SSE 成功：HTTP 200，data: [DONE]
worker Python client 通过
one-shot Python client 通过
测试结束后已恢复默认 one-shot
```

worker SSE 示例输出摘要：

```text
data: {"delta":{"role":"assistant"}}
data: {"delta":{"content":"R"}}
data: {"delta":{"content":"K3"}}
data: {"delta":{"content":"588"}}
...
data: {"delta":{},"finish_reason":"stop"}
data: [DONE]
```

---

## 11. 当前限制

Phase 10 当前仍有以下限制：

1. `stream=true` 只在 persistent worker 模式支持；
2. one-shot 模式仍拒绝 `stream=true`；
3. 当前是 chunk 级增量输出，不承诺严格 token 级切分；
4. `usage.prompt_tokens`、`usage.completion_tokens`、`usage.total_tokens` 仍为 `null`；
5. `temperature` 尚未真正下传到 RKLLM runtime；
6. `top_p` 仍只接受 `1.0`；
7. `response_format` 仍只接受 `{"type":"text"}`，不支持 JSON mode；
8. `finish_reason` 当前主要返回 `stop`，尚未细分 `length`；
9. worker 后端仍保持单并发，busy 时返回 429；
10. 尚未提供 OpenAI SDK 官方客户端示例。

---

## 12. 后续建议

Phase 10 SSE 收口后，后续可以继续推进：

```text
1. usage token 统计；
2. finish_reason=length 判断；
3. OpenAI SDK base_url 示例；
4. 更完善的 stream 客户端示例；
5. 流式响应中的错误处理与客户端断开压测；
6. 可选轻量请求队列；
7. temperature / top_p 真正下传 RKLLM runtime。
```

当前节点可以作为 Phase 10 worker streaming MVP 的阶段性收口点。
