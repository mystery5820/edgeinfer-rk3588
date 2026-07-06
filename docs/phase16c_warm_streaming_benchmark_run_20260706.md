# Phase 16C：Warm Worker Streaming Benchmark Run 2026-07-06

本文档记录 2026-07-06 对 `edgeinfer-rk3588` 执行的 warm worker streaming benchmark。

本次测试基于 Phase 16A 新增脚本：

```text
scripts/host/benchmark_llm_streaming.py
```

与 Phase 16B 的区别：

```text
Phase 16B：包含 worker cold start 影响；
Phase 16C：先 warm-up，再执行 repeat=3，重点观察 warm worker 首 content 延迟。
```

---

## 1. 测试目标

本次测试关注：

```text
1. warm worker 模式下 stream=true 是否稳定；
2. time_to_first_event_ms；
3. time_to_first_content_ms；
4. total_stream_latency_ms；
5. content chunk 数量；
6. finish_reason；
7. data: [DONE]；
8. worker runtime 是否稳定复用。
```

---

## 2. 测试环境

Host：

```text
repo: ~/edgeinfer-rk3588
```

Board：

```text
board_url: http://192.168.43.7:8000
model_id: qwen3-4b-rkllm-all-npu
service: edgeinfer-serving.service
```

启用 worker mode：

```bash
ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/enable_edgeinfer_worker_mode.sh"
```

启用结果：

```text
service status: active
service enabled: enabled
health.status: ok
EDGEINFER_RKLLM_BACKEND_MODE=worker
EDGEINFER_RKLLM_WORKER_MAX_NEW=128
EDGEINFER_RKLLM_WORKER_CTX=1024
```

---

## 3. Warm-up

先执行一次 warm-up：

```bash
python3 scripts/host/benchmark_llm_streaming.py \
  --repeat 1 \
  --max-tokens 64 \
  --output-prefix llm_streaming_benchmark_warmup
```

warm-up 开始时：

```text
backend_mode=worker
worker_enabled=True
worker_started=False
```

warm-up 结果：

| prompt | ok | first_content_ms | total_ms | chunks | chars | finish_reason | done |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| `rk3588_intro` | True | 10182.353 | 20936.991 | 41 | 82 | stop | True |
| `edge_ai_value` | True | 4474.957 | 14219.971 | 37 | 80 | stop | True |

说明：

```text
warm-up 第一条请求仍然包含 worker 启动成本；
warm-up 第二条请求开始进入 worker 复用状态。
```

---

## 4. 正式 warm repeat=3 benchmark

正式执行：

```bash
python3 scripts/host/benchmark_llm_streaming.py \
  --repeat 3 \
  --max-tokens 64 \
  --output-prefix llm_streaming_benchmark_warm_repeat3
```

正式测试开始时：

```text
backend_mode=worker
worker_enabled=True
worker_started=True
```

说明：

```text
worker_started=True 表示本轮正式 benchmark 已经避开 worker cold start，测试更接近 warm worker 表现。
```

输出文件：

```text
results/benchmark/llm_streaming_benchmark_warm_repeat3.csv
results/benchmark/llm_streaming_benchmark_warm_repeat3_report.md
```

---

## 5. Summary 结果

| prompt | runs | ok | first_content_avg_ms | first_content_p50_ms | total_avg_ms | total_p50_ms | chars_avg | content_chunks_avg |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `rk3588_intro` | 3 | 3 | 5232.026 | 5089.104 | 15630.382 | 15809.715 | 80.667 | 40.000 |
| `edge_ai_value` | 3 | 3 | 4515.733 | 4539.413 | 16685.367 | 15555.707 | 91.333 | 45.667 |

核心结论：

```text
rk3588_intro warm first_content 平均约 5.23 s；
edge_ai_value warm first_content 平均约 4.52 s；
6 次请求全部成功；
全部收到 data: [DONE]；
全部 finish_reason=stop。
```

---

## 6. Raw rows

