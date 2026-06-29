# Phase 6：Qwen2.5 RKLLM 模型对比总结

## 1. 文档目的

本文档对 edgeinfer-rk3588 项目中已经完成 RK3588 板端部署验证的两个 Qwen2.5 RKLLM 模型进行阶段性对比总结。

已验证模型包括：

- Qwen2.5-0.5B-Instruct
- Qwen2.5-1.5B-Instruct

两个模型均采用 RKLLM W8A8 量化格式，最大上下文长度为 2048，并已经在 RK3588 开发板上完成资产检查、模型初始化、交互式文本生成和自动化 benchmark 验证。

## 2. 验证环境

开发板环境：

- 开发板：RK3588
- 板端用户：linaro
- 板端项目目录：/home/linaro/edgeinfer-rk3588-board
- 大文件资产目录：/userdata/edgeinfer-assets
- RKLLM runtime：1.3.0
- rknpu driver：0.9.2
- NPU core num：3
- 模型 dtype：W8A8
- max_context：2048

运行时提示 rknpu driver 版本低于 RKLLM runtime 建议版本，但没有影响模型初始化和文本生成。

## 3. 模型资产状态

当前模型注册状态如下：

| 模型 | 后端 | 量化 | 状态 |
|---|---|---|---|
| Qwen2.5-0.5B-Instruct | rkllm | W8A8 | ready |
| Qwen2.5-1.5B-Instruct | rkllm | W8A8 | ready |

开发板端执行 tools/check_assets.py 后，两个模型的 source_dir 和 runtime_model 均为 OK。

## 4. 自动化 Benchmark 对比

两个模型使用相同 benchmark prompt 集：

- identity
- rk3588_intro
- edge_ai
- python_sort

运行参数一致：

- max_new_tokens = 512
- max_context = 2048

### 4.1 平均性能结果

| 模型 | 平均初始化时间 ms | 平均 Prefill TPS | 平均 Generate TPS | 平均峰值内存 MB |
|---|---:|---:|---:|---:|
| Qwen2.5-0.5B-Instruct | 747.57 | 318.56 | 21.79 | 674.22 |
| Qwen2.5-1.5B-Instruct | 1747.12 | 163.78 | 9.14 | 1721.02 |

### 4.2 相对变化

以 Qwen2.5-0.5B-Instruct 作为 baseline：

| 指标 | 1.5B 相对 0.5B 的变化 |
|---|---:|
| 初始化时间 | 约 2.34 倍 |
| Prefill 速度 | 约 51.4% |
| Generate 速度 | 约 41.9% |
| 峰值内存 | 约 2.55 倍 |

## 5. 结果分析

Qwen2.5-0.5B-Instruct 的主要特点：

- 初始化速度更快。
- 生成速度约 21 到 22 tokens/s。
- 峰值内存约 674 MB。
- 更适合对响应速度、内存占用和部署稳定性要求较高的边缘场景。
- 适合轻量问答、简单指令理解、设备状态说明、边缘端辅助交互等任务。

Qwen2.5-1.5B-Instruct 的主要特点：

- 模型规模更大。
- 生成速度约 9 tokens/s。
- 峰值内存约 1721 MB。
- 对内存和推理时间的要求明显更高。
- 适合需要更强语言表达、复杂指令理解和较高回答质量的场景。

从工程部署角度看，0.5B 模型更适合作为默认边缘端 LLM baseline；1.5B 模型更适合作为高质量模式或对比模型保留。

## 6. 阶段性结论

本阶段已经完成 Qwen2.5-0.5B-Instruct 和 Qwen2.5-1.5B-Instruct 在 RK3588 上的 RKLLM 部署验证。

当前结论如下：

1. 两个 Qwen2.5 模型均可在 RK3588 上成功加载和运行。
2. 两个模型均可通过 RKLLM runtime 1.3.0 完成交互式文本生成。
3. 两个模型均已完成自动化 benchmark。
4. 0.5B 模型具备更好的速度和内存表现，适合作为默认部署模型。
5. 1.5B 模型具备更大的模型容量，但推理速度和内存占用成本明显更高。
6. 后续可根据业务场景在速度优先和质量优先之间选择模型。

## 7. 建议默认策略

建议在 edgeinfer-rk3588 项目中采用如下策略：

- 默认 LLM 模型：Qwen2.5-0.5B-Instruct
- 质量优先模型：Qwen2.5-1.5B-Instruct
- 默认上下文长度：2048
- 默认生成上限：512
- 默认 runtime：RKLLM runtime 1.3.0

## 8. 后续工作建议

后续可以继续开展以下工作：

1. 增加更贴近项目场景的 prompt 集，例如设备状态解释、边缘 AI 部署问答、日志解释和故障诊断。
2. 对比 0.5B 与 1.5B 在回答质量上的差异。
3. 增加统一的 LLM 运行入口脚本，便于按模型名称选择运行。
4. 评估 rknpu driver 从 0.9.2 升级到建议版本的必要性和风险。
5. 后续将 LLM 能力逐步接入 edgeinfer 的统一应用层。
