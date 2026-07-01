# Phase 8：Qwen3-4B RKLLM 板端验证、根因分析与 all-NPU / hybrid 对比

## 1. 阶段目标

本阶段目标是在正点原子 ATK-DLRK3588 开发板上验证 Qwen3-4B W8A8 RKLLM 模型，并彻底排查此前反复出现的 RKNPU DMA / IOVA 映射失败问题。

本阶段重点验证两个模型：

- `Qwen3-4B-w8a8-npu.rkllm`
- `Qwen3-4B-w8a8-hybrid.rkllm`

验证环境如下：

- 开发板：ATK-DLRK3588
- SoC：RK3588
- 系统：Debian GNU/Linux 11
- 内核：Linux 5.10.209-g16b8cb7e2392-dirty
- RKNPU driver：v0.9.8
- RKLLM runtime：v1.3.0
- RKNPU memory manager：DRM_GEM
- CMA：512 MiB
- Runtime 工具：`rkllm_enhanced`
- 测试参数：`ctx=1024`，`max_new_tokens=128`

## 2. 初始问题

在本阶段前，Qwen3-4B 模型初始化时持续失败。hybrid 模型典型错误为：

```text
E RKNN: failed to allocate handle, ret: -1, errno: 14, errstr: Bad address
E RKNN: failed to malloc npu memory, size: 93241344, flags: 0x2
E RKNN: load model file error!
E rkllm: rkllm_init failed
```

内核日志对应错误为：

```text
RKNPU: failed to allocate IOVA: -12
RKNPU fdab0000.npu: RKNPU: rknpu_gem_get_pages: dma map 93241344 fail
```

all-NPU 模型此前也曾失败，典型错误为：

```text
failed to malloc npu memory, size: 4022272000
```

这些失败一度被怀疑与以下因素有关：

- RKLLM runtime 版本不兼容；
- RKNPU 驱动版本过低；
- CMA 预留空间不足；
- 普通内存不足；
- root 权限或 ulimit 限制；
- 模型文件损坏；
- Qwen3-4B 本身不适合当前板端环境。

## 3. 已完成的底层环境修复

为了排除底层环境因素，本阶段前后完成了以下工作：

1. 将 RKNPU driver 升级到 v0.9.8。
2. 确认 RKLLM runtime v1.3.0 可以正确识别 RKNPU 0.9.8。
3. 将 RKNPU memory manager 恢复为 DRM_GEM。
4. 将 CMA 从 128 MiB 提升到 512 MiB。
5. 验证 Qwen2.5-1.5B 在新内核下仍然可以正常运行。
6. 对 RKLLM runtime v1.2.3 与 v1.3.0 进行 A/B 测试。
7. 编译 `rkllm_enhanced`，加入 `n_keep=4`、`embed_flash=1`、`enabled_cpus_mask=0xF0` 等参数。
8. 构建临时 debug kernel，加入 RKNPU IOVA 映射日志。

## 4. Debug Kernel 发现

临时 debug kernel 在以下源码中加入日志：

- `drivers/rknpu/rknpu_gem.c`
- `drivers/rknpu/rknpu_iommu.c`

调试日志显示，Qwen3-4B 模型初始化时需要在 RKNPU IOMMU 中映射大块 IOVA 地址空间，例如 hybrid 模型中出现：

```text
size=3633315840
size=93241344
aperture_start=0x0
aperture_end=0xffffffff
limit_pfn=1048575
```

这说明 RKNPU IOMMU 的 IOVA aperture 为 4 GiB：

```text
0x00000000 ~ 0xffffffff
```

同时，内核侧真实 flags 为：

```text
flags=0x403
```

其含义为：

```text
0x001 = RKNPU_MEM_NON_CONTIGUOUS
0x002 = RKNPU_MEM_CACHEABLE
0x400 = RKNPU_MEM_IOMMU_LIMIT_IOVA_ALIGNMENT
```

因此，模型加载路径会进入 RKNPU 驱动自定义的 IOVA 分配路径，而不是直接走标准 `dma_map_sg()` 快速路径。

## 5. 根本原因

最终确认，Qwen3-4B 模型此前失败的根本原因并不是模型本身不可运行，也不是 CMA512 不够、普通内存不足、runtime 版本不兼容或 root 权限问题。