| prompt | repeat | status | ok | first_event_ms | first_content_ms | total_ms | events | content_chunks | chars | finish_reason | done |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `rk3588_intro` | 1 | 200 | True | 73.931 | 5082.882 | 15809.715 | 43 | 41 | 82 | stop | True |
| `edge_ai_value` | 1 | 200 | True | 63.458 | 4539.413 | 19803.817 | 60 | 58 | 109 | stop | True |
| `rk3588_intro` | 2 | 200 | True | 85.871 | 5524.091 | 15989.101 | 42 | 40 | 80 | stop | True |
| `edge_ai_value` | 2 | 200 | True | 76.341 | 4440.127 | 14696.578 | 40 | 38 | 81 | stop | True |
| `rk3588_intro` | 3 | 200 | True | 62.590 | 5089.104 | 15092.329 | 41 | 39 | 80 | stop | True |
| `edge_ai_value` | 3 | 200 | True | 62.012 | 4567.658 | 15555.707 | 43 | 41 | 84 | stop | True |

CSV 原始行：

```csv
timestamp,board_url,model_id,backend_mode,worker_enabled,worker_started,prompt_name,repeat_idx,max_tokens,http_status,ok,header_latency_ms,time_to_first_event_ms,time_to_first_content_ms,total_stream_latency_ms,event_count,content_event_count,assistant_chars,finish_reason,done_received,prompt_tokens,completion_tokens,total_tokens,edgeinfer_backend,error
2026-07-06T15:05:48+0800,http://192.168.43.7:8000,qwen3-4b-rkllm-all-npu,worker,True,True,rk3588_intro,1,64,200,True,73.858,73.931,5082.882,15809.715,43,41,82,stop,True,27,44,71,rkllm-persistent-worker,
2026-07-06T15:06:03+0800,http://192.168.43.7:8000,qwen3-4b-rkllm-all-npu,worker,True,True,edge_ai_value,1,64,200,True,63.314,63.458,4539.413,19803.817,60,58,109,stop,True,34,69,103,rkllm-persistent-worker,
2026-07-06T15:06:23+0800,http://192.168.43.7:8000,qwen3-4b-rkllm-all-npu,worker,True,True,rk3588_intro,2,64,200,True,85.701,85.871,5524.091,15989.101,42,40,80,stop,True,27,42,69,rkllm-persistent-worker,
2026-07-06T15:06:39+0800,http://192.168.43.7:8000,qwen3-4b-rkllm-all-npu,worker,True,True,edge_ai_value,2,64,200,True,76.318,76.341,4440.127,14696.578,40,38,81,stop,True,34,48,82,rkllm-persistent-worker,
2026-07-06T15:06:54+0800,http://192.168.43.7:8000,qwen3-4b-rkllm-all-npu,worker,True,True,rk3588_intro,3,64,200,True,62.551,62.590,5089.104,15092.329,41,39,80,stop,True,27,42,69,rkllm-persistent-worker,
2026-07-06T15:07:09+0800,http://192.168.43.7:8000,qwen3-4b-rkllm-all-npu,worker,True,True,edge_ai_value,3,64,200,True,61.403,62.012,4567.658,15555.707,43,41,84,stop,True,34,51,85,rkllm-persistent-worker,
```

---

## 7. Metrics before / after

### 7.1 Before

正式 benchmark 开始前：

```text
llm.total_requests = 2
llm.completed_requests = 2
llm.failed_requests = 0
llm.timeout_requests = 0
llm.rejected_busy = 0

rkllm_backend.mode = worker
worker_enabled = true
worker_runtime.started = true
worker_runtime.request_count = 2
worker_runtime.restart_count = 0
worker_runtime.startup_ms = 5063.471
```

说明：

```text
前面的 2 次请求来自 warm-up；
worker 已经启动并完成模型初始化；
正式 repeat=3 benchmark 是 warm worker 场景。
```

### 7.2 After

正式 benchmark 完成后：

