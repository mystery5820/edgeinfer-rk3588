# Phase 9 Serving 运维与验证手册

本文档用于记录 EdgeInfer-RK3588 Phase 9 Serving Framework 的日常部署、运行模式切换、验证脚本和故障排查流程。

当前 Phase 9 的核心目标是：在 RK3588 板端提供一个工程化的 OpenAI-like LLM Serving API，并保证 one-shot 与 persistent worker 两种 RKLLM 后端模式都可以被清晰部署、验证和回退。

---

## 1. 当前 Serving 服务概览

### 1.1 服务路径

主机侧仓库：

```bash
~/edgeinfer-rk3588
```

板端部署目录：

```bash
/home/linaro/edgeinfer-rk3588-board
```

板端模型与资产根目录：

```bash
/userdata/edgeinfer-assets
```

Serving Python 虚拟环境：

```bash
/home/linaro/edgeinfer-rk3588-board/.venv-serving
```

### 1.2 systemd 服务

当前 Serving 服务名：

```bash
edgeinfer-serving.service
```

服务监听端口：

```text
0.0.0.0:8000
```

常用检查命令：

```bash
ssh linaro@192.168.43.7 '
cd /home/linaro/edgeinfer-rk3588-board
./scripts/board/check_edgeinfer_serving.sh
'
```

### 1.3 Legacy demo 服务要求

Phase 9 Serving 运行时要求旧 demo 服务保持 disabled/inactive，避免占用 RKLLM / RKNPU 资源：

```text
qwen-web-chat.service
yolov5-web.service
```

`check_edgeinfer_serving.sh` 会检查这两个服务的状态。

---

## 2. 当前 API

当前 Serving API 主要包括：

```text
GET  /v1/health
GET  /v1/models
GET  /v1/metrics
POST /v1/chat/completions
```

`/v1/chat/completions` 的 OpenAI-like 兼容范围、请求字段、错误码和 curl 示例见：

```text
docs/phase9_openai_compat.md
```

### 2.1 Health

```bash
curl http://192.168.43.7:8000/v1/health | python3 -m json.tool
```

预期核心字段：

```json
{
  "status": "ok",
  "service": "edgeinfer-rk3588-serving",
  "phase": "phase9-serving-framework-mvp"
}
```

### 2.2 Models

```bash
curl http://192.168.43.7:8000/v1/models | python3 -m json.tool
```

当前推荐 LLM 模型：

```text
qwen3-4b-rkllm-all-npu
```

对应 RKLLM 文件：

```text
/userdata/edgeinfer-assets/models/llm/rkllm_outputs/Qwen3-4B-w8a8-npu.rkllm
```

### 2.3 Metrics

```bash
curl http://192.168.43.7:8000/v1/metrics | python3 -m json.tool
```

重点关注字段：

```json
{
  "rkllm_backend": {
    "mode": "oneshot 或 worker",
    "worker_enabled": false,
    "worker_ctx": 1024,
    "worker_max_new_tokens": 128,
    "worker_bin": "...rkllm_enhanced_no_template_no_history",
    "worker_runtime": null
  },
  "llm": {
    "max_concurrent": 1,
    "queue_policy": "reject_when_busy",
    "total_requests": 0,
    "accepted_requests": 0,
    "rejected_busy": 0,
    "completed_requests": 0,
    "failed_requests": 0,
    "timeout_requests": 0,
    "last_error": null
  }
}
```

---

## 3. RKLLM 后端模式

Phase 9 当前支持两种 RKLLM 后端模式。

### 3.1 默认 one-shot 模式

默认模式不需要额外环境变量：

```text
EDGEINFER_RKLLM_BACKEND_MODE 未设置或为 oneshot
```

特征：

```text
每次请求启动一次 rkllm runner 子进程
实现简单，资源生命周期清晰
默认安全模式
首 token / 总延迟较高
```

metrics 预期：

```json
{
  "rkllm_backend": {
    "mode": "oneshot",
    "worker_enabled": false,
    "worker_runtime": null
  }
}
```

Chat 响应预期：

```json
{
  "edgeinfer": {
    "backend": "rkllm-runner"
  }
}
```

### 3.2 可选 persistent worker 模式

worker 模式通过 systemd drop-in 启用：

```bash
ssh linaro@192.168.43.7 '
cd /home/linaro/edgeinfer-rk3588-board
./scripts/board/enable_edgeinfer_worker_mode.sh
'
```

特征：

```text
服务启动后仍然懒启动 worker
第一次 chat 请求才真正启动 RKLLM worker 子进程
后续请求复用同一个 no-history worker
仍然保持 max_concurrent=1
并发请求采用 reject_when_busy 策略返回 429
systemctl restart/stop 时通过 FastAPI shutdown hook 主动清理 worker 子进程
```

