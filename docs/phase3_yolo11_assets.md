# Phase 3：YOLOv11 模型资产整理与 Benchmark 框架

## 目标

本阶段围绕 YOLOv11 视觉模型建立统一资产管理和 Benchmark 基础，为后续端侧视觉推理优化、多线程流水线、C++ 后处理和 Vision + LLM 并发调度打基础。

本阶段不直接追求新的 FPS 提升，而是先把已有 YOLOv11 权重、ONNX、RKNN、INT8 量化模型、剪枝蒸馏结果和验证报告整理清楚，形成可复用的视觉模型资产结构。

## 本阶段重点

1. 扫描已有 YOLOv11 模型资产；
2. 识别 PyTorch、ONNX、RKNN、INT8 模型文件；
3. 建立 models/vision/yolo11/ 本地模型包；
4. 更新 configs/model_registry.yaml 中的 YOLOv11 配置；
5. 后续实现 YOLOv11 Benchmark 脚本；
6. 统计 preprocess、NPU inference、postprocess 和端到端耗时；
7. 为后续 C++ 后处理、多线程流水线和多模型并发调度做准备。

## 当前模型包目录

当前本地模型包目录规划如下：

    models/vision/yolo11/
    ├── weights/
    ├── onnx/
    ├── rknn/
    ├── configs/
    ├── reports/
    └── benchmark/

目录说明：

- weights：保存 YOLOv11 的 PyTorch 权重文件，例如 .pt / .pth；
- onnx：保存导出的 ONNX 模型；
- rknn：保存转换后的 RKNN 模型；
- configs：保存类别文件、数据集配置、量化配置等；
- reports：保存剪枝、蒸馏、验证、转换报告；
- benchmark：保存本地 Benchmark 输出结果。

该目录只保存本地资产，不提交到 GitHub。GitHub 只提交工具脚本、配置文件和文档。

## 资产扫描工具

脚本路径：

    tools/scan_yolo_assets.py

运行方式：

    source scripts/activate_rknn_env.sh
    python tools/scan_yolo_assets.py
    deactivate

功能说明：

1. 扫描 experiments/yolo11_prune；
2. 扫描 models/vision；
3. 列出 .pt、.pth、.onnx、.rknn、.yaml、.json、.csv、.md、.log 等文件；
4. 显示文件大小、修改时间和相对路径；
5. 为后续选择 YOLOv11 baseline 模型和优化模型提供依据。

## 需要重点关注的资产类型

### 1. PyTorch 权重

常见后缀：

    .pt
    .pth

用途：

- 作为训练、剪枝、蒸馏和 fine-tune 的源模型；
- 用于导出 ONNX；
- 用于对比 baseline 模型和优化模型的参数量、精度和体积。

### 2. ONNX 模型

常见后缀：

    .onnx

用途：

- 作为 RKNN 转换的输入；
- 用于 PC 侧 ONNX Runtime 推理对比；
- 用于定位 RKNN 转换前后的输出差异。

### 3. RKNN 模型

常见后缀：

    .rknn

用途：

- 作为 RK3588 NPU 的实际运行模型；
- 用于板端 Benchmark；
- 用于后续模型注册表中的 runtime_model 字段。

### 4. 报告与日志

常见后缀：

    .csv
    .md
    .log
    .json

用途：

- 保存剪枝率、mAP、FPS、延迟、模型大小等实验结果；
- 为后续简历描述和项目 README 提供数据依据；
- 方便复现实验结论。

## 后续资产整理原则

YOLOv11 资产整理时，不建议把所有历史文件都堆到模型目录里。建议按用途选择关键版本：

1. 保留一个 baseline PyTorch 权重；
2. 保留一个 baseline ONNX；
3. 保留一个 baseline RKNN INT8；
4. 保留一个剪枝 + 蒸馏后的 PyTorch 权重；
5. 保留一个剪枝 + 蒸馏后的 ONNX；
6. 保留一个剪枝 + 蒸馏后的 RKNN INT8；
7. 保留必要的验证报告和 Benchmark 结果；
8. 过旧的临时日志、重复导出文件和无用中间文件可以不纳入模型包。

