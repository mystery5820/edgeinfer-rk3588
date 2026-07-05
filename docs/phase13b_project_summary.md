# Phase 13B：EdgeInfer-RK3588 项目阶段总结

本文档是 `edgeinfer-rk3588` 项目从初始模型验证到 OpenAI-like LLM Serving 主线收口后的阶段性总结，便于后续复盘、交接、答辩、简历项目描述和继续开发。

---

## 1. 项目概述

`edgeinfer-rk3588` 是一个基于 RK3588 NPU 的端侧多模型推理服务框架。项目围绕端侧 AI Infra、模型部署优化、推理服务化和工程化验证展开，目标不是停留在单个模型 Demo，而是构建一个可部署、可验证、可扩展的小型端侧推理系统。

当前项目已完成以下主线闭环：

```text
YOLOv11 RKNN 板端验证
Qwen2.5 / Qwen3 RKLLM 板端验证
Qwen3-4B RKLLM all-NPU 推荐模型确立
FastAPI Serving Framework
OpenAI-like Chat Completions API
RKLLM one-shot / persistent worker 双模式
stream=true SSE 流式输出
OpenAI Python SDK base_url 示例
estimated usage token 统计
finish_reason=length 语义调研
busy rejection 与 metrics
systemd 工程化部署
host -> board 自动化验收
README 与 docs 对外展示整理
```

---

## 2. 项目定位

本项目面向以下方向：

```text
1. 端侧 AI Infra；
2. RK3588 NPU 模型部署；
3. RKNN / RKLLM 推理后端封装；
4. 多模型推理服务框架；
5. OpenAI-like API 兼容；
6. 边缘设备 systemd 服务化部署；
7. 自动化 Benchmark 与回归验证；
8. 项目工程化与长期维护。
```

项目核心价值在于：将 RK3588 上分散的模型验证、脚本测试、手工部署过程，逐步收敛为统一的 Serving 框架和自动化验证体系。

---

## 3. 技术栈

### 3.1 硬件平台

```text
RK3588 开发板
RKNPU
板端 Linux 环境
```

### 3.2 推理后端

```text
RKNN：视觉模型推理
RKLLM：端侧大语言模型推理
```

### 3.3 服务框架

```text
FastAPI
Uvicorn
systemd
HTTP JSON API
SSE streaming
```

### 3.4 工程工具

```text
Python
Bash
ssh / rsync
git / GitHub
host-side validation scripts
board-side service scripts
```

---

## 4. 阶段推进概览

### Phase 1：项目规划

早期阶段完成项目总体方向设计，确定以 RK3588 NPU 为核心，逐步覆盖视觉检测、端侧 LLM、VLM、多模型管理、Benchmark 和 Serving 部署。

对应文档：

```text
docs/phase1_plan.md
```

---

### Phase 2：模型管理

完成模型管理思路设计，逐步形成 `configs/model_registry.yaml` 作为模型注册表，用于统一记录模型 ID、任务类型、backend、状态、推荐模型、运行时要求和验证结果。

对应文档：

```text
docs/phase2_model_manager.md
```

---

### Phase 3：YOLOv11 RKNN 资产与 Benchmark

完成 YOLOv11 模型资产整理、Benchmark 流程、后处理逻辑分析和初步验证。

主要成果：

```text
1. 整理 YOLOv11 模型资产；
2. 建立 Benchmark 脚本；
3. 分析 RKNN 输出与后处理；
4. 为后续板端验证打基础。
```

对应文档：

```text
docs/phase3_yolo11_assets.md
docs/phase3_yolo11_benchmark.md
docs/phase3_yolo11_benchmark_postprocess.md
docs/phase3_yolo11_postprocess.md
```

---

### Phase 4：板端部署包

围绕 host 到 RK3588 board 的部署流程，整理板端部署包设计，为后续 Serving systemd 部署和 host 侧自动化脚本奠定基础。

对应文档：

```text
docs/phase4_board_deploy_package.md
```

---

### Phase 5：YOLOv11 压缩与板端验证

