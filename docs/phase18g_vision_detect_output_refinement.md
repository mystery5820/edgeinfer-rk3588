# Phase 18G：Vision Detect Output Refinement

本文档记录 Phase 18G：对 Phase 18F 的 `/v1/vision/detect` 真实检测输出进行工程化精修。

---

## 1. 背景

Phase 18F 已经打通：

```text
/v1/vision/detect
  -> image_path
  -> cv2 preprocess
  -> RKNNLite inference
  -> postprocess_yolo_outputs
  -> objects
```

但 Phase 18F 仍存在两个输出层问题：

```text
1. class_name 仍为数字字符串，例如 "43"、"69"；
2. bbox 仍是 640x640 模型输入坐标，可能超过原始图片高度。
```

例如原始图片为 640x480，但模型输入为 640x640，Phase 18F 中可能出现：

```json
"bbox": [140.0, 271.0, 479.0, 638.5]
```

其中 `y2=638.5` 对 640x640 输入空间合法，但对 640x480 原图不合法。

---

## 2. 本阶段目标

Phase 18G 完成：

```text
1. 增加 COCO 80 类类别名；
2. detect probe 输出 class_name；
3. bbox 映射回原始图像坐标；
4. 保留 bbox_input 作为模型输入空间坐标；
5. objects 标注 coordinate_space；
6. test client 校验 bbox 不越界；
7. 文档记录当前坐标变换逻辑。
```

---

## 3. 新增文件

```text
server/vision/coco_classes.py
docs/phase18g_vision_detect_output_refinement.md
```

更新：

```text
scripts/board/probe_rknn_yolo_detect.py
server/runtime/rknn_yolo_backend.py
server/api/vision_api.py
scripts/host/test_vision_detect_client.py
README.md
docs/README.md
```

---

## 4. 坐标变换说明

当前 Phase 18F/18G 的 preprocess 是直接 resize/stretch：

```text
original image: W x H
model input:    640 x 640
```

因此 scale back 使用：

```text
x_original = x_input * original_width  / input_width
y_original = y_input * original_height / input_height
```

以 640x480 原图为例：

```text
x_original = x_input * 640 / 640
y_original = y_input * 480 / 640
```

所以：

```text
y2_input = 638.5
y2_original = 638.5 * 480 / 640 = 478.875
```

这样返回给 API 用户的 `bbox` 就在原图坐标内。

---

## 5. objects 输出格式

Phase 18G 后，objects 格式为：

```json
{
  "class_id": 69,
  "class_name": "oven",
  "confidence": 0.8935546875,
  "bbox": [140.0, 203.25, 479.0, 478.875],
  "bbox_input": [140.0, 271.0, 479.0, 638.5],
  "box_format": "xyxy",
  "coordinate_space": "original_image"
}
```

字段说明：

```text
bbox:
  原始图像坐标，给 API 用户使用。

bbox_input:
  640x640 模型输入坐标，主要用于调试。

coordinate_space:
  bbox 的坐标空间。
```

---

## 6. COCO 类别名

新增：

```text
server/vision/coco_classes.py
```

包含 COCO 80 类：

```text
person, bicycle, car, ..., oven, sink, refrigerator, ...
```

例如：

```text
class_id 43 -> knife
class_id 68 -> microwave
class_id 69 -> oven
```

---

## 7. Backend 与 Runtime

仍复用 Phase 18F 的 backend 名称：

```text
backend = rknn-yolo-detect-probe
```

runtime 更新为：

```text
runtime = phase18g-vision-detect-output-refinement
```

原因是 Phase 18G 没有引入新的推理后端，只是精修 detect probe 输出格式。

---

## 8. 验证方式

启用 detect probe：

```bash
ssh linaro@192.168.43.7 '
cd /home/linaro/edgeinfer-rk3588-board
./scripts/board/enable_edgeinfer_vision_rknn_detect_probe.sh
'
```

Host 测试：

```bash
EDGEINFER_EXPECT_VISION_BACKEND=rknn-yolo-detect-probe \
python3 scripts/host/test_vision_detect_client.py
```

手动 curl：

```bash
curl -s http://192.168.43.7:8000/v1/vision/detect \
  -H "Content-Type: application/json" \
  -d '{
    "model": "YOLOv11n-FP-Baseline",
    "image_path": "/home/linaro/edgeinfer-rk3588-board/datasets/coco128/images/train2017/000000000089.jpg"
  }' | python3 -m json.tool
```

重点确认：

```text
edgeinfer.runtime = phase18g-vision-detect-output-refinement
objects 非空
objects[0].class_name 不是数字字符串
objects[0].coordinate_space = original_image
objects[0].bbox 在原始图片尺寸内
objects[0].bbox_input 存在
```

---

## 9. 阶段限制

Phase 18G 仍然是 probe backend：

```text
1. 每次请求仍会新建 subprocess；
2. 每次请求仍会重新 load/init/release RKNN；
3. 还没有 persistent vision worker；
4. 还没有 vision queue / busy reject；
5. 当前坐标反变换基于 direct resize/stretch，不是 letterbox pipeline。
```

---

## 10. 后续阶段

建议下一步：

```text
Phase 18H：Vision Serving Stabilization
```

重点：

```text
1. persistent RKNN vision worker；
2. 避免每次请求重复 import/load/init；
3. vision queue / reject_when_busy；
4. 统一 vision metrics；
5. 让 rknn-yolo-detect 从 probe 走向正式 backend。
```

---

## 11. 阶段结论

Phase 18G 完成后，Vision API 的输出将从“能看到检测框”变为“可给上层应用使用的检测对象”：

```text
COCO class_name
original-image bbox
bbox_input for debug
coordinate_space metadata
```
