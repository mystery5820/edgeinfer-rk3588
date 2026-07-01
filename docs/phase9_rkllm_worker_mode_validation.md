# Phase 9 RKLLM Persistent Worker Mode Validation

## 1. Background

Phase 9 has already connected the EdgeInfer RK3588 Serving API to the real Qwen3-4B RKLLM backend.

The original serving path uses a one-shot subprocess runner. For every `/v1/chat/completions` request, the server starts a new RKLLM subprocess, loads the `.rkllm` model, runs one prompt, returns the result, and exits the subprocess.

This approach is simple and stable, but it has a high per-request latency because the model is reloaded for every request.

To reduce repeated model loading overhead, this phase adds an optional persistent RKLLM worker mode.

## 2. Current Backend Modes

The serving framework now supports two RKLLM backend modes.

### 2.1 One-shot mode

One-shot mode is the default mode.

Environment:

```bash
EDGEINFER_RKLLM_BACKEND_MODE is not set
```

Expected Chat API backend:

```text
rkllm-runner
```

Characteristics:

- Starts a fresh RKLLM subprocess for each request.
- Loads the model for every request.
- Has higher latency.
- Has simpler process lifecycle.
- Remains the default safe mode.

### 2.2 Persistent worker mode

Worker mode is enabled explicitly through an environment variable or systemd drop-in.

Environment:

```bash
EDGEINFER_RKLLM_BACKEND_MODE=worker
EDGEINFER_RKLLM_WORKER_MAX_NEW=128
EDGEINFER_RKLLM_WORKER_CTX=1024
```

Expected Chat API backend:

```text
rkllm-persistent-worker
```

Characteristics:

- Starts one persistent RKLLM process.
- Keeps the model loaded across requests.
- Uses the no-history RKLLM wrapper binary.
- Clears KV cache after each request.
- Reduces repeated model loading overhead.
- Still rejects concurrent LLM requests through the existing busy mechanism.

## 3. Related Files

### 3.1 Runtime backend files

```text
server/runtime/rkllm_backend.py
server/runtime/rkllm_worker_backend.py
server/runtime/rkllm_runner.py
server/runtime/prompt_policy.py
```

### 3.2 Board scripts

```text
scripts/board/build_rkllm_no_history_binary.sh
scripts/board/probe_rkllm_persistent_worker.py
scripts/board/enable_edgeinfer_worker_mode.sh
scripts/board/disable_edgeinfer_worker_mode.sh
scripts/board/check_edgeinfer_serving.sh
```

### 3.3 Host smoke test

```text
scripts/host/smoke_test_serving.sh
```

The host smoke test supports backend checking through:

```bash
EDGEINFER_EXPECT_BACKEND=rkllm-runner
EDGEINFER_EXPECT_BACKEND=rkllm-persistent-worker
```

## 4. No-history RKLLM Wrapper

The persistent worker uses the following board-side binary:

```text
/home/linaro/edgeinfer-rk3588-board/tools/rkllm_enhanced/rkllm_enhanced_no_template_no_history
```

This binary is generated from the no-template RKLLM wrapper and applies two key changes:

```cpp
ip.keep_history = 0;
rkllm_clear_kv_cache(g_handle, 0, nullptr, nullptr);
```

Purpose:

- Keep each request isolated.
- Prevent cross-request prompt or answer contamination.
- Allow the RKLLM process to stay alive while still avoiding history carry-over.

## 5. Persistent Worker Probe Result

The standalone Python persistent worker backend probe has passed.

Observed result:

```text
request_1_latency_ms: 12384.256
request_1_text: 瑞芯微Rockchip推出的RK3588是一款高性能AIoT SoC，搭载四核Cortex-A76和四核Cortex-A55架构，并集成NPU，适用于智能物联网设备。

request_2_latency_ms: 7361.892
request_2_text: RK3588 适合端侧 AI 是因为它内置 NPU，能够高效支持端侧 AI 推理任务。

startup_ms: 4489.368
backend: rkllm-persistent-worker
probe_status: ok
```

Conclusion:

- The persistent worker can start the RKLLM process.
- The model is loaded once.
- Multiple requests can be processed by the same process.
- The second request returns valid non-empty text.
- The stale `You:` prompt issue has been fixed by draining stdout before sending the next request.

## 6. FastAPI Worker Mode Validation

Worker mode was enabled through a systemd drop-in.

Enable command:

```bash
./scripts/board/enable_edgeinfer_worker_mode.sh
```

The script creates:

```text
/etc/systemd/system/edgeinfer-serving.service.d/worker-mode.conf
```

Expected environment:

```text
EDGEINFER_RKLLM_BACKEND_MODE=worker
EDGEINFER_RKLLM_WORKER_MAX_NEW=128
EDGEINFER_RKLLM_WORKER_CTX=1024
```

Observed Chat API backend:

```text
rkllm-persistent-worker
```

Observed single chat result:

```text
backend: rkllm-persistent-worker
latency_ms: 10361.362
failed_requests: 0
timeout_requests: 0
last_error: null
```

Conclusion:

- FastAPI can route `/v1/chat/completions` to the persistent worker backend.
- The response is non-empty.
- Metrics remain healthy.
- The backend field correctly reports `rkllm-persistent-worker`.

