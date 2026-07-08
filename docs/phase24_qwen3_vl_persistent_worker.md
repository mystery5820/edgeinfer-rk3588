# Phase 24: Qwen3-VL Persistent Worker

## 1. 背景

Phase 22 已经完成 Qwen3-VL-2B 在 RK3588 上的真实 VLM 服务化：

```text
image -> RKNN vision encoder -> RKLLM decoder -> answer
```

Phase 23 完成了 Qwen3-VL 后端的并发保护和 benchmark。

但 Phase 22/23 使用的是 one-shot subprocess 模式：

```text
每次 /v1/infer 请求
  -> 启动 VLM_NPU
  -> 加载 RKLLM decoder
  -> 加载 RKNN vision encoder
  -> 推理
  -> 进程退出
```

这种方式可靠，但每次请求都会重复初始化模型，导致端到端延迟通常在 20s 到 32s 左右。

Phase 24 的目标是引入 persistent worker：

```text
服务内启动 VLM_NPU_WORKER
  -> RKLLM / RKNN 只初始化一次
  -> 每次请求只发送 image_path + prompt
  -> worker 返回 answer
  -> 后续请求复用同一个 worker 进程
```

## 2. Worker 协议

Phase 24 在 Qwen3-VL demo 侧新增 `VLM_NPU_WORKER`，使用 stdin/stdout 文本协议。

请求格式：

```text
image_path<TAB>prompt
```

成功响应：

```text
EDGEINFER_VLM_BEGIN
image_path: /path/to/image.jpg
latency_ms: 15681
answer:
...
EDGEINFER_VLM_END
```

错误响应：

```text
EDGEINFER_VLM_ERROR_BEGIN
code: image_read_failed
image_path: /path/to/image.jpg
EDGEINFER_VLM_ERROR_END
```

退出：

```text
exit
```

## 3. 服务端实现

核心文件：

```text
server/runtime/qwen3_vl_backend.py
```

Phase 24 将 Qwen3-VL backend 改为 worker 优先：

```text
默认模式：
EDGEINFER_QWEN3_VL_BACKEND_MODE=worker

可选回退：
EDGEINFER_QWEN3_VL_BACKEND_MODE=oneshot
```

默认 worker 路径：

```text
/home/linaro/qwen3-vl-2b-npu/VLM_NPU_WORKER
```

默认模型路径：

```text
/userdata/edgeinfer-assets/models/vlm/qwen3-vl-2b-instruct-rkllm-v123/qwen3-vl-2b_vision_672_rk3588.rknn
/userdata/edgeinfer-assets/models/vlm/qwen3-vl-2b-instruct-rkllm-v123/qwen3-vl-2b-instruct_w8a8_rk3588.rkllm
```

## 4. NPU Guard 集成

Phase 24 保持 Phase 20 的全局 NPU Guard 语义不变。

每个 VLM 请求仍然会 acquire：

```python
npu_resource_guard.acquire_nowait(
    task=task,
    owner="qwen3-vl",
    model_id=model_id,
)
```

请求结束后释放：

```python
lease.finish_success()
```

异常时释放：

```python
lease.finish_error(exc)
```

这意味着：

```text
VLM 推理正在占用 NPU 时，Vision / LLM 等其他 NPU 任务仍会返回 429 npu_resource_busy。
```

同时，已经验证 idle 状态的 `VLM_NPU_WORKER` 不会阻塞 YOLO Vision worker。

## 5. 历史污染修复

Persistent worker 初版出现过连续多图请求串图问题：

```text
Pizza.jpg -> pizza answer
Singapore.jpg -> pizza answer
```

根因是 RKLLM 历史 / KV cache 没有在每次请求之间清理。

修复方式是在 worker 每次请求前执行：

```cpp
rkllm.Ask("clear");
rkllm.LoadImage(image);
std::string answer = rkllm.Ask(prompt);
```

修复后验证：