完成 YOLOv11 RKNN 板端验证，并对压缩路线进行阶段性取舍。

主要结论：

```text
1. YOLOv11 相关工作已形成阶段性闭环；
2. INT8 路线当前继续深挖的收益有限；
3. 项目主线转向端侧 LLM Serving；
4. YOLO 工作作为视觉模型方向的基础沉淀保留。
```

对应文档：

```text
docs/phase5_yolo11_compression_decision.md
docs/phase5_yolo11_compression_v2.md
docs/phase5_yolo11_compression_v2_pipeline.md
docs/phase5_yolo11_rknn_board_validation.md
```

---

### Phase 6：Qwen2.5 RKLLM 板端验证

完成 Qwen2.5-0.5B 与 Qwen2.5-1.5B RKLLM 模型在 RK3588 上的板端验证，并进行模型对比。

主要成果：

```text
1. 验证 RKLLM 运行链路；
2. 对比 Qwen2.5 不同规模模型；
3. 为后续 Qwen3-4B 模型验证积累经验；
4. 建立 LLM 板端验证记录方式。
```

对应文档：

```text
docs/phase6_qwen25_0_5b_rkllm_board_validation.md
docs/phase6_qwen25_1_5b_rkllm_board_validation.md
docs/phase6_qwen25_rkllm_model_comparison.md
```

---

### Phase 7：Qwen3-4B 与 RKNPU 驱动问题

早期 Qwen3-4B RKLLM 验证受到 RKNPU driver / kernel 环境限制。随后通过 RKNPU 0.9.8 与 kernel rebuild 等工作推进，解除阻塞。

主要成果：

```text
1. 记录 Qwen3-4B 初期 blocked 状态；
2. 定位问题与 RKNPU driver / kernel 相关；
3. 推进 RKNPU 0.9.8 环境建设；
4. 为 Phase 8 Qwen3-4B 正式验证打基础。
```

对应文档：

```text
docs/phase7_qwen3_4b_rkllm_blocked_by_driver.md
docs/phase7_rknpu098_kernel_rebuild_and_qwen3_status.md
```

---

### Phase 8：Qwen3-4B all-NPU / hybrid 验证

完成 Qwen3-4B RKLLM all-NPU 与 hybrid 路线的板端验证，并最终将 all-NPU 作为当前推荐模型路线。

主要成果：

```text
1. Qwen3-4B all-NPU 路线跑通；
2. Qwen3-4B hybrid 路线完成对比；
3. 记录 init_ms、prefill_tps、generate_tps、peak_memory 等指标；
4. 在 model_registry 中标记推荐模型；
5. 为 Serving API 接入真实 Qwen3-4B 后端打基础。
```

当前推荐模型：

```text
qwen3-4b-rkllm-all-npu
```

对应文档：

```text
docs/phase8_qwen3_4b_all_npu_hybrid_rkllm_board_validation.md
```

---

## 5. Phase 9：Serving Framework 与 OpenAI-like API 主线

Phase 9 是项目从“模型验证”转向“服务框架”的关键阶段。

### 5.1 Serving Framework MVP

完成 FastAPI Serving 框架，提供基础接口：

```text
/v1/health
/v1/models
/v1/metrics
/v1/chat/completions
```

并将 Qwen3-4B RKLLM 后端纳入服务接口。

对应文档：

```text
docs/phase9_serving_framework_mvp_initial_validation.md
docs/phase9_qwen3_real_backend_validation.md
```

---

### 5.2 systemd 服务化

完成板端 systemd 服务部署：

```text
edgeinfer-serving.service
```

主要能力：

```text
1. 板端开机服务化；
2. 统一启动 FastAPI / Uvicorn；
3. 禁用旧 qwen-web-chat / yolov5-web demo 服务；
4. 通过 systemctl 查看状态；
5. host 侧脚本自动重启与健康检查。
```

对应文档：

```text
docs/phase9_systemd_serving_validation.md
docs/phase9_serving_operations.md
```

---

