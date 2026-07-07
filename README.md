# EdgeInfer-RK3588

基于 RK3588 NPU 的端侧多模型推理服务框架，面向端侧 AI Infra、模型部署优化、RKNN / RKLLM 推理服务化和工程化部署实践。

当前项目已经完成从视觉模型验证到端侧 LLM Serving 的主线闭环：YOLOv11 RKNN 板端验证、Qwen3-4B RKLLM 板端推理、OpenAI-like Chat Completions API、persistent worker 流式输出、busy rejection、metrics、systemd 部署和 host 侧自动化验收。

---

## 1. 项目定位

本项目不是单一模型 Demo，而是一个围绕 RK3588 构建的小型端侧推理服务框架，目标包括：

- 统一管理视觉检测、端侧 LLM、后续 VLM 等多类型模型；
- 统一封装 RKNN / RKLLM 多后端推理能力；
- 提供 OpenAI-like HTTP API，方便上层应用接入；
- 提供 host -> board 自动化部署、验证和回归脚本；
- 提供 metrics、busy rejection、worker mode 等服务稳定性能力；
- 沉淀完整阶段文档，便于复盘和继续扩展。

---

## 2. 当前能力概览

| 方向 | 当前状态 |
| --- | --- |
| YOLOv11 RKNN | 已完成板端验证与压缩路线取舍 |
| Qwen2.5 RKLLM | 已完成 0.5B / 1.5B 板端验证与对比 |
| Qwen3-4B RKLLM | 已完成 all-NPU / hybrid 板端验证，当前推荐 all-NPU |
| Serving API | 已实现 FastAPI 服务框架 |
| OpenAI-like Chat API | 已支持 `/v1/chat/completions` 基础兼容 |
| `max_tokens` | 已兼容 OpenAI 风格参数，并映射到 `max_new_tokens` |
| `stop` | 已支持 stop sequences |
| `stream=true` | persistent worker 模式已支持 SSE；one-shot 模式显式拒绝 |
| OpenAI Python SDK | 已提供 `base_url` 示例 |
| `usage` | 已返回 estimated usage，并明确标注估算方法 |
| `finish_reason=length` | 已完成语义调研，当前暂不实现不可靠的 length 判断 |
| 并发控制 | 单 LLM backend busy 时立即返回 429 |
| Metrics | 已暴露 LLM queue、backend、latency、busy、request counters |
| systemd 部署 | 已支持板端服务化部署 |
| 自动化验证 | 已支持 one-shot / worker 双模式验收 |

---

## 3. 架构概览

```text
Host Ubuntu
├── scripts/host/
│   ├── deploy_serving_to_board.sh
│   ├── smoke_test_serving.sh
│   ├── validate_serving_modes.sh
│   ├── test_openai_chat_client.py
│   └── check_openai_sdk_examples.py
│
└── rsync / ssh
    ↓

RK3588 Board
├── systemd: edgeinfer-serving.service
├── FastAPI server
│   ├── /v1/health
│   ├── /v1/models
│   ├── /v1/metrics
│   └── /v1/chat/completions
│
├── server/runtime/
│   ├── rkllm_backend.py
│   ├── rkllm_runner.py
│   └── rkllm_worker_backend.py
│
├── RKLLM one-shot runner
└── RKLLM persistent worker
    └── stream=true SSE
```

---

## 4. 推荐模型

当前 LLM 主推模型：

```text
qwen3-4b-rkllm-all-npu
```

模型状态在：

```text
configs/model_registry.yaml
```

推荐原因：

- 已完成 RK3588 板端验证；
- all-NPU 路线性能和工程稳定性更适合当前 Serving 主线；
- 已被 `/v1/chat/completions`、worker mode、streaming、SDK examples 覆盖验证。

---

## 5. Benchmark Snapshot

Current sample results for `qwen3-4b-rkllm-all-npu` on one RK3588 board:

| Scenario | Metric | Sample result | Notes |
| --- | --- | ---: | --- |
| Non-streaming one-shot | client latency | ~21.3-21.7 s | repeat=1, `max_tokens=48` |
| Non-streaming warm worker | client latency | ~13.5 s | worker already started |
| Streaming warm worker | first content latency | ~4.52-5.23 s | repeat=3, `max_tokens=64` |
| Streaming warm worker | success | 6/6 OK | `finish_reason=stop`, `data: [DONE]` received |

Key interpretation:

```text
Streaming does not make total generation time disappear.
Its main benefit is that the client can see the first assistant content much earlier.
```

Detailed benchmark notes:

```text
docs/phase14c_benchmark_run_20260705.md
docs/phase16c_warm_streaming_benchmark_run_20260706.md
docs/phase16d_streaming_vs_nonstreaming_summary.md
```

Benchmark values are sample measurements on one RK3588 board and may vary with prompt, `max_tokens`, runtime state and board load.

---

## 6. 快速开始

### 6.1 Host 侧进入仓库

```bash
cd ~/edgeinfer-rk3588
```

### 6.2 静态检查