systemd drop-in 主要环境变量：

```text
EDGEINFER_RKLLM_BACKEND_MODE=worker
EDGEINFER_RKLLM_WORKER_MAX_NEW=128
EDGEINFER_RKLLM_WORKER_CTX=1024
```

metrics 初始状态，即启用 worker 但尚未 chat：

```json
{
  "rkllm_backend": {
    "mode": "worker",
    "worker_enabled": true,
    "worker_runtime": {
      "started": false,
      "pid": null,
      "request_count": 0,
      "failed_request_count": 0
    }
  }
}
```

metrics 经过 chat 后：

```json
{
  "rkllm_backend": {
    "mode": "worker",
    "worker_enabled": true,
    "worker_runtime": {
      "started": true,
      "pid": 3050,
      "startup_ms": 4999.662,
      "request_count": 1,
      "failed_request_count": 0,
      "last_latency_ms": 14774.055,
      "last_error": null,
      "restart_count": 0
    }
  }
}
```

Chat 响应预期：

```json
{
  "edgeinfer": {
    "backend": "rkllm-persistent-worker"
  }
}
```

### 3.3 恢复默认 one-shot 模式

任何 worker 模式测试完成后，都应恢复默认 one-shot：

```bash
ssh linaro@192.168.43.7 '
cd /home/linaro/edgeinfer-rk3588-board
./scripts/board/disable_edgeinfer_worker_mode.sh
'
```

该脚本会删除：

```text
/etc/systemd/system/edgeinfer-serving.service.d/worker-mode.conf
/etc/systemd/system/edgeinfer-serving.service.d/worker-test.conf
```

如果显示 `not found`，说明对应 drop-in 本来不存在，这是正常情况。

---
### 3.3 Phase 10 stream=true SSE 模式

Phase 10 在 persistent worker 模式下新增 `stream=true` SSE 流式输出能力。

支持矩阵：

```text
one-shot 模式：
  stream=false：支持普通 JSON
  stream=true ：拒绝，HTTP 400，stream_backend_not_supported

worker 模式：
  stream=false：支持普通 JSON
  stream=true ：支持 text/event-stream SSE
```

手动验证 worker SSE：

```bash
cat > /tmp/edgeinfer_stream_req.json <<'JSON'
{
  "model": "qwen3-4b-rkllm-all-npu",
  "messages": [
    {"role": "user", "content": "请用一句话介绍 RK3588。"}
  ],
  "max_tokens": 64,
  "stream": true
}
JSON

ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/enable_edgeinfer_worker_mode.sh"

curl -N -sS \
  -H "Content-Type: application/json" \
  --data-binary @/tmp/edgeinfer_stream_req.json \
  http://192.168.43.7:8000/v1/chat/completions
```

预期可以看到：

```text
data: {"...","delta":{"role":"assistant"}}
data: {"...","delta":{"content":"R"}}
data: {"...","delta":{"content":"K3"}}
...
data: {"...","delta":{},"finish_reason":"stop"}
data: [DONE]
```

测试结束后恢复默认 one-shot：

```bash
ssh linaro@192.168.43.7 \
  "cd /home/linaro/edgeinfer-rk3588-board && ./scripts/board/disable_edgeinfer_worker_mode.sh"
```

完整设计与验证记录见：

```text
docs/phase10_streaming_sse.md
```

---


## 4. Host 侧脚本

Host 侧脚本位于：

```bash
scripts/host
```

当前主要脚本：

```text
scripts/host/deploy_serving_to_board.sh
scripts/host/smoke_test_serving.sh
scripts/host/validate_serving_modes.sh
scripts/host/check_openai_sdk_examples.py
```

### 4.1 deploy_serving_to_board.sh

用途：将主机侧 Serving 代码同步到板端，并完成编译检查、服务重启和健康检查。

普通部署：

```bash
cd ~/edgeinfer-rk3588
./scripts/host/deploy_serving_to_board.sh
```

带 one-shot smoke test 的部署：

```bash
cd ~/edgeinfer-rk3588
EDGEINFER_DEPLOY_SMOKE=1 \
EDGEINFER_EXPECT_BACKEND=rkllm-runner \
./scripts/host/deploy_serving_to_board.sh
```

该脚本会同步：

```text
server/
configs/
scripts/board/
```

不会同步或修改：

```text
/userdata/edgeinfer-assets
模型文件
第三方 RKLLM / RKNN runtime 文件
```

### 4.2 smoke_test_serving.sh

用途：对当前板端 Serving 服务执行单模式 smoke test。