### 5.3 host smoke test 与双模式验证

建立 host 侧验证脚本：

```text
scripts/host/deploy_serving_to_board.sh
scripts/host/smoke_test_serving.sh
scripts/host/validate_serving_modes.sh
```

其中 `validate_serving_modes.sh` 可完成：

```text
1. host 本地语法检查；
2. rsync 同步到板端；
3. board compileall；
4. 重启服务；
5. 验证 one-shot 模式；
6. 验证 worker 模式；
7. 验证完成后恢复默认 one-shot。
```

对应文档：

```text
docs/phase9_host_smoke_test_validation.md
docs/phase9_serving_operations.md
```

---

### 5.4 busy rejection 与 metrics

LLM backend 当前为单并发资源。Phase 9 引入 `reject_when_busy` 策略：

```text
1. 第一个请求被接受；
2. 第二个并发请求立即返回 429；
3. 错误码为 llm_backend_busy；
4. retryable=true；
5. metrics 中记录 total_requests / accepted_requests / rejected_busy 等字段。
```

对应文档：

```text
docs/phase9_busy_metrics_validation.md
```

---

### 5.5 OpenAI-like Chat Completions MVP

Phase 9 完成 OpenAI-like API 基础兼容：

```text
1. 支持 /v1/chat/completions；
2. 支持 messages；
3. 支持 max_tokens alias；
4. 保留 max_new_tokens；
5. 支持 stop sequences；
6. n > 1 显式拒绝；
7. top_p != 1.0 显式拒绝；
8. response_format json_object 显式拒绝；
9. 输出 choices[].message.content；
10. 输出 choices[].finish_reason；
11. 输出 edgeinfer metadata。
```

对应 tag：

```text
phase9-openai-compat-mvp
```

对应文档：

```text
docs/phase9_openai_compat.md
docs/phase9_openai_compat_mvp_summary.md
```

---

## 6. Phase 10：worker stream=true SSE

Phase 10 完成 persistent worker 模式下的 SSE 流式输出。

### 6.1 设计目标

```text
1. stream=true 时返回 text/event-stream；
2. 首 chunk 输出 delta.role=assistant；
3. 中间 chunk 输出 delta.content；
4. final chunk 输出 finish_reason=stop；
5. 最后输出 data: [DONE]；
6. one-shot 模式下 stream=true 显式拒绝。
```

### 6.2 关键实现

```text
server/runtime/rkllm_worker_backend.py
server/runtime/rkllm_backend.py
server/api/chat_api.py
server/scheduler/request_queue.py
```

重点改动：

```text
1. 新增 persistent worker generate_stream；
2. 使用 select + os.read 增量读取 stdout；
3. 使用 UTF-8 incremental decoder 处理中文多字节拆包；
4. 识别 <|im_end|> / You: 等结束标记；
5. 修复 LLM: 前缀在流式分片中泄漏；
6. 使用 LLMRequestLease 覆盖整个 StreamingResponse 生命周期，避免并发混流。
```

对应 tag：

```text
phase10-worker-streaming-mvp
```

对应文档：

```text
docs/phase10_streaming_sse.md
```

---

## 7. Phase 11：OpenAI Python SDK 示例

Phase 11 增加官方 OpenAI Python SDK 的 `base_url` 示例，使项目更接近标准 OpenAI-compatible server 使用方式。

新增示例：

```text
examples/openai_sdk_chat_completion.py
examples/openai_sdk_streaming_chat.py
scripts/host/check_openai_sdk_examples.py
```

验证内容：

```text
1. one-shot 模式下 stream=false SDK 示例通过；
2. one-shot 模式下 stream=true 默认跳过或显式拒绝；
3. worker 模式下 stream=true SDK 示例通过；
4. 输出 finish_reason=stop；
5. 服务恢复默认 one-shot。
```

对应 tag：

```text
phase11-openai-sdk-examples
```

对应文档：

```text
docs/phase11_openai_sdk_examples.md
```

---

## 8. Phase 12A：estimated usage token 统计

