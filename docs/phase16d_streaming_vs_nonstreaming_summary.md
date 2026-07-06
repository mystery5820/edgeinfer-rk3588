# Phase 16D：Streaming vs Non-streaming Performance Summary

本文档汇总 `edgeinfer-rk3588` 当前非流式与流式 benchmark 结果，用于对外展示、README 性能摘要和后续 release note。

数据来源：

```text
docs/phase14c_benchmark_run_20260705.md
docs/phase16b_streaming_benchmark_run_20260706.md
docs/phase16c_warm_streaming_benchmark_run_20260706.md
```

---

## 1. 对比目标

本阶段目标不是重新跑 benchmark，而是将已有结果横向整理，回答：

```text
1. one-shot 非流式表现如何？
2. worker 非流式表现如何？
3. worker streaming 首 content 延迟如何？
4. streaming 相比非流式的优势在哪里？
5. 哪组数据适合写入 README？
6. 哪些数据只适合作为验证记录？
```

---

## 2. 测试条件概览

### 2.1 非流式 benchmark

来源：

```text
docs/phase14c_benchmark_run_20260705.md
```

测试脚本：

```text
scripts/host/benchmark_llm_serving.py
```

请求模式：

```text
stream=false
```

测试配置：

```text
model_id=qwen3-4b-rkllm-all-npu
max_tokens=48
repeat=1
```

---

### 2.2 流式 benchmark

来源：

```text
docs/phase16b_streaming_benchmark_run_20260706.md
docs/phase16c_warm_streaming_benchmark_run_20260706.md
```

测试脚本：

```text
scripts/host/benchmark_llm_streaming.py
```

请求模式：

```text
stream=true
```

测试配置：

```text
model_id=qwen3-4b-rkllm-all-npu
max_tokens=64
```

注意：

```text
非流式测试 max_tokens=48；
流式测试 max_tokens=64；
因此 total latency 不是严格同参数横向对比，只适合展示趋势。
```

---

## 3. 非流式 benchmark 结果

### 3.1 one-shot 非流式

| prompt | backend | client_latency_ms | edgeinfer_latency_ms | completion_tokens | total_tokens | finish_reason |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `rk3588_intro` | `rkllm-runner` | 21332.354 | 21252.085 | 40 | 76 | stop |
| `edge_ai_value` | `rkllm-runner` | 21657.876 | 21573.018 | 50 | 92 | stop |

观察：

```text
one-shot 模式 client_latency_ms 与 edgeinfer_latency_ms 非常接近；
说明耗时主要来自模型执行本身。
```

---

### 3.2 worker 非流式

| prompt | backend | worker_started_before_request | client_latency_ms | edgeinfer_latency_ms | completion_tokens | total_tokens | finish_reason |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| `rk3588_intro` | `rkllm-persistent-worker` | false | 21434.632 | 15254.611 | 42 | 78 | stop |
| `edge_ai_value` | `rkllm-persistent-worker` | true | 13455.843 | 13049.420 | 35 | 77 | stop |

观察：

```text
1. 第一条 worker 请求包含 worker 启动成本；
2. 第二条请求复用已启动 worker；
3. warm worker 非流式总耗时明显低于 one-shot；
4. edge_ai_value 从 one-shot 约 21.66 s 降到 worker warm 约 13.46 s。
```

---

## 4. 流式 benchmark 结果

### 4.1 Phase 16B：worker streaming 单次结果

| prompt | worker_started | first_event_ms | first_content_ms | total_ms | content_chunks | chars | finish_reason | done |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `rk3588_intro` | false | 75.945 | 9794.570 | 19521.244 | 38 | 81 | stop | True |
| `edge_ai_value` | true | 60.486 | 4531.683 | 15299.840 | 40 | 84 | stop | True |

观察：

```text
1. first_event_ms 约 60-76 ms，说明 SSE 通道建立很快；
2. first_content_ms 才是用户看到第一段文本的时间；
3. rk3588_intro 第一条包含 worker cold start，first_content 更高；
4. edge_ai_value 复用 worker，first_content 降到约 4.53 s。
```

---

### 4.2 Phase 16C：warm worker streaming repeat=3

| prompt | runs | ok | first_content_avg_ms | first_content_p50_ms | total_avg_ms | total_p50_ms | chars_avg | content_chunks_avg |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `rk3588_intro` | 3 | 3 | 5232.026 | 5089.104 | 15630.382 | 15809.715 | 80.667 | 40.000 |
| `edge_ai_value` | 3 | 3 | 4515.733 | 4539.413 | 16685.367 | 15555.707 | 91.333 | 45.667 |

观察：

```text
1. warm worker streaming 6 次正式请求全部成功；
2. 全部 HTTP 200；
3. 全部 finish_reason=stop；
4. 全部收到 data: [DONE]；
5. worker 未重启；
6. 无 failed / timeout / rejected_busy。
```

---

## 5. 横向对比表

### 5.1 one-shot 非流式 vs warm worker 非流式

| prompt | one-shot client_ms | worker client_ms | 改善 |
| --- | ---: | ---: | --- |
| `rk3588_intro` | 21332.354 | 21434.632 | 第一条 worker 包含启动成本，client 总耗时不占优 |
| `edge_ai_value` | 21657.876 | 13455.843 | warm worker 明显更低 |

