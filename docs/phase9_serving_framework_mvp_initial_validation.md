# Phase 9：EdgeInfer-RK3588 Serving Framework MVP 初始验证

## 1. 阶段目标

Phase 9 的目标是将已经跑通的 YOLOv11、Qwen2.5、Qwen3-4B 模型纳入统一端侧推理服务框架，完成从“单模型验证”到“模型管理 + API Serving + Benchmark + 调度”的工程化过渡。

本阶段 MVP 先完成以下内容：

- 建立 `server/` 服务框架目录；
- 新增 `configs/server.yaml`；
- 新增 `configs/scheduler.yaml`；
- 实现模型注册读取；
- 实现 FastAPI 服务入口；
- 实现 `/v1/health`；
- 实现 `/v1/models`；
- 实现 `/v1/metrics`；
- 实现 `/v1/chat/completions` 原型；
- 使用 fake LLM 模式验证 Chat API 链路。

## 2. 当前新增目录

```text
server/
  main.py
  api/
    health_api.py
    model_api.py
    metrics_api.py
    chat_api.py
  model_manager/
    config.py
    registry.py
  runtime/
    rkllm_backend.py
  scheduler/
    request_queue.py
```

## 3. 当前新增配置

```text
configs/server.yaml
configs/scheduler.yaml
```

## 4. 已验证 API

### 4.1 Health API

请求：

```bash
curl http://127.0.0.1:8000/v1/health | python3 -m json.tool
```

结果：

```text
/v1/health 返回 200 OK
服务状态为 ok
能返回 legacy demo service 禁用提醒
```

### 4.2 Models API

请求：

```bash
curl http://127.0.0.1:8000/v1/models | python3 -m json.tool
```

结果：

```text
/v1/models 返回 200 OK
成功读取 7 个模型条目
qwen3-4b-rkllm-all-npu recommended=true
qwen3-4b-rkllm-hybrid recommended=false
validation 全部为空列表
```

核心模型：

```text
qwen3-4b-rkllm-all-npu
qwen3-4b-rkllm-hybrid
Qwen2.5-0.5B-Instruct
Qwen2.5-1.5B-Instruct
YOLOv11n-FP-Baseline
```

### 4.3 Metrics API

请求：

```bash
curl http://127.0.0.1:8000/v1/metrics | python3 -m json.tool
```

结果：

```text
/v1/metrics 返回 200 OK
能返回 uptime_seconds
能返回 pid
能返回 process_max_rss_kb
能返回 LLM 队列基础信息
```

### 4.4 Chat Completions API

启动方式：

```bash
EDGEINFER_FAKE_LLM=1 \
python3 -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```

请求：

```bash
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-4b-rkllm-all-npu",
    "messages": [
      {"role": "system", "content": "你是 EdgeInfer-RK3588 端侧推理助手。"},
      {"role": "user", "content": "简单介绍一下 RK3588。"}
    ],
    "max_new_tokens": 64
  }' | python3 -m json.tool
```

结果：

```text
/v1/chat/completions 返回 200 OK
fake LLM 模式正常返回 assistant message
返回结构接近 OpenAI chat completions 风格
返回 edgeinfer backend、latency、runtime、rknpu_driver、requirement 等扩展信息
```

## 5. OpenAPI 路由验证

检查命令：

```bash
python3 - <<'PY'
from server.main import app

schema = app.openapi()

print("OPENAPI OK")
print("title:", schema["info"]["title"])
print("version:", schema["info"]["version"])
print("paths:")

for path, item in sorted(schema["paths"].items()):
    methods = ",".join(k.upper() for k in item.keys())
    print(f"  {methods:12s} {path}")
PY
```

验证结果：

```text
OPENAPI OK
title: EdgeInfer-RK3588 Serving Framework
version: phase9-mvp
paths:
  GET          /
  POST         /v1/chat/completions
  GET          /v1/health
  GET          /v1/metrics
  GET          /v1/models
  GET          /v1/models/{model_id}
```

## 6. 代码语法验证

检查命令：

```bash
python3 -m compileall -q server
echo "compileall OK"
```

结果：

```text
compileall OK
```

## 7. 当前结论

Phase 9 Serving Framework MVP 的第一版骨架已经完成，并通过本地 fake LLM 模式验证。

当前已经具备：

- FastAPI 服务入口；
- 模型注册读取；
- 基础健康检查；
- 基础模型列表；
- 基础运行指标；
- LLM 请求队列；
- Chat Completions API 原型；
- fake LLM 后端验证链路。

下一步应将 fake LLM 后端切换为板端可运行的 RKLLM wrapper，优先接入推荐模型：

```text
qwen3-4b-rkllm-all-npu
```

## 8. 后续工作

后续建议按以下顺序推进：

1. 提交 Phase 9 MVP skeleton；
2. 在板端同步 `server/` 与配置；
3. 封装 `rkllm_enhanced` stdin/stdout wrapper；
4. 将 `/v1/chat/completions` 接入真实 Qwen3-4B all-NPU；
5. 增加 LLM benchmark 自动化；
6. 增加 systemd service；
7. 后续再扩展 streaming、SSE、Web Demo 与多模型调度。