Phase 12A 完成 Chat Completions 的 estimated usage 字段。

### 8.1 实现内容

非流式响应：

```json
{
  "usage": {
    "prompt_tokens": 67,
    "completion_tokens": 42,
    "total_tokens": 109
  },
  "edgeinfer": {
    "usage": {
      "estimated": true,
      "method": "simple_mixed_text_heuristic_v1"
    }
  }
}
```

worker stream final chunk 也携带 usage。

### 8.2 设计原则

```text
1. 不接入真实 tokenizer；
2. 不假装返回精确 token；
3. 明确 edgeinfer.usage.estimated=true；
4. 明确 method=simple_mixed_text_heuristic_v1；
5. usage 不用于计费、不用于严格 quota；
6. 不用 estimated usage 判断 finish_reason=length。
```

对应 tag：

```text
phase12a-estimated-usage
```

对应文档：

```text
docs/phase12_estimated_usage.md
```

---

## 9. Phase 12B：finish_reason=length 语义调研

Phase 12B 对 `finish_reason=length` 进行调研，并决定当前不实现。

### 9.1 调研结论

当前不能可靠判断 length，原因包括：

```text
1. one-shot runner 只返回清洗后的文本和 latency；
2. persistent worker 非流式只知道是否读到 end marker；
3. persistent worker stream 只知道是否读到 <|im_end|> / You:；
4. RKLLM runtime 未暴露 stop_reason；
5. 未暴露 generated_tokens；
6. Phase 12A usage 是估算值，不能用于判断 length；
7. worker 实际 max_new_tokens 可能大于请求 max_tokens。
```

### 9.2 当前策略

继续保守返回：

```json
{
  "finish_reason": "stop"
}
```

后续只有当 RKLLM runtime / worker wrapper 暴露可靠 stop reason 后，再实现：

```text
finish_reason=length
```

对应 tag：

```text
phase12b-finish-reason-research
```

对应文档：

```text
docs/phase12b_finish_reason_length_research.md
```

---

## 10. Phase 13：项目展示层整理

Phase 13 对 README 和 docs 导航进行整理，使项目更适合对外展示。

完成内容：

```text
1. 重写 README；
2. 增加项目定位；
3. 增加能力矩阵；
4. 增加架构概览；
5. 增加 Quick Start；
6. 增加 API 示例；
7. 增加 OpenAI SDK 示例入口；
8. 增加 docs/README.md；
9. 增加当前限制；
10. 增加 tag 列表。
```

对应 tag：

```text
phase13-project-showcase-docs
```

对应文档：

```text
README.md
docs/README.md
docs/phase13_project_showcase.md
```

---

## 11. 当前系统能力

当前系统已经具备：

```text
1. 板端 FastAPI 推理服务；
2. 模型注册表；
3. Qwen3-4B RKLLM all-NPU 推理；
4. one-shot 后端；
5. persistent worker 后端；
6. OpenAI-like Chat Completions；
7. SSE streaming；
8. SDK examples；
9. usage estimated metadata；
10. stop sequence；
11. max_tokens alias；
12. busy rejection；
13. metrics；
14. systemd 部署；
15. host/board 自动化验收。
```

---

## 12. 当前限制

当前仍有以下限制：

```text
1. usage 是 estimated，不是 tokenizer 精确 token；
2. finish_reason=length 暂不实现；
3. stream=true 仅 worker 模式支持；
4. one-shot stream=true 显式拒绝；
5. n > 1 暂不支持；
6. top_p != 1.0 暂不支持；
7. response_format json_object 暂不支持；
8. temperature 暂未完整下传到底层 runtime；
9. 暂不支持 tool calls / function calling；
10. VLM 仍是后续方向；
11. 当前 LLM backend 仍按单并发资源处理。
```

这些限制都已显式记录，避免对外展示时夸大兼容能力。

---

## 13. 当前推荐验证命令

完整验收：

```bash
EDGEINFER_VALIDATE_DEPLOY=1 \
./scripts/host/validate_serving_modes.sh
```

