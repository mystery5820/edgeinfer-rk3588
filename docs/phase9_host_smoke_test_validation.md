# Phase 9：主机侧 Serving Smoke Test 脚本验证记录

## 1. 文档目的

本文档记录 `edgeinfer-rk3588` 项目 Phase 9 Serving Framework 增加主机侧 smoke test 脚本后的验证过程。

在前面阶段中，项目已经完成：

```text
- Qwen3-4B all-NPU RKLLM 真实后端接入
- FastAPI /v1/chat/completions 调用真实 RKLLM 后端
- systemd 后台服务化
- busy 拒绝机制
- /v1/metrics 暴露 LLM 后端状态
```

本阶段新增主机侧自动化验证脚本，用于在 Ubuntu 主机上一键检查 RK3588 板端 Serving 服务是否可用。

新增脚本：

```text
scripts/host/smoke_test_serving.sh
```

---

## 2. 阶段结论

本阶段已经完成并验证：

```text
Phase 9 Serving Framework 已具备主机侧一键 smoke test 能力。
```

脚本已成功验证以下内容：

```text
1. /v1/health 正常
2. /v1/models 正常
3. /v1/metrics 正常
4. 单次真实 Qwen3-4B chat completion 正常
5. 并发 busy 拒绝测试正常
6. 第二个并发请求返回 HTTP 429 llm_backend_busy
7. 第一个真实请求最终返回 HTTP 200
8. 最终 metrics 计数正确
```

提交记录：

```text
238bb5d add host serving smoke test script
```

---

## 3. 新增脚本

文件路径：

```text
scripts/host/smoke_test_serving.sh
```

文件权限：

```text
100755
```

即该脚本可直接执行：

```bash
./scripts/host/smoke_test_serving.sh
```

---

## 4. 脚本作用

该脚本用于从 Ubuntu 主机侧验证板端 Serving API。

默认访问地址：

```text
http://192.168.43.7:8000
```

默认模型：

```text
qwen3-4b-rkllm-all-npu
```

默认会执行：

```text
- health 检查
- models 检查
- metrics 检查
- 单次真实 chat 检查
- busy 并发拒绝检查
- 最终 metrics 检查
```

完整测试会调用真实 Qwen3-4B all-NPU 后端，因此耗时较长，通常需要 1 到 2 分钟。

---

## 5. 使用方式

### 5.1 完整 smoke test

在 Ubuntu 主机执行：

```bash
cd ~/edgeinfer-rk3588

./scripts/host/smoke_test_serving.sh
```

该模式会运行真实 Qwen3-4B 推理，并执行 busy 并发测试。

### 5.2 只测试基础接口

如果只想快速检查服务是否在线，不运行真实大模型，可以执行：

```bash
cd ~/edgeinfer-rk3588

EDGEINFER_SMOKE_CHAT=0 EDGEINFER_SMOKE_BUSY=0 \
./scripts/host/smoke_test_serving.sh
```

该模式只测试：

```text
- /v1/health
- /v1/models
- /v1/metrics
```

不会触发真实 Qwen3-4B 推理。

---

## 6. 环境变量

脚本支持以下环境变量。

### 6.1 `EDGEINFER_BOARD_URL`

用于指定板端 Serving API 地址。

默认值：

```text
http://192.168.43.7:8000
```

示例：

```bash
EDGEINFER_BOARD_URL=http://192.168.43.7:8000 \
./scripts/host/smoke_test_serving.sh
```

如果后续板端 IP 改变，只需要修改该变量即可。

### 6.2 `EDGEINFER_MODEL_ID`

用于指定测试模型。

默认值：

```text
qwen3-4b-rkllm-all-npu
```

示例：

```bash
EDGEINFER_MODEL_ID=qwen3-4b-rkllm-all-npu \
./scripts/host/smoke_test_serving.sh
```

### 6.3 `EDGEINFER_SMOKE_CHAT`

用于控制是否执行单次真实 Chat Completion 测试。

默认值：

```text
1
```

含义：

```text
1 - 执行真实 chat 测试
0 - 跳过真实 chat 测试
```

### 6.4 `EDGEINFER_SMOKE_BUSY`

用于控制是否执行 busy 并发拒绝测试。

默认值：

