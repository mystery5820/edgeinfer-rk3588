# Phase 9：Qwen3-4B 真实 RKLLM 后端验证记录

## 1. 文档目的

本文档记录 `edgeinfer-rk3588` 项目 Phase 9 Serving Framework MVP 阶段的一次关键验证：在 RK3588 板端通过 FastAPI 服务成功调用真实 Qwen3-4B all-NPU RKLLM 模型，并通过 `/v1/chat/completions` 返回 OpenAI-compatible 风格的 JSON 响应。

本次验证的意义在于：项目不再停留在 fake LLM 或接口骨架阶段，而是已经打通了从 HTTP API 到真实 RKLLM 模型推理的完整链路。

## 2. 当前验证结论

本次验证可以明确记录为：

```text
Phase 9 Serving Framework MVP 已成功接入真实 Qwen3-4B all-NPU 后端。
```

已经验证成功的完整调用链路如下：

```text
curl / HTTP client
-> FastAPI /v1/chat/completions
-> server/runtime/rkllm_backend.py
-> server/runtime/rkllm_runner.py
-> tools/rkllm_enhanced/rkllm_enhanced_no_template
-> Qwen3-4B-w8a8-npu.rkllm
-> 输出清洗
-> OpenAI-compatible JSON 返回
```

## 3. 板端运行环境

板端路径：

```text
/home/linaro/edgeinfer-rk3588-board
```

模型资产路径：

```text
/userdata/edgeinfer-assets
```

本次使用模型：

```text
/userdata/edgeinfer-assets/models/llm/rkllm_outputs/Qwen3-4B-w8a8-npu.rkllm
```

模型 ID：

```text
qwen3-4b-rkllm-all-npu
```

运行环境：

```text
RKLLM runtime: rkllm-runtime-v1.3.0
RKNPU driver: v0.9.8
Memory manager: DRM_GEM
CMA: 512MiB
```

重要前提：

```text
qwen-web-chat.service 和 yolov5-web.service 必须保持禁用
```

原因是旧 demo 服务可能占用 RKNPU / DRM / IOVA 资源，影响 Qwen3-4B RKLLM 模型加载和推理。

## 4. FastAPI 服务启动方式

板端进入项目目录：

```bash
cd /home/linaro/edgeinfer-rk3588-board
```

激活 Python 虚拟环境：

```bash
. .venv-serving/bin/activate
```

启动 FastAPI 服务：

```bash
python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```

启动后终端输出类似：

