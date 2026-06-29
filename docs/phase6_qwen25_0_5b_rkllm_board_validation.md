# Phase 6：Qwen2.5-0.5B RKLLM 板端验证

## 1. 验证目的

本文档记录 edgeinfer-rk3588 项目中 Qwen2.5-0.5B-Instruct 模型在 RK3588 开发板上的 RKLLM 部署验证结果。

本阶段目标是先验证大语言模型在板端的基本部署链路，包括模型资产准备、RKLLM runtime 接入、项目路径适配、交互式文本生成和基础性能记录。确认 0.5B 模型跑通后，再继续推进 Qwen2.5-1.5B-Instruct。

## 2. 板端环境

开发板登录信息：

- 用户：linaro
- 地址：192.168.43.7
- 主机名：ATK-DLRK3588
- 板端项目目录：/home/linaro/edgeinfer-rk3588-board
- 大文件资产目录：/userdata/edgeinfer-assets

当前 RKLLM runtime 来源于板端旧工程：

- 旧工程路径：/home/linaro/rk3588_ai/tools/rknn-llm-release-v1.3.0
- demo 程序：llm_demo
- runtime 动态库：librkllmrt.so

为适配当前项目，已将 runtime 整理到：

- /userdata/edgeinfer-assets/tools/rkllm/v1.3.0/demo_Linux_aarch64

并在当前项目中建立软链接：

- third_party/rkllm_runtime -> /userdata/edgeinfer-assets/tools/rkllm/v1.3.0/demo_Linux_aarch64

## 3. 模型资产

本阶段使用模型：

- Qwen2.5-0.5B-Instruct

HuggingFace 源模型已同步到开发板：

- /userdata/edgeinfer-assets/models/llm/baseline/Qwen2.5-0.5B-Instruct

RKLLM 运行模型已同步到开发板：

- /userdata/edgeinfer-assets/models/llm/rkllm_outputs/qwen2_5_0_5b_instruct_w8a8_opt1_ctx2048_rk3588.rkllm

在项目目录中建立软链接，使 configs/model_registry.yaml 中的相对路径保持有效：

- models/llm/baseline/Qwen2.5-0.5B-Instruct
- models/llm/rkllm_outputs/qwen2_5_0_5b_instruct_w8a8_opt1_ctx2048_rk3588.rkllm

软链接建立后，tools/check_assets.py 已能识别 Qwen2.5-0.5B-Instruct 的 source_dir 和 runtime_model，二者均为 OK。

## 4. 运行脚本

本阶段新增板端运行脚本：

- scripts/run_board_llm_demo.sh

默认模型：

- Qwen2.5-0.5B-Instruct

默认参数：

- max_new_tokens = 512
- max_context = 2048

运行命令：

    bash scripts/run_board_llm_demo.sh Qwen2.5-0.5B-Instruct 512 2048

脚本内部会自动设置：

    export LD_LIBRARY_PATH="${RUNTIME_DIR}/lib:${LD_LIBRARY_PATH:-}"

因此可以避免直接运行 llm_demo 时出现 librkllmrt.so => not found 的问题。

## 5. 板端验证结果

板端运行脚本后，模型成功初始化：

- rkllm init success

运行时信息如下：

- rkllm-runtime version: 1.3.0
- rknpu driver version: 0.9.2
- platform: RK3588
- rkllm-toolkit version: 1.3.0
- max_context_limit: 2048
- npu_core_num: 3
- target_platform: RK3588
- model_dtype: W8A8
- Enabled cpus: [4, 5, 6, 7]

运行时出现警告：

- Warning: Your rknpu driver version is too low, please upgrade to 0.9.7

当前 rknpu driver 版本为 0.9.2，低于 RKLLM runtime 建议的 0.9.7。不过该警告没有阻止模型初始化和文本生成，因此驱动升级暂时记录为后续环境维护任务，不在当前阶段处理。

## 6. 交互式测试

测试输入：

