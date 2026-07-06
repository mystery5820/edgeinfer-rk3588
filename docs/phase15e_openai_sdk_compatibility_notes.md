# Phase 15E：OpenAI Python SDK Compatibility Notes

本文档整理 `edgeinfer-rk3588` 当前与官方 OpenAI Python SDK 的兼容使用方式、环境变量、示例脚本、streaming 条件和已知差异。

本文档基于当前源码：

```text
examples/openai_sdk_chat_completion.py
examples/openai_sdk_streaming_chat.py
scripts/host/check_openai_sdk_examples.py
```

---

## 1. 当前结论

`edgeinfer-rk3588` 当前已经可以通过 OpenAI Python SDK 的 `base_url` 方式接入：

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://192.168.43.7:8000/v1",
    api_key="edgeinfer-local",
)
```

当前支持：

```text
1. client.chat.completions.create(..., stream=False)
2. worker 模式下 client.chat.completions.create(..., stream=True)
3. max_tokens
4. messages
5. model
6. finish_reason
7. choices[0].message.content
8. choices[0].delta.content
```

当前注意事项：

```text
1. api_key 只是 SDK 客户端必填字段，本地服务当前不做真实鉴权；
2. one-shot 模式下 stream=True 会返回 stream_backend_not_supported；
3. streaming 示例需要先启用 RKLLM persistent worker mode；
4. usage 是 estimated usage；
5. 当前不是完整 OpenAI API 兼容实现，只是 Chat Completions MVP 兼容。
```

---

## 2. 安装 OpenAI Python SDK

安装：

```bash
python3 -m pip install openai
```

验证：

```bash
python3 - <<'PY'
import openai
print(openai.__version__)
PY
```

如果没有安装，`scripts/host/check_openai_sdk_examples.py` 会返回 skip：

```text
SKIP: Python package 'openai' is not installed.
Install it with: python3 -m pip install openai
```

---

## 3. 环境变量

SDK 示例使用以下环境变量：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `EDGEINFER_BOARD_URL` | `http://192.168.43.7:8000` | 板端 Serving 地址 |
| `EDGEINFER_OPENAI_BASE_URL` | `${EDGEINFER_BOARD_URL}/v1` | OpenAI SDK base_url |
| `EDGEINFER_MODEL_ID` | `qwen3-4b-rkllm-all-npu` | 默认模型 |
| `EDGEINFER_OPENAI_API_KEY` | `edgeinfer-local` | SDK 必填，本地服务当前不校验 |
| `EDGEINFER_EXPECT_STREAM` | `0` | 是否运行 streaming SDK 示例 |

推荐默认配置：

```bash
export EDGEINFER_BOARD_URL=http://192.168.43.7:8000
export EDGEINFER_OPENAI_BASE_URL=${EDGEINFER_BOARD_URL}/v1
export EDGEINFER_MODEL_ID=qwen3-4b-rkllm-all-npu
export EDGEINFER_OPENAI_API_KEY=edgeinfer-local
```

---

## 4. 为什么 api_key 可以是 dummy value

OpenAI Python SDK 初始化时要求提供 `api_key`。对于真实 OpenAI API，该字段用于鉴权；但 `edgeinfer-rk3588` 当前是本地 / 局域网内的 RK3588 Serving 服务，暂未实现 API key 鉴权。

因此示例中使用：

```python
API_KEY = os.environ.get("EDGEINFER_OPENAI_API_KEY", "edgeinfer-local")
```

含义是：

```text
1. 满足 OpenAI SDK 客户端初始化要求；
2. 不代表真实 OpenAI API key；
3. 当前不会被服务端校验；
4. 后续如果加入鉴权，可以继续复用该环境变量。
```

---

## 5. 非流式 SDK 示例

示例文件：

```text
examples/openai_sdk_chat_completion.py
```

执行：

```bash
cd ~/edgeinfer-rk3588
python3 examples/openai_sdk_chat_completion.py
```

核心代码：

```python
client = OpenAI(
    base_url=BASE_URL,
    api_key=API_KEY,
)

completion = client.chat.completions.create(
    model=MODEL_ID,
    messages=[
        {
            "role": "system",
            "content": "你是 EdgeInfer-RK3588 端侧推理助手。",
        },
        {
            "role": "user",
            "content": "请用一句话介绍 RK3588。",
        },
    ],
    max_tokens=64,
    stream=False,
)
```

读取结果：

```python
choice = completion.choices[0]
print(choice.finish_reason)
print(choice.message.content)
```

当前示例还会尝试读取项目扩展字段：

```python
edgeinfer = getattr(completion, "edgeinfer", None)
```

说明：

```text
1. 标准 SDK 字段通过 completion.choices 读取；
2. 项目扩展 metadata 可通过 getattr 读取；
3. 扩展字段不是官方 OpenAI API 标准字段，客户端应做好兼容处理。
```

---

## 6. Streaming SDK 示例

示例文件：

```text
examples/openai_sdk_streaming_chat.py
```

该示例只适合 worker 模式。

### 6.1 启用 worker mode

```bash
ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/enable_edgeinfer_worker_mode.sh"
```

### 6.2 执行 streaming SDK 示例

```bash
cd ~/edgeinfer-rk3588
EDGEINFER_EXPECT_STREAM=1 python3 scripts/host/check_openai_sdk_examples.py
```

或者直接执行：

```bash
python3 examples/openai_sdk_streaming_chat.py
```

核心代码：

