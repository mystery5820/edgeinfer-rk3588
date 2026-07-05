# Phase 14：Benchmark 与性能展示总表

本文档汇总 `edgeinfer-rk3588` 当前已经沉淀的性能与验证数据，用于 README 展示、阶段复盘、答辩材料和后续 Benchmark 规划。

注意：本文档不是一次全新统一压测结果，而是对当前仓库中已有验证记录的整理。不同阶段的测试 prompt、参数、后端模式和服务状态可能不同，因此表格中的数据主要用于阶段性对比和项目展示，不应直接作为严格同条件 Benchmark 结论。

---

## 1. 数据来源

当前已盘点的数据来源包括：

```text
configs/model_registry.yaml
docs/phase5_yolo11_rknn_board_validation.md
docs/phase6_qwen25_0_5b_rkllm_board_validation.md
docs/phase6_qwen25_1_5b_rkllm_board_validation.md
docs/phase6_qwen25_rkllm_model_comparison.md
docs/phase8_qwen3_4b_all_npu_hybrid_rkllm_board_validation.md
docs/phase9_qwen3_real_backend_validation.md
docs/phase9_rkllm_worker_mode_validation.md
docs/phase9_prompt_policy_validation.md
docs/phase9_host_smoke_test_validation.md
docs/phase9_busy_metrics_validation.md
results/benchmark/
```

其中：

```text
1. Qwen3-4B all-NPU / hybrid 的指标以 configs/model_registry.yaml 为主要来源；
2. Qwen2.5 的指标以 Phase 6 文档中的平均 tokens/s 记录为主要来源；
3. YOLOv11 的有效板端 FPS 以 Phase 5 板端验证文档为主要来源；
4. results/benchmark 下存在若干 dryrun CSV，不能直接等同于真实板端性能；
5. Serving latency 来自不同阶段的功能验证日志，只作为代表性样例。
```

---

## 2. LLM 模型性能汇总

### 2.1 Qwen3-4B RKLLM all-NPU / hybrid

| 模型 | 路线 | 状态 | 推荐 | ctx | max_new_tokens | init_ms | prefill_tps | generate_tps | peak_memory_mb |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3-4B W8A8 | all-NPU | runnable | yes | 1024 | 128 | 3759.09 | 49.83 | 4.14 | 4182.84 |
| Qwen3-4B W8A8 | hybrid | runnable | no | 1024 | 128 | 16665.54 | 39.51 | 3.79 | 4342.63 |

结论：

```text
1. all-NPU init_ms 明显低于 hybrid；
2. all-NPU prefill_tps 高于 hybrid；
3. all-NPU generate_tps 略高于 hybrid；
4. all-NPU peak_memory_mb 低于 hybrid；
5. 当前推荐 qwen3-4b-rkllm-all-npu 作为 Serving 主线模型。
```

---

### 2.2 Qwen2.5 RKLLM 基线

| 模型 | 量化 | max_context | 平均 prefill_tps | 平均 generate_tps | 备注 |
| --- | --- | ---: | ---: | ---: | --- |
| Qwen2.5-0.5B-Instruct | W8A8 | 2048 | 318.56 | 21.79 | 生成速度约 21 到 22 tokens/s，峰值内存约 674 MB |
| Qwen2.5-1.5B-Instruct | W8A8 | 2048 | 163.78 | 9.14 | 生成速度约 9 tokens/s |

结论：

```text
1. Qwen2.5-0.5B 速度明显更快，适合作为轻量 baseline；
2. Qwen2.5-1.5B 在速度和能力之间折中；
3. Qwen3-4B 能力更强，但 generate_tps 明显低于 Qwen2.5 小模型；
4. Qwen2.5 数据主要用于早期 RKLLM 链路验证和性能基线对比。
```

---

## 3. 视觉模型性能汇总

### 3.1 YOLOv11 RKNN

| 模型 | backend | 输入尺寸 | 状态 | 板端平均 FPS | 备注 |
| --- | --- | --- | --- | ---: | --- |
| YOLOv11n-FP-Baseline | RKNN | 640x640 | ready | 5.29 | 已完成板端验证 |
| YOLOv11n-INT8-Baseline | RKNN | 640x640 | debug | 暂不列入 | INT8 可加载推理，但类别分支输出异常，暂不作为有效部署模型 |

说明：

```text
1. YOLOv11 FP baseline 已完成板端验证；
2. INT8 路线当前不作为主线继续深挖；
3. results/benchmark 中存在 dryrun CSV，这类文件主要用于流程调试，不作为真实板端性能；
4. 后续如需对外展示，建议重新执行统一 Benchmark 并生成 avg / p50 / p95 / FPS 表。
```

---

## 4. Serving 延迟样例

以下数据来自不同阶段功能验证日志，不是统一压测环境下的 Benchmark，仅用于展示 Serving 主线的代表性延迟范围。

