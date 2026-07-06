# Phase 17B：v0.1.0 Release Notes / Final Milestone Summary

本文档整理 `edgeinfer-rk3588` 当前主线达到的 v0.1.0 候选状态，用于项目版本收口、GitHub release note、简历描述和后续交接。

注意：

```text
本文档是 v0.1.0 release notes 草案 / milestone summary。
是否真正创建 v0.1.0 tag，建议在 Phase 17C final checklist 通过后再执行。
```

---

## 1. Release 定位

`edgeinfer-rk3588` v0.1.0 的定位：

```text
面向 RK3588 开发板的端侧多模型推理服务框架 MVP。
```

当前版本已经完成从视觉模型验证到端侧 LLM Serving 的主线闭环：

```text
YOLOv11 RKNN 板端验证
Qwen3-4B RKLLM 板端推理
FastAPI Serving Framework
OpenAI-like Chat Completions API
persistent worker stream=true SSE
OpenAI Python SDK base_url 接入
busy rejection
metrics
systemd 服务化部署
host 侧自动化验收
controlled benchmark
README benchmark snapshot
docs 阶段化整理
```

---

## 2. 当前核心能力

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| RK3588 board deployment | 已完成 | 支持部署到 RK3588 板端运行 |
| FastAPI Serving | 已完成 | 提供 HTTP Serving 入口 |
| `/v1/health` | 已完成 | 服务健康检查 |
| `/v1/models` | 已完成 | 模型注册表查询 |
| `/v1/metrics` | 已完成 | 服务状态、busy、worker runtime、计数器 |
| `/v1/chat/completions` | 已完成 | OpenAI-like Chat API |
| Qwen3-4B RKLLM all-NPU | 已验证 | 当前推荐 LLM 主线 |
| YOLOv11 RKNN | 已验证 | 完成视觉模型板端验证和路线取舍 |
| one-shot RKLLM backend | 已完成 | 默认安全路径 |
| persistent worker backend | 已完成 | 支持 worker 复用与 streaming |
| `stream=true` SSE | 已完成 | worker-only |
| OpenAI Python SDK examples | 已完成 | 支持 `base_url` 指向本地板端服务 |
| estimated usage | 已完成 | 返回估算 token usage |
| busy rejection | 已完成 | 后端忙时返回 429 |
| systemd deployment | 已完成 | 支持服务启停、worker mode 切换 |
| host smoke tests | 已完成 | 支持部署、验收、API 兼容验证 |
| benchmark tools | 已完成 | 非流式与流式 benchmark 脚本 |

---

## 3. 推荐模型

当前推荐模型：

```text
qwen3-4b-rkllm-all-npu
```

推荐原因：

```text
1. 已完成板端真实推理验证；
2. 已注册到 model_registry；
3. 已被 /v1/chat/completions 覆盖；
4. 已被 one-shot / worker / streaming 路径覆盖；
5. 已被 OpenAI SDK examples 覆盖；
6. all-NPU 路线更适合当前 Serving 主线。
```

---

## 4. API 能力范围

### 4.1 支持

| 能力 | 状态 |
| --- | --- |
| `messages` | 支持 |
| `model` | 支持 |
| `max_tokens` | 支持，映射到 `max_new_tokens` |
| `max_new_tokens` | 支持，EdgeInfer 扩展参数 |
| `stop` | 支持 string / string array |
| `stream=false` | 支持 |
| `stream=true` | persistent worker mode 支持 |
| `usage` | 支持 estimated usage |
| `edgeinfer` metadata | 支持 |

---

### 4.2 显式拒绝或暂不支持

| 能力 | 当前行为 |
| --- | --- |
| `n > 1` | HTTP 400 `n_not_supported` |
| `top_p != 1.0` | HTTP 400 `top_p_not_supported` |
| `response_format=json_object` | HTTP 400 `response_format_not_supported` |
| one-shot mode `stream=true` | HTTP 400 `stream_backend_not_supported` |
| unknown model | HTTP 404 `model_not_found` |
| non-LLM model for chat | HTTP 400 `model_not_llm` |
| invalid stop | HTTP 400 `invalid_stop` |
| busy backend | HTTP 429 `llm_backend_busy` |
| runtime timeout | HTTP 504 `llm_timeout` |
| RKLLM runtime error | HTTP 502 `rkllm_runtime_error` |

---

## 5. Streaming 行为

### 5.1 one-shot mode

默认 one-shot mode：

```text
stream=false：支持
stream=true：拒绝
```

拒绝原因：