```text
Pizza.jpg -> pizza / crust / basil
Singapore.jpg -> Singapore / skyline / Marina Bay / Singapore Flyer
```

同时增强了 host 测试，防止只检查 HTTP 200 而忽略语义串图。

## 6. 测试脚本

新增：

```text
scripts/host/test_qwen3_vl_worker_backend.py
```

测试内容：

```text
1. 连续发送 Pizza 与 Singapore 两个 VLM 请求；
2. 检查两次请求均返回 HTTP 200；
3. 检查 runtime = phase24-qwen3-vl-persistent-worker；
4. 检查 mode = persistent-worker；
5. 检查两次请求复用同一个 worker pid；
6. 检查 request_count 递增；
7. 检查 Pizza answer 包含 pizza / cheese / basil / crust 等关键词；
8. 检查 Singapore answer 包含 singapore / skyline / marina / flyer / city / water 等关键词；
9. 检查两次 answer 不完全相同。
```

## 7. 实测结果

Phase 24 验证结果：

```text
worker pid: 3981
worker request_count: 17
Pizza latency_ms: 14516
Singapore latency_ms: 16273
```

语义结果：

```text
Pizza:
A freshly baked, rustic pizza with a thick, charred crust and vibrant green basil leaves sits on a white surface.

Singapore:
A stunning twilight view of Singapore's skyline, featuring the iconic Marina Bay Sands hotel with its distinctive rooftop structure, the illuminated Singapore Flyer observation wheel, and the city's modern skyscrapers reflected in the calm waters of Marina Bay.
```

与 Phase 23 one-shot benchmark 对比：

```text
one-shot pizza_caption:      ~20.2s
persistent worker pizza:     ~14.5s - 17.0s

one-shot singapore_caption:  ~20.6s
persistent worker singapore: ~16.2s - 18.1s
```

主要收益来自避免每次重复加载 RKLLM / RKNN 模型。

## 8. 当前边界

Phase 24 仍然有以下边界：

```text
1. worker 是单进程串行处理；
2. 每次请求仍然需要重新跑 image encoder；
3. worker 当前通过 stdin/stdout 协议通信；
4. VLM_NPU_WORKER 属于板端外部 runtime artifact，未纳入主仓库源码；
5. 如果 worker 异常或超时，Python backend 会终止并在后续请求中重启 worker。
```

后续可以继续优化：

```text
1. 将 worker 源码和构建脚本纳入项目管理；
2. 增加 worker health endpoint；
3. 增加 worker restart metrics；
4. 优化 image encoder / decoder 的耗时拆分；
5. 支持多 VLM 模型注册与选择。
```

## 9. 结论

Phase 24 将 Qwen3-VL 从 one-shot subprocess backend 升级为 persistent worker backend，在保持统一 `/v1/infer` API、全局 NPU Guard 和旧测试兼容的前提下，实现了：

```text
1. RKLLM / RKNN 模型常驻；
2. VLM 请求复用 worker 进程；
3. 单次请求延迟下降；
4. 多图连续请求不串图；
5. worker 状态进入 API response；
6. worker 复用逻辑可测试、可回归。
```

## 10. 测试运行策略

为了避免 RKLLM/RKNN 重型 VLM 请求在频繁回归中占用 NPU 或被主机端中断后留下 busy 状态，Phase 24 将部分旧测试调整为默认 smoke 模式。

默认快速回归：

```bash
python3 scripts/host/test_qwen3_vl_worker_backend.py
python3 scripts/host/test_qwen3_vl_infer_client.py
python3 scripts/host/test_unified_infer_response_schema.py
```

重型 VLM worker 双图回归需要显式开启：

```bash
EDGEINFER_QWEN3_VL_RUN_HEAVY=1 python3 scripts/host/test_qwen3_vl_worker_backend.py
```

Phase 24 已经完成过重型双图验证，确认 `Pizza.jpg` 与 `Singapore.jpg` 连续请求不会串图，且复用同一个 `VLM_NPU_WORKER` 进程。
