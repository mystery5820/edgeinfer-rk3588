# Phase 3：YOLOv11 Benchmark 接入后处理

## 目标

将 YOLOv11 Python 后处理模块接入 Benchmark 脚本，使离线图片 Benchmark 能统计完整链路：

    preprocess
    -> RKNN inference
    -> YOLO decode + NMS
    -> detections count
    -> CSV report

## 更新内容

本阶段更新脚本：

    tools/benchmark_yolo11_rknn.py

新增统计字段：

- conf_thres
- iou_thres
- num_outputs
- num_detections
- postprocess_ms

## dry-run 模式

在 Ubuntu 虚拟机中，dry-run 模式会生成一个假的 YOLO 输出，用于验证后处理链路。

运行：

    source scripts/activate_rknn_env.sh
    python tools/benchmark_yolo11_rknn.py \
      --model YOLOv11n-INT8-Baseline \
      --runtime dryrun \
      --limit 5 \
      --repeat 2
    deactivate

预期结果：

- CSV 能正常生成；
- num_outputs 应大于 0；
- num_detections 通常为 2；
- postprocess_ms 不再一直为 0。

## RK3588 板端模式

在 RK3588 板端使用真实 NPU 推理时运行：

    python tools/benchmark_yolo11_rknn.py \
      --model YOLOv11n-INT8-Baseline \
      --runtime rknnlite \
      --limit 50 \
      --repeat 5

也可以测试 slim 模型：

    python tools/benchmark_yolo11_rknn.py \
      --model YOLOv11n-INT8-Slim016-Init \
      --runtime rknnlite \
      --limit 50 \
      --repeat 5

## 当前限制

1. 当前后处理假设 YOLO 输出为单输出格式；
2. 不同 RKNN 导出方式可能导致输出 shape 不同；
3. 板端首次测试时应先打印 outputs shape；
4. 当前 NMS 是 Python / NumPy 实现，后续会迁移到 C++。

## 后续计划

1. 在 Benchmark 中增加 output shape 打印选项；
2. 增加 P50 / P95 延迟统计；
3. 增加检测结果可视化保存；
4. 增加 C++ 后处理版本；
5. 增加摄像头实时检测 Benchmark。
