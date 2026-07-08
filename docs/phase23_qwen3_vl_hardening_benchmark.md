# Phase 23: Qwen3-VL Backend Hardening & Benchmark

## Scope

Phase 23 hardens the Phase 22 Qwen3-VL backend and adds repeatable validation around global NPU resource protection and VLM benchmark behavior.

Phase 22 proved the real VLM service path:

```text
/v1/infer task=vision-language
  -> qwen3-vl-rkllm-rknn-runner
  -> RKNN vision encoder
  -> RKLLM decoder
```

Phase 23 focuses on making this path reliable and measurable.

## Step 1: VLM Global NPU Guard Validation

Qwen3-VL is protected by the same global NPU resource guard introduced in Phase 20.

Manual validation result:

```text
Start Qwen3-VL vision-language inference in background.
Call /v1/vision/detect while Qwen3-VL is still running.

Expected:
HTTP 429
error.code = npu_resource_busy
current_task = vision-language
current_model = qwen3-vl-2b-instruct-rkllm-v123
current_owner = qwen3-vl
```

Observed:

```text
/v1/vision/detect returned HTTP 429.
npu_resource.current_task = vision-language.
npu_resource.current_owner = qwen3-vl.
After Qwen3-VL completed, /v1/metrics showed npu_resource.busy = false.
```

This proves the Qwen3-VL backend does not bypass the project-level RK3588 NPU resource policy.

## Automated test

```bash
python3 scripts/host/test_vlm_npu_resource_guard.py
```

The test:

```text
1. Starts a long Qwen3-VL request in a background thread.
2. Sends a competing /v1/vision/detect request.
3. Requires the competing request to return HTTP 429 npu_resource_busy.
4. Verifies current_task/current_model/current_owner point to Qwen3-VL.
5. Waits for Qwen3-VL to complete.
6. Confirms /v1/metrics reports npu_resource.busy = false.
```

## Next work

Planned follow-up steps:

```text
Phase 23 Step 2: Qwen3-VL multi-image / multi-prompt benchmark CSV.
Phase 23 Step 3: README demo polish with a clear VLM showcase.
Phase 24: Qwen3-VL persistent worker to avoid model reload on every request.
```
## Step 2: Qwen3-VL Multi-Image Benchmark CSV

The benchmark script sends repeatable VLM requests to `/v1/infer` and writes a CSV report.

Script:

```text
scripts/host/benchmark_qwen3_vl.py
```

Quick benchmark:

```bash
python3 scripts/host/benchmark_qwen3_vl.py --quick
```

Full default benchmark:

```bash
python3 scripts/host/benchmark_qwen3_vl.py
```

The default benchmark covers:

```text
Pizza.jpg one-sentence caption
Pizza.jpg detailed description
Singapore.jpg caption
Moon.jpg VQA-style question
ChineseWall.jpg landmark/scene description
```

CSV output is written to:

```text
benchmarks/phase23_qwen3_vl_benchmark_<timestamp>.csv
```

CSV fields include:

```text
case_id
task
image_path
prompt
max_new_tokens
http_status
success
client_latency_ms
backend_latency_ms
answer_chars
answer_preview
backend
source_runtime
error_code
```

For the current one-shot subprocess backend, latency includes model initialization time. This makes the benchmark useful as a Phase 22/23 baseline before implementing the Phase 24 persistent VLM worker.