## 模型注册表更新计划

当前 configs/model_registry.yaml 中 YOLOv11 可能仍处于以下状态：

    name: YOLOv11
    task: object-detection
    backend: rknn
    source_dir: experiments/yolo11_prune
    runtime_model: null
    quantization: INT8
    input_size: [640, 640]
    status: todo

完成 YOLOv11 资产整理后，应更新为类似：

    name: YOLOv11
    task: object-detection
    backend: rknn
    source_dir: models/vision/yolo11
    runtime_model: models/vision/yolo11/rknn/yolo11n_int8.rknn
    quantization: INT8
    input_size: [640, 640]
    status: ready

如果同时保留 baseline 和优化模型，后续可以注册为两个模型：

    YOLOv11n-INT8-Baseline
    YOLOv11n-INT8-Pruned-Distilled

这样 Benchmark 时可以直接对比二者的速度、延迟、模型大小和精度变化。

## Benchmark 设计

YOLOv11 Benchmark 后续需要统计以下指标：

- model_name
- quantization
- input_size
- image_count
- preprocess_ms
- rknn_inference_ms
- postprocess_ms
- end_to_end_ms
- fps
- cpu_usage
- memory_mb
- npu_core
- model_size_mb

推荐输出 CSV：

    results/benchmark/yolo11_benchmark.csv

推荐后续生成 Markdown 报告：

    results/benchmark/yolo11_benchmark_report.md

## 端到端链路拆分

后续视觉链路应拆分为：

    image / camera input
    -> preprocess
    -> RKNN inference
    -> postprocess
    -> draw boxes / encode
    -> HTTP stream or image output

其中最重要的是区分：

1. 纯 NPU 推理耗时；
2. 预处理耗时；
3. 后处理耗时；
4. Web 或摄像头端到端耗时。

这样可以避免只展示纯推理 FPS，而忽略真实端到端性能。

## 后续优化方向

### 1. C++ 后处理

将 YOLO decode 和 NMS 从 Python 改为 C++，降低 Python 后处理开销。

### 2. 多线程流水线

将摄像头读取、预处理、NPU 推理、后处理和 Web 输出拆成不同线程，减少阻塞。

### 3. 队列限长与丢帧策略

实时摄像头场景下，不应无限排队旧帧。后续应使用有限队列，并在推理延迟过高时丢弃旧帧。

### 4. NPU core 配置对比

对比单核、双核和三核 NPU 配置下的 YOLOv11 推理耗时和端到端 FPS。

### 5. Vision + LLM 并发调度

YOLOv11 将作为实时视觉 workload，与 Qwen LLM 同时运行，用于测试资源争用、动态降帧和服务稳定性。

## 本阶段验收标准

本阶段初步完成的标准：

1. tools/scan_yolo_assets.py 可以正常运行；
2. 能列出已有 YOLOv11 的 PyTorch、ONNX、RKNN 文件；
3. models/vision/yolo11/ 本地模型包目录已建立；
4. docs/phase3_yolo11_assets.md 已提交到 GitHub；
5. 未提交任何 .pt、.onnx、.rknn 等大模型文件；
6. 下一步能够根据扫描结果选择 YOLOv11 baseline 和优化模型。

## 下一阶段

Phase 3 后续小步骤：

1. 运行 YOLOv11 资产扫描；
2. 根据扫描结果选择可用的 RKNN 模型；
3. 将关键 YOLOv11 资产复制到 models/vision/yolo11/；
4. 更新 configs/model_registry.yaml；
5. 编写第一版 YOLOv11 Benchmark 脚本；
6. 生成第一版 yolo11_benchmark.csv。