OpenAI-like client 验证：

```bash
./scripts/host/test_openai_chat_client.py
```

OpenAI SDK 示例验证：

```bash
python3 scripts/host/check_openai_sdk_examples.py
```

worker stream SDK 示例：

```bash
ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/enable_edgeinfer_worker_mode.sh"

EDGEINFER_EXPECT_STREAM=1 \
python3 scripts/host/check_openai_sdk_examples.py

ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/disable_edgeinfer_worker_mode.sh"
```

---

## 14. Git tags

当前关键 tags：

```text
phase9-serving-worker-mvp
phase9-openai-compat-mvp
phase10-worker-streaming-mvp
phase11-openai-sdk-examples
phase12a-estimated-usage
phase12b-finish-reason-research
phase13-project-showcase-docs
```

---

## 15. 可用于简历的项目描述

### 15.1 简短版

基于 RK3588 NPU 设计并实现端侧多模型推理服务框架，完成 YOLOv11 RKNN 与 Qwen3-4B RKLLM 板端验证，构建 FastAPI Serving 服务，支持 OpenAI-like Chat Completions、SSE 流式输出、OpenAI Python SDK 接入、metrics、busy rejection、systemd 部署和 host/board 自动化验收。

### 15.2 详细版

设计并实现基于 RK3588 NPU 的端侧多模型推理服务框架，覆盖视觉检测与端侧大语言模型推理。项目完成 YOLOv11 RKNN 板端验证、Qwen2.5 / Qwen3 RKLLM 模型对比与 Qwen3-4B all-NPU Serving 接入；基于 FastAPI 构建 OpenAI-like Chat Completions API，支持 `max_tokens`、`stop`、estimated `usage`、persistent worker `stream=true` SSE、OpenAI Python SDK `base_url` 示例；实现单 LLM 后端 busy rejection、metrics、systemd 服务化部署，以及 host 到 RK3588 board 的自动化部署与双模式验收脚本。项目沉淀完整阶段文档和 Git tags，具备较好的工程复现性和可维护性。

### 15.3 技术关键词

```text
RK3588
RKNPU
RKNN
RKLLM
Qwen3-4B
YOLOv11
FastAPI
OpenAI-compatible API
SSE streaming
systemd
Edge AI
Model Serving
LLM inference
Automation validation
```

---

## 16. 后续路线图

建议后续按以下方向推进：

### 16.1 Phase 14：Benchmark 总表与性能展示

```text
1. 汇总 YOLOv11 RKNN 指标；
2. 汇总 Qwen2.5 / Qwen3 RKLLM 指标；
3. 汇总 one-shot / worker latency；
4. 形成 README 性能表；
5. 生成 benchmark summary 文档。
```

### 16.2 Phase 15：API polish

```text
1. 更系统的错误码文档；
2. 更完整的 OpenAI-compatible response examples；
3. client SDK 示例增强；
4. stream final chunk 语义说明；
5. 兼容性矩阵。
```

### 16.3 Phase 16：VLM 或视觉服务接入

```text
1. 将视觉模型纳入统一 Serving API；
2. 增加 object detection endpoint；
3. 后续扩展 VLM 图文问答。
```

### 16.4 Phase 17：真实 tokenizer 与 stop reason

```text
1. 引入 tokenizer 做更准确 usage；
2. 改造 RKLLM worker wrapper；
3. 暴露 stop_reason；
4. 实现可靠 finish_reason=length。
```

---

## 17. 阶段结论

截至 Phase 13B，`edgeinfer-rk3588` 已经从模型验证项目演进为一个具备工程闭环的端侧 LLM Serving 项目。

当前最核心的成果是：

```text
Qwen3-4B RKLLM all-NPU
+
FastAPI Serving
+
OpenAI-like Chat Completions
+
persistent worker stream=true SSE
+
estimated usage
+
busy rejection / metrics
+
systemd deployment
+
host/board automated validation
+
complete docs and tags
```

这已经是一个可以用于项目展示、后续扩展和工程复盘的稳定阶段成果。
