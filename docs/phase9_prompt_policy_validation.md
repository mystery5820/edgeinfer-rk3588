# Phase 9：RK3588 Prompt Policy 优化与验证记录

## 1. 文档目的

本文档记录 `edgeinfer-rk3588` 项目 Phase 9 Serving Framework 中针对 Qwen3-4B RKLLM 后端增加 RK3588 prompt policy 的过程、问题定位、修复方案和验证结果。

本阶段的目标不是提升模型通用能力，而是解决服务验证中暴露出的一个具体问题：

```text
当用户要求模型介绍 RK3588 时，Qwen3-4B 偶尔会生成硬件事实幻觉，
例如将 RK3588 错误说成联发科推出，或编造 4nm、5G、Wi-Fi 6E、Mali-G78 等未给出的信息。
```

因此，本阶段在 Serving 层增加轻量级 prompt policy，用来为 RK3588 相关问题注入稳定事实，并避免多行 prompt 导致 `rkllm_enhanced` 出现多轮输入误判。

---

## 2. 阶段结论

本阶段已经完成并验证：

```text
Phase 9 Serving Framework 已加入 RK3588 事实约束 prompt policy。
```

最终验证结果：

```text
1. 单次 RK3588 介绍请求返回 HTTP 200
2. 输出不再出现“联发科、4nm、5G、Wi-Fi 6E、Mali-G78、Mali-G710”等错误事实
3. max_new_tokens=96 时输出完整，不再明显截断
4. latency_ms 约 30.5 秒，低于 90 秒超时线
5. /v1/metrics 显示 failed_requests=0，timeout_requests=0，last_error=null
6. 完整 smoke test 通过
7. busy 拒绝机制仍然正常
```

提交记录：

```text
8a3f163 add rk3588 prompt policy for serving
```

---

## 3. 涉及文件

本阶段修改或新增了以下文件：

```text
server/runtime/prompt_policy.py
server/runtime/rkllm_backend.py
server/runtime/rkllm_runner.py
```

其中：

```text
prompt_policy.py      新增 RK3588 prompt policy
rkllm_backend.py      调用 build_serving_prompt() 构造最终 prompt
rkllm_runner.py       在写入 stdin 前强制将 prompt 压成单行
```

---

## 4. 背景问题

在前面 smoke test 的 busy 长请求中，模型曾生成如下错误事实：

```text
RK3588 是联发科推出的……
支持 5G……
Mali-G78……
```

这说明：

```text
1. Serving 服务链路是通的
2. RKLLM 后端能正常执行
3. busy 拒绝机制也能正常工作
4. 但模型在开放式硬件介绍问题上容易产生事实幻觉
```

因此，需要在 Serving 层对 RK3588 相关问题增加基础事实约束。

---

## 5. 第一次 prompt policy 尝试

第一次实现中，`prompt_policy.py` 使用了多行事实清单，例如：

```text
【已知事实】
1. RK3588 是瑞芯微 Rockchip 推出的高性能 AIoT SoC。
2. RK3588 采用四核 Cortex-A76 加四核 Cortex-A55 的 CPU 架构。
3. RK3588 内置 NPU，可用于端侧 AI 推理。
...
```

该方案在本地 Python 层面语法正确，也能注入事实。

但板端真实测试时出现问题。

---

## 6. 第一次方案的问题

板端请求：

```text
POST /v1/chat/completions
model = qwen3-4b-rkllm-all-npu
max_new_tokens = 96
```

返回：

```text
rkllm_runtime_error
returncode=124
ERROR: rkllm command timeout
```

日志中反复出现：

```text
You:
LLM:
You:
LLM:
```

说明 `rkllm_enhanced_no_template` 将多行 prompt 误认为多轮输入。

这是因为当前 one-shot RKLLM 命令行后端通过 stdin 读取输入，而底层 `rkllm_enhanced` 是按行读取 prompt 的：

```text
一行 prompt -> 一次推理输入
```

当 Serving 层传入多行 prompt 时，后端就可能将事实清单中的每一行都当成一次新的输入，导致模型连续响应多段内容，最终超时。

---

## 7. 根因总结

第一次 prompt policy 的根因不是 FastAPI 问题，也不是 systemd 问题，而是：

```text
Serving 层生成了多行 prompt，
但当前 RKLLM 命令行后端按 stdin 行读取输入。
```

因此，当前 one-shot subprocess 后端必须保证：

```text
最终写入 rkllm_enhanced stdin 的 prompt 必须是单行。
```

---

## 8. 最终修复方案

最终方案做了两层保护。

### 8.1 prompt_policy 层压缩单行

新增函数：

