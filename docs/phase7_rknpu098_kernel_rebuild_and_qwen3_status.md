# Phase 7: RKNPU 0.9.8 内核重建与 Qwen3-4B RKLLM 验证结论

## 1. 阶段目标

本阶段目标是解决 Qwen3-4B-W8A8-RK3588 在 RK3588 开发板端运行时遇到的 RKNPU driver 版本过低问题，并进一步验证该模型是否可以在正点原子 ATK-DLRK3588 开发板上通过 RKLLM runtime 正常加载和推理。

原始开发板环境：

```text
Board: 正点原子 ATK-DLRK3588
SoC: RK3588
OS: Debian GNU/Linux 11
Original Kernel: 5.10.160
Original RKNPU driver: v0.9.2
RKLLM runtime: v1.3.0
Board project path: /home/linaro/edgeinfer-rk3588-board
Large asset path: /userdata/edgeinfer-assets
```

Qwen3-4B 初始运行失败时提示：

```text
Your rknpu driver version is too low, please upgrade to 0.9.7
rkllm-runtime version: 1.3.0, rknpu driver version: 0.9.2
failed to malloc npu memory, size: 4022272000
rkllm_init failed
```

因此本阶段首先进行 RKNPU driver 升级。

## 2. R8 SDK 恢复与 RKNPU 0.9.8 替换

使用正点原子 R8 SDK 作为内核重建基础：

```text
SDK: atk-rk3588_linux_release_R8_v1.0_20250104
SDK path: ~/atk-rk3588-r8-sdk
Board config: alientek_rk3588_defconfig
Kernel config: rockchip_linux_defconfig
Kernel DTS: rk3588-atk-devkit.dts
Target board: ATK_DLRK3588
```

R8 SDK 自带 RKNPU driver 为 v0.9.6，不能满足本阶段 Qwen3-4B 验证需求。随后使用 RKLLM v1.3.0 工具包中的 RKNPU driver 0.9.8 替换 SDK 中的 `kernel/drivers/rknpu`。

替换后版本：

```text
RKNPU driver: v0.9.8
Driver date: 20240828
```

## 3. 编译兼容修复

替换 RKNPU 0.9.8 后，首次编译出现 `rockchip_opp_set_low_length` 未定义问题。该问题位于 RK3576 相关 OPP 分支中，而当前开发板为 RK3588，不走该分支。

采用最小兼容修复方式，删除 `rknpu_devfreq.c` 中 RK3576 分支的：

```c
.set_soc_info = rockchip_opp_set_low_length,
```

修复后，RKNPU 0.9.8 内核成功编译。

稳定版内核产物目录：

```text
~/atk-rk3588-r8-sdk/artifacts/rknpu098_kernel_20260629_230004
```

关键产物：

```text
boot.img
Image
rk3588-atk-devkit.dtb
resource.img
rknpu_0_9_6_to_0_9_8.patch
rknpu_0_9_6_to_0_9_8.stat.txt
```

稳定版 boot.img SHA256：

```text
b66c1a0e297ff653947ad2dea50a2d8ba12d457c466c54d0f6b08887de3c7455
```

## 4. 刷写 boot.img 与 Wi-Fi 修复

开发板 boot 分区为：

```text
/dev/mmcblk0p3
```

首次刷入 RKNPU 0.9.8 boot.img 后，新内核可以启动，RKNPU driver 成功升级：

```text
Linux ATK-DLRK3588 5.10.209-g16b8cb7e2392-dirty
RKNPU driver: v0.9.8
```

但 Wi-Fi 不能正常使用。排查后确认，新 kernel release 对应的模块目录中缺少外部 Wi-Fi 驱动 `8733bu.ko`。

SDK 中驱动源码路径：

```text
external/rkwifibt/drivers/rtl8733bu
```

重新编译并安装 `8733bu.ko` 后，Wi-Fi 和 SSH 恢复正常。

最终稳定状态：

```text
Kernel: 5.10.209-g16b8cb7e2392-dirty #1
RKNPU driver: v0.9.8
Wi-Fi interface: wlx4ca38f7e645d
Wi-Fi state: connected
SSH: normal
```

## 5. Qwen2.5-1.5B 回归验证

在 RKNPU 0.9.8 稳定版内核下，Qwen2.5-1.5B-Instruct RKLLM 模型可以正常初始化和推理。

运行命令：

```bash
cd ~/edgeinfer-rk3588-board

export LD_LIBRARY_PATH="$(pwd)/third_party/rkllm_runtime/lib:${LD_LIBRARY_PATH:-}"
export RKLLM_LOG_LEVEL=1

./third_party/rkllm_runtime/llm_demo \
  models/llm/rkllm_outputs/qwen2_5_1_5b_instruct_w8a8_opt1_ctx2048_rk3588.rkllm \
  256 \
  2048
```

验证结果：

```text
rkllm-runtime version: 1.3.0
rknpu driver version: 0.9.8
platform: RK3588
rkllm init success
```

性能记录：

```text
Model init time: 6805.94 ms
Prefill: 33 tokens, 122.99 tokens/s
Generate: 29 tokens, 9.16 tokens/s
Peak Memory Usage: 1719.96 MB
```

说明 RKNPU 0.9.8 稳定版内核可以被 RKLLM runtime 正常识别和使用，Qwen2.5-1.5B 仍是当前可运行的大模型基线。

## 6. Qwen3-4B 在 DRM_GEM 稳定版下的验证结果

RKNPU driver 升级到 v0.9.8 后，Qwen3-4B 不再提示 driver 版本过低。

