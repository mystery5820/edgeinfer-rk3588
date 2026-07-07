# Phase 18I：Vision Queue and Busy Rejection

本文档记录 Phase 18I：为 `/v1/vision/detect` 增加 VisionRequestQueue，并采用 `reject_when_busy` 并发策略。

---

## 1. 背景

Phase 18H 已经完成 persistent RKNN YOLO worker：

```text
FastAPI
  -> rknn-yolo-worker
  -> 长驻 worker subprocess
  -> RKNN model load/init 一次
  -> 后续请求复用 worker
```

但是 Phase 18H 仍然没有显式的 Vision queue。

虽然 worker backend 内部有锁，但并发请求会等待锁，而不是像 LLM 一样在忙时立即拒绝。

---

## 2. 本阶段目标

Phase 18I 对齐 LLM Serving 的策略：

```text
reject_when_busy
```

当 `/v1/vision/detect` 已经有一个请求在执行时，第二个并发请求应立即返回：

```text
HTTP 429
code = vision_backend_busy
retryable = true
```

---

## 3. 新增文件

```text
server/scheduler/vision_queue.py
scripts/host/test_vision_busy_rejection.py
docs/phase18i_vision_queue_busy_rejection.md
```

更新：

```text
server/api/vision_api.py
server/api/metrics_api.py
README.md
docs/README.md
```

---

## 4. VisionRequestQueue

新增：

```python
VisionRequestQueue
VisionQueueBusyError
VisionQueueTimeoutError
vision_queue
```

核心字段：

```text
max_concurrent
busy
queue_policy
total_requests
accepted_requests
rejected_busy
completed_requests
failed_requests
timeout_requests
last_error
last_latency_ms
last_started_at
last_finished_at
current_model
```

---

## 5. API 行为

正常请求：

```text
POST /v1/vision/detect
```

如果空闲：

```text
vision_queue.acquire_nowait()
_run_backend()
vision_queue.finish_success()
```

如果忙：

```json
{
  "detail": {
    "error": {
      "code": "vision_backend_busy",
      "message": "Vision backend is busy; please retry later",
      "type": "edgeinfer_error",
      "retryable": true
    }
  }
}
```

---

## 6. Metrics

`edgeinfer.vision` 结构改为包含：

```json
{
  "queue": {
    "busy": false,
    "queue_policy": "reject_when_busy",
    "total_requests": 2,
    "accepted_requests": 1,
    "rejected_busy": 1
  },
  "backend": {
    "...": "..."
  }
}
```

如果 `server/api/metrics_api.py` 包含 `llm_queue.snapshot()`，补丁也会向 `/v1/metrics` 增加：

```json
"vision": vision_queue.snapshot()
```

---

## 7. 验证方式

启用 worker backend：

```bash
ssh linaro@192.168.43.7 '
cd /home/linaro/edgeinfer-rk3588-board
./scripts/board/enable_edgeinfer_vision_rknn_worker.sh
'
```

正常检测：

```bash
EDGEINFER_EXPECT_VISION_BACKEND=rknn-yolo-worker \
python3 scripts/host/test_vision_detect_client.py
```

并发 busy 测试：

```bash
python3 scripts/host/test_vision_busy_rejection.py
```

预期：

```text
一个请求 HTTP 200
一个请求 HTTP 429
429 error.code = vision_backend_busy
```

---

## 8. 当前限制

Phase 18I 仍然是单 worker 模式：

```text
1. max_concurrent = 1；
2. 不做排队等待；
3. 忙时直接拒绝；
4. 还没有多 vision worker；
5. 还没有请求优先级。
```

---

## 9. 后续阶段

建议下一阶段：

```text
Phase 18J：Vision Metrics and Model Selection Cleanup
```

可以处理：

```text
1. /v1/metrics 中 vision backend/queue 结构统一；
2. 默认 object-detection 模型改为 FP ready 模型；
3. INT8 debug 模型不再作为默认 vision detect 模型；
4. README 增加 Vision Serving 使用示例。
```

---

## 10. 阶段结论

Phase 18I 完成后，Vision Serving 将拥有和 LLM Serving 一致的基本服务稳定性策略：

```text
单资源保护
reject_when_busy
429 retryable error
queue metrics
```
