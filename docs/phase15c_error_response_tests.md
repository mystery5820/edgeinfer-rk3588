# Phase 15C：Error Response Test Coverage

本文档记录 Phase 15C 对 OpenAI-like Chat Client 测试脚本的错误响应覆盖增强。

Phase 15B 已经整理了错误响应参考文档。Phase 15C 在此基础上补充 host-side assertion，使更多错误码进入自动化验证路径。

---

## 1. 修改目标

本阶段修改：

```text
scripts/host/test_openai_chat_client.py
docs/phase15c_error_response_tests.md
docs/phase15b_error_response_reference.md
README.md
docs/README.md
```

目标：

```text
1. 补充 invalid_stop 测试；
2. 补充 model_not_found 测试；
3. 补充 model_not_llm 测试；
4. 保留已有 n_not_supported / top_p_not_supported / response_format_not_supported / stream_backend_not_supported 测试；
5. 不改 server runtime；
6. 不改 RKLLM 后端；
7. 不增加耗时较长的 timeout/runtime error 测试。
```

---

## 2. 新增测试项

### 2.1 invalid_stop

测试非法 stop：

```json
{
  "stop": ""
}
```

预期：

```text
HTTP 400
detail.error.code = invalid_stop
```

原因：

```text
stop 必须是非空字符串，或非空字符串列表。
```

---

### 2.2 model_not_found

测试不存在的模型 ID：

```json
{
  "model": "__edgeinfer_missing_model__"
}
```

预期：

```text
HTTP 404
detail.error.code = model_not_found
```

原因：

```text
模型 ID 不存在于 model registry。
```

---

### 2.3 model_not_llm

测试将非 LLM 模型传给 `/v1/chat/completions`。

测试脚本会先调用：

```text
GET /v1/models
```

然后从返回列表中自动寻找非 LLM / 非 text-generation 模型 ID。

如果当前服务没有暴露非 LLM 模型，该测试会 skip，而不是失败。

预期：

```text
HTTP 400
detail.error.code = model_not_llm
```

原因：

```text
/v1/chat/completions 只接受 LLM 模型。
```

---

## 3. 已有错误测试覆盖

Phase 15C 后，`scripts/host/test_openai_chat_client.py` 覆盖：

```text
stream_backend_not_supported
n_not_supported
top_p_not_supported
response_format_not_supported
invalid_stop
model_not_found
model_not_llm
```

其中：

```text
1. stream_backend_not_supported 在 one-shot 模式下验证；
2. worker 模式下 stream=true 会验证 SSE 成功路径；
3. model_not_llm 如果没有可用非 LLM 模型会自动 skip；
4. llm_backend_busy 仍由 smoke_test_serving.sh / Phase 9 busy validation 覆盖；
5. llm_timeout / rkllm_runtime_error 暂不进入常规 client test，避免拖慢和扰动正常验证。
```

---

## 4. 推荐验证命令

执行 Python client test：

```bash
python3 scripts/host/test_openai_chat_client.py
```

完整 serving 验收仍使用：

```bash
EDGEINFER_VALIDATE_DEPLOY=1 ./scripts/host/validate_serving_modes.sh
```

如果只想静态检查：

```bash
python3 -m py_compile scripts/host/test_openai_chat_client.py
python3 -m compileall -q server scripts/host
git diff --check
```

---

## 5. 阶段结论

Phase 15C 让错误响应文档与 host-side 测试覆盖更加一致：

```text
1. 参数错误类错误码有更完整测试覆盖；
2. 模型错误类错误码有测试覆盖；
3. 不支持能力类错误码继续保留测试覆盖；
4. 异常型 runtime/timeout 错误暂不纳入常规 smoke test；
5. API polish 主线更加接近工程可维护状态。
```