## 7. Busy Rejection Validation

The existing LLM busy policy remains active in worker mode.

Expected behavior:

- First long request is accepted.
- Second concurrent request is rejected.
- HTTP status of the second request is 429.
- Error code is `llm_backend_busy`.
- First request finishes with HTTP 200.

Observed behavior:

```text
second HTTP 429
code: llm_backend_busy

first HTTP 200
backend: rkllm-persistent-worker

failed_requests: 0
timeout_requests: 0
last_error: null
```

Conclusion:

- Persistent worker mode does not bypass the scheduler guard.
- Concurrent LLM requests are still rejected safely.
- The no-concurrency rule remains valid for RKLLM on RK3588.

## 8. Metrics Validation

The `/v1/metrics` endpoint now reports the active RKLLM backend mode.

### 8.1 One-shot mode metrics

Expected:

```json
{
  "rkllm_backend": {
    "mode": "oneshot",
    "worker_enabled": false,
    "worker_ctx": 1024,
    "worker_max_new_tokens": 128
  }
}
```

Observed:

```text
mode: oneshot
worker_enabled: false
notes: one-shot subprocess runner
```

### 8.2 Worker mode metrics

Expected:

```json
{
  "rkllm_backend": {
    "mode": "worker",
    "worker_enabled": true,
    "worker_ctx": 1024,
    "worker_max_new_tokens": 128
  }
}
```

Observed:

```text
mode: worker
worker_enabled: true
notes: persistent no-history worker
```

Conclusion:

- `/v1/metrics` can clearly show whether the service is using one-shot mode or worker mode.
- This avoids confusion during board-side testing and debugging.

## 9. Host Smoke Test Backend Check

The host smoke test now supports expected backend checking.

One-shot validation:

```bash
EDGEINFER_EXPECT_BACKEND=rkllm-runner \
./scripts/host/smoke_test_serving.sh
```

Expected output:

```text
backend check OK: single chat: rkllm-runner
backend check OK: busy first request: rkllm-runner
=== Smoke test passed ===
```

Worker validation:

```bash
EDGEINFER_EXPECT_BACKEND=rkllm-persistent-worker \
./scripts/host/smoke_test_serving.sh
```

Expected output:

```text
backend check OK: single chat: rkllm-persistent-worker
backend check OK: busy first request: rkllm-persistent-worker
=== Smoke test passed ===
```

Mismatch validation:

```bash
EDGEINFER_EXPECT_BACKEND=rkllm-persistent-worker \
EDGEINFER_SMOKE_BUSY=0 \
./scripts/host/smoke_test_serving.sh
```

When the board is actually running in one-shot mode, this correctly fails with:

```text
ERROR: single chat backend mismatch: expected rkllm-persistent-worker, got rkllm-runner
```

Conclusion:

- The smoke test no longer only checks HTTP success.
- It can also verify that the expected backend is actually used.

## 10. Toggle Commands

### 10.1 Enable worker mode

On board:

```bash
cd /home/linaro/edgeinfer-rk3588-board
./scripts/board/enable_edgeinfer_worker_mode.sh
```

Then verify from host:

```bash
curl http://192.168.43.7:8000/v1/metrics | python3 -m json.tool
```

Expected:

```text
mode: worker
worker_enabled: true
```

### 10.2 Disable worker mode

On board:

```bash
cd /home/linaro/edgeinfer-rk3588-board
./scripts/board/disable_edgeinfer_worker_mode.sh
```

Then verify from host:

```bash
curl http://192.168.43.7:8000/v1/metrics | python3 -m json.tool
```

Expected:

```text
mode: oneshot
worker_enabled: false
```

The disable script also removes the older temporary test drop-in:

```text
/etc/systemd/system/edgeinfer-serving.service.d/worker-test.conf
```

This makes the script safe to run repeatedly.

## 11. Current Safe Default

The repository default remains one-shot mode.

Worker mode is opt-in only.

This is intentional because:

- One-shot mode is simpler.
- It avoids persistent process lifecycle risk.
- It is easier to recover from unknown RKLLM runtime state.
- It keeps the default behavior conservative.

Worker mode should be used when lower latency is desired and the board has already been validated with the smoke test.

## 12. Known Limitations

1. The worker currently communicates with the RKLLM wrapper through stdin/stdout text prompts.
2. Response boundary detection still depends on wrapper output markers such as `You:` and `<|im_end|>`.
3. The worker is single-process and single-request only.
4. Worker crash recovery is still basic.
5. The runtime does not yet expose worker PID or restart count in metrics.
6. The ideal long-term solution is a dedicated JSON-line RKLLM worker protocol.

## 13. Next Work Items

Recommended next steps:

1. Expose worker process status in `/v1/metrics`.
2. Add worker PID, startup time, request count, and restart count.
3. Improve worker lifecycle integration with FastAPI startup/shutdown.
4. Add a dedicated worker smoke test mode.
5. Design a C++ RKLLM JSON-line worker wrapper to replace text prompt parsing.
6. Add documentation for one-shot mode versus worker mode deployment recommendations.