- 请用一句话说明 RKLLM 在 RK3588 上的作用。

模型成功生成回答，并输出 RKLLM 性能统计信息。

一次验证运行中的性能数据如下：

- Model init time: 706.32 ms
- Prefill tokens: 45
- Prefill total time: 153.20 ms
- Prefill tokens per second: 293.73
- Generate tokens: 73
- Generate total time: 3388.93 ms
- Generate time per token: 46.42 ms
- Generate tokens per second: 21.54
- Peak memory usage: 674.36 MB

此前手动验证中也得到过相近结果：

- Generate speed: about 20.80 tokens/s
- Peak memory usage: about 674 MB

## 7. 当前结论

Qwen2.5-0.5B-Instruct 已完成 RK3588 板端 RKLLM 初步部署验证。

当前模型状态应更新为：

- Qwen2.5-0.5B-Instruct：ready
- Qwen2.5-1.5B-Instruct：baseline

本阶段已跑通的链路为：

HuggingFace 源模型 -> RKLLM W8A8 运行模型 -> /userdata 大文件资产存储 -> 项目目录软链接 -> RKLLM runtime 接入 -> 板端交互式文本生成

## 8. 后续工作

后续建议继续完成：

1. 增加非交互式 RKLLM benchmark 脚本，用于自动解析性能日志。
2. 同步并验证 Qwen2.5-1.5B-Instruct。
3. 对比 0.5B 与 1.5B 的生成速度、内存占用和回答质量。
4. 单独评估 rknpu driver 从 0.9.2 升级到 RKLLM 建议版本的风险和步骤。
5. 后续如有需要，将 LLM 运行能力整合到 edgeinfer 统一命令入口中。

## 9. 文件管理约束

模型权重、.rkllm 产物和 RKLLM runtime 二进制文件均不应提交到 Git。

Git 仓库中只保留：

- 脚本
- 配置文件
- 文档
- 小型测试样例
- benchmark 结果文本或 CSV

大文件继续统一放在：

- /userdata/edgeinfer-assets

## 10. 自动化 Benchmark 结果

在交互式验证通过后，项目新增了非交互式 RKLLM benchmark 脚本：

- scripts/run_board_llm_benchmark.py

该脚本通过伪终端方式启动 RKLLM demo，自动输入测试 prompt，解析 RKLLM 输出日志，并生成 CSV 结果文件。

本次 benchmark 使用模型：

- Qwen2.5-0.5B-Instruct

运行参数：

- max_new_tokens = 512
- max_context = 2048

测试 prompt 包括：

- identity
- rk3588_intro
- edge_ai
- python_sort

板端运行命令：

    python3 scripts/run_board_llm_benchmark.py --model Qwen2.5-0.5B-Instruct --max-new-tokens 512 --max-context 2048

结果文件已保存为：

- benchmark_results/llm_qwen25_0_5b/llm_benchmark.csv

本次 benchmark 结果如下：

| prompt_name | model_init_ms | prefill_tps | generate_tps | peak_memory_mb |
|---|---:|---:|---:|---:|
| identity | 717.14 | 340.77 | 22.17 | 674.14 |
| rk3588_intro | 693.75 | 268.05 | 21.55 | 674.43 |
| edge_ai | 834.60 | 401.19 | 21.70 | 673.99 |
| python_sort | 744.80 | 264.22 | 21.73 | 674.31 |

平均结果：

- 平均初始化时间：约 747.57 ms
- 平均 Prefill 速度：约 318.56 tokens/s
- 平均 Generate 速度：约 21.79 tokens/s
- 平均峰值内存：约 674.22 MB

结论：

Qwen2.5-0.5B-Instruct 在 RK3588 上的 RKLLM W8A8 推理速度较稳定，四个 prompt 的生成速度基本维持在 21 到 22 tokens/s，峰值内存稳定在约 674 MB。该结果可作为后续 Qwen2.5-1.5B-Instruct 板端部署和性能对比的 baseline。