| 场景 | 后端模式 | 参数/说明 | latency_ms |
| --- | --- | --- | ---: |
| Qwen3 real backend validation | one-shot | `max_new_tokens=64` | 43387.491 |
| prompt policy validation | one-shot | `max_new_tokens=96` | 30495.365 |
| prompt policy validation | one-shot | 后续短回答样例 | 20968.391 |
| host smoke test sample | one-shot | smoke test 样例 | 48572.324 |
| host smoke test sample | one-shot | smoke test 样例 | 59093.692 |
| RKLLM worker probe request 1 | persistent worker | first request | 12384.256 |
| RKLLM worker probe request 2 | persistent worker | second request | 7361.892 |
| RKLLM worker API sample | persistent worker | API validation sample | 10361.362 |

观察：

```text
1. one-shot 模式每次请求包含 RKLLM 进程启动与模型初始化成本；
2. persistent worker 模式复用已启动 worker，后续请求延迟明显降低；
3. worker 模式更适合作为 stream=true 和低延迟交互的基础；
4. 当前延迟数据来自功能验证阶段，不是严格统一 Benchmark。
```

---

## 5. API / Serving 验证能力表

| 能力 | 状态 | 验证入口 |
| --- | --- | --- |
| `/v1/health` | 已支持 | `smoke_test_serving.sh` |
| `/v1/models` | 已支持 | `smoke_test_serving.sh` |
| `/v1/metrics` | 已支持 | `smoke_test_serving.sh` |
| `/v1/chat/completions` | 已支持 | `test_openai_chat_client.py` |
| `max_tokens` | 已支持 | `test_openai_chat_client.py` |
| `max_new_tokens` | 已保留 | `smoke_test_serving.sh` |
| `stop` | 已支持 | `test_openai_chat_client.py` |
| `stream=true` one-shot | 显式拒绝 | `stream_backend_not_supported` |
| `stream=true` worker | 已支持 | SSE final chunk + `[DONE]` |
| OpenAI Python SDK | 已支持 | `check_openai_sdk_examples.py` |
| estimated usage | 已支持 | Phase 12A |
| `finish_reason=length` | 暂不实现 | Phase 12B 调研 |
| busy rejection | 已支持 | HTTP 429 `llm_backend_busy` |
| systemd deployment | 已支持 | `edgeinfer-serving.service` |
| one-shot / worker 双模式验收 | 已支持 | `validate_serving_modes.sh` |

---

## 6. 当前推荐展示表

如需在 README 或答辩材料中展示，可优先使用以下简化表。

### 6.1 LLM 模型对比

| 模型 | 路线 | generate_tps | peak_memory_mb | 结论 |
| --- | --- | ---: | ---: | --- |
| Qwen2.5-0.5B | RKLLM W8A8 | 21.79 | 约 674 | 轻量 baseline |
| Qwen2.5-1.5B | RKLLM W8A8 | 9.14 | 未统一摘录 | 中等规模 baseline |
| Qwen3-4B | all-NPU W8A8 | 4.14 | 4182.84 | 当前推荐主线模型 |
| Qwen3-4B | hybrid W8A8 | 3.79 | 4342.63 | 可运行但不推荐 |

### 6.2 Serving 能力展示

| 项目 | 当前能力 |
| --- | --- |
| 模型 | Qwen3-4B RKLLM all-NPU |
| 服务 | FastAPI + Uvicorn + systemd |
| API | OpenAI-like `/v1/chat/completions` |
| 流式 | worker 模式 SSE |
| SDK | OpenAI Python SDK `base_url` |
| 稳定性 | busy rejection + metrics |
| 验收 | host/board 自动化验证 |

---

## 7. 后续 Benchmark 规划

后续如果要做更严格的性能展示，建议新增一个统一 Benchmark 阶段：

```text
Phase 14B：controlled benchmark run
```

建议统一记录：

```text
1. board 型号；
2. kernel / RKNPU driver；
3. RKLLM runtime 版本；
4. 模型文件；
5. ctx；
6. max_new_tokens；
7. prompt；
8. prefill_tps；
9. generate_tps；
10. latency_ms；
11. first token latency；
12. total tokens；
13. peak memory；
14. one-shot / worker 是否区分；
15. 重复次数；
16. avg / p50 / p95。
```

建议输出文件：

```text
results/benchmark/llm_serving_benchmark.csv
results/benchmark/llm_serving_benchmark_report.md
docs/phase14b_controlled_benchmark.md
```

---

## 8. 阶段结论

当前已有数据足以支撑项目展示：

```text
1. Qwen3-4B all-NPU 是当前推荐 LLM Serving 模型；
2. Qwen2.5 小模型提供早期 RKLLM 性能基线；
3. YOLOv11 FP baseline 已完成板端视觉模型验证；
4. persistent worker 明显改善交互式请求延迟；
5. OpenAI-like API、streaming、usage、metrics、busy rejection 已形成工程闭环。
```

但若要发布更严谨的性能报告，应继续执行 Phase 14B 统一 Benchmark，而不是混用不同阶段验证日志。
