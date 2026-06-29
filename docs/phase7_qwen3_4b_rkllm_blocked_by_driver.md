# Phase 7：Qwen3-4B RKLLM 初始化失败记录

## 1. 目标

本阶段尝试在 RK3588 开发板上部署参数规模更大的 Qwen3-4B RKLLM 模型，用于验证更大文本模型在 edgeinfer-rk3588 项目中的可行性。

## 2. 模型信息

模型文件：

- Qwen3-4B-w8a8-npu.rkllm

模型来源：

- Qwen3-4B W8A8 RK3588 预转换 RKLLM 模型

模型大小：

- 约 4.6G

模型属性：

- backend: rkllm
- quantization: W8A8
- max_context_limit: 4096
- target_platform: RK3588

该模型已下载到 Ubuntu 虚拟机，并同步到开发板：

- /userdata/edgeinfer-assets/models/llm/rkllm_outputs/Qwen3-4B-w8a8-npu.rkllm

文件已通过 SHA256 校验，说明模型文件传输完整。

## 3. 当前开发板环境

开发板环境：

- Board: RK3588
- OS: Debian 11 bullseye
- Kernel: 5.10.160
- RKLLM Runtime: 1.3.0
- RKNPU driver: 0.9.2
- Memory: 15 GiB
- NPU core num: 3

此前 Qwen2.5-0.5B-Instruct 和 Qwen2.5-1.5B-Instruct 已经在同一环境下完成 RKLLM W8A8 部署和 benchmark 验证。

## 4. 测试命令

4096 上下文测试：

    ./third_party/rkllm_runtime/llm_demo /userdata/edgeinfer-assets/models/llm/rkllm_outputs/Qwen3-4B-w8a8-npu.rkllm 256 4096

2048 上下文测试：

    ./third_party/rkllm_runtime/llm_demo /userdata/edgeinfer-assets/models/llm/rkllm_outputs/Qwen3-4B-w8a8-npu.rkllm 256 2048

## 5. 失败现象

两次测试均在模型初始化阶段失败。

关键日志：

    rkllm init start
    W rkllm: Warning: Your rknpu driver version is too low, please upgrade to 0.9.7
    I rkllm: rkllm-runtime version: 1.3.0, rknpu driver version: 0.9.2, platform: RK3588
    I rkllm: loading rkllm model from /userdata/edgeinfer-assets/models/llm/rkllm_outputs/Qwen3-4B-w8a8-npu.rkllm
    I rkllm: rkllm-toolkit version: 1.2.1b1, max_context_limit: 4096, npu_core_num: 3, target_platform: RK3588, model_dtype: W8A8
    E RKNN: failed to allocate handle, ret: -1, errno: 14, errstr: Bad address
    E RKNN: failed to malloc npu memory, size: 4022272000, flags: 0x2
    E RKNN: load model file error!
    E rkllm: rkllm_init failed

2048 上下文测试仍然失败，说明该问题不是由生成上下文长度直接引起，而是发生在模型加载和 NPU 内存申请阶段。

## 6. 初步判断

Qwen3-4B RKLLM 模型文件可以被 RKLLM runtime 识别，但当前 RKNPU driver v0.9.2 无法完成约 4.02GB NPU 内存申请，导致模型加载失败。

因此，该模型当前不应标记为 ready，而应标记为 blocked。

建议状态：

- Qwen3-4B-W8A8-RK3588：blocked

阻塞原因：

- 当前 RKNPU driver 版本过低
- NPU memory allocation failed
- 需要升级 RKNPU driver 后重新验证

## 7. 后续工作

后续应优先完成：

1. 查找正点原子 RK3588 对应的新 BSP、内核或系统镜像。
2. 评估 RKNPU driver 从 v0.9.2 升级到 v0.9.7 或 v0.9.8 的可行性。
3. 升级前保留当前 eMMC 关键分区备份。
4. 升级后回归测试 Qwen2.5-0.5B 和 Qwen2.5-1.5B。
5. 再次验证 Qwen3-4B 是否可以初始化和生成。