```python
def normalize_prompt_line(text: str) -> str:
    return " ".join(text.replace("\r", " ").replace("\n", " ").split())
```

作用：

```text
1. 将 \r 替换为空格
2. 将 \n 替换为空格
3. 合并多余空白
4. 保证返回值为单行 prompt
```

### 8.2 runner 层再次压缩单行

在 `rkllm_runner.py` 中，在写入 stdin 前增加：

```python
prompt_line = " ".join(args.prompt.replace("\r", " ").replace("\n", " ").split())
```

并将：

```python
input=args.prompt + "\n"
```

改为：

```python
input=prompt_line + "\n"
```

这样即使上游意外传入多行 prompt，runner 也会在最后一道关口压成单行，避免再次触发多行 stdin 问题。

---

## 9. 最终 prompt policy 内容

最终 prompt policy 拆成三部分：

```text
1. 基础回答指令
2. RK3588 已知事实
3. RK3588 防幻觉约束
```

### 9.1 RK3588 已知事实

```python
RK3588_FACTS_COMPACT = (
    "已知事实：RK3588 是瑞芯微 Rockchip 推出的高性能 AIoT SoC；"
    "采用四核 Cortex-A76 加四核 Cortex-A55 的 CPU 架构；"
    "内置 NPU，可用于端侧 AI 推理。"
)
```

### 9.2 RK3588 防幻觉约束

```python
RK3588_GUARDRAILS = (
    "不要把 RK3588 说成联发科、英伟达、高通或其他厂商推出的芯片；"
    "不要编造 4nm、5G、Wi-Fi 6E、Mali-G78、Mali-G710 等未给出的信息；"
    "不要复述规则或事实清单。"
)
```

### 9.3 触发关键词

```python
RK3588_KEYWORDS = (
    "RK3588",
    "rk3588",
    "Rockchip",
    "rockchip",
    "瑞芯微",
    "端侧",
    "AIoT",
    "NPU",
)
```

只要用户 prompt 中包含这些关键词之一，就会注入 RK3588 事实约束。

---

## 10. 为什么要精简事实内容

在第一次单行修复后，模型能够正常返回 HTTP 200，但 `max_new_tokens=64` 时输出截断在：

```text
本项目在
```

原因是 prompt 中包含了：

```text
本项目当前在 RK3588 上验证的是 Qwen3-4B all-NPU RKLLM 后端
```

这条事实对普通“介绍 RK3588”问题不是必要内容，而且容易被模型复述出来，占用输出 token。

因此最终精简掉项目后端事实，只保留最核心硬件事实：

```text
瑞芯微 Rockchip
高性能 AIoT SoC
四核 Cortex-A76 + 四核 Cortex-A55
内置 NPU
端侧 AI 推理
```

这样既能约束事实，又不会让模型输出被无关项目背景拖长。

---

## 11. 本地验证

本地执行：

```bash
python3 -m compileall -q server
```

结果：

```text
compileall OK
```

本地 prompt policy 测试结果：

```text
has_newline: False
has_facts: True
has_guard: True
starts_no_think: True
```

说明最终 prompt：

```text
1. 不包含换行
2. 包含 RK3588 基础事实
3. 包含防幻觉约束
4. 以 /no_think 开头
```

---

## 12. 板端部署验证

同步文件到板端后，执行：

```bash
python -m compileall -q server
sudo systemctl restart edgeinfer-serving.service
./scripts/board/check_edgeinfer_serving.sh
```

结果：

```text
board compileall OK
edgeinfer-serving.service enabled
edgeinfer-serving.service active
port 8000 LISTEN
legacy services disabled / inactive
/v1/health OK
```

说明：

```text
新的 prompt policy 已经在板端部署并由 systemd 服务加载。
```

---

## 13. max_new_tokens=64 验证

请求：

```text
POST /v1/chat/completions
model = qwen3-4b-rkllm-all-npu
max_new_tokens = 64
```

返回：

```text
HTTP 200
```

输出内容未出现：

```text
联发科
4nm
5G
Wi-Fi 6E
Mali-G78
Mali-G710
```

但由于 `max_new_tokens=64` 偏小，输出末尾仍有轻微截断，因此继续使用 `max_new_tokens=96` 验证。

---

## 14. max_new_tokens=96 验证

请求：

```text
POST /v1/chat/completions
model = qwen3-4b-rkllm-all-npu
max_new_tokens = 96
```

返回：

```text
HTTP 200
```

返回内容：

```text
RK3588 是瑞芯微推出的高性能 AIoT SoC，搭载四核 Cortex-A76 和四核 Cortex-A55 处理器，支持端侧 AI 推理。它内置 NPU，可高效运行机器学习模型，降低对云端依赖。RK3588 在功耗和性能之间取得良好平衡，适合物联网设备进行本地智能处理。
```

