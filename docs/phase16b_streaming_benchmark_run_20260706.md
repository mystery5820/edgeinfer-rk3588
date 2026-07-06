# Phase 16B：Streaming Benchmark Run 2026-07-06

本文档记录 2026-07-06 在 RK3588 板端执行 `stream=true` SSE benchmark 的一次 controlled run 结果。

本次运行基于 Phase 16A 新增脚本：

```text
scripts/host/benchmark_llm_streaming.py
```

---

## 1. Git 基线

本次运行发生在 Phase 16A 工具补丁应用并验证之后，随后 Phase 16A 已提交：

```text
commit: 4123312 add streaming llm benchmark
tag: phase16a-streaming-benchmark
```

Phase 16A 新增：

```text
scripts/host/benchmark_llm_streaming.py
docs/phase16a_streaming_benchmark.md
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

测试前 `/v1/metrics` 显示默认模式为 one-shot：

```text
rkllm_backend.mode = oneshot
rkllm_backend.worker_enabled = false
```

随后启用 worker mode：

```bash
ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/enable_edgeinfer_worker_mode.sh"
```

启用后服务状态：

```text
active
enabled
health.status = ok
```

---

## 3. Benchmark 命令

执行命令：

```bash
python3 scripts/host/benchmark_llm_streaming.py \
  --repeat 1 \
  --max-tokens 64
```

脚本配置：

```text
board_url=http://192.168.43.7:8000
model_id=qwen3-4b-rkllm-all-npu
repeat=1
max_tokens=64
timeout=180.0
```

运行开始时 metrics：

```text
backend_mode=worker
worker_enabled=True
worker_started=False
```

说明：

```text
worker_started=False 表示本次 benchmark 的第一条请求会包含 worker 首次启动成本。
```

---

## 4. 输出文件

脚本生成：

```text
results/benchmark/llm_streaming_benchmark.csv
results/benchmark/llm_streaming_benchmark_report.md
```

这些文件属于 benchmark 生成产物，不建议直接提交到 Git。

本次 Phase 16B 只提交摘要文档：

```text
docs/phase16b_streaming_benchmark_run_20260706.md
```

---

## 5. 结果摘要

| prompt | status | ok | first_event_ms | first_content_ms | total_ms | events | content_chunks | chars | finish_reason | done |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `rk3588_intro` | 200 | True | 75.945 | 9794.570 | 19521.244 | 40 | 38 | 81 | stop | True |
| `edge_ai_value` | 200 | True | 60.486 | 4531.683 | 15299.840 | 42 | 40 | 84 | stop | True |

CSV 原始行：

```csv
timestamp,board_url,model_id,backend_mode,worker_enabled,worker_started,prompt_name,repeat_idx,max_tokens,http_status,ok,header_latency_ms,time_to_first_event_ms,time_to_first_content_ms,total_stream_latency_ms,event_count,content_event_count,assistant_chars,finish_reason,done_received,prompt_tokens,completion_tokens,total_tokens,edgeinfer_backend,error
2026-07-06T14:52:21+0800,http://192.168.43.7:8000,qwen3-4b-rkllm-all-npu,worker,True,False,rk3588_intro,1,64,200,True,75.800,75.945,9794.570,19521.244,40,38,81,stop,True,27,41,68,rkllm-persistent-worker,
2026-07-06T14:52:41+0800,http://192.168.43.7:8000,qwen3-4b-rkllm-all-npu,worker,True,False,edge_ai_value,1,64,200,True,60.463,60.486,4531.683,15299.840,42,40,84,stop,True,34,51,85,rkllm-persistent-worker,
```

---

## 6. 关键观察

### 6.1 SSE 首事件很快返回

两条请求的 `time_to_first_event_ms` 分别为：

```text
rk3588_intro: 75.945 ms
edge_ai_value: 60.486 ms
```

这说明 FastAPI 层能够很快返回 SSE event。

但首 event 通常是：

```json
{
  "delta": {
    "role": "assistant"
  }
}
```

它不等价于用户可见文本。

---

### 6.2 首 content 延迟才是用户感知关键指标

两条请求的 `time_to_first_content_ms` 分别为：

```text
rk3588_intro: 9794.570 ms
edge_ai_value: 4531.683 ms
```

这更接近用户感知的：

```text
首文本可见延迟
```

注意：

```text
当前 chunk 来自 worker stdout 片段，不一定严格等价于 tokenizer token；
因此文档和脚本使用 first_content，而不是 first_token。
```

---

### 6.3 第一条请求包含 worker 启动成本

运行前：

```text
worker_started=False
```

运行后 metrics 中显示：

```text
worker_runtime.started = true
worker_runtime.startup_ms = 4730.006
worker_runtime.request_count = 2
```

因此第一条 `rk3588_intro` 的首 content 延迟更高：

```text
9794.570 ms
```

它包含了 worker 首次启动和模型初始化相关成本。

第二条请求复用已启动 worker，首 content 延迟降到：

```text
4531.683 ms
```

这更接近 warm worker 的 streaming 首 content 表现。

---

### 6.4 总流式耗时

两条请求的 `total_stream_latency_ms`：

```text
rk3588_intro: 19521.244 ms
edge_ai_value: 15299.840 ms
```

对比 Phase 14B 非流式 benchmark 时要注意：

```text
1. streaming 的优势不是总耗时一定更低；
2. streaming 的优势在于更早开始向客户端返回可见内容；
3. total latency 仍受模型生成速度、max_new_tokens、prompt 和 worker 状态影响。
```

---

### 6.5 SSE 完整性

两条请求都满足：

```text
HTTP 200
ok=True
finish_reason=stop
done_received=True
edgeinfer_backend=rkllm-persistent-worker
error=""
```

说明：

```text
1. worker streaming 路径正常；
2. final chunk 返回 finish_reason=stop；
3. 收到了 data: [DONE]；
4. 未出现 worker prefix 泄漏；
5. final usage 正常返回 estimated usage。
```

---

## 7. Metrics before / after 摘要

### 7.1 Metrics before

```text
llm.total_requests = 0
llm.completed_requests = 0
rkllm_backend.mode = worker
worker_enabled = true
worker_runtime.started = false
worker_runtime.request_count = 0
```

### 7.2 Metrics after

```text
llm.total_requests = 2
llm.accepted_requests = 2
llm.completed_requests = 2
llm.failed_requests = 0
llm.timeout_requests = 0
llm.rejected_busy = 0

