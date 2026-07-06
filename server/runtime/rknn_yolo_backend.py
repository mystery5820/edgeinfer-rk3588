from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Tuple

from server.model_manager.config import default_registry_path, load_yaml
from server.vision.image_probe import probe_image


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class RKNNYoloDryRunError(RuntimeError):
    pass


class RKNNYoloDryBackend:
    """RKNN YOLO dry integration backend.

    This backend intentionally invokes a subprocess with system Python because
    the board-side serving venv may not contain rknnlite. It validates the real
    RKNN model path and RKNNLite load/init/release lifecycle, but it does not
    perform pixel preprocessing, inference output decoding or NMS yet.
    """

    _total_requests = 0
    _completed_requests = 0
    _failed_requests = 0
    _last_latency_ms = None
    _last_error = None
    _last_started_at = None
    _last_finished_at = None
    _current_model = None
    _last_probe = None

    @classmethod
    def metrics_snapshot(cls) -> Dict[str, object]:
        return {
            "total_requests": cls._total_requests,
            "completed_requests": cls._completed_requests,
            "failed_requests": cls._failed_requests,
            "last_error": cls._last_error,
            "last_latency_ms": cls._last_latency_ms,
            "last_started_at": cls._last_started_at,
            "last_finished_at": cls._last_finished_at,
            "current_model": cls._current_model,
            "last_probe": cls._last_probe,
        }

    @staticmethod
    def _raw_registry_models() -> List[Dict[str, object]]:
        raw = load_yaml(default_registry_path())
        models = raw.get("models", [])
        if isinstance(models, list):
            return [m for m in models if isinstance(m, dict)]
        return []

    @classmethod
    def _raw_model_config(cls, model: Dict[str, object]) -> Dict[str, object]:
        model_id = str(model.get("id") or "")
        model_name = str(model.get("name") or "")

        for item in cls._raw_registry_models():
            item_id = str(item.get("id") or item.get("name") or "")
            item_name = str(item.get("name") or item.get("id") or "")
            if model_id in {item_id, item_name} or model_name in {item_id, item_name}:
                return item

        return {}

    @classmethod
    def _model_path(cls, model: Dict[str, object]) -> Path:
        raw = cls._raw_model_config(model)
        value = (
            raw.get("runtime_model")
            or raw.get("model_file")
            or model.get("runtime_model")
            or model.get("model_file")
        )
        if not value:
            raise RKNNYoloDryRunError(
                f"object-detection model has no runtime_model/model_file: {model.get('id') or model.get('name')}"
            )

        path = Path(str(value))
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path

    @classmethod
    def _target_size(cls, model: Dict[str, object]) -> Tuple[int, int]:
        raw = cls._raw_model_config(model)
        value = raw.get("input_size") or model.get("input_size") or [640, 640]
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            try:
                return int(value[0]), int(value[1])
            except Exception:
                pass
        return 640, 640

    @staticmethod
    def _build_preprocess_plan(image: Dict[str, object], target_width: int, target_height: int) -> Dict[str, object]:
        width = max(1, int(image["width"]))
        height = max(1, int(image["height"]))
        scale = min(target_width / width, target_height / height)
        resized_width = int(round(width * scale))
        resized_height = int(round(height * scale))
        pad_x = max(0, target_width - resized_width)
        pad_y = max(0, target_height - resized_height)

        return {
            "method": "letterbox-metadata-only",
            "target_width": target_width,
            "target_height": target_height,
            "scale": round(float(scale), 6),
            "resized_width": resized_width,
            "resized_height": resized_height,
            "pad_left": pad_x // 2,
            "pad_right": pad_x - pad_x // 2,
            "pad_top": pad_y // 2,
            "pad_bottom": pad_y - pad_y // 2,
            "note": "No pixel resize is performed in Phase 18D dry integration.",
        }

    @staticmethod
    def _probe_script() -> Path:
        return PROJECT_ROOT / "scripts" / "board" / "probe_rknn_yolo_runtime.py"

    @staticmethod
    def _extract_json_payload(text: str) -> Dict[str, object]:
        """Extract the JSON object printed by the probe script from noisy RKNN logs.

        RKNNLite may print warning/info lines to stdout around the script's JSON
        payload. This helper scans for a balanced top-level JSON object and
        parses the first object that contains an "ok" field.
        """

        decoder = json.JSONDecoder()
        for idx, ch in enumerate(text):
            if ch != "{":
                continue
            try:
                payload, _end = decoder.raw_decode(text[idx:])
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and "ok" in payload:
                return payload

        raise RKNNYoloDryRunError(f"RKNN probe JSON payload not found in stdout: {text[-2000:]!r}")

    @classmethod
    def _run_probe(cls, model_path: Path, timeout_sec: float) -> Dict[str, object]:
        python_bin = os.environ.get("EDGEINFER_RKNN_YOLO_PYTHON", "/usr/bin/python3")
        script = cls._probe_script()

        if not script.exists():
            raise RKNNYoloDryRunError(f"probe script not found: {script}")

        cmd = [
            python_bin,
            str(script),
            "--model-path",
            str(model_path),
            "--runtime",
            "rknnlite",
        ]

        started = time.time()
        proc = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        elapsed_ms = (time.time() - started) * 1000.0

        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()

        payload = cls._extract_json_payload(stdout)

        payload["subprocess"] = {
            "cmd": cmd,
            "returncode": proc.returncode,
            "elapsed_ms": round(elapsed_ms, 3),
            "stdout_tail": stdout[-1000:] if stdout else "",
            "stderr_tail": stderr[-1000:] if stderr else "",
        }

        if proc.returncode != 0 or not payload.get("ok"):
            raise RKNNYoloDryRunError(json.dumps(payload, ensure_ascii=False))

        return payload

    @classmethod
    def detect(
        cls,
        *,
        model: Dict[str, object],
        image_path: str,
        confidence_threshold: float,
        iou_threshold: float,
    ) -> Dict[str, object]:
        cls._total_requests += 1
        cls._last_started_at = time.time()
        cls._current_model = model.get("id")

        started = time.time()
        try:
            model_path = cls._model_path(model)
            if not model_path.exists():
                raise FileNotFoundError(f"RKNN model not found: {model_path}")

            load_started = time.time()
            image = probe_image(image_path)
            load_image_ms = (time.time() - load_started) * 1000.0

            preprocess_started = time.time()
            target_width, target_height = cls._target_size(model)
            preprocess = cls._build_preprocess_plan(image, target_width, target_height)
            preprocess_ms = (time.time() - preprocess_started) * 1000.0

            probe_started = time.time()
            probe = cls._run_probe(
                model_path=model_path,
                timeout_sec=float(os.environ.get("EDGEINFER_RKNN_YOLO_PROBE_TIMEOUT_SECONDS", "60")),
            )
            backend_init_ms = (time.time() - probe_started) * 1000.0

            objects: List[Dict[str, object]] = []
            elapsed_ms = (time.time() - started) * 1000.0

            cls._completed_requests += 1
            cls._last_latency_ms = round(elapsed_ms, 3)
            cls._last_error = None
            cls._last_finished_at = time.time()
            cls._current_model = None
            cls._last_probe = {
                "ok": probe.get("ok"),
                "runtime": probe.get("runtime"),
                "model_path": probe.get("model_path"),
                "model_size_mb": probe.get("model_size_mb"),
                "load_rknn_ms": probe.get("load_rknn_ms"),
                "init_runtime_ms": probe.get("init_runtime_ms"),
                "release_ms": probe.get("release_ms"),
                "subprocess_elapsed_ms": probe.get("subprocess", {}).get("elapsed_ms"),
            }

            return {
                "objects": objects,
                "image": {
                    "path": image["path"],
                    "format": image["format"],
                    "width": image["width"],
                    "height": image["height"],
                    "channels": image["channels"],
                    "size_bytes": image["size_bytes"],
                    "preprocess": preprocess,
                },
                "model_runtime": {
                    "backend": "rknn-yolo-dryrun",
                    "model_path": str(model_path),
                    "model_size_mb": probe.get("model_size_mb"),
                    "probe": probe,
                },
                "latency_ms": {
                    "load_image": round(load_image_ms, 3),
                    "preprocess": round(preprocess_ms, 3),
                    "backend_init": round(backend_init_ms, 3),
                    "inference": 0.0,
                    "postprocess": 0.0,
                },
            }
        except Exception as exc:
            cls._failed_requests += 1
            cls._last_error = repr(exc)
            cls._last_finished_at = time.time()
            cls._current_model = None
            raise