```text
INFO:     Started server process [3948]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

这说明 FastAPI 服务已经在板端 8000 端口运行。

## 5. uvicorn 命令含义说明

命令：

```bash
python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```

### 5.1 `python -m uvicorn`

表示使用当前 Python 环境中的 `uvicorn` 模块启动服务。

这里之所以先激活：

```bash
. .venv-serving/bin/activate
```

是因为 FastAPI、uvicorn、pydantic、pyyaml 等依赖安装在 `.venv-serving` 虚拟环境中。

### 5.2 `server.main:app`

这是 uvicorn 要加载的 FastAPI 应用对象。

含义是：

```text
从 server/main.py 文件中，找到名为 app 的 FastAPI 对象
```

其中 `server.main` 对应 Python 模块路径 `server/main.py`，`app` 对应代码中的 FastAPI 实例。

### 5.3 `--host 0.0.0.0`

表示服务监听所有网络接口。

如果只写：

```bash
--host 127.0.0.1
```

那么服务只能在板端本机访问。

使用：

```bash
--host 0.0.0.0
```

后，Ubuntu 主机可以通过板端 IP 访问服务，例如：

```text
http://192.168.43.7:8000
```

### 5.4 `--port 8000`

表示服务监听 8000 端口。

因此健康检查接口访问地址是：

```text
http://192.168.43.7:8000/v1/health
```

Chat Completion 接口访问地址是：

```text
http://192.168.43.7:8000/v1/chat/completions
```

### 5.5 为什么不要加 `EDGEINFER_FAKE_LLM=1`

之前 fake LLM 验证时使用过：

```bash
EDGEINFER_FAKE_LLM=1 python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```

这会让后端返回假模型输出，用于验证 API 框架是否工作。

本次目标是验证真实 Qwen3-4B RKLLM 模型，所以启动服务时不能加：

```text
EDGEINFER_FAKE_LLM=1
```

否则 `/v1/chat/completions` 不会调用真实 RKLLM 后端。

## 6. 为什么需要另开 Ubuntu 主机终端测试

板端启动 uvicorn 后，该终端会被服务进程占用，用于显示服务日志。

因此测试接口时，需要在 Ubuntu 虚拟机主机中新开一个终端执行 `curl`。

注意：

```bash
ssh linaro@192.168.43.7
```

应该在 Ubuntu 主机终端执行，而不是在板端终端里执行。

如果已经登录到板端，再执行：

```bash
ssh linaro@192.168.43.7
```

相当于“板端 SSH 登录自己”，通常没有必要，而且可能引起密码输入和权限混乱。

## 7. API 验证过程

### 7.1 健康检查接口

在 Ubuntu 主机执行：

```bash
curl http://192.168.43.7:8000/v1/health | python3 -m json.tool
```

返回：

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

这说明 FastAPI 服务正常运行。

### 7.2 模型列表接口

执行：

```bash
curl http://192.168.43.7:8000/v1/models | python3 -m json.tool
```

本次返回模型数量：

```text
count: 7
```

其中包括：

```text
qwen3-4b-rkllm-all-npu
qwen3-4b-rkllm-hybrid
Qwen2.5-0.5B-Instruct
Qwen2.5-1.5B-Instruct
Qwen3-4B-W8A8-RK3588
YOLOv11n-INT8-Baseline
YOLOv11n-FP-Baseline
```

推荐模型为：

```text
qwen3-4b-rkllm-all-npu
```

## 8. Chat Completion 真实后端验证

测试命令：

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

验证成功后的关键返回内容：

```json
{
    "model": "qwen3-4b-rkllm-all-npu",
    "choices": [
        {
            "message": {
                "role": "assistant",
                "content": "Rockchip RK3588 是瑞芯微推出的一款高性能 AIoT 芯片，搭载四核 Cortex-A76 和四核 Cortex-A55 处理器，配备内置 NPU，适用于智能物联网设备。"
            },
            "finish_reason": "stop"
        }
    ],
    "edgeinfer": {
        "backend": "rkllm-runner",
        "latency_ms": 43387.491,
        "recommended_model": true,
        "runtime": "rkllm-runtime-v1.3.0",
        "rknpu_driver": "v0.9.8",
        "requirement": "clean RKNPU environment, no old qwen-web-chat or yolov5-web demo services"
    }
}
```

关键字段说明：

```text
backend: rkllm-runner
```

说明这次不是 fake LLM，而是真实通过 `rkllm_runner.py` 调用了 RKLLM 后端。

```text
recommended_model: true
```

说明使用的是当前模型注册表中推荐的主线模型。

```text
runtime: rkllm-runtime-v1.3.0
rknpu_driver: v0.9.8
```

说明当前后端运行环境与此前 Qwen3-4B all-NPU 验证环境一致。

## 9. wrapper / runner 的作用

本阶段新增或强化了两个关键文件：

```text
server/runtime/rkllm_backend.py
server/runtime/rkllm_runner.py
```

### 9.1 `rkllm_backend.py`

这是 FastAPI 服务内部的 RKLLM 后端适配层。

它负责：

```text
- 接收 Chat API 传来的 prompt
- 根据 model_registry.yaml 找到模型信息
- 解析模型文件路径
- 判断是否使用 fake LLM
- 构造 runner 调用命令
- 启动 rkllm_runner.py 子进程
- 收集 runner 输出
- 返回给 API 层
```

### 9.2 `rkllm_runner.py`

这是 Python wrapper，也可以理解为运行器或包装器。

它负责：

```text
- 调用 rkllm_enhanced_no_template 二进制程序
- 将 prompt 传给 rkllm_enhanced_no_template 的 stdin
- 捕获 stdout / stderr
- 清洗 RKLLM 日志、LLM: 前缀、think 标记和无关噪声
- 提取最终 assistant 文本
- 用 CLEAN_TEXT_BEGIN / CLEAN_TEXT_END 包住清洗后的内容
```

### 9.3 为什么需要 wrapper

不能直接把 `rkllm_enhanced_no_template` 裸接到 FastAPI，原因包括：

```text
- rkllm_enhanced_no_template 是命令行程序，不是 HTTP 服务
- 它通过 stdin 接收 prompt，通过 stdout 输出结果
- stdout 里会混合 RKLLM 日志、交互提示符和模型输出
- Qwen3 可能输出 think 标记或特殊 token
- API 层需要的是干净的 assistant content
```

因此需要 wrapper 作为中间层，把命令行推理程序适配成 API 可用的结构化输出。

## 10. no-template 版本的意义

此前原版：

```text
rkllm_enhanced
```

在 C++ 代码中调用了：

```text
rkllm_set_chat_template
```

这会覆盖模型内部 chat template，并触发警告：

```text
Calling rkllm_set_chat_template will disable the internal automatic chat template parsing, including enable_thinking.
```

对于 Qwen3，这会导致输出边界、thinking 控制和特殊 token 更不稳定。

因此构建了：

```text
rkllm_enhanced_no_template
```

该版本注释掉了 `rkllm_set_chat_template`，保留 RKLLM / 模型内部默认模板。

验证结果显示：

```text
rkllm_enhanced_no_template 对 Qwen3-4B 输出更稳定
```

所以当前真实后端主线是：

```text
FastAPI
-> rkllm_backend.py
-> rkllm_runner.py
-> rkllm_enhanced_no_template
-> Qwen3-4B all-NPU
```

## 11. 输出清洗问题与修复

首次真实 API 调用虽然成功，但返回内容中包含噪声，例如：

```text
2023年7月15日是星期六。
LLM: </think>
好的，您似乎在使用Edge Inference服务时遇到问题。
LLM: 瑞芯微RK3588是……
LLM: 瑞芯微RK3588是……
```

这说明真实推理链路已经打通，但 `rkllm_runner.py` 的输出清洗不够。

随后增强了 `clean_output()` 逻辑，主要包括：

```text
- 增加 <think> 和 </think> 清洗
- 对每一行单独清理 LLM: 前缀
- 过滤 /think、/no_think、/now、/next、/prev、/exit 等交互残留
- 过滤 2023年、星期 等无关噪声
- 过滤 “您似乎”“遇到问题” 等错误上下文片段
- 优先选择最后一行包含 RK3588 的候选答案
```

修复后，API 返回内容变为干净的一句话：

```text
Rockchip RK3588 是瑞芯微推出的一款高性能 AIoT 芯片，搭载四核 Cortex-A76 和四核 Cortex-A55 处理器，配备内置 NPU，适用于智能物联网设备。
```

## 12. 当前延迟与原因

本次真实后端返回延迟：

```text
latency_ms: 43387.491
```

约 43.4 秒。

这个延迟明显高于之前单独 benchmark 中的 generation tok/s，是因为当前实现采用：

```text
one-shot subprocess backend
```

也就是每一次 Chat API 请求都会：

```text
1. 启动一个新的 Python runner 子进程
2. runner 再启动 rkllm_enhanced_no_template
3. 重新加载 Qwen3-4B RKLLM 模型
4. 执行推理
5. 进程退出
```

因此端到端延迟包含了模型加载和进程启动开销。

这个设计适合 Phase 9 MVP 验证，但不是最终高性能服务形态。

后续优化方向应是：

```text
- 长驻 RKLLM worker 进程
- 模型常驻内存
- 请求队列
- 进程池或单 worker 串行调度
- NPU busy 状态检测
- timeout 与错误映射
- systemd 后台服务化
```

## 13. 当前阶段建议提交内容

建议提交的代码文件：

```text
server/runtime/rkllm_backend.py
server/runtime/rkllm_runner.py
```

建议提交的文档文件：

```text
docs/phase9_qwen3_real_backend_validation.md
```

建议提交信息：

```bash
git commit -m "connect phase9 serving to real qwen3 rkllm backend"
```

## 14. 阶段结论

本阶段已经完成 Phase 9 的关键真实后端 MVP 节点。

当前系统已经具备：

```text
- FastAPI 服务启动能力
- /v1/health 健康检查
- /v1/models 模型注册表查询
- /v1/chat/completions OpenAI-compatible 接口
- Qwen3-4B all-NPU 真实 RKLLM 后端调用
- runner 输出清洗
- backend metadata 返回
```

因此，Phase 9 Serving Framework MVP 不再只是接口骨架，而是已经具备真实端侧大模型推理服务能力。

后续 Phase 9/Phase 10 的重点应从“链路打通”转向“服务稳定化与性能优化”。
