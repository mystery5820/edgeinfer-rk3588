# Phase 9：Serving Framework systemd 服务化验证记录

## 1. 文档目的

本文档记录 `edgeinfer-rk3588` 项目 Phase 9 Serving Framework 在 RK3588 板端完成 systemd 后台服务化的过程。

在前一阶段中，项目已经完成：

```text
FastAPI /v1/chat/completions
-> rkllm_backend.py
-> rkllm_runner.py
-> rkllm_enhanced_no_template
-> Qwen3-4B all-NPU
-> OpenAI-compatible JSON 返回
```

本阶段的目标是把原本需要手动前台运行的 FastAPI 服务，改造成可由 systemd 管理的后台服务，使其具备：

```text
- 后台启动
- systemctl start / stop / restart / status 管理
- journalctl 日志查看
- 开机启用能力
- 板端本地健康检查
- 主机侧远程 API 访问
```

---

## 2. 阶段结论

本阶段已经完成 systemd 服务化验证，可以记录为：

```text
Phase 9 Serving Framework 已完成 systemd 后台服务化验证。
```

当前真实服务链路为：

```text
systemd edgeinfer-serving.service
-> uvicorn
-> FastAPI server.main:app
-> /v1/chat/completions
-> rkllm_backend.py
-> rkllm_runner.py
-> rkllm_enhanced_no_template
-> Qwen3-4B all-NPU RKLLM
```

验证结果表明：

```text
- edgeinfer-serving.service enabled
- edgeinfer-serving.service active
- 8000 端口正常监听
- /v1/health 正常返回
- /v1/models 正常返回 7 个模型
- /v1/chat/completions 可调用真实 Qwen3-4B all-NPU 后端
- backend = rkllm-runner
- 输出内容干净
```

---

## 3. 新增文件

本阶段新增 3 个文件：

```text
deploy/systemd/edgeinfer-serving.service
scripts/board/install_edgeinfer_serving_service.sh
scripts/board/check_edgeinfer_serving.sh
```

提交记录：

```text
e01513e add systemd service for phase9 serving
```

---

## 4. systemd 服务文件

服务文件路径：

```text
deploy/systemd/edgeinfer-serving.service
```

板端安装目标路径：

```text
/etc/systemd/system/edgeinfer-serving.service
```

服务内容：

