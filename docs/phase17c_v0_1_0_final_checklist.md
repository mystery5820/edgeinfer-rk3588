# Phase 17C：v0.1.0 Final Checklist

本文档记录 `edgeinfer-rk3588` 在创建正式 `v0.1.0` release tag 前执行的最终验收结果。

结论：

```text
Phase 17C final checklist passed.
```

说明：

```text
本文档仍然是 Phase 17C 阶段文档。
建议先提交本文档并创建 phase17c-v0.1.0-final-checklist tag；
确认 main / origin/main / phase17c tag 均正常后，再单独创建正式 v0.1.0 tag。
```

---

## 1. Git 基线

最终检查时 HEAD：

```text
5bb48f0 add v0.1.0 release notes draft
```

最近提交：

```text
5bb48f0 add v0.1.0 release notes draft
c8356e4 add readme benchmark snapshot
0bd9910 summarize streaming and nonstreaming benchmarks
b1e84c5 document warm streaming benchmark run
a96fb29 document streaming benchmark run
4123312 add streaming llm benchmark
2a20c21 document openai sdk compatibility notes
5a193c4 document chat api request response examples
```

当前 Phase 17 tags：

```text
phase17a-readme-benchmark-snapshot Phase 17A README benchmark snapshot
phase17b-v0.1.0-release-notes Phase 17B v0.1.0 release notes
```

---

## 2. 静态检查

执行：

```bash
python3 -m compileall -q server scripts/host tools examples
bash -n scripts/host/*.sh scripts/board/*.sh
git diff --check
```

结果：

```text
PASS
```

说明：

```text
1. Python 编译检查通过；
2. shell 脚本 bash -n 检查通过；
3. git diff --check 无 whitespace error。
```

---

## 3. README / docs 链接检查

执行修正版链接检查脚本后结果：

```text
All README/docs markdown references exist. checked_refs=29
```

说明：

```text
README.md 与 docs/README.md 中引用的 docs/*.md 均存在。
```

README.md 中检查到的主要引用包括：

```text
docs/README.md
docs/phase9_serving_operations.md
docs/phase9_openai_compat.md
docs/phase10_streaming_sse.md
docs/phase11_openai_sdk_examples.md
docs/phase12_estimated_usage.md
docs/phase12b_finish_reason_length_research.md
docs/phase13_project_showcase.md
docs/phase13b_project_summary.md
docs/phase14_benchmark_summary.md
docs/phase14b_controlled_benchmark.md
docs/phase14c_benchmark_run_20260705.md
docs/phase15_api_compatibility_matrix.md
docs/phase15b_error_response_reference.md
docs/phase15c_error_response_tests.md
docs/phase15d_chat_api_examples.md
docs/phase15e_openai_sdk_compatibility_notes.md
docs/phase16a_streaming_benchmark.md
docs/phase16b_streaming_benchmark_run_20260706.md
docs/phase16c_warm_streaming_benchmark_run_20260706.md
docs/phase16d_streaming_vs_nonstreaming_summary.md
docs/phase17a_readme_benchmark_snapshot.md
docs/phase17b_v0_1_0_release_notes.md
```

docs/README.md 中检查到的引用包括：

```text
docs/phase9_serving_operations.md
docs/phase9_openai_compat.md
docs/phase10_streaming_sse.md
docs/phase11_openai_sdk_examples.md
docs/phase12_estimated_usage.md
docs/phase12b_finish_reason_length_research.md
```

---

## 4. 板端默认 one-shot 状态

执行：

```bash
curl -s http://192.168.43.7:8000/v1/health | python3 -m json.tool

curl -s http://192.168.43.7:8000/v1/metrics \
  | python3 -m json.tool \
  | grep -nE "mode|worker_enabled|started|pid|request_count|busy|queue_policy"
```

health：

```json
{
  "status": "ok",
  "service": "edgeinfer-rk3588-serving",
  "phase": "phase9-serving-framework-mvp",
  "legacy_services_should_be_disabled": [
    "qwen-web-chat.service",
    "yolov5-web.service"
  ]
}
```

