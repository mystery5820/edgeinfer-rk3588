# Phase 14B：Controlled LLM Serving Benchmark

本文档记录 `edgeinfer-rk3588` 的 controlled LLM Serving benchmark 设计与执行方式。

Phase 14A 已经整理了历史性能数据；Phase 14B 开始新增统一脚本，对 `/v1/chat/completions` 做可重复的 host 侧性能采样。

---

## 1. 新增脚本

```text
scripts/host/benchmark_llm_serving.py
```

该脚本会请求板端 OpenAI-like Chat Completions API，并输出：

```text
results/benchmark/llm_serving_benchmark_<backend_mode>.csv
results/benchmark/llm_serving_benchmark_<backend_mode>_report.md
```

其中 `<backend_mode>` 会根据 `/v1/metrics` 中的 `rkllm_backend.mode` 自动生成，例如：

```text
llm_serving_benchmark_oneshot.csv
llm_serving_benchmark_oneshot_report.md
llm_serving_benchmark_worker.csv
llm_serving_benchmark_worker_report.md
```

---

## 2. 采样字段

CSV 当前记录：

```text
timestamp
board_url
model_id
backend_mode
worker_enabled
worker_started
prompt_name
repeat_idx
max_tokens
http_status
ok
client_latency_ms
edgeinfer_latency_ms
llm_last_latency_ms
prompt_tokens
completion_tokens
total_tokens
finish_reason
edgeinfer_backend
assistant_chars
error
```

说明：

```text
client_latency_ms：host 侧完整 HTTP 请求耗时
edgeinfer_latency_ms：服务端 edgeinfer metadata 中的后端耗时
llm_last_latency_ms：/v1/metrics 中的 llm.last_latency_ms
usage：Phase 12A estimated usage，不是 tokenizer 精确值
```

---

## 3. one-shot benchmark

默认模式通常是 one-shot。

执行：

```bash
cd ~/edgeinfer-rk3588

python3 scripts/host/benchmark_llm_serving.py \
  --repeat 1 \
  --max-tokens 48
```

输出示例：

```text
results/benchmark/llm_serving_benchmark_oneshot.csv
results/benchmark/llm_serving_benchmark_oneshot_report.md
```

---

## 4. worker benchmark

启用 worker：

```bash
ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/enable_edgeinfer_worker_mode.sh"
```

执行 benchmark：

```bash
python3 scripts/host/benchmark_llm_serving.py \
  --repeat 1 \
  --max-tokens 48
```

恢复默认 one-shot：

```bash
ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/disable_edgeinfer_worker_mode.sh"
```

输出示例：

```text
results/benchmark/llm_serving_benchmark_worker.csv
results/benchmark/llm_serving_benchmark_worker_report.md
```

---

## 5. 推荐初始验证流程

为了避免一次跑太久，建议先执行：

```bash
python3 scripts/host/benchmark_llm_serving.py --repeat 1 --max-tokens 48
```

确认脚本和输出格式正常后，再提高 repeat：

```bash
python3 scripts/host/benchmark_llm_serving.py --repeat 3 --max-tokens 48
```

---

## 6. 报告说明

Markdown report 会包含：

```text
1. benchmark 配置；
2. health 响应；
3. benchmark 前 metrics；
4. summary 表；
5. raw request rows；
6. benchmark 后 metrics；
7. 注意事项。
```

summary 表会给出：

```text
client_avg_ms
client_p50_ms
client_p95_ms
backend_avg_ms
backend_p50_ms
backend_p95_ms
completion_tokens_avg
```

---

## 7. 当前限制

当前 Phase 14B 只做非流式 `/v1/chat/completions` benchmark，不统计 SSE first-token latency。

原因：

```text
1. 当前 stream=true 仅 worker 模式支持；
2. first-token latency 需要更精细的 SSE 事件时间戳采样；
3. 当前阶段先统一 one-shot / worker 的非流式请求指标；
4. 后续可新增 stream benchmark 脚本。
```

---

## 8. 后续扩展

后续可继续增加：

```text
1. stream first-token latency；
2. stream total latency；
3. one-shot 与 worker 自动切换；
4. 多 max_tokens 参数矩阵；
5. prompt set 外部 JSON 文件；
6. CSV 历史追加模式；
7. README benchmark 表自动生成。
```