worker_runtime.started = true
worker_runtime.pid = 2295
worker_runtime.request_count = 2
worker_runtime.restart_count = 0
worker_runtime.failed_request_count = 0
worker_runtime.startup_ms = 4730.006
worker_runtime.last_latency_ms = 14930.351
```

---

## 8. 测试后恢复 one-shot

测试完成后已执行：

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

这说明测试后板端服务已经恢复默认 one-shot 模式。

---

## 9. 是否提交 CSV / report

本次不建议提交：

```text
results/benchmark/llm_streaming_benchmark.csv
results/benchmark/llm_streaming_benchmark_report.md
```

原因：

```text
1. 它们是 benchmark 生成产物；
2. 默认会受到 .gitignore 管理；
3. 每次运行都会变化；
4. 更适合本地保留；
5. 对外展示应提交稳定摘要文档。
```

因此 Phase 16B 只提交：

```text
docs/phase16b_streaming_benchmark_run_20260706.md
```

并更新：

```text
README.md
docs/README.md
```

---

## 10. 后续建议

### 10.1 warm worker repeat

本次 `repeat=1`，第一条请求包含 worker cold start 成本。

后续建议执行：

```bash
python3 scripts/host/benchmark_llm_streaming.py \
  --repeat 3 \
  --max-tokens 64
```

这样可以更好地区分：

```text
cold worker first_content latency
warm worker first_content latency
```

---

### 10.2 与非流式 benchmark 对比

后续可以把 Phase 14B 和 Phase 16B 的结果放在同一张表中：

```text
non-streaming total latency
streaming first_content latency
streaming total latency
```

展示重点：

```text
streaming 不一定降低总耗时；
但可以显著提前用户看到第一段内容的时间。
```

---

### 10.3 README 性能摘要

后续可以在 README 的 Benchmark 展示中新增：

```text
Streaming first content latency:
  warm worker sample: 4.53 s
```

但建议等 `repeat=3` 或更多样本后再写入 README 首页，避免单次结果代表性不足。

---

## 11. 阶段结论

Phase 16B 证明：

```text
1. Phase 16A streaming benchmark 工具可正常运行；
2. worker stream=true SSE 返回完整；
3. 首 event 延迟约 60-76 ms；
4. 首 content 延迟在本次样例中为 4.53-9.79 s；
5. 第二条 warm worker 请求明显优于第一条 cold worker 请求；
6. benchmark 后已恢复 one-shot；
7. 结果适合进入 docs 摘要，不建议提交 CSV/report 生成产物。
```
