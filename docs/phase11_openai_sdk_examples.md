# Phase 11：OpenAI Python SDK 示例与验证记录

本文档记录 `edgeinfer-rk3588` 项目在 Phase 11 中新增 OpenAI Python SDK 示例的目标、使用方法、验证范围和当前限制。

Phase 10 已经完成 worker 模式下 `/v1/chat/completions` 的 `stream=true` SSE 流式输出 MVP。Phase 11 在此基础上补齐面向外部开发者的 OpenAI SDK 风格调用示例，证明当前 RK3588 板端 Serving API 可以通过 `base_url` 被标准 OpenAI Python SDK 访问。

---

## 1. 当前目标

Phase 11 的目标是：

```text
1. 提供 OpenAI Python SDK 的 stream=false 普通调用示例；
2. 提供 OpenAI Python SDK 的 stream=true 流式调用示例；
3. 保留 urllib 版本 test_openai_chat_client.py 作为无第三方依赖回归测试；
4. 新增轻量 smoke 脚本，便于验证 examples 能正常运行；
5. 不改变板端 Serving 核心逻辑；
6. 不改变默认 one-shot 部署模式。
```

---

## 2. 新增文件

本阶段新增：

```text
examples/openai_sdk_chat_completion.py
examples/openai_sdk_streaming_chat.py
scripts/host/check_openai_sdk_examples.py
docs/phase11_openai_sdk_examples.md
```

其中：

```text
openai_sdk_chat_completion.py
  使用 OpenAI(base_url=..., api_key=...) 调用 stream=false 普通 chat completion。

openai_sdk_streaming_chat.py
  使用 OpenAI(base_url=..., api_key=...) 调用 stream=true 流式 chat completion。

check_openai_sdk_examples.py
  主机侧轻量检查脚本。
  默认只跑 stream=false 示例；
  设置 EDGEINFER_EXPECT_STREAM=1 后额外跑 stream=true 示例。
```

---

## 3. 依赖安装

OpenAI SDK 示例需要主机 Python 环境安装 `openai` 包。

```bash
python3 -m pip install openai
```

这些 example 不是板端服务运行依赖，不需要安装到板端 `.venv-serving` 中。

---

## 4. 环境变量

示例脚本支持以下环境变量：

```text
EDGEINFER_BOARD_URL
  默认：http://192.168.43.7:8000

EDGEINFER_OPENAI_BASE_URL
  默认：${EDGEINFER_BOARD_URL}/v1

EDGEINFER_MODEL_ID
  默认：qwen3-4b-rkllm-all-npu

EDGEINFER_OPENAI_API_KEY
  默认：edgeinfer-local
```

说明：

```text
当前 EdgeInfer Serving API 不校验 API key。
OpenAI SDK 仍要求传入 api_key，因此示例使用 edgeinfer-local 作为占位值。
```

---

## 5. stream=false 普通调用示例

默认 one-shot 模式即可运行：

```bash
cd ~/edgeinfer-rk3588
python3 examples/openai_sdk_chat_completion.py
```

预期输出包含：

```text
=== EdgeInfer OpenAI SDK chat completion example ===
base_url: http://192.168.43.7:8000/v1
model: qwen3-4b-rkllm-all-npu
finish_reason: stop
assistant:
...
```

---

## 6. stream=true 流式调用示例

流式示例需要先启用 worker 模式：

```bash
ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/enable_edgeinfer_worker_mode.sh"
```

运行：

```bash
cd ~/edgeinfer-rk3588
python3 examples/openai_sdk_streaming_chat.py
```

预期输出会逐步打印 assistant 内容，并在结尾显示：

```text
finish_reason: stop
assistant_content_length: ...
```

测试结束后恢复默认 one-shot：

```bash
ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/disable_edgeinfer_worker_mode.sh"
```

---

## 7. 一键检查脚本

默认只检查 stream=false 示例：

```bash
cd ~/edgeinfer-rk3588
python3 scripts/host/check_openai_sdk_examples.py
```

如果主机环境未安装 `openai`，脚本会返回 skip，并提示：

```text
python3 -m pip install openai
```

启用 worker 后，可以检查 stream=false 与 stream=true：

```bash
ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/enable_edgeinfer_worker_mode.sh"

EDGEINFER_EXPECT_STREAM=1 \
python3 scripts/host/check_openai_sdk_examples.py

ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/disable_edgeinfer_worker_mode.sh"
```

---

## 8. 与现有测试的关系

当前测试分层如下：

```text
scripts/host/smoke_test_serving.sh
  面向 Serving API 的主机侧 curl smoke test。
  已覆盖 one-shot / worker、stream=false / stream=true、busy、max_tokens、stop、n、top_p、response_format。

scripts/host/test_openai_chat_client.py
  无第三方依赖的 OpenAI-like API 回归测试。
  使用 urllib 直接请求，适合作为稳定 CI 基础。

scripts/host/check_openai_sdk_examples.py
  面向 OpenAI Python SDK examples 的轻量验证脚本。
  依赖 openai 包，适合作为可选集成验证。
```

Phase 11 不用 OpenAI SDK 替代原有 urllib 测试，因为 SDK 是额外依赖；无第三方依赖测试仍是主回归入口。

---

## 9. 当前限制

当前 OpenAI SDK 示例仍受 Serving API 能力限制：

1. `stream=true` 仅在 persistent worker 模式支持；
2. one-shot 模式下 `stream=true` 会返回 `stream_backend_not_supported`；
3. `usage.prompt_tokens`、`usage.completion_tokens`、`usage.total_tokens` 仍为 `null`；
4. `temperature` 尚未真正下传 RKLLM runtime；
5. `top_p` 仍只接受 `1.0`；
6. `response_format` 仅支持 `{"type":"text"}`；
7. 不支持 OpenAI tool calls / function calling；
8. 不支持 JSON mode；
9. 不支持多候选 `n>1`。

---

## 10. 后续建议

Phase 11 完成后，后续可以继续推进：

```text
1. usage token 统计；
2. finish_reason=length；
3. 官方 OpenAI SDK 的更多示例，例如 base_url、stream、错误处理；
4. LangChain / LlamaIndex 最小接入示例；
5. 客户端断开、stream 异常、busy 并发的压力测试。
```
