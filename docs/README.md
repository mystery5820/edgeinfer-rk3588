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
| `phase17a_readme_benchmark_snapshot.md` | README 首页 benchmark snapshot 展示口径与数据来源 |
| `phase17b_v0_1_0_release_notes.md` | v0.1.0 release notes 草案、最终里程碑总结与后续路线 |
| `phase17c_v0_1_0_final_checklist.md` | v0.1.0 final checklist 验收结果与正式 tag 前检查记录 |
| `phase18_realign_with_original_design.md` | 将当前 LLM Serving milestone 重新对齐到原始多模型推理服务框架总设计 |
| `phase18b_vision_api_skeleton.md` | `/v1/vision/detect` API skeleton、fake vision backend 与 host-side 测试 |
| `phase18c_vision_image_input_skeleton.md` | `/v1/vision/detect` 真实 image_path 校验、图片 metadata 与 preprocess skeleton |
| `phase18d_rknn_yolo_backend_dryrun.md` | RKNN YOLO backend dryrun、rknnlite subprocess probe 与 vision backend 模式切换 |
| `phase18e_rknn_yolo_inference_probe.md` | RKNN YOLO inference probe、NHWC batch tensor、output_shapes 与 inference_ms |
| `phase18f_yolo_postprocess_integration.md` | RKNN YOLO detect probe、postprocess_yolo_outputs 与真实 objects 输出 |
| `phase18g_vision_detect_output_refinement.md` | COCO class names、original-image bbox、bbox_input 与 coordinate_space 输出精修 |
| `phase18h_vision_worker_stabilization.md` | persistent RKNN YOLO worker、rknn-yolo-worker backend 与重复初始化开销消除 |
| `phase18i_vision_queue_busy_rejection.md` | VisionRequestQueue、reject_when_busy、429 vision_backend_busy 与 queue metrics |
| `phase18j_vision_default_model_metadata_cleanup.md` | 默认 FP vision model、direct resize metadata、preprocess 坐标语义清理 |
| `phase18k_vision_serving_polish.md` | Vision Serving 使用示例、响应字段说明、demo 脚本与 Phase 18 收尾整理 |
| `phase19a_unified_inference_vlm_ready.md` | /v1/infer 统一推理入口、task dispatch、LLM/Vision adapter 与 VLM placeholder |

| `phase13b_project_summary.md` | 项目阶段总结、交接、简历描述与后续路线图 |


## Phase 19B：Unified Inference Response and Adapter Polish

Phase 19B 在 Phase 19A `/v1/infer` 统一推理入口基础上，进一步规范统一响应结构：

- `output.summary`：面向用户和前端的简要结果；
- `output.data`：标准化后的核心任务输出；
- `output.raw`：保留原任务后端完整响应，方便调试和回归；
- `edgeinfer.dispatch`：记录 task adapter、source endpoint、backend 和 source runtime。

详细文档见：

```text
docs/phase19b_unified_response_adapter_polish.md
```

## Phase 20: Global Multi-Model NPU Resource Guard

- Document: [`phase20_global_npu_resource_guard.md`](phase20_global_npu_resource_guard.md)
- Adds a global NPU resource guard across LLM and Vision requests.
- Preserves same-task queue behavior while rejecting cross-task contention with `npu_resource_busy`.

## Phase 22: Qwen3-VL RK3588 Backend MVP

- Document: [`phase22_qwen3_vl_backend.md`](phase22_qwen3_vl_backend.md)
- Adds a real Qwen3-VL RKNN + RKLLM backend for `/v1/infer` VLM tasks.
- Validates `vision-language` inference with board-side image input and global NPU guard protection.

## Phase 23: Qwen3-VL Backend Hardening & Benchmark

- Document: [`phase23_qwen3_vl_hardening_benchmark.md`](phase23_qwen3_vl_hardening_benchmark.md)
- Adds VLM global NPU guard validation.
- Confirms Qwen3-VL inference returns `npu_resource_busy` to competing NPU workloads while the VLM backend owns the resource.
