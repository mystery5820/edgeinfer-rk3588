# EdgeInfer-RK3588

基于 RK3588 NPU 的端侧多模型推理服务框架。

## 项目定位

本项目面向端侧 AI Infra、模型部署优化与推理系统方向，基于 RK3588 NPU 构建一个支持视觉检测、端侧 LLM、视觉语言模型、多模型调度、自动化 Benchmark 和工程化部署的小型推理服务框架。

## 当前目标

- YOLOv11 实时视觉检测
- Qwen2.5 / Qwen3 系列端侧 LLM 推理
- VLM 图文问答扩展
- RKNN / RKLLM 多后端统一封装
- 模型包管理
- OpenAI-like API
- 自动化 Benchmark
- 多模型调度与资源监控
- systemd 工程化部署

## 目录说明

- datasets：数据集
- models/vision：视觉模型
- models/llm：大语言模型
- models/vlm：视觉语言模型
- experiments：历史实验与优化实验
- server：推理服务框架代码
- cpp：C++ 推理与后处理代码
- tools：转换、量化、Benchmark 工具
- third_party：RKNN / RKLLM 官方工具包
- results：Benchmark 与日志结果
- envs：Python 环境依赖记录

## Phase 9 Serving 运维与验证

Phase 9 Serving Framework 已提供 host 侧部署与验收脚本：

```bash
./scripts/host/deploy_serving_to_board.sh
./scripts/host/smoke_test_serving.sh
./scripts/host/validate_serving_modes.sh
```

推荐完整验收命令：

```bash
./scripts/host/validate_serving_modes.sh
```

该命令会自动验证默认 one-shot 模式与可选 RKLLM persistent worker 模式，并在结束后恢复默认 one-shot。

详细说明见：

```text
docs/phase9_serving_operations.md
```

OpenAI-like Chat API 兼容说明见：

```text
docs/phase9_openai_compat.md
```


- Phase 10 stream=true SSE 流式输出说明：`docs/phase10_streaming_sse.md`
- Phase 11 OpenAI Python SDK 示例说明：`docs/phase11_openai_sdk_examples.md`
