# Phase 9：busy 拒绝机制与 metrics 验证记录

## 1. 文档目的

本文档记录 `edgeinfer-rk3588` 项目 Phase 9 Serving Framework 在真实 Qwen3-4B RKLLM 后端接入之后，进一步完成的服务稳定性增强工作。

本阶段的核心目标是：

```text
防止多个真实 Qwen3-4B all-NPU 请求同时进入 RKLLM 后端，避免并发抢占 RKNPU / DRM / IOVA 资源。
```

在前一阶段中，项目已经完成：

```text
systemd edgeinfer-serving.service
-> uvicorn
-> FastAPI
-> /v1/chat/completions
-> rkllm_backend.py
-> rkllm_runner.py
-> rkllm_enhanced_no_template
-> Qwen3-4B all-NPU RKLLM
```

但该链路仍然存在一个风险：如果多个 HTTP 请求同时调用 `/v1/chat/completions`，就可能同时启动多个 RKLLM 子进程，导致多个 Qwen3-4B 模型实例同时加载并竞争 NPU、DRM、IOVA 和内存资源。

因此，本阶段增加了：

```text
- busy 拒绝机制
- LLM 请求状态统计
- /v1/metrics 后端状态暴露
- 结构化错误返回
- 并发请求验证
```

---

## 2. 阶段结论

本阶段已经完成并验证：

```text
Phase 9 Serving Framework 已支持 LLM busy 拒绝与服务状态 metrics。
```

当前行为为：

```text
当没有 LLM 请求运行时：
    /v1/chat/completions 正常进入真实 Qwen3-4B all-NPU 推理。

当已有 LLM 请求正在运行时：
    新的 /v1/chat/completions 请求不会等待排队，
    而是立即返回 HTTP 429，错误码为 llm_backend_busy。
```

本阶段最新提交：

```text
8406a2f add llm busy rejection and serving metrics
```

---

## 3. 为什么需要 busy 拒绝机制

当前真实 RKLLM 后端仍然是 one-shot 子进程模式。

每次 Chat API 请求都会执行：

```text
FastAPI 收到请求
-> rkllm_backend.py 构造调用
-> 启动 rkllm_runner.py
-> rkllm_runner.py 启动 rkllm_enhanced_no_template
-> 重新加载 Qwen3-4B RKLLM 模型
-> 使用 RKNPU 执行推理
-> 清洗输出
-> 返回 JSON
-> 子进程退出
```

Qwen3-4B all-NPU 模型对运行环境要求较高，之前已经验证必须保持 clean RKNPU 环境：

```text
qwen-web-chat.service disabled / inactive
yolov5-web.service disabled / inactive
```

如果允许多个真实 LLM 请求并发执行，就可能出现：

```text
- 多个 RKLLM 进程同时加载大模型
- 多个进程同时访问 RKNPU
- DRM / IOVA / CMA 资源竞争
- 内存峰值过高
- 模型加载失败
- RKLLM runtime 报错
- 服务卡死或长时间无响应
```

因此，在 long-running worker 或模型常驻后端完成之前，最稳妥的策略是：

```text
同一时间只允许 1 个真实 LLM 请求进入后端。
```

---

## 4. 等待队列与 reject_when_busy 的区别

### 4.1 原来的 Semaphore 等待队列

原始 `server/scheduler/request_queue.py` 使用的是：

```python
asyncio.Semaphore(max_concurrent=1)
```

其行为是：

```text
第一个请求进入后端；
第二个请求如果到来，会等待第一个请求完成；
等第一个请求结束后，第二个请求再进入后端。
```

这种方式可以限制并发数量，但问题是：

```text
- 调用方不知道请求正在排队
- 请求可能长时间挂起
- 对 one-shot 大模型后端不够透明
- 如果第一个请求耗时 40-60 秒，第二个请求也会等待很久
- 如果多用户访问，HTTP 请求可能堆积
```

### 4.2 新的 reject_when_busy 策略

本阶段将策略改为：

```text
reject_when_busy
```

其行为是：

```text
第一个请求进入后端；
第二个请求如果到来，立即返回 429 llm_backend_busy。
```

这样做的好处是：

```text
- 明确保护 RKLLM / RKNPU 资源
- 调用方能立即知道后端繁忙
- 不会在服务端堆积长时间等待的请求
- 更适合当前 one-shot RKLLM 后端
- 后续客户端可以根据 retryable=true 自行重试
```

---

## 5. 修改文件

本阶段主要修改 3 个文件：

```text
server/scheduler/request_queue.py
server/api/chat_api.py
server/api/metrics_api.py
```

---

## 6. `request_queue.py` 改动说明

文件：

```text
server/scheduler/request_queue.py
```

新增异常类型：

```python
class LLMQueueBusyError(RuntimeError):
    pass


class LLMQueueTimeoutError(RuntimeError):
    pass
```

