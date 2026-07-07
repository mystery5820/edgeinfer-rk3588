# Phase 18J：Vision Default Model and Metadata Cleanup

本文档记录 Phase 18J：清理 Vision Serving 的默认模型选择和 preprocess metadata。

---

## 1. 背景

Phase 18I 已经完成 Vision queue busy rejection：

```text
/v1/vision/detect
  -> VisionRequestQueue
  -> reject_when_busy
  -> 429 vision_backend_busy
```

但是当前还有两个工程细节需要整理：

```text
1. 不传 model 时，默认 object-detection 模型仍可能选到 INT8 debug 模型；
2. Phase 18E/F/G/H 的实际预处理是 direct resize，但 metadata 仍残留 letterbox pad_top/pad_bottom。
```

---

## 2. 本阶段目标

Phase 18J 目标：

```text
1. 默认 vision model 优先选择 YOLOv11n-FP-Baseline；
2. 支持 EDGEINFER_DEFAULT_VISION_MODEL 环境变量覆盖；
3. direct resize 阶段的 preprocess metadata 与真实行为一致；
4. host 测试覆盖默认模型选择。
```

---

## 3. 默认模型选择策略

当请求不传 `model` 时：

```text
优先使用 EDGEINFER_DEFAULT_VISION_MODEL；
如果未设置，默认使用 YOLOv11n-FP-Baseline；
如果 preferred 模型不存在或不是 object-detection，则回退到 registry.get_default_model("object-detection")。
```

默认 preferred：

```text
YOLOv11n-FP-Baseline
```

这样可以避免 INT8 debug 模型被误用为默认检测模型。

---

## 4. Preprocess Metadata 清理

Phase 18E/F/G/H/J 的实际预处理是：

```text
cv2.resize(image, (640, 640))
BGR -> RGB
uint8
NHWC
expand batch
```

所以 metadata 应改为：

```json
{
  "method": "resize-nhwc-uint8-worker-postprocess-scale-back",
  "target_width": 640,
  "target_height": 640,
  "scale": null,
  "scale_x": 1.0,
  "scale_y": 1.333333,
  "resized_width": 640,
  "resized_height": 640,
  "pad_left": 0,
  "pad_right": 0,
  "pad_top": 0,
  "pad_bottom": 0,
  "coordinate_transform": "resize_stretch_scale_back_to_original",
  "coordinate_space": "original_image"
}
```

---

## 5. Runtime 标识

worker backend 的 runtime 更新为：

```text
phase18j-vision-default-model-metadata-cleanup
```

注意：这不代表 worker 功能被替换，而是表示在 Phase 18H worker 与 Phase 18I queue 的基础上完成了默认模型和 metadata 清理。

---

## 6. 验证方式

启用 worker backend：

```bash
ssh linaro@192.168.43.7 '
cd /home/linaro/edgeinfer-rk3588-board
./scripts/board/enable_edgeinfer_vision_rknn_worker.sh
'
```

回归测试：

```bash
EDGEINFER_EXPECT_VISION_BACKEND=rknn-yolo-worker \
python3 scripts/host/test_vision_detect_client.py
```

并发测试：

```bash
python3 scripts/host/test_vision_busy_rejection.py
```

重点确认：

```text
1. 不传 model 的 default model success 返回 YOLOv11n-FP-Baseline；
2. default model 返回 objects 非空；
3. preprocess.resized_height = 640；
4. preprocess.pad_top = 0；
5. preprocess.pad_bottom = 0；
6. preprocess.scale_x / scale_y 存在；
7. runtime = phase18j-vision-default-model-metadata-cleanup；
8. busy rejection 仍然返回 429 vision_backend_busy。
```

---

## 7. 阶段结论

Phase 18J 完成后，Vision Serving 的默认行为更适合展示和使用：

```text
默认使用 ready FP 模型；
metadata 与真实 direct resize 行为一致；
测试覆盖默认模型选择；
保留 persistent worker 与 reject_when_busy。
```