默认 one-shot：

```bash
cd ~/edgeinfer-rk3588
EDGEINFER_EXPECT_BACKEND=rkllm-runner \
EDGEINFER_EXPECT_BACKEND_MODE=oneshot \
./scripts/host/smoke_test_serving.sh
```

worker 模式：

```bash
cd ~/edgeinfer-rk3588
EDGEINFER_EXPECT_BACKEND=rkllm-persistent-worker \
EDGEINFER_EXPECT_BACKEND_MODE=worker \
./scripts/host/smoke_test_serving.sh
```

该脚本会检查：

```text
/v1/health
/v1/models
/v1/metrics before chat
single chat completion
/v1/metrics after chat
busy rejection: 第二个请求应返回 HTTP 429 llm_backend_busy
/v1/metrics after busy test
```

在 one-shot 模式下，重点检查：

```text
backend=rkllm-runner
metrics mode=oneshot
worker_enabled=false
worker_runtime=null
```

在 worker 模式下，重点检查：

```text
backend=rkllm-persistent-worker
metrics mode=worker
worker_enabled=true
chat 后 worker_runtime.started=true
chat 后 worker_runtime.request_count>=1
worker_runtime.failed_request_count=0
```

### 4.3 validate_serving_modes.sh

用途：一键验证 one-shot 与 worker 两种模式，并在结束时自动恢复默认 one-shot。

推荐用于较大改动后的完整验收：

```bash
cd ~/edgeinfer-rk3588
./scripts/host/validate_serving_modes.sh
```

它会自动执行：

```text
1. disable worker，确保默认 one-shot
2. one-shot smoke test
3. enable worker
4. worker smoke test
5. cleanup 阶段自动 disable worker，恢复默认 one-shot
```

带部署的完整验收：

```bash
cd ~/edgeinfer-rk3588
EDGEINFER_VALIDATE_DEPLOY=1 \
./scripts/host/validate_serving_modes.sh
```

---

## 5. Board 侧脚本

Board 侧脚本位于：

```bash
/home/linaro/edgeinfer-rk3588-board/scripts/board
```

当前主要脚本：

```text
build_rkllm_no_history_binary.sh
check_edgeinfer_serving.sh
disable_edgeinfer_worker_mode.sh
enable_edgeinfer_worker_mode.sh
install_edgeinfer_serving_service.sh
probe_rkllm_persistent_worker.py
```

### 5.1 check_edgeinfer_serving.sh

用途：检查 systemd 服务、端口、uvicorn 进程、legacy 服务和本地 health。

```bash
ssh linaro@192.168.43.7 '
cd /home/linaro/edgeinfer-rk3588-board
./scripts/board/check_edgeinfer_serving.sh
'
```

通过时应看到：

```text
service active
enabled
port 8000 listening
legacy services disabled/inactive
health status ok
```

### 5.2 enable_edgeinfer_worker_mode.sh

用途：启用 persistent worker 模式。

```bash
ssh linaro@192.168.43.7 '
cd /home/linaro/edgeinfer-rk3588-board
./scripts/board/enable_edgeinfer_worker_mode.sh
'
```

通过时应看到 systemd 环境里包含：

```text
EDGEINFER_RKLLM_BACKEND_MODE=worker
EDGEINFER_RKLLM_WORKER_MAX_NEW=128
EDGEINFER_RKLLM_WORKER_CTX=1024
```

### 5.3 disable_edgeinfer_worker_mode.sh

用途：关闭 persistent worker 模式，恢复默认 one-shot。

```bash
ssh linaro@192.168.43.7 '
cd /home/linaro/edgeinfer-rk3588-board
./scripts/board/disable_edgeinfer_worker_mode.sh
'
```

建议每次 worker 测试后执行。

### 5.4 probe_rkllm_persistent_worker.py

用途：绕过 FastAPI，直接验证 persistent worker 进程的独立可用性。

典型用途：

```text
当 FastAPI worker 模式异常时，用该脚本确认问题是在 RKLLM worker 自身，还是在 Serving API 封装层。
```

注意：直接 probe 可能占用 RKLLM / NPU 资源，执行前应确保 Serving 服务不会同时使用 RKLLM。

---

## 6. 标准开发流程

### 6.1 小改动流程

适用于只修改 Python API、metrics、runtime 封装、脚本等轻量改动：

```bash
cd ~/edgeinfer-rk3588
python3 -m compileall -q server
./scripts/host/deploy_serving_to_board.sh
```

如果只需要确认默认 one-shot：

```bash
EDGEINFER_DEPLOY_SMOKE=1 \
EDGEINFER_EXPECT_BACKEND=rkllm-runner \
./scripts/host/deploy_serving_to_board.sh
```

