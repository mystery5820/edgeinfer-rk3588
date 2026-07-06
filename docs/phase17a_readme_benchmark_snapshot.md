# Phase 17A：README Benchmark Snapshot

本文档记录 Phase 17A 对 README 首页 Benchmark Snapshot 的整理原则、数据来源和最终展示口径。

---

## 1. 目标

Phase 17A 的目标不是新增 benchmark 工具，也不是重新跑测试，而是把 Phase 14 / Phase 16 已完成的 benchmark 结论压缩成 README 首页可读的性能快照。

README 首页需要满足：

```text
1. 简洁；
2. 对外展示友好；
3. 不堆 raw metrics；
4. 不夸大结果；
5. 明确样例测量条件；
6. 链接到详细 benchmark 文档。
```

---

## 2. 数据来源

README Benchmark Snapshot 基于以下文档：

```text
docs/phase14c_benchmark_run_20260705.md
docs/phase16c_warm_streaming_benchmark_run_20260706.md
docs/phase16d_streaming_vs_nonstreaming_summary.md
```

核心数据：

```text
Non-streaming one-shot:
  sample latency: ~21.3-21.7 s

Non-streaming warm worker:
  sample latency: ~13.5 s

Streaming warm worker:
  first content latency: ~4.52-5.23 s
  warm streaming runs: 6/6 OK
```

---

## 3. README 展示原则

README 首页只展示摘要，不展示完整 raw rows。

推荐保留：

```text
1. Qwen3-4B all-NPU RKLLM；
2. RK3588；
3. non-streaming one-shot sample latency；
4. non-streaming warm worker sample latency；
5. streaming warm worker first content latency；
6. 6/6 OK；
7. 简短 disclaimer；
8. 指向详细 docs。
```

不推荐放入 README 首页：

```text
1. 完整 metrics JSON；
2. worker pid；
3. request_count；
4. last_started_at / last_finished_at；
5. process_max_rss_kb；
6. cold start 单条 raw row；
7. 过多 CSV 原始行。
```

---

## 4. README 新增内容

Phase 17A 在 README 中新增：

```text
## 5. Benchmark Snapshot
```

并将原有章节顺延：

```text
原 ## 5. 快速开始 -> ## 6. 快速开始
原 ## 6. 板端服务 -> ## 7. 板端服务
原 ## 7. API 示例 -> ## 8. API 示例
原 ## 8. OpenAI Python SDK 示例 -> ## 9. OpenAI Python SDK 示例
原 ## 9. 目录说明 -> ## 10. 目录说明
原 ## 10. 文档导航 -> ## 11. 文档导航
原 ## 11. 当前限制 -> ## 12. 当前限制
原 ## 12. 已完成阶段标签 -> ## 13. 已完成阶段标签
原 ## 13. 项目当前状态 -> ## 14. 项目当前状态
```

---

## 5. 最终展示口径

README 中采用：

```text
Qwen3-4B RKLLM all-NPU on RK3588
```

表格：

| 场景 | 指标 | 样例结果 | 说明 |
| --- | --- | ---: | --- |
| Non-streaming one-shot | client latency | ~21.3-21.7 s | repeat=1, max_tokens=48 |
| Non-streaming warm worker | client latency | ~13.5 s | worker 已启动后的样例 |
| Streaming warm worker | first content latency | ~4.52-5.23 s | repeat=3, max_tokens=64 |
| Streaming warm worker | success | 6/6 OK | finish_reason=stop, done=True |

说明：

```text
Benchmark values are sample measurements on one RK3588 board and may vary with prompt, max_tokens, runtime state and board load.
```

---

## 6. 阶段结论

Phase 17A 将 benchmark 结果从详细 docs 提炼到 README 首页，使项目对外展示更加完整：

```text
1. README 现在能直接看到性能快照；
2. 详细数据仍保留在 docs；
3. 性能描述没有夸大；
4. streaming 的优势被明确表达为 first content latency；
5. 后续可进入 v0.1.0 release note / final checklist。
```
