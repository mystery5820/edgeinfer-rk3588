# Phase 13：项目工程化整理与对外展示

本文档记录 Phase 13 对项目 README 与文档导航的整理。

---

## 1. 背景

在 Phase 9 到 Phase 12B 中，项目已经完成端侧 LLM Serving 主线：

```text
OpenAI-like Chat API
worker stream=true SSE
OpenAI Python SDK examples
estimated usage
finish_reason=length 语义调研
```

此时原 README 已经不能完整表达当前项目能力，因此 Phase 13 开始对外展示层面的整理。

---

## 2. 本阶段目标

Phase 13 第一阶段目标：

```text
1. 重写 README，使其具备开源项目首页的基本结构；
2. 增加当前能力矩阵；
3. 增加架构概览；
4. 增加 Quick Start；
5. 增加 API 示例；
6. 增加 OpenAI SDK 示例入口；
7. 增加 docs/README.md 文档导航；
8. 明确当前限制；
9. 保留已完成 tag 列表；
10. 不改 server / runtime 运行时代码。
```

---

## 3. 改动范围

本阶段只改文档：

```text
README.md
docs/README.md
docs/phase13_project_showcase.md
```

不修改：

```text
server/
scripts/
tools/
configs/
```

因此本阶段不需要重新上板验证。只需要：

```bash
git diff --check
```

以及人工检查 README 和 docs 结构即可。

---

## 4. 当前展示重点

README 当前重点展示：

```text
1. RK3588 端侧多模型推理服务框架；
2. YOLOv11 RKNN 板端验证；
3. Qwen3-4B RKLLM all-NPU Serving；
4. OpenAI-like Chat Completions；
5. persistent worker stream=true SSE；
6. estimated usage；
7. host/board 自动化验收；
8. systemd 工程化部署。
```

---

## 5. 后续建议

后续 Phase 13 可以继续补充：

```text
1. 架构图图片；
2. API 响应示例截图；
3. Demo GIF；
4. benchmark 总表；
5. README 英文版；
6. GitHub release notes；
7. 项目答辩 / 简历版总结。
```