说明：

```text
worker 需要区分 cold 与 warm；
只看第一条 worker 请求容易低估 worker 模式价值。
```

---

### 5.2 非流式 total latency vs 流式 first content latency

| prompt | non-stream one-shot client_ms | non-stream warm worker client_ms | streaming warm first_content_avg_ms | streaming warm total_avg_ms |
| --- | ---: | ---: | ---: | ---: |
| `rk3588_intro` | 21332.354 | 21434.632 | 5232.026 | 15630.382 |
| `edge_ai_value` | 21657.876 | 13455.843 | 4515.733 | 16685.367 |

注意：

```text
1. 这里的非流式 max_tokens=48，流式 max_tokens=64；
2. total latency 不是严格同配置对比；
3. 但 first_content_latency 可以表达 streaming 的用户体验优势；
4. streaming 不是让模型生成总时间消失，而是让用户更早看到输出。
```

---

## 6. 适合 README 展示的数据

建议 README 中不要堆太多细节，只放稳定、易理解的摘要。

推荐写法：

```text
Qwen3-4B RKLLM all-NPU on RK3588:

Non-streaming:
  one-shot sample latency: ~21.3-21.7 s
  warm worker sample latency: ~13.5 s

Streaming:
  warm worker first content latency:
    rk3588_intro avg: ~5.23 s
    edge_ai_value avg: ~4.52 s
  all warm streaming runs: 6/6 OK
```

更严谨的表格：

| 类别 | 指标 | 数值 | 说明 |
| --- | --- | ---: | --- |
| non-stream one-shot | client latency | 21.3-21.7 s | repeat=1, max_tokens=48 |
| non-stream warm worker | client latency | 13.46 s | worker 已启动后的样例 |
| streaming warm worker | first content avg | 4.52-5.23 s | repeat=3, max_tokens=64 |
| streaming warm worker | success | 6/6 OK | finish_reason=stop, done=True |

建议加注：

```text
Benchmark values are sample measurements on one RK3588 board and may vary with prompt, model file, max_tokens, runtime state and board load.
```

---

## 7. 不建议放进 README 首页的数据

不建议直接把以下内容放到 README 首页：

```text
1. Phase 16B 的 cold worker first_content=9.79 s；
2. 单条请求的所有 raw rows；
3. process_max_rss_kb；
4. worker pid；
5. last_started_at / last_finished_at；
6. full metrics JSON。
```

原因：

```text
1. 首页需要简洁；
2. cold start 数据容易被误解为 warm streaming 性能；
3. raw metrics 更适合保留在 docs；
4. README 更适合放摘要和链接。
```

---

## 8. 结论解释

### 8.1 one-shot

one-shot 的特点：

```text
1. 请求简单；
2. 不需要常驻 worker；
3. 每次通过 runner 执行；
4. stream=true 不支持；
5. 总耗时在本次样例中约 21 s。
```

适合：

```text
低频请求；
简单部署；
调试或兜底路径。
```

---

### 8.2 persistent worker

persistent worker 的特点：

```text
1. worker 常驻；
2. warm 状态下可降低非流式总耗时；
3. 支持 stream=true SSE；
4. 可以显著提前首 content 可见时间；
5. 需要 systemd drop-in 控制 worker mode。
```

适合：

```text
交互式聊天；
OpenAI SDK streaming；
需要更好用户体验的场景。
```

---

### 8.3 streaming

streaming 的主要价值：

```text
不是保证 total latency 一定降低；
而是降低用户等待第一段文本的时间。
```

本次 warm repeat=3 中：

```text
first content avg: 4.52-5.23 s
total avg: 15.63-16.69 s
```

这说明：

```text
用户可以在总生成完成前约 10 秒左右先看到内容。
```

---

## 9. 后续建议

### 9.1 README benchmark 摘要更新

下一步可以做：

```text
Phase 17A：README Benchmark Snapshot
```

建议更新 README 中的 benchmark 部分，加入：

```text
1. Qwen3-4B all-NPU raw RKLLM prefill/generate 指标；
2. non-stream one-shot latency；
3. non-stream warm worker latency；
4. streaming warm first content latency；
5. 文档链接。
```

---

### 9.2 Release note

后续可以做：

```text
Phase 17B：v0.1.0 Release Notes
```

总结：

```text
1. RKNN YOLOv11；
2. RKLLM Qwen3-4B；
3. FastAPI Serving；
4. OpenAI-like API；
5. streaming SSE；
6. benchmark；
7. docs；
8. known limitations。
```

---

## 10. 阶段结论

Phase 16D 得出的最终性能表述：

```text
1. one-shot 非流式样例延迟约 21.3-21.7 s；
2. worker warm 非流式样例延迟可降到约 13.5 s；
3. worker warm streaming 首 content 平均约 4.52-5.23 s；
4. streaming 优势主要体现在首内容可见延迟；
5. total latency 仍受模型生成速度、max_tokens、prompt 和 runtime 状态影响；
6. README 建议使用 warm worker repeat=3 的 streaming first_content 数据作为展示指标。
```
