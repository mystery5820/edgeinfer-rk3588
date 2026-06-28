# Phase 5：YOLOv11 模型压缩 V2

## 背景

上一版 slim_width016 模型压缩过于激进，并且当前 RKNN 文件属于 init 版本，不适合作为最终压缩模型。V2 阶段重新设计压缩流程，重点从“极限缩小模型”调整为“在可接受精度下降范围内提升 RK3588 端侧推理性能”。

## V2 目标

1. 保留 YOLOv11n baseline 作为对照；
2. 采用温和结构化剪枝，而不是直接大幅缩小宽度；
3. 生成 prune10、prune20、prune30 三类候选模型；
4. 每个候选模型都必须经过 fine-tune；
5. 每个候选模型都导出 ONNX 和 RKNN；
6. 最终以 RK3588 板端真实推理速度和检测效果作为选择依据。

## 候选模型

- YOLOv11n-Baseline
- YOLOv11n-Prune10-Finetune
- YOLOv11n-Prune20-Finetune
- YOLOv11n-Prune30-Finetune

## 压缩原则

1. 不再使用 width016 作为最终模型；
2. 不使用未经 fine-tune 的 init 模型作为最终结果；
3. 不只看模型大小，重点看 mAP、NPU inference_ms、端到端 FPS；
4. 剪枝比例从小到大逐步测试；
5. 以 mAP 下降不超过 1%～3% 为优先约束。

## 评估指标

- model_size_mb
- params
- FLOPs
- mAP50
- mAP50-95
- RKNN inference_ms
- postprocess_ms
- end_to_end_ms
- FPS
- num_detections

## 实验目录

    experiments/yolo11_compress_v2

## 后续流程

1. 建立 baseline 评估结果；
2. 生成温和剪枝候选模型；
3. 对候选模型 fine-tune；
4. 导出 ONNX；
5. 转换 RKNN INT8；
6. 板端 Benchmark；
7. 选择最优模型进入 model_registry.yaml。
