# Phase 12B：finish_reason=length 语义调研

本文档记录 `edgeinfer-rk3588` 项目 Phase 12B 对 OpenAI-like Chat Completions `finish_reason=length` 的可行性调研。

结论先行：当前版本暂不实现 `finish_reason=length`。原因是 RKLLM one-shot runner 与 persistent worker 目前都没有向 API 层暴露可靠的生成停止原因、真实生成 token 数或是否命中 `max_new_tokens` 上限的结构化信号。

---

## 1. 调研目标

Phase 12A 已经完成 estimated usage：

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

Phase 12B 原本希望继续完善：

```text
finish_reason=length
```

也就是当模型因为达到 `max_tokens` / `max_new_tokens` 上限而停止生成时，在 OpenAI-like 响应中返回：

```json
{
  "finish_reason": "length"
}
```

但要正确实现这一语义，API 层必须能可靠知道底层生成结束原因。

---

## 2. 当前代码现状

### 2.1 API 层

`server/api/chat_api.py` 当前非流式响应仍返回：

```json
{
  "finish_reason": "stop"
}
```

worker stream 的最终 chunk 也返回：

```json
{
  "finish_reason": "stop"
}
```

API 层目前没有收到类似下面这些字段：

```text
generated_tokens
finish_reason
stop_reason
hit_max_new_tokens
eos_reached
```

因此 API 层无法直接判断 `length`。

### 2.2 one-shot runner

`server/runtime/rkllm_runner.py` 当前行为：

1. 调用 RKLLM enhanced 二进制；
2. 把 prompt 写入 stdin；
3. 等待进程返回；
4. 清洗 stdout；
5. 输出 `=== CLEAN_TEXT_BEGIN ===` / `=== CLEAN_TEXT_END ===`；
6. stderr 只打印 `latency_ms=...`。

当前 one-shot runner 只把清洗后的文本交给 API 层，没有返回真实 token 数，也没有返回底层 stop reason。

### 2.3 persistent worker 非流式

`server/runtime/rkllm_worker_backend.py` 中，worker 非流式生成逻辑主要通过 `_read_until()` 等待：

```text
<|im_end|>
\r\nYou:
\nYou:
```

读取完成后调用 `_clean_response()` 清理输出，然后返回：

```text
text
latency_ms
backend
startup_ms
model_path
```

当前 `WorkerGenerateResult` 没有包含：

```text
finish_reason
matched_end_marker
generated_tokens
hit_max_new_tokens
```

因此 API 层也不能基于 worker 非流式结果判断 `length`。

### 2.4 persistent worker 流式

worker stream 当前读取 stdout 增量数据，并等待以下 end markers：

```text
<|im_end|>
\r\nYou:
\nYou:
```

如果发现 end marker，就认为生成完成，并停止 streaming。

如果一直没有看到 end marker，直到超时，则抛出：

```text
TimeoutError
```

这只能区分：

```text
看到交互式结束标记
等待超时
worker 异常退出
```

不能区分：

```text
自然 EOS
命中 max_new_tokens
用户 stop sequence
```

其中用户 stop sequence 是 API 层自己通过 `_apply_stop_sequences()` 或 `_filter_stream_delta()` 处理的，不等价于 RKLLM runtime 的生成停止原因。

---

## 3. 为什么不能用 estimated usage 判断 length

Phase 12A 的 usage 是估算值：

```text
simple_mixed_text_heuristic_v1
```

它不是 Qwen tokenizer，也不是 RKLLM runtime 的真实 token 统计。

因此不能使用：

```text
completion_tokens >= max_tokens
```

来判断 `finish_reason=length`。

这种做法会把启发式估算值误用为真实 tokenizer 结果，容易产生错误语义。

---

## 4. 为什么不能用请求 max_tokens 直接判断

当前 worker 模式还有一个额外复杂点：

```python
return max(128, int(request_max_new_tokens))
```

也就是说，当用户请求：

```json
{
  "max_tokens": 64
}
```

worker 实际可能以：

```text
worker_max_new_tokens = 128
```

运行。

因此即使输出较长，也不能简单认为它触发了用户请求的 `max_tokens=64` 截断。

---

## 5. 当前保守策略

Phase 12B 的结论是：

```text
1. 不实现假的 finish_reason=length；
2. 继续保守返回 finish_reason=stop；
3. 文档明确当前不能可靠区分 length；
4. 后续等 RKLLM runtime / runner / worker 暴露真实停止原因后再实现；
5. Phase 12A 的 estimated usage 继续保留，但不得用于 length 判断。
```

---

## 6. 未来可行实现路径

后续可以选择以下路径之一：

### 6.1 RKLLM runtime 暴露真实停止原因

理想情况是底层直接返回：

```text
stop_reason = eos | max_tokens | stop_sequence | timeout | error
generated_tokens = N
```

这时 API 层可以可靠映射：

```text
eos / stop_sequence -> finish_reason=stop
max_tokens          -> finish_reason=length
timeout             -> HTTP 504 llm_timeout
error               -> HTTP 502 rkllm_runtime_error
```

### 6.2 worker wrapper 增加结构化尾标记

如果 RKLLM enhanced 二进制可以改造，可在每次生成结束时输出结构化 marker：

```text
=== EDGEINFER_GENERATION_META_BEGIN ===
{"stop_reason":"eos","generated_tokens":42,"hit_max_new_tokens":false}
=== EDGEINFER_GENERATION_META_END ===
```

API 层再解析该 metadata。

### 6.3 tokenizer 级别二次统计

如果引入 Qwen tokenizer，可以更准确统计 usage，但仍然只能帮助 token 数统计，不足以单独判断底层停止原因。

tokenizer 统计可以作为辅助信号，不能替代 runtime stop reason。

---

## 7. 暂不实现 length 的原因总结

当前不能可靠实现 `finish_reason=length`，因为：

```text
1. one-shot runner 没有返回 stop reason；
2. worker 非流式没有返回 stop reason；
3. worker stream 只知道是否看到 end marker；
4. estimated usage 不是 tokenizer 真实 token 数；
5. worker 实际 max_new_tokens 可能大于请求 max_tokens；
6. timeout 已作为错误路径处理，不应伪装成 length；
7. 错误实现 length 会降低 OpenAI-like API 语义可信度。
```

因此 Phase 12B 的合理结论是：**暂不实现 `finish_reason=length`，保留后续扩展点。**

---

## 8. 当前状态

当前版本继续保持：

```json
{
  "finish_reason": "stop"
}
```

并在文档中明确说明：

```text
finish_reason=length 暂未实现；
当前 RKLLM runner / worker 未暴露可靠 length 判断信号；
后续需要 runtime stop reason 或 worker 结构化 metadata 支持。
```
