# Phase 4：RK3588 板端部署打包

## 目标

将 PC 侧完成的 YOLOv11 Benchmark 框架整理为可拷贝到 RK3588 开发板的部署包，用于后续真实 NPU 推理测试。

## 当前脚本

打包脚本：

    scripts/package_for_board.sh

板端运行脚本：

    scripts/run_board_yolo_benchmark.sh

## 生成结果

执行打包脚本后生成：

    dist/edgeinfer-rk3588-board
    dist/edgeinfer-rk3588-board.tar.gz

## 打包内容

1. configs 模型注册与运行配置；
2. tools Benchmark、汇总、模型检查脚本；
3. server/vision YOLO 后处理模块；
4. YOLOv11 baseline RKNN 模型；
5. YOLOv11 slim016 RKNN 模型；
6. 少量 coco128 测试图片；
7. README_BOARD.md 板端运行说明。

## 注意事项

dist/ 目录包含 RKNN 模型和测试图片，已经加入 .gitignore，不提交到 GitHub。

## 板端运行方式

解压：

    tar -xzf edgeinfer-rk3588-board.tar.gz
    cd edgeinfer-rk3588-board

检查资产：

    python3 tools/list_models.py
    python3 tools/check_assets.py

运行 baseline：

    bash scripts/run_board_yolo_benchmark.sh YOLOv11n-INT8-Baseline

运行 slim016：

    bash scripts/run_board_yolo_benchmark.sh YOLOv11n-INT8-Slim016-Init

## 后续计划

1. 将部署包拷贝到 RK3588 开发板；
2. 安装 rknnlite runtime；
3. 运行真实 NPU Benchmark；
4. 打印并确认 RKNN outputs shape；
5. 修正后处理适配真实输出；
6. 对 baseline 和 slim016 进行真实板端性能对比。
