# EdgeInfer-RK3588 文档导航

本文档用于快速定位 `edgeinfer-rk3588` 项目的阶段文档、验证记录和运维说明。

---

## 推荐阅读顺序

如果是第一次阅读本项目，建议按下面顺序：

1. `README.md`
2. `docs/phase9_serving_operations.md`
3. `docs/phase9_openai_compat.md`
4. `docs/phase10_streaming_sse.md`
5. `docs/phase11_openai_sdk_examples.md`
6. `docs/phase12_estimated_usage.md`
7. `docs/phase12b_finish_reason_length_research.md`

---

## Serving / OpenAI-like API 主线

| 文档 | 说明 |
| --- | --- |
| `phase9_serving_operations.md` | Serving 部署、systemd、host 侧验收与运维 |
| `phase9_openai_compat.md` | OpenAI-like Chat Completions 兼容说明 |
| `phase9_openai_compat_mvp_summary.md` | Phase 9 OpenAI compatibility 阶段总结 |
| `phase10_streaming_sse.md` | `stream=true` SSE 流式输出设计与验证 |
| `phase11_openai_sdk_examples.md` | OpenAI Python SDK `base_url` 示例 |
| `phase12_estimated_usage.md` | estimated usage token 统计 |
| `phase12b_finish_reason_length_research.md` | `finish_reason=length` 暂不实现的语义调研 |

---

## RKLLM / Qwen 主线

| 文档 | 说明 |
| --- | --- |
| `phase6_qwen25_0_5b_rkllm_board_validation.md` | Qwen2.5-0.5B RKLLM 板端验证 |
| `phase6_qwen25_1_5b_rkllm_board_validation.md` | Qwen2.5-1.5B RKLLM 板端验证 |
| `phase6_qwen25_rkllm_model_comparison.md` | Qwen2.5 RKLLM 模型对比 |
| `phase7_qwen3_4b_rkllm_blocked_by_driver.md` | Qwen3-4B 早期驱动阻塞记录 |
| `phase7_rknpu098_kernel_rebuild_and_qwen3_status.md` | RKNPU 0.9.8 / kernel rebuild 与 Qwen3 状态 |
| `phase8_qwen3_4b_all_npu_hybrid_rkllm_board_validation.md` | Qwen3-4B all-NPU / hybrid 板端验证 |
| `phase9_qwen3_real_backend_validation.md` | Qwen3 real backend Serving 验证 |
| `phase9_prompt_policy_validation.md` | prompt policy 与 RK3588 稳定回答验证 |
| `phase9_rkllm_worker_mode_validation.md` | RKLLM persistent worker mode 验证 |

---

## YOLOv11 / RKNN 主线

| 文档 | 说明 |
| --- | --- |
| `phase3_yolo11_assets.md` | YOLOv11 模型资产整理 |
| `phase3_yolo11_benchmark.md` | YOLOv11 Benchmark |
| `phase3_yolo11_benchmark_postprocess.md` | YOLOv11 Benchmark 后处理记录 |
| `phase3_yolo11_postprocess.md` | YOLOv11 后处理实现记录 |
| `phase5_yolo11_compression_decision.md` | YOLOv11 压缩路线决策 |
| `phase5_yolo11_compression_v2.md` | YOLOv11 压缩 v2 |
| `phase5_yolo11_compression_v2_pipeline.md` | YOLOv11 压缩 pipeline |
| `phase5_yolo11_rknn_board_validation.md` | YOLOv11 RKNN 板端验证 |

---

## Serving 验证记录

| 文档 | 说明 |
| --- | --- |
| `phase9_serving_framework_mvp_initial_validation.md` | Serving Framework MVP 初始验证 |
| `phase9_systemd_serving_validation.md` | systemd 服务化验证 |
| `phase9_host_smoke_test_validation.md` | host smoke test 验证 |
| `phase9_busy_metrics_validation.md` | busy rejection 与 metrics 验证 |

---

## 项目规划

| 文档 | 说明 |
| --- | --- |
| `phase1_plan.md` | 初始阶段计划 |
| `phase2_model_manager.md` | 模型管理设计 |
| `phase4_board_deploy_package.md` | 板端部署包设计 |

---

## 当前主线状态

当前推荐主线是：

```text
Qwen3-4B RKLLM all-NPU
+
FastAPI Serving
+
OpenAI-like Chat Completions
+
optional persistent worker stream=true SSE
+
estimated usage
+
host/board automated validation
```

当前推荐完整验收命令：

```bash
EDGEINFER_VALIDATE_DEPLOY=1 \
./scripts/host/validate_serving_modes.sh
```

## Phase 13B 项目总结

| `phase14_benchmark_summary.md` | Benchmark 与性能展示总表 |
| `phase14b_controlled_benchmark.md` | Controlled LLM Serving Benchmark 脚本与执行说明 |
| `phase14c_benchmark_run_20260705.md` | 2026-07-05 one-shot / worker benchmark 结果摘要 |
| `phase15_api_compatibility_matrix.md` | OpenAI-compatible API 支持矩阵、错误码与后续扩展方向 |
| `phase15b_error_response_reference.md` | OpenAI-like API 错误响应结构、错误码与客户端处理建议 |
| `phase15c_error_response_tests.md` | 错误响应 host-side 测试覆盖增强 |
| `phase15d_chat_api_examples.md` | Chat API 请求、成功响应与错误响应示例 |
| `phase15e_openai_sdk_compatibility_notes.md` | OpenAI Python SDK base_url 接入、streaming 条件与兼容差异说明 |
| `phase16a_streaming_benchmark.md` | Streaming SSE benchmark 工具、首 content 延迟指标与执行说明 |
| `phase16b_streaming_benchmark_run_20260706.md` | 2026-07-06 streaming benchmark 实测结果摘要 |
| `phase16c_warm_streaming_benchmark_run_20260706.md` | 2026-07-06 warm worker streaming benchmark repeat=3 结果摘要 |
| `phase16d_streaming_vs_nonstreaming_summary.md` | 非流式与流式 benchmark 横向对比、README 展示建议 |

| `phase13b_project_summary.md` | 项目阶段总结、交接、简历描述与后续路线图 |
