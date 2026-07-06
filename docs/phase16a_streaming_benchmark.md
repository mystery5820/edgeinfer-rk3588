# Phase 16A：Streaming Benchmark / First Content Latency

本文档记录 Phase 16A 新增的 LLM streaming SSE benchmark 工具，用于评估 RKLLM persistent worker 模式下 `stream=true` 的首事件延迟、首 content 延迟和总流式耗时。

---

## 1. 背景

此前项目已经完成：

```text
Phase 10：worker stream=true SSE 能力
Phase 14B：非流式 controlled benchmark
Phase 15E：OpenAI Python SDK streaming 使用说明
```

但还缺少针对 streaming 的性能指标，例如：

```text
1. time_to_first_event_ms；
2. time_to_first_content_ms；
3. total_stream_latency_ms；
4. content chunk 数量；
5. data: [DONE] 是否收到；
6. final finish_reason；
7. final usage。
```

Phase 16A 新增独立脚本：

```text
scripts/host/benchmark_llm_streaming.py
```

该脚本不修改 server runtime，只从 host 侧请求 `/v1/chat/completions` 并解析 SSE。

---

## 2. 前置条件

Streaming benchmark 需要 RKLLM persistent worker mode。

启用 worker：

```bash
ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/enable_edgeinfer_worker_mode.sh"
```

确认：

```bash
curl -s http://192.168.43.7:8000/v1/metrics | python3 -m json.tool
```

重点查看：

```text
rkllm_backend.mode
rkllm_backend.worker_enabled
rkllm_backend.worker_runtime.started
```

---

## 3. 执行 benchmark

默认执行：

```bash
cd ~/edgeinfer-rk3588

python3 scripts/host/benchmark_llm_streaming.py \
  --repeat 1 \
  --max-tokens 64
```

默认参数：

```text
board_url: EDGEINFER_BOARD_URL or http://192.168.43.7:8000
model_id: EDGEINFER_MODEL_ID or qwen3-4b-rkllm-all-npu
repeat: 1
max_tokens: 64
timeout: 180
```

输出文件：

```text
results/benchmark/llm_streaming_benchmark.csv
results/benchmark/llm_streaming_benchmark_report.md
```

注意：

```text
results/benchmark/llm_streaming_benchmark*.csv / *.md 属于 benchmark 生成产物；
默认可以只保留本地，不必提交到 Git。
```

---

## 4. 恢复 one-shot

测试完成后建议恢复默认 one-shot：

```bash
ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/disable_edgeinfer_worker_mode.sh"
```

---

## 5. CSV 字段说明

| 字段 | 说明 |
| --- | --- |
| `timestamp` | benchmark 行生成时间 |
| `board_url` | 板端 Serving URL |
| `model_id` | 模型 ID |
| `backend_mode` | `/v1/metrics` 中的 RKLLM backend mode |
| `worker_enabled` | worker 是否启用 |
| `worker_started` | benchmark 开始前 worker 是否已启动 |
| `prompt_name` | prompt 名称 |
| `repeat_idx` | 第几轮 |
| `max_tokens` | 请求 max_tokens |
| `http_status` | HTTP 状态码 |
| `ok` | 本行是否通过 |
| `header_latency_ms` | 请求到响应头返回耗时 |
| `time_to_first_event_ms` | 第一个 SSE `data:` event 到达耗时 |
| `time_to_first_content_ms` | 第一个 `delta.content` 到达耗时 |
| `total_stream_latency_ms` | 请求到 `[DONE]` 或错误结束耗时 |
| `event_count` | JSON SSE event 数 |
| `content_event_count` | 含 content 的 SSE event 数 |
| `assistant_chars` | 拼接后的 assistant content 字符数 |
| `finish_reason` | final chunk 的 finish_reason |
| `done_received` | 是否收到 `data: [DONE]` |
| `prompt_tokens` | estimated prompt tokens |
| `completion_tokens` | estimated completion tokens |
| `total_tokens` | estimated total tokens |
| `edgeinfer_backend` | SSE payload 中的 backend |
| `error` | 错误信息 |

---

## 6. 指标解释

### 6.1 time_to_first_event_ms

表示从 host 发起 HTTP 请求到收到第一个 SSE `data:` event 的耗时。

首 event 通常可能是：

```json
{
  "choices": [
    {
      "delta": {
        "role": "assistant"
      },
      "finish_reason": null
    }
  ]
}
```

该指标反映：

```text
HTTP 请求建立 + API 接收 + worker 准备 + 首个 SSE event 返回
```

---

### 6.2 time_to_first_content_ms

表示从 host 发起 HTTP 请求到收到第一个非空 `delta.content` 的耗时。

这个指标更接近用户感知的：

```text
首 token / 首文本可见延迟
```

注意：

```text
由于当前 streaming chunk 是 worker stdout 片段，不一定等价于严格 tokenizer token；
因此命名为 first_content，而不是 first_token。
```

---

### 6.3 total_stream_latency_ms

表示从请求发起到收到 `data: [DONE]` 或出错结束的总耗时。

该指标可与 Phase 14B 的非流式 benchmark 对比，但要注意：

```text
1. streaming 会先返回部分内容；
2. total latency 不一定比非流式低；
3. streaming 的优势主要体现在 first content latency；
4. worker 首次启动时可能包含 worker startup 成本。
```

---

## 7. one-shot 模式行为

默认 one-shot 模式不支持 `stream=true`。

如果直接执行 benchmark，脚本会先检查 `/v1/metrics`：

```text
rkllm_backend.mode
```

如果不是 worker 模式，默认退出并提示启用 worker。

如需记录 one-shot 拒绝路径，可使用：

```bash
python3 scripts/host/benchmark_llm_streaming.py --allow-non-worker
```

此时预期会记录：

```text
HTTP 400
error=stream_backend_not_supported
```

但这不是性能 benchmark，只是拒绝路径记录。

---

## 8. 与现有脚本关系

| 脚本 | 用途 |
| --- | --- |
| `scripts/host/test_openai_chat_client.py` | OpenAI-like API 正确性与错误响应测试 |
| `scripts/host/smoke_test_serving.sh` | host-side serving smoke / mode validation |
| `scripts/host/benchmark_llm_serving.py` | 非流式 controlled benchmark |
| `scripts/host/benchmark_llm_streaming.py` | 流式 SSE benchmark / first content latency |

Phase 16A 的脚本复用了既有 SSE 语义：

```text
1. data: [DONE]；
2. choices[0].delta.role；
3. choices[0].delta.content；
4. choices[0].finish_reason=stop；
5. final chunk usage；
6. worker prefix 不应泄漏。
```

---

## 9. 推荐展示方式

后续可以在 README 或 Phase 14 benchmark 总表中补一行：

```text
Streaming first content latency: 待 Phase 16A 实测填入
```

建议等实际运行结果出来后再写：

```text
docs/phase16b_streaming_benchmark_run_YYYYMMDD.md
```

---

## 10. 阶段结论

Phase 16A 新增了 streaming benchmark 工具，为后续展示 worker streaming 的用户感知延迟打基础。

当前阶段只完成工具和文档：

```text
1. 新增 streaming benchmark 脚本；
2. 新增 Phase 16A 文档；
3. 不改 server runtime；
4. 不改变 RKLLM worker 行为；
5. 实测结果留到 Phase 16B。
```