```ini
[Unit]
Description=EdgeInfer RK3588 Serving API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=linaro
Group=linaro
WorkingDirectory=/home/linaro/edgeinfer-rk3588-board

Environment=PYTHONUNBUFFERED=1
Environment=EDGEINFER_ASSETS_ROOT=/userdata/edgeinfer-assets

ExecStart=/home/linaro/edgeinfer-rk3588-board/.venv-serving/bin/python -m uvicorn server.main:app --host 0.0.0.0 --port 8000

Restart=on-failure
RestartSec=3

StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

---

## 5. systemd 服务文件字段说明

### 5.1 `[Unit]`

```ini
Description=EdgeInfer RK3588 Serving API
```

表示服务描述，在 `systemctl status` 中显示。

```ini
After=network-online.target
Wants=network-online.target
```

表示该服务希望在网络就绪后启动。由于 FastAPI 服务需要被主机通过 IP 访问，因此网络应先可用。

### 5.2 `[Service]`

```ini
Type=simple
```

表示这是一个普通前台进程。systemd 会认为 `ExecStart` 启动的进程就是主服务进程。

```ini
User=linaro
Group=linaro
```

表示服务以 `linaro` 用户和用户组运行，不使用 root 直接运行应用逻辑。

```ini
WorkingDirectory=/home/linaro/edgeinfer-rk3588-board
```

表示服务启动时的工作目录。这一点很重要，因为 FastAPI 代码、配置文件、相对路径解析都依赖项目根目录。

```ini
Environment=PYTHONUNBUFFERED=1
```

表示 Python 输出不缓存，日志能更及时写入 journal。

```ini
Environment=EDGEINFER_ASSETS_ROOT=/userdata/edgeinfer-assets
```

表示模型和工具资产根目录，后端会根据它定位 RKLLM 模型文件。

```ini
ExecStart=/home/linaro/edgeinfer-rk3588-board/.venv-serving/bin/python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```

这是服务真正启动命令。它使用 `.venv-serving` 虚拟环境中的 Python，启动 uvicorn，并加载 FastAPI 应用。

```ini
Restart=on-failure
RestartSec=3
```

表示服务异常退出时自动重启，重启前等待 3 秒。

```ini
StandardOutput=journal
StandardError=journal
```

表示 stdout 和 stderr 写入 systemd journal，可通过 `journalctl` 查看。

### 5.3 `[Install]`

```ini
WantedBy=multi-user.target
```

表示服务可以被 `systemctl enable` 挂到常规多用户启动目标下，支持开机启动。

---

## 6. uvicorn 的作用说明

本项目中，FastAPI 只是 Python Web 框架，真正监听 HTTP 端口、接收请求、分发到 FastAPI 应用的是 uvicorn。

启动命令：

```bash
python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```

含义如下：

```text
python -m uvicorn
```

使用当前 Python 环境中的 uvicorn 模块启动 Web 服务。

```text
server.main:app
```

表示加载 `server/main.py` 文件中的 `app` 对象。这个 `app` 是 FastAPI 实例。

```text
--host 0.0.0.0
```

表示监听所有网卡。这样 Ubuntu 主机可以通过 RK3588 板端 IP 访问服务。

```text
--port 8000
```

表示监听 8000 端口。

因此，主机可以访问：

```text
http://192.168.43.7:8000/v1/health
http://192.168.43.7:8000/v1/models
http://192.168.43.7:8000/v1/chat/completions
```

---

## 7. 为什么 systemd 服务中不能加 `EDGEINFER_FAKE_LLM=1`

在早期验证 API 框架时，曾使用：

```bash
EDGEINFER_FAKE_LLM=1 python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```

这会使 `/v1/chat/completions` 返回假 LLM 输出，用于验证接口结构和 FastAPI 逻辑。

但本阶段目标是验证真实 Qwen3-4B RKLLM 后端，因此 systemd 服务中不能设置：

```text
EDGEINFER_FAKE_LLM=1
```

否则服务不会调用真实模型。

当前 systemd 服务只设置：

```ini
Environment=PYTHONUNBUFFERED=1
Environment=EDGEINFER_ASSETS_ROOT=/userdata/edgeinfer-assets
```

没有设置 fake LLM 环境变量。

---

## 8. 安装脚本

脚本路径：

```text
scripts/board/install_edgeinfer_serving_service.sh
```

作用：

```text
- 检查项目目录是否存在
- 检查 systemd service 文件是否存在
- 检查 .venv-serving 虚拟环境是否存在
- 检查 server/main.py 是否存在
- 禁用旧 demo 服务
- 安装 edgeinfer-serving.service 到 /etc/systemd/system/
- 执行 systemctl daemon-reload
- 执行 systemctl enable edgeinfer-serving.service
```

脚本中会禁用旧服务：

```bash
sudo systemctl disable --now qwen-web-chat.service 2>/dev/null || true
sudo systemctl disable --now yolov5-web.service 2>/dev/null || true
```

这一步非常重要，因为旧 demo 服务可能占用 RKNPU / DRM / IOVA 资源，影响 Qwen3-4B 模型加载和真实推理。

---

## 9. 检查脚本

脚本路径：

```text
scripts/board/check_edgeinfer_serving.sh
```

作用：

```text
- 查看 edgeinfer-serving.service 是否 enable
- 查看 edgeinfer-serving.service 是否 active
- 查看 systemctl status
- 查看 8000 端口监听状态
- 查看 uvicorn 进程
- 查看旧服务 qwen-web-chat.service / yolov5-web.service 状态
- 执行本地 /v1/health 检查
```

运行方式：

```bash
cd /home/linaro/edgeinfer-rk3588-board
./scripts/board/check_edgeinfer_serving.sh
```

---

## 10. 板端安装与启动验证

安装 systemd 服务后，执行：

```bash
sudo systemctl start edgeinfer-serving.service
```

随后执行检查脚本：

```bash
cd /home/linaro/edgeinfer-rk3588-board
./scripts/board/check_edgeinfer_serving.sh
```

本次验证输出关键内容如下：

```text
=== service enabled state ===
enabled

=== service active state ===
active
```

服务状态：

```text
● edgeinfer-serving.service - EdgeInfer RK3588 Serving API
     Loaded: loaded (/etc/systemd/system/edgeinfer-serving.service; enabled; vendor preset: enabled)
     Active: active (running)
   Main PID: 4595 (python)