运行命令：

```bash
cd ~/edgeinfer-rk3588-board

export LD_LIBRARY_PATH="$(pwd)/third_party/rkllm_runtime/lib:${LD_LIBRARY_PATH:-}"
export RKLLM_LOG_LEVEL=1

./third_party/rkllm_runtime/llm_demo \
  /userdata/edgeinfer-assets/models/llm/rkllm_outputs/Qwen3-4B-w8a8-npu.rkllm \
  256 \
  2048
```

失败信息变为：

```text
rkllm-runtime version: 1.3.0, rknpu driver version: 0.9.8
failed to malloc npu memory, size: 4022272000
load model file error
rkllm_init failed
```

dmesg 中进一步确认：

```text
RKNPU: failed to allocate IOVA: -12
RKNPU: rknpu_gem_get_pages: dma map 4022272000 fail
```

结论：

```text
Qwen3-4B 的 driver-too-low 问题已经解决；
模型文件可以被 RKLLM runtime 识别；
但模型加载阶段需要一次性映射约 4022272000 bytes，即约 3.75 GiB；
当前 RKNPU DRM_GEM / IOMMU 路径无法完成该大块地址映射。
```

因此 Qwen3-4B 当前状态应更新为：

```text
blocked: RKNPU IOVA mapping failed for 3.75GiB model allocation
```

## 7. DMA_HEAP 实验版内核验证

为排查 Qwen3-4B 是否受 DRM_GEM 内存管理路径限制，额外构建了 DMA_HEAP 实验版内核。

实验配置：

```text
CONFIG_DMABUF_HEAPS_ROCKCHIP=y
CONFIG_DMABUF_HEAPS_ROCKCHIP_CMA_HEAP=y
# CONFIG_ROCKCHIP_RKNPU_DRM_GEM is not set
CONFIG_ROCKCHIP_RKNPU_DMA_HEAP=y
```

实验版内核产物目录：

```text
~/atk-rk3588-r8-sdk/artifacts/rknpu098_dma_heap_kernel_20260630_194630
```

实验版 boot.img SHA256：

```text
fe8dce90939c4689aa306c14f3f1baa21b78f8a496a9f2cd7db481f13d9b7915
```

实验版可以启动，Wi-Fi 和 SSH 正常：

```text
Linux ATK-DLRK3588 5.10.209-g16b8cb7e2392-dirty #2
RKNPU driver: v0.9.8
Wi-Fi: connected
```

但 RKLLM runtime 无法打开 RKNPU/RKNN 设备：

```text
failed to open rknpu module, need to insmod rknpu dirver!
failed to open rknn device!
Device is not available
Get device properties failed
rkllm init failed
```

结论：

```text
DMA_HEAP 实验版内核本身可以启动；
RKNPU driver 也显示为 v0.9.8；
但当前 RKLLM runtime v1.3.0 无法使用该 DMA_HEAP 版本的 RKNPU 设备接口；
因此 DMA_HEAP 路线不适合作为当前 RKLLM 部署环境。
```

随后系统已回滚到 DRM_GEM 稳定版。

## 8. 最终状态

当前稳定运行环境为：

```text
Kernel: 5.10.209-g16b8cb7e2392-dirty #1
RKNPU driver: v0.9.8
RKNPU memory manager: DRM_GEM
Wi-Fi: normal
SSH: normal
Qwen2.5-0.5B: ready
Qwen2.5-1.5B: ready
Qwen3-4B-W8A8-RK3588: blocked
```

Qwen3-4B 最终阻塞原因：

```text
RKNPU driver 已升级到 v0.9.8；
RKLLM runtime 已可识别 RKNPU 0.9.8；
DRM_GEM 路径下 Qwen3-4B 仍因 4022272000 bytes NPU DMA/IOVA 映射失败而无法加载；
DMA_HEAP 实验版可启动但 RKLLM runtime 无法打开 RKNPU/RKNN 设备；
因此 Qwen3-4B-W8A8-RK3588 当前保持 blocked。
```

## 9. 阶段结论

本阶段完成了：

```text
1. R8 SDK 恢复；
2. RKNPU driver 0.9.8 替换；
3. RKNPU 0.9.8 编译兼容修复；
4. boot.img 重新构建；
5. 开发板 boot 分区刷写；
6. rtl8733bu Wi-Fi 模块修复；
7. RKNPU 0.9.8 稳定版验证；
8. Qwen2.5-1.5B 回归验证；
9. Qwen3-4B DRM_GEM 路径失败定位；
10. DMA_HEAP 实验版验证；
11. 回滚到 DRM_GEM 稳定版。
```

最终工程结论：

```text
RKNPU 0.9.8 升级成功；
Qwen2.5-0.5B 与 Qwen2.5-1.5B 是当前可运行 RKLLM 模型；
Qwen3-4B 当前受 RKNPU 大块 IOVA/DMA 映射限制，暂不继续投入；
后续工作应转向可运行模型的系统化应用开发。
```

## 10. 后续工作建议

后续不建议继续围绕 Qwen3-4B 修改内核，而应转向：

```text
1. 在 RKNPU 0.9.8 稳定内核下重新跑 Qwen2.5-0.5B 和 Qwen2.5-1.5B benchmark；
2. 以 Qwen2.5-1.5B 作为主力板端 LLM；
3. 以 Qwen2.5-0.5B 作为轻量低延迟基线；
4. 编写统一 LLM 推理入口脚本；
5. 开发板端 LLM 服务接口；
6. 整理大模型部署阶段总结。
```