```text
llm.total_requests = 8
llm.accepted_requests = 8
llm.completed_requests = 8
llm.failed_requests = 0
llm.timeout_requests = 0
llm.rejected_busy = 0

worker_runtime.started = true
worker_runtime.pid = 2476
worker_runtime.request_count = 8
worker_runtime.restart_count = 0
worker_runtime.failed_request_count = 0
worker_runtime.last_latency_ms = 15190.808
```

说明：

```text
6 次正式请求全部完成；
worker 没有重启；
没有 failed / timeout / rejected_busy。
```

---

## 8. 首 event 与首 content 的区别

本次 warm worker 中：

```text
first_event_ms 大约 62-86 ms；
first_content_ms 大约 4.44-5.52 s。
```

含义：

```text
first_event_ms：
  FastAPI / SSE 通道很快建立，首个 data event 很快返回。

first_content_ms：
  用户真正看到第一段 assistant 文本的时间。
```

当前更适合作为展示指标的是：

```text
time_to_first_content_ms
```

原因：

```text
首 event 往往只是 delta.role=assistant；
首 content 才代表用户看到模型输出。
```

---

## 9. 与 Phase 16B 的对比

Phase 16B 中第一条请求：

```text
worker_started=False
rk3588_intro first_content_ms=9794.570
```

Phase 16C warm repeat=3 中：

```text
rk3588_intro first_content_avg_ms=5232.026
edge_ai_value first_content_avg_ms=4515.733
```

对比说明：

```text
1. worker cold start 对第一条请求影响明显；
2. warm worker 下首 content 延迟更稳定；
3. 后续 README 展示建议优先使用 warm worker repeat=3 数据；
4. cold start 数据仍应保留，用于说明首次启动成本。
```

---

## 10. 测试后恢复 one-shot

正式 benchmark 后已恢复默认模式：

```bash
ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/disable_edgeinfer_worker_mode.sh"
```

恢复结果：

```text
worker-mode.conf removed
service active
service enabled
health.status = ok
```

---

## 11. 是否提交 CSV / report

本次不建议提交：

```text
results/benchmark/llm_streaming_benchmark_warmup.csv
results/benchmark/llm_streaming_benchmark_warmup_report.md
results/benchmark/llm_streaming_benchmark_warm_repeat3.csv
results/benchmark/llm_streaming_benchmark_warm_repeat3_report.md
```

原因：

```text
1. 它们是生成产物；
2. 每次 benchmark 都会变化；
3. 默认可继续由 .gitignore 管理；
4. 对外展示提交稳定摘要文档即可。
```

Phase 16C 建议提交：

```text
docs/phase16c_warm_streaming_benchmark_run_20260706.md
README.md
docs/README.md
```

---

## 12. 后续建议

### 12.1 README 性能摘要

后续可以考虑在 README benchmark 摘要中加入：

```text
Warm worker streaming first content latency:
  rk3588_intro avg: 5.23 s
  edge_ai_value avg: 4.52 s
```

但建议明确：

```text
sample: repeat=3, max_tokens=64, Qwen3-4B all-NPU RKLLM, RK3588
```

---

### 12.2 Phase 16D 对比总表

可以单独整理：

```text
docs/phase16d_streaming_vs_nonstreaming_summary.md
```

包含：

```text
1. Phase 14B non-streaming latency；
2. Phase 16B cold/warm streaming latency；
3. Phase 16C warm repeat=3 first content latency；
4. 结论：streaming 优势主要在首内容可见延迟，而不是总耗时。
```

---

## 13. 阶段结论

Phase 16C 证明：

```text
1. warm worker streaming benchmark 可以稳定运行；
2. 6 次正式请求全部成功；
3. SSE 全部收到 data: [DONE]；
4. finish_reason 全部为 stop；
5. worker 没有重启或失败；
6. warm first_content 平均约 4.52-5.23 s；
7. 相比 cold start 样例，warm worker 首 content 延迟明显更稳定；
8. 测试完成后已恢复 one-shot。
```