真正原因是：开发板开机后自动启动了旧的 AI demo 服务，这些服务提前占用了 RKNPU / DRM 设备，并消耗了 RKNPU IOVA 地址空间。

相关服务包括：

```text
qwen-web-chat.service
yolov5-web.service
```

对应进程包括：

```text
llm_demo qwen2_5_0_5b_instruct_w8a8_rk3588.rkllm
yolov5_web_server_config.py
```

它们占用了 `/dev/dri/card1`，导致后续 Qwen3-4B 模型初始化时无法继续获得所需 IOVA 映射空间，最终表现为：

```text
RKNPU: failed to allocate IOVA: -12
rknpu_gem_get_pages: dma map 93241344 fail
```

禁用旧服务并重启后，RKNPU 环境恢复干净，Qwen3-4B hybrid 和 Qwen3-4B all-NPU 均成功运行。

## 6. 最终服务状态

已禁用旧 demo 服务：

```bash
sudo systemctl disable qwen-web-chat.service
sudo systemctl disable yolov5-web.service
```

最终状态：

```text
qwen-web-chat.service: disabled
yolov5-web.service: disabled
```

后续主项目以 `~/edgeinfer-rk3588-board` 为准，不再让 `/home/linaro/rk3588_ai` 下的旧 Web demo 在开机后自动占用 RKNPU。

## 7. 内核恢复

调试完成后，开发板已从 debug kernel 刷回无 debug 日志的正式 CMA512 内核：

```text
boot_rknpu098_drm_gem_cma512.img
```

镜像 SHA256：

```text
aa4f835f7f075cc60c8dad864ce24c7f2b0ca4692b4b8a49f9ee06b2739b8880
```

最终内核状态：

```text
Linux ATK-DLRK3588 5.10.209-g16b8cb7e2392-dirty #3 SMP Wed Jul 1 10:13:08 CST 2026 aarch64 GNU/Linux
```

CMA 状态：

```text
CmaTotal: 524288 kB
CmaFree:  516992 kB
```

debug 日志状态：

```text
no debug iova logs
```

## 8. Qwen3-4B all-NPU 验证结果

运行命令：

```bash
cd ~/edgeinfer-rk3588-board/tools/rkllm_enhanced

export LD_LIBRARY_PATH="$HOME/edgeinfer-rk3588-board/third_party/rkllm_runtime/lib:${LD_LIBRARY_PATH:-}"
export RKLLM_LOG_LEVEL=1

./rkllm_enhanced \
  /userdata/edgeinfer-assets/models/llm/rkllm_outputs/Qwen3-4B-w8a8-npu.rkllm \
  1024 \
  128
```

最终成功进入交互并完成推理。

测试问题：

```text
请用一句话介绍 RK3588。
```

最终 benchmark 结果：

```text
Model init time (ms): 3759.09
Prefill: 19 tokens, 49.83 tokens/s
Generate: 127 tokens, 4.14 tokens/s
Peak Memory Usage: 4182.84 MB
```

日志文件：

```text
logs/llm/qwen3_all_npu/qwen3_4b_all_npu_ctx1024_new128_clean_kernel.log
logs/llm/qwen3_all_npu/qwen3_4b_all_npu_ctx1024_new128_clean_kernel_dmesg.log
logs/llm/qwen3_all_npu/qwen3_4b_all_npu_final_status.txt
```

其中 all-NPU 的 dmesg 日志文件为 0 字节，说明正式无 debug 内核下未捕获到 `failed / IOVA / dma map / Bad address` 等错误信息。

## 9. Qwen3-4B hybrid 验证结果

运行命令：

```bash
cd ~/edgeinfer-rk3588-board/tools/rkllm_enhanced

export LD_LIBRARY_PATH="$HOME/edgeinfer-rk3588-board/third_party/rkllm_runtime/lib:${LD_LIBRARY_PATH:-}"
export RKLLM_LOG_LEVEL=1

./rkllm_enhanced \
  /userdata/edgeinfer-assets/models/llm/rkllm_outputs/Qwen3-4B-w8a8-hybrid.rkllm \
  1024 \
  128
```

