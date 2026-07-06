# Phase 18：Realign With Original Multi-Model Design

本文档用于将 `edgeinfer-rk3588` 当前开发状态重新对齐到原始总设计方案。

结论：

```text
当前已经完成的是 LLM Serving milestone；
项目还没有达到完整 multi-model edge AI serving framework 的 release 状态；
Phase 18 应停止 GitHub Release Page 路线，转入 Vision Serving MVP。
```

---

## 1. 原始总设计目标

原始设计中的项目定位是：

```text
EdgeInfer-RK3588: Multi-Model Edge AI Serving Framework
基于 RK3588 NPU 的端侧多模型推理服务框架
```

核心负载：

```text
1. YOLOv11 实时检测；
2. Qwen2.5 / Qwen3 文本生成；
3. VLM 图文问答。
```

核心能力：

```text
1. 模型包管理；
2. 统一 API；
3. 请求队列；
4. 多模型调度；
5. 自动化 Benchmark；
6. systemd 工程化部署；
7. Web Demo；
8. Benchmark 报告；
9. README / 设计文档；
10. 可写入简历的优化数据。
```

因此，完整项目不是单独的 LLM Chat API，而是视觉检测、文本生成、多模态、调度、benchmark 和工程化部署共同组成的端侧推理服务框架。

---

## 2. 当前已经完成的部分

截至 Phase 17C，当前完成最充分的是 LLM Serving 子系统：

```text
FastAPI Serving Framework
/v1/health
/v1/models
/v1/metrics
/v1/chat/completions
OpenAI-like Chat API
max_tokens compatibility
stop sequence support
structured error response
busy rejection
metrics
systemd deployment
one-shot RKLLM backend
persistent worker RKLLM backend
stream=true SSE
OpenAI Python SDK examples
non-streaming benchmark
streaming benchmark
README benchmark snapshot
final checklist
```

这些成果可以定义为：

```text
LLM Serving milestone
```

但不能等同于完整的：

```text
Multi-Model Edge AI Serving Framework MVP
```

---

## 3. 当前关键缺口

| 模块 | 当前状态 | 缺口 |
| --- | --- | --- |
| LLM Chat Serving | 基本完成 | 后续可补精确 tokenizer usage、finish_reason=length |
| OpenAI-like API | 基本完成 | 高级参数暂不支持是合理边界 |
| systemd 部署 | 基本完成 | 后续可补 watchdog / logrotate |
| YOLOv11 RKNN 板端验证 | 有历史验证 | 尚未接入当前 FastAPI Serving |
| Vision Detect API | 未完成 | 缺 `/v1/vision/detect` |
| Vision Stream API | 未完成 | 缺 `/v1/vision/stream` |
| RKNN Backend | 未完成 | 缺 `server/runtime/rknn_backend.py` 服务化封装 |
| Vision Metrics | 未完成 | 缺 preprocess / inference / postprocess / e2e latency |
| Vision Benchmark | 未完成 | 缺 `benchmark_vision_detect.py` 和报告 |
| Vision + LLM 调度 | 未完成 | 缺动态降帧、丢帧、并发 benchmark |
| model.yaml 模型包机制 | 部分完成 | 当前是 registry，尚未升级到 per-model package |
| Web Demo / Dashboard | 未完成 | 缺 dashboard / vision / chat 展示页 |
| VLM 图文问答 | 未完成 | 原计划阶段 4，可延后 |

---

## 4. 为什么暂停 release 页面

当前曾创建正式 tag：

```text
v0.1.0
```

但根据原始总设计，真正的 MVP 至少应包含：

```text
1. YOLOv11n INT8 RKNN 可通过 /v1/vision/detect 调用；
2. YOLOv11n INT8 RKNN 可通过 /v1/vision/stream 调用；
3. Qwen 系列模型可通过 /v1/chat/completions 流式输出；
4. 模型采用 model.yaml 或兼容模型包机制注册和加载；
5. Benchmark 可输出 yolo_report.csv、llm_report.csv 和 report.md；
6. 服务可通过 systemd 开机自启，异常退出后自动恢复。
```

当前满足了 LLM / systemd 的主要部分，但 Vision API、Vision Stream、Vision Benchmark 仍未完成。

因此：

```text
v0.1.0 不应作为正式项目 release；
它更准确地说是 LLM Serving 子系统 checkpoint。
```

---

## 5. 版本策略调整

建议删除 premature `v0.1.0` tag：

```bash
git tag -d v0.1.0
git push origin :refs/tags/v0.1.0
```

保留所有 phase tags：