```text
1
```

含义：

```text
1 - 执行 busy 并发测试
0 - 跳过 busy 并发测试
```

---

## 7. 脚本执行流程

脚本执行时会依次运行以下步骤：

```text
1. 打印 BOARD_URL、MODEL_ID、RUN_CHAT、RUN_BUSY
2. GET /v1/health
3. GET /v1/models
4. GET /v1/metrics
5. POST /v1/chat/completions 进行单次真实 chat 测试
6. 再次 GET /v1/metrics
7. 发起 busy 并发测试
8. 最后 GET /v1/metrics
9. 打印 Smoke test passed
```

如果中间任何一个关键步骤失败，脚本会退出并返回错误。

---

## 8. health 测试

请求：

```text
GET /v1/health
```

本次返回：

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

验证结论：

```text
FastAPI 服务正常在线。
```

---

## 9. models 测试

请求：

```text
GET /v1/models
```

本次返回：

```text
HTTP 200
count: 7
```

包含模型：

```text
qwen3-4b-rkllm-all-npu
qwen3-4b-rkllm-hybrid
Qwen2.5-0.5B-Instruct
Qwen2.5-1.5B-Instruct
Qwen3-4B-W8A8-RK3588
YOLOv11n-INT8-Baseline
YOLOv11n-FP-Baseline
```

其中推荐模型：

```text
qwen3-4b-rkllm-all-npu
```

验证结论：

```text
模型注册表读取正常。
```

---

## 10. metrics 测试

请求：

```text
GET /v1/metrics
```

本次初始 metrics 返回关键字段：

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

验证结论：

```text
/v1/metrics 能正确暴露 LLM 后端状态。
```

---

## 11. 单次真实 Chat Completion 测试

请求：

```text
POST /v1/chat/completions
```

测试模型：

```text
qwen3-4b-rkllm-all-npu
```

测试 prompt：

```text
已知事实：RK3588 是瑞芯微 Rockchip 推出的高性能 AIoT SoC，采用四核 Cortex-A76 加四核 Cortex-A55 架构，内置 NPU。请用一句话介绍 RK3588。
```

本次返回：

```text
HTTP 200
```

返回内容：

```text
RK3588 是瑞芯微推出的一款高性能 AIoT 芯片，搭载四核 Cortex-A76 和四核 Cortex-A55 核心，集成 NPU，适用于人工智能物联网设备。
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
latency_ms: 48572.324
```

验证结论：

```text
systemd 后台服务模式下，真实 Qwen3-4B all-NPU 后端仍然可以正常完成单次 Chat Completion。
```

---

## 12. 单次 chat 后 metrics

单次 chat 完成后，再次请求：

```text
GET /v1/metrics
```

返回关键字段：

```json
{
    "llm": {
        "total_requests": 3,
        "accepted_requests": 2,
        "rejected_busy": 1,
        "completed_requests": 2,
        "failed_requests": 0,
        "timeout_requests": 0,
        "busy": false,
        "last_error": null,
        "last_latency_ms": 48572.842,
        "current_model": null
    }
}
```

验证结论：

```text
单次 chat 请求完成后，metrics 计数正确增加，后端恢复空闲。
```

---

## 13. busy 并发测试

busy 测试逻辑：

```text
1. 启动第一个较长请求，并放到后台
2. 等待 2 秒
3. 发起第二个请求
4. 第二个请求应立即返回 HTTP 429
5. 等待第一个请求完成
6. 第一个请求应返回 HTTP 200
```

### 13.1 第二个请求结果

第二个请求返回：

```text
HTTP 429
```