新增 `LLMRequestQueue.run_nowait()`：

```text
如果后端空闲，则立即执行任务；
如果后端繁忙，则立即抛出 LLMQueueBusyError；
如果任务超时，则抛出 LLMQueueTimeoutError。
```

新增状态统计字段：

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

新增 `snapshot()` 方法，用于将当前 LLM 后端状态暴露给 `/v1/metrics` 和错误响应。

当前队列实例：

```python
llm_queue = LLMRequestQueue(max_concurrent=1)
```

当前策略：

```text
queue_policy = reject_when_busy
```

---

## 7. `chat_api.py` 改动说明

文件：

```text
server/api/chat_api.py
```

主要改动：

```text
- 引入 LLMQueueBusyError
- 引入 LLMQueueTimeoutError
- 使用 llm_queue.run_nowait()
- 将 busy 错误映射为 HTTP 429
- 将 timeout 错误映射为 HTTP 504
- 将 RKLLM runtime 错误映射为 HTTP 502
- 在成功响应的 edgeinfer 字段中加入 llm_queue.snapshot()
- 在错误响应中加入结构化 error 和 edgeinfer.llm 状态
```

当前超时时间来自环境变量：

```python
LLM_TIMEOUT_SECONDS = float(os.environ.get("EDGEINFER_LLM_TIMEOUT_SECONDS", "90"))
```

如果没有设置环境变量，默认超时时间为：

```text
90 seconds
```

---

## 8. 结构化错误返回

### 8.1 busy 错误

当 LLM 后端正在运行真实推理时，第二个请求立即返回：

```text
HTTP 429
```

错误码：

```text
llm_backend_busy
```

示例：

```json
{
    "detail": {
        "error": {
            "code": "llm_backend_busy",
            "message": "LLM backend is busy; please retry later",
            "type": "edgeinfer_error",
            "retryable": true
        },
        "edgeinfer": {
            "model": "qwen3-4b-rkllm-all-npu",
            "backend": "rkllm-runner",
            "llm": {
                "max_concurrent": 1,
                "busy": true,
                "queue_policy": "reject_when_busy",
                "total_requests": 2,
                "accepted_requests": 1,
                "rejected_busy": 1,
                "completed_requests": 0,
                "failed_requests": 0,
                "timeout_requests": 0,
                "last_error": "LLM backend busy",
                "last_latency_ms": null,
                "current_model": "qwen3-4b-rkllm-all-npu"
            }
        }
    }
}
```

其中：

```text
retryable: true
```

表示调用方可以稍后重试。

### 8.2 timeout 错误

如果 LLM 请求超时，返回：

```text
HTTP 504
```

错误码：

```text
llm_timeout
```

当前阶段没有专门做真实 timeout 注入测试，因为真实 Qwen3-4B 请求通常能在 35-60 秒左右完成，而默认超时时间是 90 秒。

### 8.3 RKLLM runtime 错误

如果 runner 或 RKLLM 后端异常，返回：

```text
HTTP 502
```

错误码：

```text
rkllm_runtime_error
```

这类错误一般表示模型文件缺失、runner 失败、RKLLM runtime 失败、底层资源错误等。

---

## 9. `metrics_api.py` 改动说明

文件：

```text
server/api/metrics_api.py
```

原来 `/v1/metrics` 只返回基础进程信息：

```text
uptime_seconds
pid
process_max_rss_kb
llm.max_concurrent
llm.queue_enabled
```

本阶段改为返回完整 LLM 状态快照：

```json
{
    "uptime_seconds": 7.582,
    "pid": 4729,
    "process_max_rss_kb": 29100,
    "llm": {
        "max_concurrent": 1,
        "busy": false,
        "queue_policy": "reject_when_busy",
        "total_requests": 0,
        "accepted_requests": 0,
        "rejected_busy": 0,
        "completed_requests": 0,
        "failed_requests": 0,
        "timeout_requests": 0,
        "last_error": null,
        "last_latency_ms": null,
        "last_started_at": null,
        "last_finished_at": null,
        "current_model": null
    },
    "notes": "Phase 9 serving metrics. The current RKLLM backend uses a one-shot subprocess runner and rejects concurrent LLM requests."
}
```

---

## 10. `/v1/metrics` 字段含义

### 10.1 `max_concurrent`

```text
当前允许的最大 LLM 并发数。
```

Phase 9 MVP 中固定为：

```text
1
```

### 10.2 `busy`

```text
当前是否有 LLM 请求正在运行。
```

取值：

```text
true  - 当前后端繁忙
false - 当前后端空闲
```

### 10.3 `queue_policy`

```text
当前请求调度策略。
```

本阶段为：

```text
reject_when_busy
```

表示忙时立即拒绝，而不是排队等待。