```text
phase17a-readme-benchmark-snapshot
phase17b-v0.1.0-release-notes
phase17c-v0.1.0-final-checklist
```

这些 phase tags 用于记录 LLM Serving milestone 的阶段性收口，不代表完整项目 release。

真正重新创建 `v0.1.0` 应至少等待：

```text
/v1/vision/detect
/v1/vision/stream
Vision detect benchmark
Vision + LLM concurrency benchmark
README 更新为多模型框架状态
最终 checklist 重新通过
```

---

## 6. 新阶段路线

### Phase 18：Vision Serving MVP

目标：

```text
让 YOLOv11 真正接入当前 FastAPI Serving 框架。
```

建议拆分：

```text
Phase 18A：Realign With Original Multi-Model Design
Phase 18B：Vision API Skeleton
Phase 18C：/v1/vision/detect MVP
Phase 18D：RKNN YOLO Backend Integration
Phase 18E：Vision Detect Host Test
```

验收：

```text
curl 上传图片或指定图片路径；
返回 model、objects、label、score、box、latency_ms；
能在 /v1/models 中看到 YOLO 模型；
能在 /v1/metrics 中看到基础 vision 计数。
```

---

### Phase 19：Vision Benchmark

目标：

```text
为 YOLOv11 detect API 建立可复现 benchmark。
```

建议任务：

```text
scripts/host/benchmark_vision_detect.py
data/benchmark/images/
results/benchmark/vision_detect_*.csv
docs/phase19_vision_benchmark.md
```

核心字段：

```text
model
input_size
preprocess_ms
inference_ms
postprocess_ms
total_ms
objects_count
p50_ms
p95_ms
fps_equivalent
```

---

### Phase 20：Vision Stream

目标：

```text
实现摄像头实时检测流。
```

建议任务：

```text
GET /v1/vision/stream
capture thread
latest-frame queue
drop old frames
MJPEG stream
vision fps metrics
e2e latency metrics
```

---

### Phase 21：Vision + LLM Concurrency

目标：

```text
实现多模型调度亮点。
```

建议任务：

```text
vision_default_fps
vision_degraded_fps
degrade_when_llm_running
policy=none
policy=queue_degrade
scripts/host/benchmark_concurrency.py
```

对比场景：

```text
Vision-only
LLM-only
Vision + LLM without scheduling
Vision + LLM with scheduling
```

---

### Phase 22：Model Package / model.yaml

目标：

```text
从全局 model_registry.yaml 逐步升级为 per-model package。
```

建议路线：

```text
短期：继续兼容 configs/model_registry.yaml；
中期：支持 models/<model_id>/model.yaml；
长期：支持 validate_model_package、checksum、load/switch/rollback。
```

---

### Phase 23：Web Demo / Dashboard

目标：

```text
做对外展示入口。
```

建议页面：

```text
/dashboard
/vision
/chat
/benchmark
```

---

### Phase 24：VLM 图文问答

目标：

```text
完成原始设计中的多模态扩展亮点。
```

接口：

```text
POST /v1/vlm/chat
```

建议等 Vision Serving、LLM Serving、模型包机制和基础资源调度稳定后再做。

---

## 7. 近期执行顺序

建议立即执行：

```text
1. 删除 premature v0.1.0 tag；
2. 提交本 realign 文档；
3. 打 phase18-realign-original-design tag；
4. 开始 Phase 18B Vision API Skeleton。
```

---

## 8. Phase 18B 建议内容

Phase 18B 不应一开始就接真实 RKNN runtime，而应先搭好 API skeleton。

建议新增：

```text
server/api/vision_api.py
server/runtime/vision_types.py
server/runtime/fake_vision_backend.py
scripts/host/test_vision_detect_client.py
docs/phase18b_vision_api_skeleton.md
```

API：

```text
POST /v1/vision/detect
```

第一版可先支持：

```text
1. model 参数；
2. image_path 参数或 multipart file；
3. 返回固定格式；
4. 返回 latency_ms；
5. 与 /v1/models 中的 object-detection 模型关联；
6. 对非 vision 模型返回 model_not_vision。
```

先稳定 API contract，再接真实 RKNN YOLO backend。

---

## 9. 阶段结论

当前项目方向调整如下：

```text
过去几阶段完成的是 LLM Serving milestone；
下一阶段回到原始总设计，补齐 Vision Serving；
暂不创建 GitHub Release 页面；
删除 premature v0.1.0 tag；
真正的 v0.1.0 等 Vision API、Vision Stream、Vision Benchmark 和 Vision + LLM concurrency 完成后再创建。
```
