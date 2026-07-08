# Phase 22: Qwen3-VL RK3588 Backend MVP

## Goal

Phase 22 turns the VLM placeholder introduced in Phase 19 into a real RK3588 VLM backend.

The implemented path is:

```text
image -> RKNN vision encoder -> RKLLM decoder -> text answer
```

This is a true VLM path, not a YOLO + LLM captioning baseline.

## Runtime assets

Validated board-side assets:

```text
/userdata/edgeinfer-assets/models/vlm/qwen3-vl-2b-instruct-rkllm-v123/qwen3-vl-2b_vision_672_rk3588.rknn
/userdata/edgeinfer-assets/models/vlm/qwen3-vl-2b-instruct-rkllm-v123/qwen3-vl-2b-instruct_w8a8_rk3588.rkllm
```

Validated SHA256:

```text
qwen3-vl-2b-instruct_w8a8_rk3588.rkllm:
d5474340221fc495c70e1ec2c7dafc4ebf88292ce466db7e771e3a20b99cf21f

qwen3-vl-2b_vision_672_rk3588.rknn:
f4e6fb4baeb27fa4e2b88b311716b166cc000c10ec218c91e70a4bdb1db3dfe9
```

## Demo binary

The board-side Qwen3-VL demo is located at:

```text
/home/linaro/qwen3-vl-2b-npu/VLM_NPU
```

It links to:

```text
/home/linaro/qwen3-vl-2b-npu/aarch64/library/librknnrt.so
/home/linaro/qwen3-vl-2b-npu/aarch64/library/librkllmrt.so
```

A small stdin EOF patch was applied to the demo input loop so one-shot subprocess invocation exits after one prompt.

## Service integration

New backend:

```text
server/runtime/qwen3_vl_backend.py
```

Backend name:

```text
qwen3-vl-rkllm-rknn-runner
```

Runtime name:

```text
phase22-qwen3-vl-rk3588-backend
```

`/v1/infer/tasks` now marks VLM tasks as real adapters:

```text
vision-language
image-captioning
visual-question-answering
multimodal-chat
```

## API example

```bash
cat > /tmp/edgeinfer_qwen3_vl_req.json <<'JSON'
{
  "task": "vision-language",
  "model": "qwen3-vl-2b-instruct-rkllm-v123",
  "input": {
    "image_path": "/home/linaro/qwen3-vl-2b-npu/Pizza.jpg",
    "prompt": "<image> Describe this image in one sentence."
  },
  "parameters": {
    "max_new_tokens": 64,
    "context_length": 1024,
    "timeout_seconds": 180
  }
}
JSON

curl -s -X POST http://192.168.43.7:8000/v1/infer \
  -H "Content-Type: application/json" \
  --data-binary @/tmp/edgeinfer_qwen3_vl_req.json \
  | python3 -m json.tool
```

Validated output includes a correct pizza description through `output.summary.answer`.

## NPU resource guard

Qwen3-VL inference is protected by the global NPU resource guard:

```text
owner = qwen3-vl
```

After successful inference, `/v1/metrics` should show:

```text
npu_resource.busy = false
```

## Validation

```bash
python3 -m compileall \
  server/api/infer_api.py \
  server/runtime/qwen3_vl_backend.py \
  scripts/host/test_qwen3_vl_infer_client.py

./scripts/host/deploy_serving_to_board.sh

python3 scripts/host/test_qwen3_vl_infer_client.py
```

Expected result:

```text
=== Qwen3-VL infer client test passed ===
```

## Current limitations

The current backend uses a one-shot subprocess runner around the Qwen3-VL demo binary. This is reliable for MVP validation but reloads the model for every request.

Future optimization:

```text
persistent Qwen3-VL worker
streaming VLM output
image upload support
more benchmark cases
Qwen3-VL-4B / larger VLM exploration
```
