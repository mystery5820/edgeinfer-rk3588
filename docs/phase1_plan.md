# Phase 1：项目框架重构计划

## 目标

将已有 RKNN / RKLLM 实验整理为统一端侧多模型推理服务框架。

## 本阶段任务

1. 完成项目目录统一
2. 建立模型注册配置
3. 建立 server / scheduler / benchmark 配置
4. 保留 Qwen2.5 0.5B / 1.5B 作为 baseline
5. 保留 YOLOv11 作为视觉推理基线
6. 搭建 Model Manager 雏形
7. 搭建 Benchmark 脚本雏形

## 暂不做

1. 暂不下载 Qwen3
2. 暂不接入 VLM
3. 暂不重写 C++ 后处理
4. 暂不做复杂多模型调度

## 下一阶段

Phase 2：实现统一模型管理与 Benchmark。