### 10.4 `total_requests`

```text
收到的 LLM 请求总数。
```

包括被接受的请求和因 busy 被拒绝的请求。

### 10.5 `accepted_requests`

```text
实际进入后端执行的请求数量。
```

### 10.6 `rejected_busy`

```text
因后端繁忙而被拒绝的请求数量。
```

### 10.7 `completed_requests`

```text
成功完成的 LLM 请求数量。
```

### 10.8 `failed_requests`

```text
执行失败的 LLM 请求数量。
```

包括 timeout 或 runtime error。

### 10.9 `timeout_requests`

```text
因超时失败的 LLM 请求数量。
```

### 10.10 `last_error`

```text
最近一次错误信息。
```

如果最近一次成功完成，则为：

```text
null
```

### 10.11 `last_latency_ms`

```text
最近一次被接受请求的端到端耗时。
```

单位：

```text
ms
```

### 10.12 `last_started_at`

```text
最近一次被接受请求的开始时间戳。
```

### 10.13 `last_finished_at`

```text
最近一次被接受请求的结束时间戳。
```

### 10.14 `current_model`

```text
当前正在运行的模型 ID。
```

空闲时为：

```text
null
```

运行时可能为：

```text
qwen3-4b-rkllm-all-npu
```

---

## 11. 板端同步与服务重启

同步到板端的正确路径为：

```bash
scp server/api/chat_api.py \
  linaro@192.168.43.7:/home/linaro/edgeinfer-rk3588-board/server/api/chat_api.py

scp server/api/metrics_api.py \
  linaro@192.168.43.7:/home/linaro/edgeinfer-rk3588-board/server/api/metrics_api.py

scp server/scheduler/request_queue.py \
  linaro@192.168.43.7:/home/linaro/edgeinfer-rk3588-board/server/scheduler/request_queue.py
```

随后在板端执行语法检查并重启服务：

```bash
ssh linaro@192.168.43.7 '
cd /home/linaro/edgeinfer-rk3588-board

. .venv-serving/bin/activate

python -m compileall -q server
echo "board compileall OK"

sudo systemctl restart edgeinfer-serving.service

sleep 2

./scripts/board/check_edgeinfer_serving.sh
'
```

验证结果：

```text
board compileall OK
edgeinfer-serving.service enabled
edgeinfer-serving.service active
0.0.0.0:8000 正常监听
legacy services disabled / inactive
/v1/health OK
```

---

## 12. 初始 metrics 验证

命令：

```bash
curl http://192.168.43.7:8000/v1/metrics | python3 -m json.tool
```

返回关键字段：

```json
{
    "llm": {
        "max_concurrent": 1,
        "busy": false,
        "queue_policy": "reject_when_busy",
        "total_requests": 0,
        "accepted_requests": 0,
        "rejected_busy": 0,
        "completed_requests": 0,
        "failed_requests": 0,
        "timeout_requests": 0,
        "last_error": null,
        "last_latency_ms": null,
        "last_started_at": null,
        "last_finished_at": null,
        "current_model": null
    }
}
```

这说明服务刚重启后，LLM 后端处于空闲状态，且计数器初始化正常。

---

## 13. 并发 busy 测试方法

本阶段使用一个临时脚本同时发起两个 Chat API 请求。

测试逻辑：

```text
1. 启动第一个较长请求，并放到后台运行
2. 等待 2 秒，让第一个请求进入真实 Qwen3 推理
3. 发起第二个请求
4. 观察第二个请求是否立即返回 429
5. 等待第一个请求完成
6. 检查第一个请求是否正常返回 200
```

测试脚本核心命令：

```bash
URL="http://192.168.43.7:8000/v1/chat/completions"

(
  curl -s -o "$OUT1" -w "%{http_code}" \
    -X POST "$URL" \
    -H "Content-Type: application/json" \
    -d @"$REQ1" > "$CODE1"
) &

PID1=$!

sleep 2

curl -s -o "$OUT2" -w "%{http_code}" \
  -X POST "$URL" \
  -H "Content-Type: application/json" \
  -d @"$REQ2" > "$CODE2"

wait "$PID1" || true
```

---

## 14. 并发 busy 测试结果

测试结果：

```text
第一个请求：HTTP 200
第二个请求：HTTP 429
```

第二个请求返回：

```json
{
    "detail": {
        "error": {
            "code": "llm_backend_busy",
            "message": "LLM backend is busy; please retry later",
            "type": "edgeinfer_error",
            "retryable": true
        },
        "edgeinfer": {
            "model": "qwen3-4b-rkllm-all-npu",
            "backend": "rkllm-runner",
            "llm": {
                "max_concurrent": 1,
                "busy": true,
                "queue_policy": "reject_when_busy",
                "total_requests": 2,
                "accepted_requests": 1,
                "rejected_busy": 1,
                "completed_requests": 0,
                "failed_requests": 0,
                "timeout_requests": 0,
                "last_error": "LLM backend busy",
                "last_latency_ms": null,
                "current_model": "qwen3-4b-rkllm-all-npu"
            }
        }
    }
}
```