```text
one-shot runner 当前通过完整进程调用拿到最终输出；
不具备真实增量输出基础。
```

---

### 5.2 persistent worker mode

worker mode：

```text
stream=false：支持
stream=true：支持 SSE
```

SSE 基本格式：

```text
data: {"object":"chat.completion.chunk", ...}

data: [DONE]
```

当前 streaming 已覆盖：

```text
1. assistant role chunk；
2. content chunk；
3. final chunk finish_reason=stop；
4. final chunk usage；
5. data: [DONE]；
6. worker prefix 清理；
7. busy lease 生命周期保护。
```

---

## 6. Benchmark Snapshot

README 首页已加入 Benchmark Snapshot。

当前样例结果：

| Scenario | Metric | Sample result | Notes |
| --- | --- | ---: | --- |
| Non-streaming one-shot | client latency | ~21.3-21.7 s | repeat=1, `max_tokens=48` |
| Non-streaming warm worker | client latency | ~13.5 s | worker already started |
| Streaming warm worker | first content latency | ~4.52-5.23 s | repeat=3, `max_tokens=64` |
| Streaming warm worker | success | 6/6 OK | `finish_reason=stop`, `data: [DONE]` received |

核心解释：

```text
streaming 不会让总生成时间消失；
streaming 的主要价值是让客户端更早看到第一段 assistant content。
```

详细文档：

```text
docs/phase14c_benchmark_run_20260705.md
docs/phase16c_warm_streaming_benchmark_run_20260706.md
docs/phase16d_streaming_vs_nonstreaming_summary.md
docs/phase17a_readme_benchmark_snapshot.md
```

---

## 7. 自动化验证

当前已经具备以下 host-side 验证能力：

```text
scripts/host/deploy_serving_to_board.sh
scripts/host/smoke_test_serving.sh
scripts/host/validate_serving_modes.sh
scripts/host/test_openai_chat_client.py
scripts/host/check_openai_sdk_examples.py
scripts/host/benchmark_llm_serving.py
scripts/host/benchmark_llm_streaming.py
```

覆盖范围：

```text
1. 板端部署；
2. systemd 服务状态；
3. health / models / metrics；
4. chat completions；
5. OpenAI-like 参数兼容；
6. 错误响应；
7. busy rejection；
8. one-shot mode；
9. worker mode；
10. stream=true SSE；
11. OpenAI Python SDK examples；
12. non-streaming benchmark；
13. streaming benchmark。
```

---

## 8. 阶段标签

当前关键 tags：

| Tag | 说明 |
| --- | --- |
| `phase9-serving-worker-mvp` | Phase 9 serving framework with RKLLM worker mode, metrics, deploy and validation scripts |
| `phase9-openai-compat-mvp` | Phase 9 OpenAI chat compatibility MVP |
| `phase10-worker-streaming-mvp` | Phase 10 worker streaming chat completions MVP |
| `phase11-openai-sdk-examples` | Phase 11 OpenAI SDK examples |
| `phase12a-estimated-usage` | Phase 12A estimated chat completion usage |
| `phase12b-finish-reason-research` | Phase 12B finish_reason length research |
| `phase13-project-showcase-docs` | Phase 13 project showcase docs |
| `phase13b-project-summary` | Phase 13B project phase summary |
| `phase14-benchmark-summary` | Phase 14 benchmark summary |
| `phase14b-controlled-benchmark` | Phase 14B controlled LLM serving benchmark |
| `phase14c-benchmark-run-summary` | Phase 14C benchmark run summary |
| `phase15a-api-compat-matrix` | Phase 15A API compatibility matrix |
| `phase15b-error-response-reference` | Phase 15B error response reference |
| `phase15c-error-response-tests` | Phase 15C error response tests |
| `phase15d-chat-api-examples` | Phase 15D chat API examples |
| `phase15e-openai-sdk-compat-notes` | Phase 15E OpenAI SDK compatibility notes |
| `phase16a-streaming-benchmark` | Phase 16A streaming benchmark |
| `phase16b-streaming-benchmark-run` | Phase 16B streaming benchmark run |
| `phase16c-warm-streaming-benchmark-run` | Phase 16C warm streaming benchmark run |
| `phase16d-streaming-nonstreaming-summary` | Phase 16D streaming vs non-streaming summary |
| `phase17a-readme-benchmark-snapshot` | Phase 17A README benchmark snapshot |

---

## 9. 当前限制

当前仍保留以下限制：

