# Phase 5：YOLOv11 压缩 V2 Pipeline

## 背景

旧版 slim_width016 压缩过于激进，并且对应模型属于 init 版本，不适合作为最终压缩模型。V2 阶段重新设计压缩流程，重点从“极限缩小模型”调整为“可验证、可部署、可对比的端侧压缩 Pipeline”。

## 当前环境

当前虚拟机环境为 CPU-only：

- torch 为 CPU 版本；
- CUDA 不可用；
- Ultralytics 已安装；
- YOLOv11 baseline 可以正常加载和推理。

因此当前阶段采用 CPU 友好策略：先完成 Pipeline 骨架、smoke train、权重保存和报告记录，再逐步接入温和剪枝模块。

## 当前脚本

    tools/yolo_compress_v2.py

## 当前支持命令

检查环境：

    python tools/yolo_compress_v2.py check

CPU smoke train：

    python tools/yolo_compress_v2.py smoke-train --epochs 1 --imgsz 320 --batch 2

## 实验目录

    experiments/yolo11_compress_v2

主要子目录：

- configs：数据集配置；
- weights：baseline 和训练后权重；
- runs：Ultralytics 训练输出；
- reports：训练和实验记录；
- onnx_exports：后续 ONNX 导出；
- rknn_exports：后续 RKNN 输出。

## 当前阶段目标

1. 验证 CPU 环境下训练链路可运行；
2. 形成标准化实验目录；
3. 自动保存训练权重；
4. 自动保存 JSON 报告；
5. 后续接入温和结构化剪枝。

## 注意事项

CPU-only 环境不适合长时间正式训练。当前 smoke train 只用于验证流程，不代表最终模型效果。

## 后续计划

1. 增加 baseline mAP 评估；
2. 增加温和剪枝模块；
3. 增加剪枝后短周期 fine-tune；
4. 导出 ONNX；
5. 转换 RKNN；
6. 在 RK3588 板端进行真实 Benchmark。
