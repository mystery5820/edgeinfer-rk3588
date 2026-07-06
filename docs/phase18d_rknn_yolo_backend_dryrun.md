# Phase 18D：RKNN YOLO Backend Dry Integration

本文档记录 Phase 18D：在不引入完整 YOLO preprocess / inference / postprocess 的前提下，先把 RKNN YOLO 后端加载生命周期接入 `/v1/vision/detect`。

---

## 1. 背景

Phase 18C 已经完成：

```text
image_path 校验
JPEG/PNG/BMP metadata 解析
letterbox metadata skeleton
load_image / preprocess latency
image_not_found / invalid_image_file 错误边界
```

Phase 18D 的目标是继续向真实 YOLO RKNN backend 靠近。

当前板端情况：

```text
.venv-serving 无 rknnlite / rknn
system python3 有 rknnlite.api
YOLOv11 RKNN 模型文件已存在
```

因此本阶段不在 FastAPI 进程内直接 import `rknnlite`，而是通过 system Python subprocess 执行 RKNNLite probe。

---

## 2. 本阶段目标

Phase 18D 完成：

```text
1. 新增 rknn-yolo-dryrun backend；
2. 通过环境变量切换 fake-vision / rknn-yolo-dryrun；
3. 用 subprocess 调用 /usr/bin/python3；
4. lazy 检查 rknnlite.api.RKNNLite；
5. load_rknn；
6. init_runtime；
7. release；
8. 将 RKNN probe 结果返回到 edgeinfer.model_runtime；
9. 保持 objects 为空；
10. 不执行真实 inference 和 postprocess。
```

---

## 3. 新增文件

```text
server/runtime/rknn_yolo_backend.py
scripts/board/probe_rknn_yolo_runtime.py
scripts/board/enable_edgeinfer_vision_rknn_dryrun.sh
scripts/board/disable_edgeinfer_vision_rknn_dryrun.sh
docs/phase18d_rknn_yolo_backend_dryrun.md
```

更新：

```text
server/api/vision_api.py
scripts/host/test_vision_detect_client.py
README.md
docs/README.md
```

---

## 4. Backend 模式

默认模式仍然是：

```text
fake-vision
```

启用 RKNN dryrun：

```text
EDGEINFER_VISION_BACKEND_MODE=rknn-yolo-dryrun
EDGEINFER_RKNN_YOLO_PYTHON=/usr/bin/python3
```

原因：

```text
FastAPI serving venv 不一定包含 rknnlite；
system python3 当前可以 import rknnlite.api。
```

---

## 5. 启用方式

板端执行：

```bash
cd /home/linaro/edgeinfer-rk3588-board
./scripts/board/enable_edgeinfer_vision_rknn_dryrun.sh
```

恢复 fake backend：

```bash
cd /home/linaro/edgeinfer-rk3588-board
./scripts/board/disable_edgeinfer_vision_rknn_dryrun.sh
```

---

## 6. API Response 变化

启用 RKNN dryrun 后：

```json
{
  "edgeinfer": {
    "backend": "rknn-yolo-dryrun",
    "runtime": "phase18d-rknn-yolo-dryrun",
    "model_runtime": {
      "backend": "rknn-yolo-dryrun",
      "model_path": ".../yolo11n_baseline_i8_rk3588.rknn",
      "model_size_mb": 4.7,
      "probe": {
        "ok": true,
        "runtime": "rknnlite",
        "load_rknn_ms": 100.0,
        "init_runtime_ms": 200.0,
        "release_ms": 10.0
      }
    }
  },
  "latency_ms": {
    "load_image": 0.5,
    "preprocess": 0.01,
    "backend_init": 300.0,
    "inference": 0.0,
    "postprocess": 0.0,
    "total": 301.0
  }
}
```

说明：

```text
backend_init 表示 RKNNLite load_rknn + init_runtime + release subprocess dryrun 的端到端耗时；
inference 仍为 0.0；
objects 仍为空。
```

---

## 7. RKNN 日志与 JSON 解析

RKNNLite 可能会把 warning / info 日志输出到 stdout，例如：

```text
W rknn-toolkit-lite2 version: 2.3.2
I RKNN: Runtime Information ...
```

因此 `server/runtime/rknn_yolo_backend.py` 不能假设 subprocess stdout 是纯 JSON。当前实现会从混合 stdout 中扫描并提取包含 `ok` 字段的 JSON 对象，再将 stdout/stderr tail 保留在 `edgeinfer.model_runtime.probe.subprocess` 中，便于调试。

---

## 8. Host 测试

默认 fake backend：

```bash
python3 scripts/host/test_vision_detect_client.py
```

RKNN dryrun backend：

```bash
EDGEINFER_EXPECT_VISION_BACKEND=rknn-yolo-dryrun \
python3 scripts/host/test_vision_detect_client.py
```

---

## 9. 当前限制

Phase 18D 仍不包含：

```text
1. 真实 pixel resize；
2. tensor 构造；
3. rknn.inference；
4. YOLO raw output 解析；
5. decode / NMS；
6. bbox 输出；
7. 摄像头实时流。
```

---

## 10. 后续阶段

### Phase 18E：RKNN YOLO Inference Probe

下一步建议：

```text
1. 解决 serving / subprocess 的 numpy / cv2 依赖；
2. 构造真实 input tensor；
3. 调用 rknn.inference；
4. 返回 num_outputs、output_shapes；
5. 仍暂不做 YOLO postprocess。
```

### Phase 18F：YOLO Postprocess Integration

随后接入：

```text
server.vision.yolo_postprocess.postprocess_yolo_outputs
objects 输出
confidence_threshold
iou_threshold
```

---

## 11. 阶段结论

Phase 18D 的意义是验证：

```text
当前 FastAPI Serving 可以通过可控方式触达真实 RKNN YOLO runtime；
YOLO RKNN 模型文件路径可解析；
RKNNLite load / init / release 生命周期可被 API 触发并返回结构化结果。
```

这一步完成后，Vision Serving 将从输入 skeleton 进入真实 RKNN runtime 接入阶段。