```bash
python3 -m compileall -q server scripts/host tools

bash -n scripts/host/deploy_serving_to_board.sh
bash -n scripts/host/smoke_test_serving.sh
bash -n scripts/host/validate_serving_modes.sh

git diff --check
```

### 6.3 部署到 RK3588 板端并验收

推荐完整验收命令：

```bash
EDGEINFER_VALIDATE_DEPLOY=1 ./scripts/host/validate_serving_modes.sh
```

该命令会自动完成：

1. host 侧语法检查；
2. 同步 Serving 代码到板端；
3. 板端 compileall；
4. 重启 `edgeinfer-serving.service`；
5. 验证默认 one-shot 模式；
6. 启用并验证 persistent worker 模式；
7. 验证 `stream=true` SSE；
8. 验证 busy rejection、metrics、OpenAI-like 参数兼容；
9. 最后恢复默认 one-shot 模式。

---

## 7. 板端服务

默认服务名：

```text
edgeinfer-serving.service
```

常用检查：

```bash
ssh linaro@192.168.43.7 "systemctl status edgeinfer-serving.service --no-pager"
ssh linaro@192.168.43.7 "curl -s http://127.0.0.1:8000/v1/health | python3 -m json.tool"
```

默认 host 侧访问地址：

```text
http://192.168.43.7:8000
```

---

## 8. API 示例

### 8.1 Health

```bash
curl -s http://192.168.43.7:8000/v1/health | python3 -m json.tool
```

### 8.2 Models

```bash
curl -s http://192.168.43.7:8000/v1/models | python3 -m json.tool
```

### 8.3 Metrics

```bash
curl -s http://192.168.43.7:8000/v1/metrics | python3 -m json.tool
```

### 8.4 Chat Completions

```bash
curl -s http://192.168.43.7:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-4b-rkllm-all-npu",
    "messages": [
      {
        "role": "user",
        "content": "请用一句话介绍 RK3588。"
      }
    ],
    "max_tokens": 64
  }' | python3 -m json.tool
```

---

## 9. OpenAI Python SDK 示例

安装依赖：

```bash
python3 -m pip install openai
```

普通非流式示例：

```bash
python3 examples/openai_sdk_chat_completion.py
```

worker stream 示例：

```bash
ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/enable_edgeinfer_worker_mode.sh"

EDGEINFER_EXPECT_STREAM=1 \
python3 scripts/host/check_openai_sdk_examples.py

ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/disable_edgeinfer_worker_mode.sh"
```

---

## 10. 目录说明

| 路径 | 说明 |
| --- | --- |
| `server/` | FastAPI Serving 与 RKLLM runtime 封装 |
| `scripts/host/` | Host 侧部署、验收、OpenAI-like client 测试 |
| `scripts/board/` | RK3588 板端服务安装、worker mode 切换和探测脚本 |
| `tools/` | 模型资产检查、Benchmark、YOLO 工具 |
| `configs/` | 模型注册表与配置 |
| `docs/` | 阶段文档与验证记录 |
| `examples/` | OpenAI Python SDK 示例 |
| `envs/` | Python 环境依赖记录 |
| `models/` | 模型目录占位与本地模型组织 |
| `results/` | Benchmark 与验证结果输出 |

---

## 11. 文档导航

推荐从这里开始：

```text
docs/README.md
```

关键文档：

