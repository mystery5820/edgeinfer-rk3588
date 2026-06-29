# Phase 6：Qwen2.5-1.5B RKLLM 板端验证

## 1. 验证目的

本文档记录 edgeinfer-rk3588 项目中 Qwen2.5-1.5B-Instruct 模型在 RK3588 开发板上的 RKLLM 部署验证结果。

在 Qwen2.5-0.5B-Instruct 已经跑通的基础上，本阶段继续验证 1.5B 模型的板端资产管理、RKLLM runtime 加载、交互式生成和自动化 benchmark 表现。

## 2. 板端环境

开发板信息：

- 用户：linaro
- 地址：192.168.43.7
- 主机名：ATK-DLRK3588
- 板端项目目录：/home/linaro/edgeinfer-rk3588-board
- 大文件资产目录：/userdata/edgeinfer-assets

RKLLM runtime：

- runtime 版本：1.3.0
- runtime 软链接：third_party/rkllm_runtime
- runtime 实际位置：/userdata/edgeinfer-assets/tools/rkllm/v1.3.0/demo_Linux_aarch64
- demo 程序：llm_demo
- 动态库：librkllmrt.so

当前 rknpu driver 版本为 0.9.2。运行时仍提示建议升级到 0.9.7，但该警告没有阻止模型初始化或文本生成。

## 3. 模型资产

本阶段使用模型：

- Qwen2.5-1.5B-Instruct

HuggingFace 源模型已同步到开发板：

- /userdata/edgeinfer-assets/models/llm/baseline/Qwen2.5-1.5B-Instruct

RKLLM 运行模型已整理到：

- /userdata/edgeinfer-assets/models/llm/rkllm_outputs/qwen2_5_1_5b_instruct_w8a8_opt1_ctx2048_rk3588.rkllm

在项目目录中建立软链接：

- models/llm/baseline/Qwen2.5-1.5B-Instruct
- models/llm/rkllm_outputs/qwen2_5_1_5b_instruct_w8a8_opt1_ctx2048_rk3588.rkllm

执行 tools/check_assets.py 后，Qwen2.5-1.5B-Instruct 的 source_dir 和 runtime_model 均为 OK。此时所有注册模型资产均有效。

## 4. 交互式验证

运行命令：

    bash scripts/run_board_llm_demo.sh Qwen2.5-1.5B-Instruct 512 2048

模型成功初始化：

- rkllm init success

运行时信息：

- rkllm-runtime version: 1.3.0
- rknpu driver version: 0.9.2
- platform: RK3588
- rkllm-toolkit version: 1.3.0
- max_context_limit: 2048
- npu_core_num: 3
- target_platform: RK3588
- model_dtype: W8A8
- Enabled cpus: [4, 5, 6, 7]

交互式测试 prompt：

- 请用三句话介绍 RK3588 的主要特点。

一次交互式运行结果：

- Model init time: 1588.72 ms
- Prefill tokens: 43
- Prefill total time: 318.51 ms
- Prefill tokens per second: 135.00
- Generate tokens: 117
- Generate total time: 12865.86 ms
- Generate tokens per second: 9.09
- Peak memory usage: 1721.32 MB

## 5. 自动化 Benchmark 结果

自动化 benchmark 脚本：

- scripts/run_board_llm_benchmark.py

运行命令：

    python3 scripts/run_board_llm_benchmark.py --model Qwen2.5-1.5B-Instruct --max-new-tokens 512 --max-context 2048 --output-dir benchmark_results/llm_qwen25_1_5b

结果文件：

- benchmark_results/llm_qwen25_1_5b/llm_benchmark.csv

本次 benchmark 结果如下：

| prompt_name | model_init_ms | prefill_tps | generate_tps | peak_memory_mb |
|---|---:|---:|---:|---:|
| identity | 1845.85 | 167.73 | 9.30 | 1721.07 |
| rk3588_intro | 1395.49 | 168.98 | 9.07 | 1720.89 |
| edge_ai | 1872.92 | 168.50 | 9.12 | 1720.95 |
| python_sort | 1874.21 | 149.92 | 9.05 | 1721.18 |

平均结果：

- 平均初始化时间：约 1747.12 ms
- 平均 Prefill 速度：约 163.78 tokens/s
- 平均 Generate 速度：约 9.14 tokens/s
- 平均峰值内存：约 1721.02 MB

## 6. 与 0.5B 的初步对比

Qwen2.5-0.5B-Instruct 自动 benchmark 平均结果：

- 平均初始化时间：约 747.57 ms
- 平均 Prefill 速度：约 318.56 tokens/s
- 平均 Generate 速度：约 21.79 tokens/s
- 平均峰值内存：约 674.22 MB

Qwen2.5-1.5B-Instruct 自动 benchmark 平均结果：

- 平均初始化时间：约 1747.12 ms
- 平均 Prefill 速度：约 163.78 tokens/s
- 平均 Generate 速度：约 9.14 tokens/s
- 平均峰值内存：约 1721.02 MB

初步结论：

- 1.5B 的生成速度约为 0.5B 的 42%。
- 1.5B 的峰值内存约为 0.5B 的 2.55 倍。
- 1.5B 初始化时间明显更长。
- 1.5B 模型虽然更重，但在 RK3588 上仍可完成 RKLLM W8A8 文本生成。

## 7. 当前结论

Qwen2.5-1.5B-Instruct 已完成 RK3588 板端 RKLLM 初步部署验证。

当前模型状态应更新为：

- Qwen2.5-0.5B-Instruct：ready
- Qwen2.5-1.5B-Instruct：ready

至此，项目中的两个 Qwen2.5 RKLLM 模型均已完成基础部署和 benchmark 验证。

## 8. 后续工作

后续建议继续完成：

1. 进一步评估 0.5B 与 1.5B 的回答质量差异。
2. 增加更贴近实际业务场景的中文 prompt 集。
3. 评估 rknpu driver 从 0.9.2 升级到 RKLLM 建议版本的风险。
4. 根据应用需求选择默认 LLM 模型。
5. 后续如有需要，将 LLM 运行能力整合到 edgeinfer 统一命令入口中。

## 9. 文件管理约束

模型权重、.rkllm 产物和 RKLLM runtime 二进制文件均不应提交到 Git。

Git 仓库中只保留：

- 脚本
- 配置文件
- 文档
- 小型测试样例
- benchmark 结果 CSV
