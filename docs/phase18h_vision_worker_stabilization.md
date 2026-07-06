# Phase 18H：Vision Worker Stabilization

本文档记录 Phase 18H：将 Phase 18G 的 `rknn-yolo-detect-probe` 从“一次请求一个 subprocess”推进为 persistent RKNN YOLO worker MVP。

---

## 1. 背景

Phase 18G 已经完成：

```text
/v1/vision/detect
  -> image_path
  -> cv2 preprocess
  -> RKNNLite inference
  -> YOLO postprocess
  -> COCO class_name
  -> original-image bbox
```

但 Phase 18G 仍然是 probe backend，每次请求都会：

```text
启动 subprocess
import cv2 / numpy / rknnlite
load_rknn
init_runtime
inference
postprocess
release
```

因此 API 总耗时通常约 1.6–1.8 秒，其中真正 inference 只有约 120–140 ms。

---

## 2. 本阶段目标

Phase 18H 新增 persistent worker：

```text
FastAPI
  -> rknn-yolo-worker backend
  -> 长驻 /usr/bin/python3 worker subprocess
  -> worker 启动时 import/load/init RKNN 一次
  -> 每次请求只做 image read / preprocess / inference / postprocess
  -> 返回 objects
```

新增 backend：

```text
backend = rknn-yolo-worker
runtime = phase18h-vision-worker-stabilization
```

---

## 3. 新增文件

```text
server/runtime/rknn_yolo_worker_backend.py
scripts/board/rknn_yolo_worker.py
scripts/board/enable_edgeinfer_vision_rknn_worker.sh
scripts/board/disable_edgeinfer_vision_rknn_worker.sh
docs/phase18h_vision_worker_stabilization.md
```

更新：

```text
server/runtime/rknn_yolo_backend.py
server/api/vision_api.py
scripts/host/test_vision_detect_client.py
README.md
docs/README.md
```

---

## 4. Worker 协议

Worker 使用 stdin/stdout JSON line protocol。

为避免 RKNN Runtime 日志干扰，所有协议消息使用前缀：

```text
__EDGEINFER_JSON__
```

启动成功后输出：

```json
{
  "type": "ready",
  "ok": true,
  "backend": "rknn-yolo-worker",
  "model_path": "...",
  "startup_ms": 820.0
}
```

请求：

```json
{
  "id": "vision-xxxx",
  "image_path": "/path/to/image.jpg",
  "conf_thres": 0.25,
  "iou_thres": 0.45
}
```

响应：

```json
{
  "type": "response",
  "id": "vision-xxxx",
  "ok": true,
  "backend": "rknn-yolo-worker",
  "num_outputs": 1,
  "num_detections": 8,
  "detections": []
}
```

---

## 5. 性能预期

首个请求可能仍包含 worker startup 成本。

后续请求应明显减少：

```text
不再重复 import cv2/numpy/rknnlite
不再重复 load_rknn
不再重复 init_runtime
不再重复 release
```

期望后续请求更接近：

```text
preprocess + inference + postprocess
约 150–220 ms 级别
```

---

## 6. 启用方式

板端执行：

```bash
cd /home/linaro/edgeinfer-rk3588-board
./scripts/board/enable_edgeinfer_vision_rknn_worker.sh
```

恢复 fake backend：

```bash
cd /home/linaro/edgeinfer-rk3588-board
./scripts/board/disable_edgeinfer_vision_rknn_worker.sh
```

---

## 7. 验证方式

Host 测试：

```bash
EDGEINFER_EXPECT_VISION_BACKEND=rknn-yolo-worker \
python3 scripts/host/test_vision_detect_client.py
```

连续 curl 两次：

```bash
curl -s http://192.168.43.7:8000/v1/vision/detect \
  -H "Content-Type: application/json" \
  -d '{
    "model": "YOLOv11n-FP-Baseline",
    "image_path": "/home/linaro/edgeinfer-rk3588-board/datasets/coco128/images/train2017/000000000089.jpg"
  }' | python3 -m json.tool
```

重点观察：

```text
edgeinfer.backend = rknn-yolo-worker
edgeinfer.runtime = phase18h-vision-worker-stabilization
objects 非空
class_name 是 COCO 名称
bbox 是 original_image 坐标
worker_reused = true（第二次请求）
latency_ms.total 明显低于 detect-probe
```

---

## 8. 当前限制

Phase 18H 是 persistent worker MVP，仍有后续工作：

```text
1. 当前仍是同步单 worker；
2. 并发请求会在 backend lock 中串行等待；
3. 尚未实现 vision queue / reject_when_busy；
4. 尚未实现 worker crash 后更完整的恢复策略；
5. 尚未把 worker backend 设为默认。
```

---

## 9. 后续阶段

建议下一步：

```text
Phase 18I：Vision Queue and Busy Rejection
```

目标：

```text
1. 参考 LLMRequestQueue；
2. 新增 VisionRequestQueue；
3. 并发请求时 reject_when_busy；
4. /v1/metrics 暴露 vision busy / rejected_busy；
5. 让 vision serving 行为和 LLM serving 保持一致。
```

---

## 10. 阶段结论

Phase 18H 完成后，Vision Serving 将从“真实检测 probe”进入“可持续服务 backend”阶段：

```text
模型常驻
worker 长驻
减少重复初始化
保留 Phase 18G 的 objects 输出格式
```