第一个请求最终返回：

```text
HTTP 200
```

返回 metadata 中包含：

```json
{
    "edgeinfer": {
        "backend": "rkllm-runner",
        "latency_ms": 58816.122,
        "recommended_model": true,
        "runtime": "rkllm-runtime-v1.3.0",
        "rknpu_driver": "v0.9.8",
        "llm": {
            "max_concurrent": 1,
            "busy": false,
            "queue_policy": "reject_when_busy",
            "total_requests": 2,
            "accepted_requests": 1,
            "rejected_busy": 1,
            "completed_requests": 1,
            "failed_requests": 0,
            "timeout_requests": 0,
            "last_error": null,
            "last_latency_ms": 58816.656,
            "current_model": null
        }
    }
}
```

验证结论：

```text
busy 拒绝机制生效。
```

---

## 15. 并发测试后的 metrics 验证

执行：

```bash
curl http://192.168.43.7:8000/v1/metrics | python3 -m json.tool
```

返回关键字段：

```json
{
    "llm": {
        "max_concurrent": 1,
        "busy": false,
        "queue_policy": "reject_when_busy",
        "total_requests": 2,
        "accepted_requests": 1,
        "rejected_busy": 1,
        "completed_requests": 1,
        "failed_requests": 0,
        "timeout_requests": 0,
        "last_error": null,
        "last_latency_ms": 58816.656,
        "current_model": null
    }
}
```

该结果说明：

```text
- 总请求数为 2
- 进入后端执行的请求数为 1
- busy 拒绝的请求数为 1
- 成功完成的请求数为 1
- 当前后端已恢复空闲
- 最近一次 accepted 请求耗时约 58.8 秒
```

---

## 16. 关于模型回答幻觉的说明

在并发测试中，第一个长请求虽然服务返回 200，但模型回答中出现了明显不可靠内容，例如将 RK3588 错误描述为“联发科推出”、包含“4nm、5G、Wi-Fi 6E”等不准确表述。

这不是本阶段服务链路问题，而是大模型在开放式问题中产生的事实幻觉。

本阶段验证目标是：

```text
- 后端 busy 拒绝是否生效
- 服务是否避免并发抢占
- metrics 是否正确统计
- 第一个真实请求是否仍能完成
```

因此，该模型回答质量问题不影响本阶段结论。

后续若要改善模型事实可靠性，可以考虑：

```text
- 更强 system prompt
- 固定事实约束模板
- RAG 检索增强
- 对特定硬件信息使用结构化知识库
- 对模型输出做事实校验
```

---

## 17. 当前限制

本阶段尚未完整验证 timeout 场景。

原因：

```text
默认 LLM_TIMEOUT_SECONDS = 90
当前 Qwen3-4B one-shot 请求一般在 35-60 秒内完成
```

如果后续要验证 timeout，可以临时降低环境变量：

```text
EDGEINFER_LLM_TIMEOUT_SECONDS=5
```

然后重启 systemd 服务并发起真实请求，观察是否返回：

```text
HTTP 504
llm_timeout
```

但在当前阶段，为避免无意义地中断真实 RKLLM 进程，暂未做该破坏性测试。

---

## 18. 后续建议

下一步建议继续推进：

```text
1. 增加主机侧 smoke test 脚本
2. 将 health / models / metrics / chat / busy 测试脚本化
3. 增加 docs 中的 busy metrics 验证文档
4. 再考虑 timeout 注入测试
5. 设计 long-running RKLLM worker
```

其中优先级最高的是：

```text
主机侧 smoke test 脚本
```

原因是后续每次修改 serving 层后，都需要快速验证：

```text
- systemd 服务是否 active
- /v1/health 是否正常
- /v1/models 是否正常
- /v1/metrics 是否正常
- 单次 chat 是否正常
- 并发 busy 是否正常
```

---

## 19. 阶段结论

本阶段完成后，`edgeinfer-rk3588` 的 Phase 9 Serving Framework 已经具备基础服务保护能力。

当前服务能力包括：

```text
- systemd 后台运行
- FastAPI 对外提供 OpenAI-compatible API
- 真实 Qwen3-4B all-NPU RKLLM 推理
- busy 时返回 429 llm_backend_busy
- timeout / runtime error 结构化错误框架
- /v1/metrics 暴露 LLM 后端状态
- 并发请求保护 RKNPU / DRM / IOVA 资源
```

这标志着 Phase 9 从“真实服务可运行”进一步推进到“真实服务具备基础稳定性保护”。