- Phase 9 Serving 运维与验证：`docs/phase9_serving_operations.md`
- Phase 9 OpenAI-like API：`docs/phase9_openai_compat.md`
- Phase 10 stream=true SSE：`docs/phase10_streaming_sse.md`
- Phase 11 OpenAI Python SDK 示例：`docs/phase11_openai_sdk_examples.md`
- Phase 12A estimated usage：`docs/phase12_estimated_usage.md`
- Phase 12B finish_reason=length 语义调研：`docs/phase12b_finish_reason_length_research.md`
- Phase 13 项目工程化整理与对外展示：`docs/phase13_project_showcase.md`
- Phase 13B 项目阶段总结：`docs/phase13b_project_summary.md`
- Phase 14 Benchmark 与性能展示总表：`docs/phase14_benchmark_summary.md`
- Phase 14B controlled LLM Serving Benchmark：`docs/phase14b_controlled_benchmark.md`
- Phase 14C Benchmark run 2026-07-05 摘要：`docs/phase14c_benchmark_run_20260705.md`
- Phase 15A OpenAI-compatible API 兼容性矩阵：`docs/phase15_api_compatibility_matrix.md`
- Phase 15B Error Response Reference：`docs/phase15b_error_response_reference.md`
- Phase 15C Error Response Test Coverage：`docs/phase15c_error_response_tests.md`
- Phase 15D Chat API Request / Response Examples：`docs/phase15d_chat_api_examples.md`
- Phase 15E OpenAI Python SDK Compatibility Notes：`docs/phase15e_openai_sdk_compatibility_notes.md`
- Phase 16A Streaming Benchmark / First Content Latency：`docs/phase16a_streaming_benchmark.md`
- Phase 16B Streaming Benchmark Run 2026-07-06：`docs/phase16b_streaming_benchmark_run_20260706.md`
- Phase 16C Warm Worker Streaming Benchmark Run 2026-07-06：`docs/phase16c_warm_streaming_benchmark_run_20260706.md`
- Phase 16D Streaming vs Non-streaming Performance Summary：`docs/phase16d_streaming_vs_nonstreaming_summary.md`
- Phase 17A README Benchmark Snapshot：`docs/phase17a_readme_benchmark_snapshot.md`
- Phase 17B v0.1.0 Release Notes / Final Milestone Summary：`docs/phase17b_v0_1_0_release_notes.md`
- Phase 17C v0.1.0 Final Checklist：`docs/phase17c_v0_1_0_final_checklist.md`
- Phase 18 Realign With Original Multi-Model Design：`docs/phase18_realign_with_original_design.md`
- Phase 18B Vision API Skeleton：`docs/phase18b_vision_api_skeleton.md`
- Phase 18C Vision Image Input / Preprocess Skeleton：`docs/phase18c_vision_image_input_skeleton.md`
- Phase 18D RKNN YOLO Backend Dry Integration：`docs/phase18d_rknn_yolo_backend_dryrun.md`
- Phase 18E RKNN YOLO Inference Probe：`docs/phase18e_rknn_yolo_inference_probe.md`
- Phase 18F YOLO Postprocess Integration：`docs/phase18f_yolo_postprocess_integration.md`
- Phase 18G Vision Detect Output Refinement：`docs/phase18g_vision_detect_output_refinement.md`
- Phase 18H Vision Worker Stabilization：`docs/phase18h_vision_worker_stabilization.md`
- Phase 18I Vision Queue Busy Rejection：`docs/phase18i_vision_queue_busy_rejection.md`
- Phase 18J Vision Default Model and Metadata Cleanup：`docs/phase18j_vision_default_model_metadata_cleanup.md`
- Phase 18K Vision Serving Polish：`docs/phase18k_vision_serving_polish.md`

---

## 12. 当前限制

当前项目仍有一些有意保留的限制：

1. `usage` 是 estimated usage，不是 tokenizer 精确统计；
2. `finish_reason=length` 暂未实现，因为 RKLLM runtime / worker 未暴露可靠 stop reason；
3. `stream=true` 仅 persistent worker 模式支持；
4. one-shot 模式下 `stream=true` 会返回 `stream_backend_not_supported`；
5. `n > 1` 暂不支持；
6. `top_p != 1.0` 暂不支持；
7. `response_format={"type":"json_object"}` 暂不支持；
8. `temperature` 当前主要作为 API 兼容字段，尚未完整下传到底层 runtime；
9. 暂不支持 tool calls / function calling；
10. VLM 仍是后续扩展方向。

---

## 13. 已完成阶段标签

| Tag | 说明 |
| --- | --- |
| `phase9-openai-compat-mvp` | OpenAI-like Chat API MVP |
| `phase10-worker-streaming-mvp` | worker stream=true SSE MVP |
| `phase11-openai-sdk-examples` | OpenAI Python SDK 示例 |
| `phase12a-estimated-usage` | estimated usage token 统计 |
| `phase12b-finish-reason-research` | finish_reason=length 语义调研 |

## Vision Serving 快速示例

默认 vision detect 请求不需要显式传 `model`。Phase 18J 后默认使用 `YOLOv11n-FP-Baseline`：

```bash
curl -s http://192.168.43.7:8000/v1/vision/detect \
  -H "Content-Type: application/json" \
  -d '{
    "image_path": "/home/linaro/edgeinfer-rk3588-board/datasets/coco128/images/train2017/000000000089.jpg"
  }' | python3 -m json.tool
```

显式指定模型：

```bash
curl -s http://192.168.43.7:8000/v1/vision/detect \
  -H "Content-Type: application/json" \
  -d '{
    "model": "YOLOv11n-FP-Baseline",
    "image_path": "/home/linaro/edgeinfer-rk3588-board/datasets/coco128/images/train2017/000000000089.jpg",
    "confidence_threshold": 0.25,
    "iou_threshold": 0.45
  }' | python3 -m json.tool
```

运行 host demo：

```bash
bash scripts/host/demo_vision_detect.sh
```

并发 busy rejection 测试：

```bash
python3 scripts/host/test_vision_busy_rejection.py
```

典型输出语义：

```text
objects[].bbox       原图坐标系中的 xyxy 检测框
objects[].bbox_input 模型输入 640x640 坐标系中的 xyxy 检测框
latency_ms.backend_init 首次 worker 启动耗时，worker 复用时为 0.0
edgeinfer.vision.queue.queue_policy = reject_when_busy
```


---

## 14. 项目当前状态

当前主线已经完成：

```text
端侧 LLM Serving MVP
OpenAI-like Chat API
Worker SSE streaming
Estimated usage
Host/Board 自动化部署与验收
工程化文档沉淀
```

下一步建议进入：

```text
Phase 13：项目工程化整理与对外展示
```