### 6.2 较大改动流程

适用于影响 RKLLM backend、worker、queue、metrics、chat API 的改动：

```bash
cd ~/edgeinfer-rk3588
./scripts/host/deploy_serving_to_board.sh
./scripts/host/validate_serving_modes.sh
```

或者合并为：

```bash
EDGEINFER_VALIDATE_DEPLOY=1 \
./scripts/host/validate_serving_modes.sh
```

### 6.3 提交前检查

```bash
cd ~/edgeinfer-rk3588

git status --short
git diff --stat
```

确认没有临时 patch 脚本：

```text
apply_*.py
```

确认板端默认已恢复 one-shot：

```bash
ssh linaro@192.168.43.7 '
systemctl show edgeinfer-serving.service -p Environment --no-pager
'
```

如果 Environment 中不包含 `EDGEINFER_RKLLM_BACKEND_MODE=worker`，说明默认模式已恢复。

---

## 7. 常见问题排查

### 7.1 服务不 active

检查：

```bash
ssh linaro@192.168.43.7 '
systemctl status edgeinfer-serving.service --no-pager
journalctl -u edgeinfer-serving.service -n 120 --no-pager
'
```

常见原因：

```text
Python 语法错误
模块导入失败
工作目录不对
虚拟环境缺依赖
端口 8000 被占用
```

### 7.2 health 正常但 chat 失败

检查 metrics：

```bash
curl http://192.168.43.7:8000/v1/metrics | python3 -m json.tool
```

重点字段：

```text
llm.failed_requests
llm.timeout_requests
llm.last_error
rkllm_backend.mode
rkllm_backend.worker_runtime.last_error
```

### 7.3 worker 模式启用后没有 worker 进程

这是正常情况。worker 是懒启动，启用 worker 模式后，只有第一次 chat 请求才会真正启动 RKLLM worker 子进程。

检查命令：

```bash
ssh linaro@192.168.43.7 '
pgrep -af rkllm_enhanced_no_template_no_history || true
'
```

### 7.4 worker 模式测试后忘记恢复默认

执行：

```bash
ssh linaro@192.168.43.7 '
cd /home/linaro/edgeinfer-rk3588-board
./scripts/board/disable_edgeinfer_worker_mode.sh
'
```

### 7.5 busy test 中第二个请求返回 429

这是预期行为。Phase 9 当前 LLM queue 策略是：

```text
max_concurrent=1
queue_policy=reject_when_busy
```

当第一个请求正在运行时，第二个请求应返回：

```json
{
  "error": {
    "code": "llm_backend_busy",
    "retryable": true
  }
}
```

### 7.6 one-shot 和 worker 响应延迟不同

one-shot 每次请求都包含 RKLLM 初始化成本；worker 模式第一次请求包含 worker 启动成本，后续请求复用 persistent worker。延迟应以 metrics 中的 `latency_ms`、`startup_ms` 和端到端 `llm.last_latency_ms` 结合判断。

---

## 8. 当前建议默认策略

当前推荐策略：

```text
默认运行 one-shot 模式
worker 模式作为可选优化路径
较大改动必须跑 validate_serving_modes.sh
worker 测试结束必须恢复默认 one-shot
```

原因：

```text
one-shot 模式资源生命周期最清晰，适合作为安全默认
worker 模式能降低重复初始化成本，但需要更严格地管理子进程生命周期
当前已实现 shutdown hook，能在 systemctl restart/stop 时主动清理 worker
```

---

## 9. 最小命令速查

部署：

```bash
./scripts/host/deploy_serving_to_board.sh
```

部署并跑默认 one-shot smoke test：

```bash
EDGEINFER_DEPLOY_SMOKE=1 \
EDGEINFER_EXPECT_BACKEND=rkllm-runner \
./scripts/host/deploy_serving_to_board.sh
```

完整双模式验收：

```bash
./scripts/host/validate_serving_modes.sh
```

启用 worker：

```bash
ssh linaro@192.168.43.7 '
cd /home/linaro/edgeinfer-rk3588-board
./scripts/board/enable_edgeinfer_worker_mode.sh
'
```

关闭 worker，恢复默认：

```bash
ssh linaro@192.168.43.7 '
cd /home/linaro/edgeinfer-rk3588-board
./scripts/board/disable_edgeinfer_worker_mode.sh
'
```

查看 metrics：

```bash
curl http://192.168.43.7:8000/v1/metrics | python3 -m json.tool
```

查看服务日志：

```bash
ssh linaro@192.168.43.7 '
journalctl -u edgeinfer-serving.service -n 120 --no-pager
'
```