```

进程：

```text
/home/linaro/edgeinfer-rk3588-board/.venv-serving/bin/python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```

端口：

```text
LISTEN 0 0 0.0.0.0:8000 0.0.0.0:* users:(("python",pid=4595,fd=6))
```

旧服务状态：

```text
qwen-web-chat.service disabled / inactive
yolov5-web.service disabled / inactive
```

本地健康检查：

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

---

## 11. Ubuntu 主机侧接口验证

### 11.1 `/v1/models`

命令：

```bash
curl http://192.168.43.7:8000/v1/models | python3 -m json.tool
```

返回模型数量：

```text
count: 7
```

模型列表包括：

```text
qwen3-4b-rkllm-all-npu
qwen3-4b-rkllm-hybrid
Qwen2.5-0.5B-Instruct
Qwen2.5-1.5B-Instruct
Qwen3-4B-W8A8-RK3588
YOLOv11n-INT8-Baseline
YOLOv11n-FP-Baseline
```

推荐模型：

```text
qwen3-4b-rkllm-all-npu
```

### 11.2 `/v1/chat/completions`

命令：

```bash
curl -X POST http://192.168.43.7:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-4b-rkllm-all-npu",
    "messages": [
      {"role": "system", "content": "你是 EdgeInfer-RK3588 端侧推理助手。"},
      {"role": "user", "content": "已知事实：RK3588 是瑞芯微 Rockchip 推出的高性能 AIoT SoC，采用四核 Cortex-A76 加四核 Cortex-A55 架构，内置 NPU。请用一句话介绍 RK3588。"}
    ],
    "max_new_tokens": 64
  }' | python3 -m json.tool
```

返回内容：

```text
RK3588 是瑞芯微推出的一款高性能 AIoT SoC，采用四核 Cortex-A76 加四核 Cortex-A55 架构，集成 NPU，专为人工智能物联网设备设计。
```

返回 metadata：

```text
backend: rkllm-runner
recommended_model: true
runtime: rkllm-runtime-v1.3.0
rknpu_driver: v0.9.8
```

本次延迟：

```text
latency_ms: 34954.64
```

这说明 systemd 后台服务模式下，真实 Qwen3-4B all-NPU 后端仍然可以正常工作。

---

## 12. 常用 systemd 管理命令

### 12.1 启动服务

```bash
ssh linaro@192.168.43.7 'sudo systemctl start edgeinfer-serving.service'
```

### 12.2 停止服务

```bash
ssh linaro@192.168.43.7 'sudo systemctl stop edgeinfer-serving.service'
```

### 12.3 重启服务

```bash
ssh linaro@192.168.43.7 'sudo systemctl restart edgeinfer-serving.service'
```

### 12.4 查看服务状态

```bash
ssh linaro@192.168.43.7 'systemctl status edgeinfer-serving.service --no-pager -l'
```

### 12.5 查看最近日志

```bash
ssh linaro@192.168.43.7 'journalctl -u edgeinfer-serving.service -n 80 --no-pager'
```

### 12.6 实时查看日志

```bash
ssh linaro@192.168.43.7 'journalctl -u edgeinfer-serving.service -f'
```

### 12.7 设置开机启动

```bash
ssh linaro@192.168.43.7 'sudo systemctl enable edgeinfer-serving.service'
```

### 12.8 取消开机启动

```bash
ssh linaro@192.168.43.7 'sudo systemctl disable edgeinfer-serving.service'
```

---

## 13. 当前限制

当前 systemd 服务已经解决了“如何后台运行和管理 FastAPI 服务”的问题，但 RKLLM 后端仍然是 one-shot 子进程模式。

也就是说，每次 Chat API 请求都会：

```text
1. FastAPI 收到请求
2. rkllm_backend.py 启动 rkllm_runner.py
3. rkllm_runner.py 启动 rkllm_enhanced_no_template
4. Qwen3-4B RKLLM 模型重新加载
5. 执行推理
6. 清洗输出并返回
7. 子进程退出
```

因此延迟仍然较高，约 35 到 45 秒。

这个问题不属于 systemd 服务化问题，而属于后端架构问题。后续应通过长驻 worker 或模型常驻进程优化。

---

## 14. 下一阶段建议

下一阶段建议进入 Phase 9 服务稳定性增强，优先级如下：

```text
1. 增强 /v1/metrics，加入 systemd/backend/runtime 状态
2. 增加 busy 状态处理，避免多个 Qwen3 请求并发抢占 NPU
3. 增加 timeout/error 结构化返回
4. 增加真实后端 smoke test 脚本
5. 设计 long-running RKLLM worker
6. 后续再做模型常驻与队列调度
```

其中最建议优先做的是：

```text
busy / timeout / error handling
```

因为 Qwen3-4B all-NPU 当前对 clean RKNPU 环境要求很高，服务端必须避免多个真实推理请求同时进入后端。

---

## 15. 阶段结论

本阶段完成后，`edgeinfer-rk3588` 已经具备一个可后台运行的真实端侧大模型推理服务：

```text
systemd 管理
FastAPI 对外服务
/v1/health
/v1/models
/v1/chat/completions
Qwen3-4B all-NPU RKLLM 后端
OpenAI-compatible JSON 返回
```

这标志着 Phase 9 从“真实链路打通”进一步推进到了“服务可运行、可管理、可验证”的状态。