```text
1. 当前默认推荐模型是 qwen3-4b-rkllm-all-npu；
2. finish_reason=length 暂未实现；
3. stream=true 仅 persistent worker mode 支持；
4. one-shot mode 下 stream=true 会返回 stream_backend_not_supported；
5. usage 是 estimated usage，不是 tokenizer 精确计数；
6. top_p、response_format=json_object、n>1 等高级 OpenAI 参数暂不支持；
7. 当前没有实现多模型并发调度；
8. LLM 并发策略是 reject_when_busy；
9. benchmark 是单板样例测量，结果会受 prompt、max_tokens、板端负载和 runtime 状态影响。
```

这些限制是当前工程阶段的显式边界，不建议在 v0.1.0 中隐藏。

---

## 10. v0.1.0 不包含的内容

v0.1.0 暂不包含：

```text
1. 多 LLM 并发推理；
2. 精确 tokenizer usage；
3. finish_reason=length；
4. JSON mode；
5. top_p / temperature 完整采样语义；
6. 多轮 history worker；
7. GPU / CUDA 路线；
8. YOLOv11 INT8 继续深挖；
9. 完整 Web UI；
10. 生产级鉴权和限流。
```

---

## 11. 推荐使用方式

### 11.1 默认 one-shot

适合：

```text
低频请求；
稳定兜底；
简单部署；
调试 API。
```

默认 one-shot 使用：

```bash
curl -s http://192.168.43.7:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-4b-rkllm-all-npu",
    "messages": [
      {"role": "user", "content": "请用一句话介绍 RK3588。"}
    ],
    "max_tokens": 64
  }' | python3 -m json.tool
```

---

### 11.2 worker mode

适合：

```text
交互式聊天；
需要更低 warm latency；
需要 stream=true SSE；
OpenAI SDK streaming。
```

启用 worker：

```bash
ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/enable_edgeinfer_worker_mode.sh"
```

恢复 one-shot：

```bash
ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/disable_edgeinfer_worker_mode.sh"
```

---

## 12. Release 前最终检查建议

在真正打 `v0.1.0` tag 前，建议执行 Phase 17C final checklist：

```text
1. git status --short 必须为空；
2. README 链接检查；
3. docs/README.md 链接检查；
4. py_compile / compileall；
5. host smoke test；
6. one-shot chat completion；
7. worker mode enable；
8. stream=true SSE；
9. worker mode disable；
10. /v1/metrics 检查；
11. OpenAI SDK non-streaming example；
12. tag 列表检查；
13. GitHub main 同步检查。
```

建议真正的 release tag：

```text
v0.1.0
```

但建议等 Phase 17C 完成后再创建。

---

## 13. 简历描述草案

可用于简历 / 项目介绍：

```text
实现了一套基于 RK3588 的端侧 AI 推理服务框架，完成 YOLOv11 RKNN 视觉模型板端验证与 Qwen3-4B RKLLM 端侧大模型 Serving。项目基于 FastAPI 设计 OpenAI-like Chat Completions API，支持 systemd 服务化部署、模型注册表、metrics、busy rejection、persistent worker、stream=true SSE 流式输出和 OpenAI Python SDK base_url 接入。实现 host 侧自动化部署、smoke test、错误响应测试、非流式与流式 benchmark，验证 Qwen3-4B 在 RK3588 上的 one-shot、warm worker 和 streaming first content latency 表现。
```

更短版本：

```text
基于 RK3588 构建端侧多模型推理服务框架，支持 YOLOv11 RKNN 与 Qwen3-4B RKLLM，提供 OpenAI-like Chat API、worker streaming SSE、metrics、busy rejection、systemd 部署、OpenAI SDK 接入与自动化 benchmark。
```

---

## 14. 后续路线

v0.1.0 之后可继续推进：

```text
1. v0.1.0 final checklist 和 release tag；
2. README 架构图 / Mermaid 图；
3. OpenAI SDK error handling example；
4. streaming first content repeat 更多样本；
5. 精确 tokenizer usage；
6. finish_reason=length；
7. 更规范的 model card；
8. Web demo；
9. 多模型统一调度；
10. 视觉模型和 LLM 的统一 benchmark dashboard。
```

---

## 15. 阶段结论

截至 Phase 17B，项目已经具备一个可展示、可复盘、可继续开发的 v0.1.0 候选状态：

```text
1. 端侧 Serving 主线闭环完成；
2. OpenAI-like API 能力边界清晰；
3. worker streaming 已验证；
4. benchmark 数据已整理；
5. README 首页已有性能快照；
6. docs 导航完整；
7. phase tags 连续；
8. 后续只需通过 final checklist 即可考虑创建 v0.1.0 release tag。
```