```python
stream = client.chat.completions.create(
    model=MODEL_ID,
    messages=[
        {
            "role": "system",
            "content": "你是 EdgeInfer-RK3588 端侧推理助手。",
        },
        {
            "role": "user",
            "content": "请用一句话介绍 RK3588。",
        },
    ],
    max_tokens=64,
    stream=True,
)

for chunk in stream:
    if not chunk.choices:
        continue

    choice = chunk.choices[0]
    delta = choice.delta

    content = getattr(delta, "content", None)
    if content:
        print(content, end="", flush=True)

    if choice.finish_reason is not None:
        final_finish_reason = choice.finish_reason
```

### 6.3 恢复 one-shot

```bash
ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/disable_edgeinfer_worker_mode.sh"
```

说明：

```text
1. worker 模式支持 stream=True；
2. one-shot 模式不支持 stream=True；
3. streaming 结束时 finish_reason 应为 stop；
4. 当前 streaming 示例不统计 first-token latency；
5. first-token latency 后续可在 Phase 15F / Phase 16 中单独实现。
```

---

## 7. SDK smoke test

脚本：

```text
scripts/host/check_openai_sdk_examples.py
```

默认行为：

```text
1. 检查 openai Python package 是否安装；
2. 运行 examples/openai_sdk_chat_completion.py；
3. 默认跳过 streaming 示例；
4. 提示设置 EDGEINFER_EXPECT_STREAM=1 后再运行 streaming。
```

执行：

```bash
python3 scripts/host/check_openai_sdk_examples.py
```

worker streaming 验证：

```bash
EDGEINFER_EXPECT_STREAM=1 python3 scripts/host/check_openai_sdk_examples.py
```

设计原因：

```text
streaming 示例只有在 RKLLM persistent worker mode 下才会成功；
默认 one-shot 模式下 stream=True 应被服务端拒绝；
one-shot stream 拒绝行为已经由 scripts/host/test_openai_chat_client.py 覆盖。
```

---

## 8. SDK 当前可用字段

当前推荐使用：

| 字段 | SDK 参数 | 当前状态 |
| --- | --- | --- |
| `model` | `model=MODEL_ID` | 支持 |
| `messages` | `messages=[...]` | 支持 |
| `max_tokens` | `max_tokens=64` | 支持 |
| `stream=False` | `stream=False` | 支持 |
| `stream=True` | `stream=True` | worker 模式支持 |
| `stop` | `stop=[...]` | 支持 |
| `top_p=1.0` | `top_p=1.0` | 支持默认值 |
| `response_format={"type":"text"}` | `response_format={"type":"text"}` | 支持 |

当前不推荐使用：

| 字段 | 当前行为 |
| --- | --- |
| `top_p != 1.0` | 返回 `top_p_not_supported` |
| `response_format={"type":"json_object"}` | 返回 `response_format_not_supported` |
| `n > 1` | 返回 `n_not_supported` |
| `stream=True` in one-shot | 返回 `stream_backend_not_supported` |
| `tools` / `tool_calls` | 暂不支持 |
| `function_call` | 暂不支持 |
| `logprobs` | 暂不支持 |
| `seed` | 暂不支持 |

---

## 9. 与官方 OpenAI API 的差异

当前 `edgeinfer-rk3588` 是 OpenAI-like / OpenAI-compatible MVP，而不是完整 OpenAI API 实现。

主要差异：

```text
1. 不支持真实 API key 鉴权；
2. 不支持组织 / project 级认证语义；
3. usage 是 estimated，不是 tokenizer 精确值；
4. finish_reason 当前可靠返回 stop，不可靠返回 length；
5. stream=True 依赖 worker backend；
6. 不支持 JSON mode；
7. 不支持 tool calls；
8. 不支持 n>1 多候选；
9. 不支持 top_p 采样下传；
10. 不支持 logprobs。
```

项目当前原则：

```text
能可靠支持的字段明确支持；
不能可靠支持的字段显式拒绝；
不假装完全兼容官方 OpenAI API。
```

---

## 10. 推荐异常处理方式

SDK 调用时建议捕获异常，并解析服务端错误：

```python
from openai import BadRequestError, NotFoundError, APIStatusError

try:
    completion = client.chat.completions.create(
        model=MODEL_ID,
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=64,
    )
except BadRequestError as exc:
    print("bad request:", exc)
except NotFoundError as exc:
    print("model not found:", exc)
except APIStatusError as exc:
    print("status:", exc.status_code)
    print("response:", exc.response)
```

客户端重试建议：

```text
1. 400/404 通常不重试，需要修正请求；
2. 429 llm_backend_busy 可以稍后重试；
3. 502/504 可以有限次数重试；
4. 不要依赖 message 做程序分支，应优先依赖 detail.error.code。
```

---

## 11. 常用命令汇总

### 11.1 非流式 SDK smoke test

```bash
cd ~/edgeinfer-rk3588
python3 scripts/host/check_openai_sdk_examples.py
```

### 11.2 worker streaming SDK smoke test

```bash
ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/enable_edgeinfer_worker_mode.sh"

EDGEINFER_EXPECT_STREAM=1 python3 scripts/host/check_openai_sdk_examples.py

ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/disable_edgeinfer_worker_mode.sh"
```

### 11.3 OpenAI-like API client test

```bash
python3 scripts/host/test_openai_chat_client.py
```

---

## 12. 阶段结论

Phase 15E 明确了当前 SDK 兼容边界：

```text
1. OpenAI Python SDK base_url 接入已经可用；
2. 非流式 chat completion 可以直接使用；
3. worker 模式下 streaming 可以使用；
4. one-shot streaming 会被显式拒绝；
5. api_key 当前只是 SDK 初始化占位符；
6. 当前仍是 OpenAI-like MVP，不是完整 OpenAI API 替代品。
```

后续如需进一步增强，可优先考虑：

```text
1. SDK error handling example；
2. stream first-token latency example；
3. JSON mode 拒绝/兼容示例；
4. 更完整的 Python client wrapper；
5. 加入可选 API key 鉴权。
```
