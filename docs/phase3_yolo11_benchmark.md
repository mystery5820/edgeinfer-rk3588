# Phase 3：YOLOv11 Benchmark 初版

## 目标

建立 YOLOv11 离线图片 Benchmark 框架，优先统计模型预处理耗时、RKNN 推理耗时和端到端耗时，为后续端侧实时摄像头检测、多线程流水线和 C++ 后处理优化打基础。

## 当前脚本

脚本路径：

    tools/benchmark_yolo11_rknn.py

## 当前支持模型

模型来自：

    configs/model_registry.yaml

当前主要支持：

    YOLOv11n-INT8-Baseline
    YOLOv11n-INT8-Slim016-Init

## PC 侧 dry-run 测试

在 Ubuntu 虚拟机中可以先运行 dry-run，验证图片读取、预处理、模型注册表和 CSV 输出流程：

    source scripts/activate_rknn_env.sh
    python tools/benchmark_yolo11_rknn.py \
      --model YOLOv11n-INT8-Baseline \
      --runtime dryrun \
      --limit 10 \
      --repeat 2
    deactivate

dry-run 不代表真实 NPU 推理性能，只用于验证 Benchmark 框架是否正常。

## RK3588 板端测试

在 RK3588 开发板上部署好 RKNN runtime 后，运行：

    python tools/benchmark_yolo11_rknn.py \
      --model YOLOv11n-INT8-Baseline \
      --runtime rknnlite \
      --limit 50 \
      --repeat 5

也可以测试优化模型：

    python tools/benchmark_yolo11_rknn.py \
      --model YOLOv11n-INT8-Slim016-Init \
      --runtime rknnlite \
      --limit 50 \
      --repeat 5

## 输出结果

默认输出：

    results/benchmark/yolo11_benchmark.csv

当前 CSV 字段包括：

- model_name
- runtime
- image_path
- repeat_idx
- input_size
- add_batch
- model_size_mb
- preprocess_ms
- inference_ms
- postprocess_ms
- end_to_end_ms
- fps
- ok
- error

## 当前限制

1. 当前后处理仍是占位；
2. 暂未实现 YOLO decode 和 NMS；
3. dry-run 不能代表真实性能；
4. RKNNLite 真实推理需要在 RK3588 板端运行；
5. 后续需要补充摄像头实时检测 Benchmark。

## 后续计划

1. 增加 YOLO decode；
2. 增加 NMS；
3. 增加 P50 / P95 延迟统计；
4. 增加多模型横向对比报告；
5. 增加摄像头端到端 FPS；
6. 增加 C++ 后处理版本。
