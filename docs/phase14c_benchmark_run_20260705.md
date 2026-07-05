# Phase 14C：LLM Serving Benchmark Run 2026-07-05

本文档记录 2026-07-05 对 `edgeinfer-rk3588` 进行的一次 controlled LLM Serving benchmark 结果摘要。

本次测试基于 Phase 14B 新增脚本：

```bash
scripts/host/benchmark_llm_serving.py
```

测试目标是验证该脚本在 one-shot 与 persistent worker 两种后端模式下均可正常执行，并产出 CSV / Markdown report。

---

## 1. 测试环境

### 1.1 Host

```text
仓库路径：~/edgeinfer-rk3588
执行脚本：scripts/host/benchmark_llm_serving.py
```

### 1.2 Board

```text
BOARD_URL=http://192.168.43.7:8000
service=edgeinfer-serving.service
model_id=qwen3-4b-rkllm-all-npu
```

### 1.3 Benchmark 参数

```text
repeat=1
max_tokens=48
timeout_seconds=180
prompt_count=2
```

测试 prompt：

```text
rk3588_intro：请用一句话介绍 RK3588。
edge_ai_value：请用两句话说明端侧 LLM Serving 的价值。
```

---

## 2. one-shot benchmark

### 2.1 执行命令

```bash
python3 scripts/host/benchmark_llm_serving.py \
  --repeat 1 \
  --max-tokens 48
```

### 2.2 输出文件

```text
results/benchmark/llm_serving_benchmark_oneshot.csv
results/benchmark/llm_serving_benchmark_oneshot_report.md
```

### 2.3 结果表

| prompt_name | backend_mode | edgeinfer_backend | client_latency_ms | edgeinfer_latency_ms | completion_tokens | total_tokens | finish_reason |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| rk3588_intro | oneshot | rkllm-runner | 21332.354 | 21252.085 | 40 | 76 | stop |
| edge_ai_value | oneshot | rkllm-runner | 21657.876 | 21573.018 | 50 | 92 | stop |

### 2.4 one-shot 观察

```text
1. 两个请求均返回 HTTP 200；
2. backend_mode=oneshot；
3. edgeinfer_backend=rkllm-runner；
4. client_latency_ms 与 edgeinfer_latency_ms 非常接近；
5. 说明 one-shot 模式下主要耗时来自后端推理流程本身；
6. 本轮测试 total_requests=2，success_count=2，failure_count=0。
```

---

## 3. worker benchmark

### 3.1 启用 worker

```bash
ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/enable_edgeinfer_worker_mode.sh"
```

启用后服务状态：

```text
EDGEINFER_RKLLM_BACKEND_MODE=worker
EDGEINFER_RKLLM_WORKER_MAX_NEW=128
EDGEINFER_RKLLM_WORKER_CTX=1024
service=active
enabled=true
health=ok
```

### 3.2 执行命令

```bash
python3 scripts/host/benchmark_llm_serving.py \
  --repeat 1 \
  --max-tokens 48
```

### 3.3 恢复 one-shot

```bash
ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/disable_edgeinfer_worker_mode.sh"
```

恢复后服务状态：

```text
EDGEINFER_RKLLM_BACKEND_MODE 已移除
service=active
enabled=true
health=ok
```

### 3.4 输出文件

```text
results/benchmark/llm_serving_benchmark_worker.csv
results/benchmark/llm_serving_benchmark_worker_report.md
```

### 3.5 结果表

| prompt_name | backend_mode | edgeinfer_backend | worker_started_before_request | client_latency_ms | edgeinfer_latency_ms | completion_tokens | total_tokens | finish_reason |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| rk3588_intro | worker | rkllm-persistent-worker | false | 21434.632 | 15254.611 | 42 | 78 | stop |
| edge_ai_value | worker | rkllm-persistent-worker | true | 13455.843 | 13049.420 | 35 | 77 | stop |

### 3.6 worker 观察

```text
1. 两个请求均返回 HTTP 200；
2. backend_mode=worker；
3. edgeinfer_backend=rkllm-persistent-worker；
4. 第一条请求前 worker_runtime.started=false；
5. 第一条请求会触发 persistent worker 启动；
6. worker benchmark report 中记录 startup_ms=5752.936；
7. 第二条请求复用已启动 worker，client_latency_ms 明显下降；
8. worker 模式 benchmark 后 worker_runtime.request_count=2；
9. 本轮测试 total_requests=2，success_count=2，failure_count=0。
```

---

## 4. one-shot 与 worker 对比

### 4.1 同 prompt 对比

| prompt_name | one-shot client_latency_ms | worker client_latency_ms | one-shot edgeinfer_latency_ms | worker edgeinfer_latency_ms | 观察 |
| --- | ---: | ---: | ---: | ---: | --- |
| rk3588_intro | 21332.354 | 21434.632 | 21252.085 | 15254.611 | worker 第一条包含启动成本，client 总耗时不占优，但后端推理耗时更低 |
| edge_ai_value | 21657.876 | 13455.843 | 21573.018 | 13049.420 | worker 已启动后，总耗时和后端耗时均明显降低 |

### 4.2 阶段结论

```text
1. one-shot 模式适合默认、简单、可恢复的服务路径；
2. worker 模式适合交互式低延迟请求和 stream=true；
3. worker 首次请求可能包含 startup cost；
4. worker 后续请求受益于 persistent worker 复用；
5. 对外展示 worker 性能时应区分 cold worker 与 warm worker；
6. 本次 repeat=1，数据仅作为 controlled run 样例，不作为严格统计结论。
```

---

## 5. 为什么不提交 CSV / report 生成产物

本次实际生成了：

```text
results/benchmark/llm_serving_benchmark_oneshot.csv
results/benchmark/llm_serving_benchmark_oneshot_report.md
results/benchmark/llm_serving_benchmark_worker.csv
results/benchmark/llm_serving_benchmark_worker_report.md
```

但这些文件被 `.gitignore` 忽略，当前阶段不强制提交。

原因：

```text
1. CSV / report 是脚本生成产物；
2. 不同时间、prompt、服务状态会生成不同结果；
3. 直接提交生成产物容易让仓库混入一次性日志；
4. 更推荐提交脚本、说明文档和人工整理后的 benchmark run 摘要；
5. 如后续要建立正式 benchmark archive，可单独设计 results/benchmark/archive 规则。
```

---

## 6. 当前已提交内容与本次补充内容

Phase 14B 已提交：

```text
scripts/host/benchmark_llm_serving.py
docs/phase14b_controlled_benchmark.md
README.md
docs/README.md
```

Phase 14C 建议提交：

```text
docs/phase14c_benchmark_run_20260705.md
README.md
docs/README.md
```

---

## 7. 后续建议

后续可以继续做更稳定的 Benchmark：

```text
1. repeat=3 或 repeat=5；
2. 单独区分 worker cold start 和 warm worker；
3. 增加 stream=true first-token latency；
4. 增加 max_tokens 参数矩阵；
5. 增加 prompt JSON 配置文件；
6. 生成 README benchmark 展示表；
7. 设计 benchmark archive 目录，选择性提交正式 benchmark 结果。
```

---

## 8. 阶段结论

本次 Phase 14C 确认：

```text
1. controlled benchmark 脚本可正常运行；
2. one-shot 模式可稳定产出 benchmark CSV / report；
3. worker 模式可稳定产出 benchmark CSV / report；
4. worker 首次请求包含启动成本；
5. worker warm request 延迟明显低于 one-shot；
6. benchmark 输出格式可用于后续更严格的 repeat run；
7. 当前仓库保留脚本和摘要文档，不强制提交一次性生成产物。
```