最终成功进入交互并完成推理。

测试问题：

```text
请用一句话介绍 RK3588。
```

最终 benchmark 结果：

```text
Model init time (ms): 16665.54
Prefill: 19 tokens, 39.51 tokens/s
Generate: 127 tokens, 3.79 tokens/s
Peak Memory Usage: 4342.63 MB
```

日志文件：

```text
logs/llm/qwen3_hybrid/qwen3_4b_hybrid_ctx1024_new128_clean_kernel_final.log
logs/llm/qwen3_hybrid/qwen3_4b_hybrid_ctx1024_new128_clean_rknpu_alloc_dmesg.log
logs/llm/qwen3_hybrid/qwen3_4b_hybrid_ctx1024_new128_clean_rknpu_dmesg.log
logs/llm/qwen3_hybrid/qwen3_4b_hybrid_final_status.txt
```

## 10. all-NPU 与 hybrid 对比

| 指标 | Qwen3-4B all-NPU | Qwen3-4B hybrid | 结论 |
|---|---:|---:|---|
| Model init time | 3759.09 ms | 16665.54 ms | all-NPU 明显更快 |
| Prefill | 49.83 tokens/s | 39.51 tokens/s | all-NPU 更快 |
| Generate | 4.14 tokens/s | 3.79 tokens/s | all-NPU 略快 |
| Peak Memory Usage | 4182.84 MB | 4342.63 MB | all-NPU 略低 |
| 是否成功运行 | 成功 | 成功 | 二者均可用 |

进一步量化：

```text
all-NPU 初始化约快 4.43 倍；
all-NPU Prefill 约快 26.1%；
all-NPU Generate 约快 9.2%；
all-NPU 峰值内存约低 159.79 MB。
```

## 11. 最终结论

本阶段最终结论如下：

```text
Qwen3-4B all-NPU 和 Qwen3-4B hybrid 均可以在 ATK-DLRK3588 上运行。
此前反复失败的根因是旧后台 AI demo 服务占用 RKNPU / DRM / IOVA 空间。
在 clean RKNPU 环境下，all-NPU 与 hybrid 均可成功初始化并推理。
```

当前推荐路线：

```text
首选：Qwen3-4B all-NPU
备选：Qwen3-4B hybrid
稳定基线：Qwen2.5-1.5B
快速验证基线：Qwen2.5-0.5B
```

推荐 all-NPU 的理由：

- 初始化时间明显短于 hybrid；
- Prefill 更快；
- Generate 略快；
- 峰值内存略低；
- clean RKNPU 环境下可以稳定进入推理。

## 12. 注意事项

运行 Qwen3-4B all-NPU 或 hybrid 前，需要确保没有其他 RKNN / RKLLM / YOLO demo 服务占用 RKNPU / DRM 设备。

建议检查：

```bash
systemctl is-enabled qwen-web-chat.service
systemctl is-enabled yolov5-web.service

ps -ef | grep -Ei "qwen_web_chat|yolov5_web|llm_demo|rkllm|rknn" | grep -v grep

sudo fuser -v /dev/dri/card* /dev/dri/renderD* /dev/rknpu* 2>/dev/null || true
```

其中 Xorg 占用图形显示设备属于正常现象，不应随意杀掉。

## 13. 后续工作

后续应回到主项目路径，继续推进大模型应用层工作：

1. 更新 `configs/model_registry.yaml`，将 Qwen3-4B all-NPU 与 hybrid 状态均标记为 runnable。
2. 将 all-NPU 标记为当前 Qwen3-4B 推荐路线。
3. 将旧 demo 服务占用 RKNPU 的问题写入部署注意事项。
4. 整理统一的 LLM runner / benchmark 脚本。
5. 优化 `rkllm_enhanced` 的 chat template、stop token 和输出截断。
6. 后续再考虑 Web/API 服务化。
7. 最后整理完整阶段性 docx 笔记。

需要特别记录：当前 Qwen3-4B 模型虽然已经部署成功，但回答内容仍存在明显幻觉，例如错误描述 RK3588 的厂商、核心数、制程和通信能力。这属于模型输出质量、提示模板、采样参数或 stop token 处理问题，不是底层部署失败。