metrics 摘要：

```text
mode = oneshot
worker_enabled = false
busy = false
queue_policy = reject_when_busy
current_model = null
```

结论：

```text
板端服务健康；
默认模式为 one-shot；
worker mode 未启用；
LLM backend 非 busy。
```

---

## 5. one-shot OpenAI-like API 验收

执行：

```bash
python3 scripts/host/test_openai_chat_client.py
```

结果：

```text
=== OpenAI-like chat client test passed in 42.539s ===
```

覆盖项：

```text
1. health；
2. chat with max_tokens；
3. chat with stop sequences；
4. stream=true one-shot rejection；
5. n>1 rejection；
6. top_p!=1 rejection；
7. response_format=json_object rejection；
8. invalid stop rejection；
9. model_not_found rejection；
10. model_not_llm rejection。
```

关键结果：

```text
max_tokens chat:
  backend = rkllm-runner
  latency_ms = 20760.65
  usage = {"prompt_tokens": 27, "completion_tokens": 40, "total_tokens": 67}

stop sequences:
  backend = rkllm-runner
  latency_ms = 21193.365
  stop.matched = RK3588
  assistant_content_length = 0

stream=true in one-shot:
  HTTP 400
  code = stream_backend_not_supported
```

结论：

```text
one-shot Chat Completions API 和错误响应路径通过最终验收。
```

---

## 6. OpenAI Python SDK 非流式验收

执行：

```bash
python3 scripts/host/check_openai_sdk_examples.py
```

结果：

```text
=== OpenAI SDK example smoke test completed ===
```

关键输出：

```text
base_url = http://192.168.43.7:8000/v1
model = qwen3-4b-rkllm-all-npu
object = chat.completion
finish_reason = stop
backend = rkllm-runner
latency_ms = 20652.078
```

默认行为：

```text
streaming SDK example skipped by default
Set EDGEINFER_EXPECT_STREAM=1 after enabling worker mode to run it.
```

结论：

```text
OpenAI Python SDK base_url 非流式示例通过；
one-shot 下默认跳过 streaming example 是预期行为。
```

---

## 7. worker mode / streaming SDK 验收

启用 worker：

```bash
ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/enable_edgeinfer_worker_mode.sh"
```

启用结果：

```text
EDGEINFER_RKLLM_BACKEND_MODE=worker
EDGEINFER_RKLLM_WORKER_MAX_NEW=128
EDGEINFER_RKLLM_WORKER_CTX=1024
service status = active
service enabled = enabled
health.status = ok
```

执行：

```bash
EDGEINFER_EXPECT_STREAM=1 python3 scripts/host/check_openai_sdk_examples.py
```

结果：

```text
=== OpenAI SDK example smoke test completed ===
```

非流式 SDK example：

```text
backend = rkllm-persistent-worker
latency_ms = 10378.769
finish_reason = stop
```

streaming SDK example：

```text
finish_reason = stop
assistant_content_length = 81
```

结论：

```text
worker mode 下 OpenAI SDK 非流式和 streaming 示例均通过。
```

---

## 8. streaming benchmark final check

执行：

```bash
python3 scripts/host/benchmark_llm_streaming.py \
  --repeat 1 \
  --max-tokens 64 \
  --output-prefix llm_streaming_final_check
```

运行条件：

```text
backend_mode = worker
worker_enabled = True
worker_started = True
```

结果：

| prompt | status | ok | first_content_ms | total_ms | chunks | chars | finish_reason | done |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- | --- |
| `rk3588_intro` | 200 | True | 5032.386 | 10742.592 | 22 | 46 | stop | True |
| `edge_ai_value` | 200 | True | 4431.882 | 14619.612 | 38 | 81 | stop | True |

输出文件：

```text
results/benchmark/llm_streaming_final_check.csv
results/benchmark/llm_streaming_final_check_report.md
```

说明：

