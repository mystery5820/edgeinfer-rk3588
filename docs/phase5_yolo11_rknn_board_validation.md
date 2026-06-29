# YOLOv11n RKNN 板端部署与验证记录

## 1. 验证目的

本文记录 `edgeinfer-rk3588` 项目中 YOLOv11n baseline 模型在 RK3588 开发板上的 RKNN 部署与验证过程。验证内容覆盖模型导出、RKNN 转换、板端运行环境、FP RKNN 推理结果、INT8 RKNN 异常定位以及当前阶段的工程结论。

本阶段的目标不是单纯追求模型体积最小或推理速度最高，而是优先完成一条可复现、可运行、结果有效的视觉模型板端部署链路，为后续摄像头接入、C++ 后处理优化和 INT8 量化优化提供基础。

## 2. 模型与文件说明

本次验证使用的源模型为 YOLOv11n baseline 权重：

```text
models/vision/yolo11/weights/yolo11n_baseline.pt
```

该模型已导出为静态输入尺寸的 ONNX 模型：

```text
models/vision/yolo11/onnx/yolo11n_baseline_640.onnx
```

ONNX 输入尺寸为：

```text
640 × 640
```

在此基础上，生成并测试了两个 RKNN 模型：

```text
models/vision/yolo11/rknn/yolo11n_baseline_fp_rk3588.rknn
models/vision/yolo11/rknn/yolo11n_baseline_i8_rk3588.rknn
```

其中，FP RKNN 模型作为当前阶段的有效部署模型；INT8 RKNN 模型虽然可以加载并推理，但类别分支输出异常，暂不作为有效部署模型使用。

## 3. 板端运行环境

开发板平台为 RK3588，板端推理使用 RKNNLite2 Python 接口。

板端运行环境已经升级并验证为：

```text
RKNNLite2 Python package : 2.3.2
librknnrt.so             : 2.3.2
Target platform          : RK3588
Runtime backend          : rknnlite
```

升级前，板端 `librknnrt.so` 版本较低，运行 RKNN Toolkit 2.3.2 转换出的模型时存在版本不匹配提示。升级到 2.3.2 后，工具链与 runtime 版本保持一致，但 INT8 模型类别分支全 0 的问题仍然存在。

因此，当前 INT8 异常不能简单归因于 runtime 版本不匹配。

## 4. 输入维度问题修正

最初运行 RKNNLite 推理时出现如下错误：

```text
The input[0] need 4dims input, but 3dims input buffer feed.
```

该问题的原因是推理脚本传入的是三维图像数据：

```text
H × W × C
```

而 RKNN 模型需要四维输入：

```text
1 × H × W × C
```

后续在板端 benchmark 中加入 batch 维度后，模型可以正常进入推理流程。因此，板端 YOLO benchmark 脚本需要默认使用 `--add-batch` 参数。

## 5. FP RKNN 验证结果

FP RKNN 模型在 RK3588 开发板上能够正常完成推理，并输出有效的类别分数和检测结果。

板端 benchmark 配置如下：

```text
Model       : YOLOv11n-FP-Baseline
Runtime     : rknnlite
Input size  : 640 × 640
Images      : 20
Warmup      : 5
Repeat      : 5
Samples     : 100
Conf thres  : 0.25
IoU thres   : 0.45
```

板端测试结果如下：

| 指标 | 数值 |
|---|---:|
| 模型大小 | 7.347 MB |
| 平均预处理耗时 | 19.992 ms |
| 平均推理耗时 | 147.135 ms |
| 平均后处理耗时 | 21.736 ms |
| 平均端到端耗时 | 188.874 ms |
| 平均 FPS | 5.29 |
| 平均检测框数量 | 3.05 |

该结果说明，当前项目已经完成以下有效链路：

```text
PT 权重 → ONNX 导出 → RKNN FP 转换 → RK3588 板端 RKNNLite 推理 → YOLO 后处理 → CSV/Markdown 报告生成
```

因此，`YOLOv11n-FP-Baseline` 可以作为当前阶段的有效视觉部署模型。

## 6. INT8 RKNN 异常现象

INT8 RKNN 模型可以在 RK3588 开发板上正常加载和执行推理，输出 shape 也符合 YOLOv11 的预期格式：

```text
(1, 84, 8400)
```

其中：

```text
前 4 个通道：bbox 坐标
后 80 个通道：类别分数
```

实际测试发现，INT8 模型的 bbox 分支存在正常数值，但类别分支全部为 0：

```text
boxes min/max/mean: 正常
cls min/max/mean  : 0.0 0.0 0.0
```

由于 YOLO 后处理需要根据类别分数进行置信度过滤，当所有类别分数均为 0 时，所有候选框都会被过滤掉，最终检测结果为空：

```text
Avg detections: 0.00
```

因此，该 INT8 模型虽然可以运行，但检测结果无效，不能作为正式部署模型使用。

## 7. INT8 异常排查过程

针对 INT8 类别分支全 0 的问题，已完成以下排查：

1. 检查输入维度
   加入 batch 维度后，模型可以正常推理，说明问题不是输入维度导致。

2. 检查输出 shape
   INT8 输出 shape 为 `(1, 84, 8400)`，与 YOLOv11 预期输出一致，说明模型输出结构没有丢失。

3. 对比 FP RKNN
   FP RKNN 类别分数正常，最高类别分数约为 `0.8598633`，说明 ONNX 模型、输入预处理、RKNNLite 推理和后处理逻辑本身是有效的。

4. 升级 runtime
   板端 `librknnrt.so` 已升级到 2.3.2，但 INT8 类别分支仍然全 0，说明问题不是单纯由 runtime 版本不匹配造成。

5. 降低优化等级
   使用 `optimization_level=0` 重新转换 INT8 RKNN 后，类别分支仍然全 0。

6. 尝试混合量化
   使用 `auto_hybrid=True` 重新转换后，类别分支仍然全 0。

经过上述排查，可以认为当前 INT8 异常主要与该 ONNX 结构的 INT8 量化方式有关，而不是普通的后处理阈值、NMS、输入格式或 runtime 版本问题。

## 8. 工程结论

当前阶段采用如下结论：

```text
YOLOv11n-FP-Baseline：作为当前有效部署模型
YOLOv11n-INT8-Baseline：保留为 debug 模型，不作为有效检测模型
```

FP RKNN 模型虽然推理速度低于理想 INT8 模型，但它已经完成了有效检测闭环，具备工程可用性。

INT8 RKNN 模型当前的主要问题是类别分支输出全 0，会直接导致检测结果为空。因此该问题不能忽略，也不能通过降低置信度阈值解决。

## 9. 后续优化方向

后续如果继续推进 INT8 部署，不建议继续沿用当前完整 decode 后输出 `(1, 84, 8400)` 的 ONNX 结构直接量化。

更合理的方向是参考 RKNN Model Zoo 的 YOLO11 转换方式：

```text
模型侧保留原始检测头输出
decode / sigmoid / NMS 放到 Python 或 C++ 后处理侧完成
```

这种方式可以减少复杂后处理算子在 INT8 图中的量化风险，更适合 RKNN 端侧部署。

后续优化路线建议如下：

1. 保留 FP RKNN 作为当前可复现的有效部署版本；
2. 将板端 benchmark 脚本默认切换到 `YOLOv11n-FP-Baseline`；
3. 默认启用 `--add-batch`，避免三维输入问题；
4. 单独开启下一阶段工作，基于 RKNN Model Zoo YOLO11 路线重新设计 INT8 转换和后处理；
5. 后处理优先从 Python 验证，后续再迁移到 C++，用于提升端到端性能。
