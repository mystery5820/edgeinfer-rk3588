# Phase 2：模型注册与资产检查

## 目标

建立 EdgeInfer-RK3588 的模型注册机制，为后续 Benchmark、Serving、模型切换和调度模块提供统一入口。

本阶段不直接实现推理服务，而是先解决项目中的模型资产管理问题，包括：

1. 哪些模型已经注册；
2. 每个模型属于什么任务类型；
3. 使用 RKNN 还是 RKLLM 后端；
4. 源模型文件在哪里；
5. 板端运行时模型文件在哪里；
6. 当前模型是否已经可用于 Benchmark 或 Serving；
7. 如何避免大模型文件被误提交到 GitHub。

---

## 当前实现

### 1. 模型注册表

配置文件：

```text
configs/model_registry.yaml
```

该文件用于统一描述项目中的模型资产。当前注册内容包括：

- Qwen2.5-0.5B-Instruct
- Qwen2.5-1.5B-Instruct
- YOLOv11

每个模型主要包含以下字段：

```yaml
name: 模型名称
task: 任务类型，例如 text-generation、object-detection、vision-language
backend: 推理后端，例如 rkllm、rknn
source_dir: 源模型目录
runtime_model: 板端运行时模型文件
quantization: 量化格式，例如 W8A8、INT8、W4A16
max_context: LLM 最大上下文长度
input_size: 视觉模型输入尺寸
status: 当前状态，例如 baseline、todo、ready
```

模型注册表是后续 Model Manager、Benchmark、Serving API 和多模型调度模块的基础。

---

### 2. 模型列表工具

脚本路径：

```text
tools/list_models.py
```

运行方式：

```bash
source scripts/activate_rknn_env.sh
python tools/list_models.py
deactivate
```

功能：

- 读取 `configs/model_registry.yaml`
- 列出当前所有注册模型
- 显示模型名称、任务类型、推理后端、量化格式和状态

预期输出示例：

```text
========================================================================================
Name                             Task               Backend  Quant      Status
========================================================================================
Qwen2.5-0.5B-Instruct            text-generation    rkllm    W8A8       baseline
Qwen2.5-1.5B-Instruct            text-generation    rkllm    W8A8       baseline
YOLOv11                          object-detection   rknn     INT8       todo
========================================================================================
Total models: 3
```

---

### 3. 资产检查工具

脚本路径：

```text
tools/check_assets.py
```

运行方式：

```bash
source scripts/activate_rknn_env.sh
python tools/check_assets.py
deactivate
```

功能：

- 检查每个模型的 `source_dir` 是否存在；
- 检查每个模型的 `runtime_model` 是否存在；
- 输出缺失资产，方便后续补齐；
- 作为后续 Benchmark 和 Serving 启动前的预检查工具。

当前阶段中，Qwen2.5 的源模型和 RKLLM 转换产物应当已经存在；YOLOv11 的 `runtime_model` 暂时可以为空，因为后续 Phase 3 会重新整理 YOLOv11 的 ONNX / RKNN / INT8 导出结果。

---

### 4. Git 大文件检查工具

脚本路径：

```text
tools/check_git_large_files.sh
```

运行方式：

```bash
bash tools/check_git_large_files.sh
```

功能：

- 检查 Git 是否正在追踪大模型文件；
- 避免 `.safetensors`、`.bin`、`.pt`、`.pth`、`.onnx`、`.rknn`、`.rkllm` 等大文件被误提交到 GitHub；
- 作为后续每次提交前的安全检查。

如果输出：

```text
OK: no large model files are tracked by Git.
```

说明当前 Git 仓库没有追踪大模型文件，可以正常提交。

---

## 当前目录关系

项目统一工作目录：

```text
~/edgeinfer-rk3588
```

本地大模型和工具包目录：

```text
models/
datasets/
experiments/
third_party/
```

这些目录只保存在本地，不提交到 GitHub。

GitHub 只提交：

```text
README.md
.gitignore
configs/
docs/
scripts/
tools/
envs/
```

这样可以保证仓库轻量、干净，同时本地仍然保留完整模型和实验资产。

---

## 当前阶段的意义

Phase 2 的核心价值不是提升推理速度，而是为后续系统化优化打基础。

如果没有统一模型注册表，后续 Benchmark、Serving、多模型调度都会变成脚本堆叠；有了模型注册机制后，后续可以做到：

1. Benchmark 自动遍历模型；
2. Web 服务按模型名加载模型；
3. 模型切换通过配置完成；
4. 多模型调度器根据 task/backend/quantization 做策略决策；
5. 新增 Qwen3、Qwen3.5、VLM 模型时只需要增加配置项。

---

## 后续计划

### Phase 3：YOLOv11 RKNN 模型资产整理与 Benchmark 框架

计划内容：

1. 查找已有 YOLOv11 ONNX / RKNN / INT8 模型；
2. 统一放入 `models/vision/yolo11/`；
3. 为 YOLOv11 增加 `model.yaml`；
4. 更新 `configs/model_registry.yaml`；
5. 创建 YOLOv11 Benchmark 脚本；
6. 统计 preprocess、inference、postprocess 和端到端耗时。

### Phase 4：LLM Benchmark 框架

计划内容：

1. 基于 Qwen2.5-0.5B 和 Qwen2.5-1.5B 建立 LLM Benchmark；
2. 统计 TTFT、prefill tokens/s、decode tokens/s、总耗时和内存占用；
3. 为后续 Qwen3 / Qwen3.5 模型加入对比基线。

### Phase 5：Serving Runtime

计划内容：

1. 搭建 FastAPI 服务；
2. 提供 OpenAI-like Chat API；
3. 提供 Vision Detect API；
4. 提供 `/v1/models` 和 `/v1/health`；
5. 基于模型注册表完成模型加载和切换。

### Phase 6：多模型调度与资源监控

计划内容：

1. 支持 LLM 请求队列；
2. 支持 YOLO 与 LLM 并发测试；
3. 实现 LLM 运行时 YOLO 动态降帧；
4. 采集 CPU、内存、温度和端到端延迟；
5. 输出并发 Benchmark 报告。

---

## 本阶段验收标准

执行以下命令：

```bash
python tools/list_models.py
python tools/check_assets.py
bash tools/check_git_large_files.sh
```

如果能够完成以下结果，则 Phase 2 初步完成：

1. 能正常列出注册模型；
2. 能检查模型资产是否存在；
3. 能发现缺失的 YOLOv11 runtime_model；
4. Git 未追踪大模型文件；
5. 工具脚本和文档已提交到 GitHub。

