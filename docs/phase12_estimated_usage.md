# Phase 12A：estimated usage token 统计验证记录

本文档记录 `edgeinfer-rk3588` 项目 Phase 12A 中对 OpenAI-like Chat Completions `usage` 字段的轻量增强。

Phase 12A 的目标不是实现官方 tokenizer 级别的精确 token 统计，而是在 RKLLM runtime 暂未暴露 token usage 的前提下，提供一个稳定、可验证、明确标注为估算值的 `usage` 字段，提升 OpenAI-like API 的可用性和客户端兼容性。

---

## 1. 当前结论

Phase 12A 后，非流式 `/v1/chat/completions` 响应中的 `usage` 不再返回 `null`：

```json
{
  "usage": {
    "prompt_tokens": 123,
    "completion_tokens": 45,
    "total_tokens": 168
  },
  "edgeinfer": {
    "usage": {
      "estimated": true,
      "method": "simple_mixed_text_heuristic_v1"
    }
  }
}
```

worker stream 模式下，最终 SSE chunk 也会携带估算 usage：

```text
data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":...,"completion_tokens":...,"total_tokens":...},"edgeinfer":{"usage":{"estimated":true,"method":"simple_mixed_text_heuristic_v1"}}}
data: [DONE]
```

---

## 2. 为什么先做 estimated usage

当前 RKLLM runtime / worker 输出中尚未暴露可靠的 tokenizer token 统计信息。直接声称精确 token 数会误导调用方。

因此 Phase 12A 采用保守策略：

```text
1. 返回整数 usage，避免 OpenAI-like 客户端因为 null 处理复杂；
2. 在 edgeinfer.usage 中明确标注 estimated=true；
3. method 字段说明当前是启发式估算；
4. 文档明确该数值不可用于精确计费或严格 token quota；
5. finish_reason=length 暂不强行实现。
```

---

## 3. 估算方法

当前估算方法名：

```text
simple_mixed_text_heuristic_v1
```

基本规则：

```text
1. CJK 字符按单字符计数；
2. 连续英文、数字、下划线按一个 token 计数；
3. 其他非空白符号按单个 token 计数；
4. 空字符串计数为 0；
5. 非空字符串至少返回 1。
```

该方法适合在中英文混合文本中提供稳定的相对估计，但不等价于 Qwen 官方 tokenizer 或 OpenAI tokenizer。

---

## 4. 响应字段

### 4.1 非流式响应

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "model": "qwen3-4b-rkllm-all-npu",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 123,
    "completion_tokens": 45,
    "total_tokens": 168
  },
  "edgeinfer": {
    "usage": {
      "estimated": true,
      "method": "simple_mixed_text_heuristic_v1"
    }
  }
}
```

### 4.2 流式最终 chunk

```text
data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":123,"completion_tokens":45,"total_tokens":168},"edgeinfer":{"backend":"rkllm-persistent-worker","stream":true,"usage":{"estimated":true,"method":"simple_mixed_text_heuristic_v1"}}}

data: [DONE]
```

普通内容 chunk 不携带 usage，只有最终 chunk 携带 usage。

---

## 5. 验证范围

Phase 12A 应验证：

```text
1. py_compile 通过；
2. compileall 通过；
3. bash -n 通过；
4. git diff --check 通过；
5. one-shot smoke test 验证非流式 usage 为整数；
6. worker smoke test 验证非流式 usage 为整数；
7. worker stream smoke test 验证最终 chunk usage 为整数；
8. one-shot Python client 验证 usage；
9. worker Python client 验证 usage；
10. OpenAI SDK examples 仍可运行。
```

---

## 6. 当前限制

1. usage 是估算值，不是官方 tokenizer 精确值；
2. 不应用于计费；
3. 不应用于严格 quota；
4. `finish_reason` 当前仍主要返回 `stop`；
5. 尚未实现 `finish_reason=length`；
6. stream 模式只有最终 chunk 携带 usage；
7. 后续如果 RKLLM runtime 暴露 token 统计，应优先切换到 runtime 真实数据。

---

## 7. 后续建议

Phase 12A 收口后，可以继续推进：

```text
1. 接入真实 tokenizer 或 RKLLM runtime token 统计；
2. 实现 finish_reason=length；
3. 增加 stream_options.include_usage 风格开关；
4. 增加 usage 估算误差说明；
5. 在 OpenAI SDK 示例中展示 usage 读取方式。
```
