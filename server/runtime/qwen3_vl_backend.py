from __future__ import annotations

import os
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from server.scheduler.npu_resource_guard import npu_resource_guard


RUNTIME_NAME = "phase22-qwen3-vl-rk3588-backend"
BACKEND_NAME = "qwen3-vl-rkllm-rknn-runner"

DEFAULT_MODEL_ID = "qwen3-vl-2b-instruct-rkllm-v123"
DEFAULT_DEMO_DIR = "/home/linaro/qwen3-vl-2b-npu"
DEFAULT_EXECUTABLE = f"{DEFAULT_DEMO_DIR}/VLM_NPU"
DEFAULT_LIBRARY_DIR = f"{DEFAULT_DEMO_DIR}/aarch64/library"
DEFAULT_VISION_MODEL = (
    "/userdata/edgeinfer-assets/models/vlm/"
    "qwen3-vl-2b-instruct-rkllm-v123/"
    "qwen3-vl-2b_vision_672_rk3588.rknn"
)
DEFAULT_LLM_MODEL = (
    "/userdata/edgeinfer-assets/models/vlm/"
    "qwen3-vl-2b-instruct-rkllm-v123/"
    "qwen3-vl-2b-instruct_w8a8_rk3588.rkllm"
)


class Qwen3VLBackendError(RuntimeError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int = 500,
        retryable: bool = False,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.extra = extra or {}


class Qwen3VLBackend:
    @staticmethod
    def backend_name() -> str:
        return BACKEND_NAME

    @staticmethod
    def runtime_name() -> str:
        return RUNTIME_NAME

    @staticmethod
    def default_model_id() -> str:
        return DEFAULT_MODEL_ID

    def __init__(self) -> None:
        self.demo_dir = Path(os.environ.get("EDGEINFER_QWEN3_VL_DEMO_DIR", DEFAULT_DEMO_DIR))
        self.executable = Path(os.environ.get("EDGEINFER_QWEN3_VL_EXECUTABLE", DEFAULT_EXECUTABLE))
        self.library_dir = Path(os.environ.get("EDGEINFER_QWEN3_VL_LIBRARY_DIR", DEFAULT_LIBRARY_DIR))
        self.vision_model = Path(os.environ.get("EDGEINFER_QWEN3_VL_VISION_MODEL", DEFAULT_VISION_MODEL))
        self.llm_model = Path(os.environ.get("EDGEINFER_QWEN3_VL_LLM_MODEL", DEFAULT_LLM_MODEL))

    def _check_assets(self, *, image_path: str) -> None:
        checks = {
            "demo_dir": self.demo_dir,
            "executable": self.executable,
            "library_dir": self.library_dir,
            "vision_model": self.vision_model,
            "llm_model": self.llm_model,
            "image_path": Path(image_path),
        }
        missing = {name: str(path) for name, path in checks.items() if not path.exists()}
        if missing:
            raise Qwen3VLBackendError(
                code="qwen3_vl_asset_missing",
                message="Qwen3-VL runtime asset is missing",
                status_code=500,
                retryable=False,
                extra={"missing": missing},
            )

    @staticmethod
    def _normalize_prompt(prompt: str) -> str:
        prompt = str(prompt or "").strip()
        if not prompt:
            prompt = "Describe this image in one sentence."
        if "<image>" not in prompt:
            prompt = "<image> " + prompt
        return prompt

    @staticmethod
    def _extract_answer(stdout: str) -> str:
        match = re.search(r"Answer:\s*(.*?)(?:\n\s*User:|$)", stdout, re.S)
        if not match:
            raise Qwen3VLBackendError(
                code="qwen3_vl_answer_parse_failed",
                message="failed to parse Answer from Qwen3-VL demo output",
                status_code=500,
                retryable=False,
                extra={"stdout_tail": stdout[-3000:]},
            )

        answer = match.group(1).strip()
        answer = re.sub(r"\x1b\[[0-9;]*m", "", answer).strip()
        if not answer:
            raise Qwen3VLBackendError(
                code="qwen3_vl_empty_answer",
                message="Qwen3-VL returned an empty answer",
                status_code=500,
                retryable=True,
                extra={"stdout_tail": stdout[-3000:]},
            )
        return answer

    def generate(
        self,
        *,
        task: str,
        image_path: str,
        prompt: str,
        model_id: Optional[str] = None,
        max_new_tokens: int = 64,
        context_length: int = 1024,
        timeout_seconds: int = 180,
    ) -> Dict[str, Any]:
        self._check_assets(image_path=image_path)

        prompt = self._normalize_prompt(prompt)
        model_id = model_id or self.default_model_id()

        lease = npu_resource_guard.acquire_nowait(
            task=task,
            owner="qwen3-vl",
            model_id=model_id,
        )

        started = time.time()
        try:
            env = os.environ.copy()
            old_ld = env.get("LD_LIBRARY_PATH", "")
            env["LD_LIBRARY_PATH"] = str(self.library_dir) + (":" + old_ld if old_ld else "")

            cmd = [
                str(self.executable),
                image_path,
                str(self.vision_model),
                str(self.llm_model),
                str(int(max_new_tokens)),
                str(int(context_length)),
            ]

            proc = subprocess.run(
                cmd,
                input=prompt + "\n",
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(self.demo_dir),
                env=env,
                timeout=float(timeout_seconds),
                check=False,
            )

            latency_ms = round((time.time() - started) * 1000.0, 3)
            stdout = proc.stdout or ""

            if proc.returncode != 0:
                raise Qwen3VLBackendError(
                    code="qwen3_vl_runtime_error",
                    message=f"Qwen3-VL demo exited with code {proc.returncode}",
                    status_code=500,
                    retryable=True,
                    extra={
                        "returncode": proc.returncode,
                        "stdout_tail": stdout[-3000:],
                        "latency_ms": latency_ms,
                    },
                )

            answer = self._extract_answer(stdout)
            lease.finish_success()

            return {
                "id": "vlm-" + uuid.uuid4().hex[:12],
                "object": "vlm.inference",
                "created": int(time.time()),
                "task": task,
                "model": model_id,
                "answer": answer,
                "prompt": prompt,
                "image": {"path": image_path},
                "latency_ms": latency_ms,
                "edgeinfer": {
                    "backend": self.backend_name(),
                    "runtime": self.runtime_name(),
                    "demo_dir": str(self.demo_dir),
                    "executable": str(self.executable),
                    "vision_model": str(self.vision_model),
                    "llm_model": str(self.llm_model),
                    "max_new_tokens": int(max_new_tokens),
                    "context_length": int(context_length),
                    "timeout_seconds": int(timeout_seconds),
                    "npu_resource": npu_resource_guard.snapshot(),
                },
                "raw": {
                    "returncode": proc.returncode,
                    "stdout_tail": stdout[-3000:],
                },
            }

        except subprocess.TimeoutExpired as exc:
            lease.finish_error(exc)
            raise Qwen3VLBackendError(
                code="qwen3_vl_timeout",
                message=f"Qwen3-VL inference timed out after {timeout_seconds}s",
                status_code=504,
                retryable=True,
                extra={"timeout_seconds": timeout_seconds},
            ) from exc
        except Exception as exc:
            if not getattr(lease, "released", False):
                lease.finish_error(exc)
            raise