错误内容：

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
                "total_requests": 5,
                "accepted_requests": 3,
                "rejected_busy": 2,
                "completed_requests": 2,
                "failed_requests": 0,
                "timeout_requests": 0,
                "last_error": "LLM backend busy",
                "current_model": "qwen3-4b-rkllm-all-npu"
            }
        }
    }
}
```

验证结论：

```text
busy 拒绝机制生效，第二个并发请求没有进入 RKLLM 后端，而是立即返回 429。
```

### 13.2 第一个请求结果

第一个请求最终返回：

```text
HTTP 200
```

metadata：

```json
{
    "edgeinfer": {
        "backend": "rkllm-runner",
        "latency_ms": 59093.692,
        "recommended_model": true,
        "runtime": "rkllm-runtime-v1.3.0",
        "rknpu_driver": "v0.9.8",
        "llm": {
            "max_concurrent": 1,
            "busy": false,
            "queue_policy": "reject_when_busy",
            "total_requests": 5,
            "accepted_requests": 3,
            "rejected_busy": 2,
            "completed_requests": 3,
            "failed_requests": 0,
            "timeout_requests": 0,
            "last_error": null,
            "last_latency_ms": 59094.081,
            "current_model": null
        }
    }
}
```

验证结论：

```text
第一个真实请求没有被 busy 机制影响，仍然可以正常完成。
```

---

## 14. 最终 metrics

busy 测试完成后，最终 metrics 为：

```json
{
    "llm": {
        "max_concurrent": 1,
        "busy": false,
        "queue_policy": "reject_when_busy",
        "total_requests": 5,
        "accepted_requests": 3,
        "rejected_busy": 2,
        "completed_requests": 3,
        "failed_requests": 0,
        "timeout_requests": 0,
        "last_error": null,
        "last_latency_ms": 59094.081,
        "current_model": null
    }
}
```

验证结论：

```text
metrics 与实际请求行为一致。
```

其中：

```text
total_requests = 5
accepted_requests = 3
rejected_busy = 2
completed_requests = 3
failed_requests = 0
timeout_requests = 0
busy = false
```

说明：

```text
- 服务累计收到 5 次 LLM 请求
- 3 次进入后端执行
- 2 次被 busy 机制拒绝
- 3 次执行成功
- 没有失败或超时
- 测试结束后后端处于空闲状态
```

---

## 15. Smoke test 通过标志

脚本最终输出：

```text
=== Smoke test passed ===
```

这表示所有关键检查均通过。

---

## 16. 关于模型回答幻觉的说明

在 busy 测试的长请求中，模型回答出现了事实幻觉，例如将 RK3588 错误描述为“联发科推出”。

这不影响本阶段结论。

原因是本阶段 smoke test 的目标是验证：

```text
- HTTP 接口是否正常
- systemd 服务是否可用
- 真实 RKLLM 后端是否能被调用
- busy 拒绝是否生效
- metrics 计数是否正确
```

而不是验证模型知识正确性。

后续若要提高事实可靠性，需要引入：

```text
- 更强的 system prompt
- 固定事实约束模板
- 本地知识库
- RAG 检索增强
- 输出事实校验
```

---

## 17. 当前脚本的意义

`scripts/host/smoke_test_serving.sh` 对后续开发非常重要。

后续每次修改 serving 层代码后，都可以先同步到板端并重启 systemd 服务，然后在 Ubuntu 主机运行：

```bash
./scripts/host/smoke_test_serving.sh
```

快速确认：

```text
- 服务仍然在线
- 模型列表仍然正常
- metrics 仍然正常
- 真实 chat 仍然可用
- busy 拒绝仍然有效
```

这比每次手动输入多段 curl 命令更稳定，也更适合作为后续回归测试基础。

---

## 18. 后续建议

完成 smoke test 脚本后，下一步建议继续增强：

```text
1. 增加 docs 中对 smoke test 的记录
2. 增加 timeout 注入测试方式
3. 优化模型事实可靠性 prompt
4. 设计 long-running RKLLM worker
5. 将 one-shot 子进程后端升级为模型常驻后端
```

短期最建议的下一步是：

```text
优化 Chat API 默认 prompt 构造，减少 RK3588 基础事实问题上的幻觉。
```

因为当前服务链路已经比较完整，但模型在开放式硬件介绍问题上仍容易编造事实。

---

## 19. 阶段结论

本阶段完成后，Phase 9 Serving Framework 已具备较完整的手动/脚本化验证能力。

当前已经具备：

```text
- systemd 后台服务
- OpenAI-compatible chat API
- 真实 Qwen3-4B all-NPU RKLLM 后端
- busy 拒绝机制
- /v1/metrics 服务状态暴露
- 主机侧一键 smoke test
```

这标志着 Phase 9 从“服务可运行、可保护”进一步推进到“服务可回归验证”的状态。
