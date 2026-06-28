# Phase 3：YOLOv11 后处理模块

## 目标

建立 YOLOv11 decode + NMS 后处理模块，为后续完整目标检测链路 Benchmark 做准备。

当前阶段先实现 Python / NumPy 版本后处理，后续再迁移为 C++ 后处理，用于降低端到端推理延迟。

## 当前实现

后处理模块：

    server/vision/yolo_postprocess.py

测试脚本：

    tools/test_yolo_postprocess.py

## 当前支持能力

1. 支持 YOLOv8 / YOLOv11 常见输出布局；
2. 支持 [1, 84, 8400]、[84, 8400]、[1, 8400, 84]、[8400, 84] 等格式；
3. 支持单元测试中的小样本输出 [1, 84, 4]；
4. 支持 xywh 到 xyxy 坐标转换；
5. 支持 confidence threshold；
6. 支持 class-agnostic NMS；
7. 支持输出 detection 字典列表。

## 当前限制

1. 当前后处理默认使用单输出 YOLO 格式；
2. 不同 RKNN 导出方式可能导致输出张量格式不同，板端测试时需要根据实际输出 shape 调整；
3. 当前 NMS 是 Python / NumPy 实现，后续需要迁移到 C++；
4. 当前尚未与 benchmark_yolo11_rknn.py 完全集成。

## 验证方式

运行：

    source scripts/activate_rknn_env.sh
    python tools/test_yolo_postprocess.py
    deactivate

预期输出：

    YOLO postprocess test passed.

## 后续计划

1. 在 RK3588 板端打印 YOLOv11 RKNN 实际输出 shape；
2. 将后处理接入 tools/benchmark_yolo11_rknn.py；
3. 增加 num_detections、postprocess_ms、NMS 耗时统计；
4. 与 baseline / slim016 两个 RKNN 模型进行对比；
5. 将 Python 后处理迁移为 C++ 后处理。