```text
上述文件是 final check 生成产物，不建议提交到 Git。
```

结论：

```text
streaming benchmark final check 通过；
两个 prompt 均 HTTP 200；
finish_reason=stop；
data: [DONE] received；
error 为空。
```

---

## 9. 恢复 one-shot

执行：

```bash
ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/disable_edgeinfer_worker_mode.sh"
```

结果：

```text
removed /etc/systemd/system/edgeinfer-serving.service.d/worker-mode.conf
service status = active
service enabled = enabled
health.status = ok
```

最终 metrics：

```text
mode = oneshot
worker_enabled = false
busy = false
queue_policy = reject_when_busy
current_model = null
```

结论：

```text
final check 后已恢复默认 one-shot；
板端服务处于健康状态。
```

---

## 10. 最终 Git 状态

执行：

```bash
git status --short
git log --oneline -8
git tag -n | grep -E "phase17|phase16|phase15" | sort
```

结果显示：

```text
5bb48f0 (HEAD -> main, tag: phase17b-v0.1.0-release-notes, origin/main) add v0.1.0 release notes draft
c8356e4 (tag: phase17a-readme-benchmark-snapshot) add readme benchmark snapshot
0bd9910 (tag: phase16d-streaming-nonstreaming-summary) summarize streaming and nonstreaming benchmarks
b1e84c5 (tag: phase16c-warm-streaming-benchmark-run) document warm streaming benchmark run
a96fb29 (tag: phase16b-streaming-benchmark-run) document streaming benchmark run
4123312 (tag: phase16a-streaming-benchmark) add streaming llm benchmark
2a20c21 (tag: phase15e-openai-sdk-compat-notes) document openai sdk compatibility notes
5a193c4 (tag: phase15d-chat-api-examples) document chat api request response examples
```

Phase 15 / 16 / 17 tags 连续存在。

---

## 11. Final checklist 总表

| 检查项 | 结果 |
| --- | --- |
| Git status clean | PASS |
| Recent log / phase tags | PASS |
| Python compileall | PASS |
| bash -n shell scripts | PASS |
| git diff --check | PASS |
| README/docs markdown references | PASS |
| `/v1/health` | PASS |
| default one-shot metrics | PASS |
| one-shot OpenAI-like client test | PASS |
| OpenAI SDK non-streaming example | PASS |
| worker mode enable | PASS |
| OpenAI SDK streaming example | PASS |
| streaming benchmark final check | PASS |
| worker mode disable | PASS |
| final one-shot metrics | PASS |

---

## 12. 是否可以创建 v0.1.0 tag

基于以上结果：

```text
可以进入 v0.1.0 tag 创建步骤。
```

建议流程：

```text
1. 先提交本 Phase 17C 文档；
2. 创建 phase17c-v0.1.0-final-checklist tag；
3. push main 和 phase17c tag；
4. 再创建正式 v0.1.0 tag；
5. push v0.1.0 tag。
```

---

## 13. v0.1.0 tag 建议说明

建议正式 tag：

```text
v0.1.0
```

建议 tag message：

```text
v0.1.0 RK3588 edge inference serving MVP
```

正式 release 可描述为：

```text
RK3588 edge inference serving MVP with YOLOv11 RKNN validation, Qwen3-4B RKLLM all-NPU serving, OpenAI-like Chat Completions API, persistent worker streaming SSE, metrics, busy rejection, systemd deployment, OpenAI Python SDK examples and benchmark documentation.
```

---

## 14. 阶段结论

Phase 17C 证明当前主线已经满足 v0.1.0 候选发布条件：

```text
1. 代码静态检查通过；
2. README/docs 链接检查通过；
3. one-shot 模式通过；
4. worker mode 通过；
5. streaming SSE 通过；
6. OpenAI SDK examples 通过；
7. benchmark final check 通过；
8. final check 后已恢复 one-shot；
9. main / origin/main / phase tags 状态正常。
```

因此，提交本文档后，可以创建正式 `v0.1.0` release tag。