本次延迟：

```text
latency_ms: 30495.365
```

metrics 关键字段：

```json
{
  "total_requests": 2,
  "accepted_requests": 2,
  "rejected_busy": 0,
  "completed_requests": 2,
  "failed_requests": 0,
  "timeout_requests": 0,
  "last_error": null,
  "last_latency_ms": 30495.9,
  "current_model": null
}
```

结论：

```text
max_new_tokens=96 能完整返回，且不再出现已知硬件事实幻觉。
```

---

## 15. 完整 smoke test 验证

执行：

```bash
./scripts/host/smoke_test_serving.sh
```

最终输出：

```text
=== Smoke test passed ===
```

完整 smoke test 覆盖：

```text
1. /v1/health
2. /v1/models
3. /v1/metrics
4. 单次真实 chat
5. busy 并发拒绝
6. busy 后 metrics
```

---

## 16. smoke test 中的单次 chat 结果

单次 chat 返回：

```text
HTTP 200
```

内容：

```text
RK3588是瑞芯微推出的高性能AIoT SoC，搭载四核Cortex-A76和四核Cortex-A55架构，并内置NPU用于端侧AI推理。
```

metadata：

```text
backend: rkllm-runner
latency_ms: 20968.391
runtime: rkllm-runtime-v1.3.0
rknpu_driver: v0.9.8
```

---

## 17. smoke test 中的 busy 测试结果

busy 测试流程：

```text
1. 第一个长请求后台启动
2. 第二个请求在第一个请求运行时发起
3. 第二个请求返回 HTTP 429
4. 第一个请求最终返回 HTTP 200
```

第二个请求：

```text
HTTP 429
code = llm_backend_busy
retryable = true
```

第一个请求：

```text
HTTP 200
```

返回内容：

```text
RK3588 是瑞芯微推出的高性能 AIoT SoC，采用四核 Cortex-A76 加四核 Cortex-A55 的 CPU 架构。它内置 NPU，支持高效的端侧 AI 推理任务。RK3588 适合端侧 AI 推理，因其低功耗、高算力和集成化设计。
```

最终 metrics：

```json
{
  "total_requests": 5,
  "accepted_requests": 4,
  "rejected_busy": 1,
  "completed_requests": 4,
  "failed_requests": 0,
  "timeout_requests": 0,
  "last_error": null,
  "busy": false,
  "current_model": null
}
```

结论：

```text
新增 prompt policy 不影响 busy 拒绝机制。
```

---

## 18. 提交记录

提交命令：

```bash
git add \
  server/runtime/prompt_policy.py \
  server/runtime/rkllm_backend.py \
  server/runtime/rkllm_runner.py

git commit -m "add rk3588 prompt policy for serving"

git push
```

提交结果：

```text
8a3f163 add rk3588 prompt policy for serving
```

提交内容：

```text
3 files changed, 71 insertions(+), 8 deletions(-)
create mode 100644 server/runtime/prompt_policy.py
```

---

## 19. 当前 Phase 9 状态

到本阶段结束后，Phase 9 Serving Framework 已具备：

```text
1. FastAPI Serving API
2. /v1/health
3. /v1/models
4. /v1/metrics
5. /v1/chat/completions
6. 真实 Qwen3-4B all-NPU RKLLM 后端
7. no-template rkllm_enhanced
8. rkllm_runner 输出清洗
9. systemd 后台服务
10. busy 拒绝机制
11. 主机侧 smoke test 脚本
12. RK3588 prompt policy
```

---

## 20. 后续建议

当前 Serving Framework MVP 已经较完整，下一步可以进入更关键的性能与架构优化：

```text
1. 设计 long-running RKLLM worker，减少 one-shot 每次加载模型带来的延迟
2. 将当前 rkllm_runner 从一次性 subprocess 调用升级为常驻 worker
3. 增加更明确的 worker 生命周期管理
4. 增加 worker health / warmup / reload 接口
5. 继续保留 busy 拒绝，防止并发抢占 RKNPU
```

其中最建议的下一步是：

```text
开始设计 long-running RKLLM worker。
```

原因是当前请求延迟主要来自 one-shot subprocess 模式，每次 chat 都需要重新启动 runner 并加载 RKLLM 模型，真实请求延迟通常在 20 到 60 秒之间。若后续实现常驻 worker，模型加载可以从“每次请求一次”变成“服务启动或 worker 启动时一次”，这将是 Phase 9 后续最重要的性能优化方向。
