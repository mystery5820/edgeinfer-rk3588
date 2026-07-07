# Phase 20: Global Multi-Model NPU Resource Guard

## 1. Goal

Phase 20 adds a global RK3588 NPU resource guard above the existing task-specific queues.

Before this phase, LLM and Vision had separate concurrency protection:

- LLM requests were protected by `llm_queue`.
- Vision requests were protected by `vision_queue`.

However, both backends can compete for the same RK3588 NPU resource. Phase 20 introduces a global guard to prevent cross-task NPU contention.

## 2. Design

The new guard is implemented in:

```text
server/scheduler/npu_resource_guard.py
```

The guard exposes:

- `npu_resource_guard`
- `NPUResourceBusyError`
- `npu_resource_error_detail(...)`
- `PHASE20_RUNTIME`

The MVP policy is intentionally simple:

```text
max_concurrent = 1
queue_policy = reject_when_busy
```

## 3. Request flow

### Vision path

```text
/v1/vision/detect
  -> vision_queue.run_nowait(...)
      -> npu_resource_guard.acquire_nowait(...)
          -> RKNN YOLO backend
```

This preserves the old same-task behavior:

```text
Vision + Vision concurrency -> vision_backend_busy
```

### LLM non-stream path

```text
/v1/chat/completions stream=false
  -> llm_queue.run_nowait(...)
      -> npu_resource_guard.acquire_nowait(...)
          -> RKLLM backend
```

This preserves the old same-task behavior:

```text
LLM + LLM concurrency -> llm_backend_busy
```

### Cross-task behavior

```text
LLM running, Vision arrives -> npu_resource_busy
Vision running, LLM arrives -> npu_resource_busy
```

## 4. Error response

When the global NPU resource is occupied, the service returns HTTP 429:

```json
{
  "detail": {
    "error": {
      "code": "npu_resource_busy",
      "message": "NPU resource is busy; please retry later",
      "type": "edgeinfer_error",
      "retryable": true
    },
    "edgeinfer": {
      "task": "object-detection",
      "model": "YOLOv11n-FP-Baseline",
      "backend": "npu-resource-guard",
      "runtime": "phase20-global-npu-resource-guard",
      "owner": "vision-detect",
      "npu_resource": {
        "busy": true,
        "current_task": "text-generation",
        "current_model": "qwen3-4b-rkllm-all-npu",
        "current_owner": "chat-completions"
      }
    }
  }
}
```

## 5. Metrics

`/v1/metrics` now includes:

```json
{
  "npu_resource": {
    "runtime": "phase20-global-npu-resource-guard",
    "max_concurrent": 1,
    "busy": false,
    "queue_policy": "reject_when_busy",
    "total_acquire": 0,
    "accepted_acquire": 0,
    "rejected_busy": 0,
    "completed": 0,
    "failed": 0,
    "current_task": null,
    "current_model": null,
    "current_owner": null,
    "last_error": null,
    "last_latency_ms": null,
    "last_started_at": null,
    "last_finished_at": null
  }
}
```

## 6. Validation

Run:

```bash
python3 -m compileall \
  server/api/chat_api.py \
  server/api/vision_api.py \
  server/api/metrics_api.py \
  server/scheduler/npu_resource_guard.py \
  scripts/host/test_npu_resource_guard.py

./scripts/host/deploy_serving_to_board.sh

python3 scripts/host/test_npu_resource_guard.py
```

Expected result:

```text
=== NPU resource guard test passed ===
```

Additional regression tests:

```bash
EDGEINFER_EXPECT_VISION_BACKEND=rknn-yolo-worker \
python3 scripts/host/test_unified_infer_response_schema.py

EDGEINFER_EXPECT_VISION_BACKEND=rknn-yolo-worker \
python3 scripts/host/test_unified_infer_client.py

EDGEINFER_EXPECT_VISION_BACKEND=rknn-yolo-worker \
python3 scripts/host/test_vision_detect_client.py

python3 scripts/host/test_vision_busy_rejection.py

bash scripts/host/demo_vision_detect.sh
```

## 7. Phase conclusion

Phase 20 turns the serving framework from independent task queues into a multi-model NPU-aware serving system.

The current implementation keeps the policy simple and predictable:

- Same-task concurrency is rejected by the task queue.
- Cross-task NPU contention is rejected by the global NPU guard.
- The guard is observable through `/v1/metrics`.
- Phase 19B unified inference response behavior remains unchanged.
