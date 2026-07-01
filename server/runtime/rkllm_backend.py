from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict

from server.runtime.prompt_policy import build_serving_prompt
from server.runtime.rkllm_worker_backend import RKLLMPersistentWorker


class RKLLMBackend:
    _worker: RKLLMPersistentWorker | None = None
    _worker_key: tuple[str, int, int, int] | None = None
    _worker_guard = threading.Lock()

    def __init__(self):
        self.fake_llm = os.environ.get("EDGEINFER_FAKE_LLM", "0") == "1"
        self.backend_mode = os.environ.get("EDGEINFER_RKLLM_BACKEND_MODE", "oneshot").strip().lower()

        self.project_root = Path(__file__).resolve().parents[2]
        self.runner_path = self.project_root / "server" / "runtime" / "rkllm_runner.py"

        self.assets_root = Path(
            os.environ.get("EDGEINFER_ASSETS_ROOT", "/userdata/edgeinfer-assets")
        )

    def _resolve_model_path(self, model: Dict[str, Any]) -> Path:
        model_file = model.get("model_file")

        if not model_file:
            raise RuntimeError(f"model_file is missing for model: {model.get('id')}")

        p = Path(str(model_file))

        if p.is_absolute():
            return p

        candidates = [
            self.assets_root / "models" / "llm" / "rkllm_outputs" / p,
            self.assets_root / "models" / "llm" / "qwen3" / "Qwen3-4B-W8A8-RK3588" / p,
            self.project_root / "models" / "llm" / "rkllm_outputs" / p,
        ]

        for candidate in candidates:
            if candidate.exists():
                return candidate

        raise RuntimeError(
            "RKLLM model file not found. "
            f"model_file={model_file}, searched={[str(c) for c in candidates]}"
        )

    @staticmethod
    def _build_prompt(prompt: str) -> str:
        """
        Phase 9 MVP prompt wrapper.

        Use prompt_policy to inject stable RK3588 facts for hardware-related
        questions and reduce hallucinated vendor/specification claims.
        """
        return build_serving_prompt(prompt)

    @staticmethod
    def _extract_clean_text(stdout: str) -> str:
        begin = "=== CLEAN_TEXT_BEGIN ==="
        end = "=== CLEAN_TEXT_END ==="

        if begin in stdout and end in stdout:
            body = stdout.split(begin, 1)[1].split(end, 1)[0]
            return body.strip()

        return stdout.strip()


    @staticmethod
    def _worker_max_new_tokens(request_max_new_tokens: int) -> int:
        configured = os.environ.get("EDGEINFER_RKLLM_WORKER_MAX_NEW")
        if configured:
            return int(configured)

        # Keep the worker stable across normal 64/96-token smoke tests while
        # still allowing larger requests to raise the worker generation cap.
        return max(128, int(request_max_new_tokens))

    @classmethod
    def _get_worker(
        cls,
        *,
        worker_bin: str,
        model_path: str,
        ctx: int,
        max_new_tokens: int,
        startup_timeout: float,
        request_timeout: float,
    ) -> RKLLMPersistentWorker:
        key = (worker_bin, hash(model_path), int(ctx), int(max_new_tokens))

        with cls._worker_guard:
            if cls._worker is not None and cls._worker_key == key:
                return cls._worker

            if cls._worker is not None:
                cls._worker.stop()

            cls._worker = RKLLMPersistentWorker(
                worker_bin=worker_bin,
                model_path=model_path,
                ctx=ctx,
                max_new_tokens=max_new_tokens,
                startup_timeout=startup_timeout,
                request_timeout=request_timeout,
            )
            cls._worker_key = key
            return cls._worker

    def _generate_with_worker(
        self,
        *,
        prompt: str,
        model: Dict[str, Any],
        max_new_tokens: int,
        timeout_seconds: float,
    ) -> Dict[str, Any]:
        model_path = self._resolve_model_path(model)

        worker_bin = os.environ.get(
            "EDGEINFER_RKLLM_WORKER_BIN",
            "/home/linaro/edgeinfer-rk3588-board/tools/rkllm_enhanced/"
            "rkllm_enhanced_no_template_no_history",
        )

        worker_ctx = int(os.environ.get("EDGEINFER_RKLLM_WORKER_CTX", "1024"))
        worker_max_new = self._worker_max_new_tokens(max_new_tokens)
        startup_timeout = float(os.environ.get("EDGEINFER_RKLLM_WORKER_STARTUP_TIMEOUT", "60"))

        worker = self._get_worker(
            worker_bin=worker_bin,
            model_path=str(model_path),
            ctx=worker_ctx,
            max_new_tokens=worker_max_new,
            startup_timeout=startup_timeout,
            request_timeout=timeout_seconds,
        )

        result = worker.generate(
            self._build_prompt(prompt),
            timeout_s=timeout_seconds,
        )

        if not result.text:
            raise RuntimeError("persistent worker returned empty text")

        return {
            "text": result.text,
            "backend": result.backend,
            "latency_ms": result.latency_ms,
            "startup_ms": result.startup_ms,
            "worker_max_new_tokens": worker_max_new,
            "worker_ctx": worker_ctx,
        }

    async def generate(
        self,
        *,
        prompt: str,
        model: Dict[str, Any],
        max_new_tokens: int,
        timeout_seconds: float,
    ) -> Dict[str, Any]:
        start = time.time()

        if self.fake_llm:
            text = (
                "这是 EdgeInfer-RK3588 Phase 9 MVP 的假 LLM 输出。"
                f" 当前模型为 {model.get('id')}，max_new_tokens={max_new_tokens}。"
            )
            return {
                "text": text,
                "backend": "fake",
                "latency_ms": round((time.time() - start) * 1000, 3),
            }

        if self.backend_mode in {"worker", "persistent", "persistent-worker"}:
            return await asyncio.to_thread(
                self._generate_with_worker,
                prompt=prompt,
                model=model,
                max_new_tokens=max_new_tokens,
                timeout_seconds=timeout_seconds,
            )

        model_path = self._resolve_model_path(model)
        ctx = int(model.get("ctx") or 1024)

        cmd = [
            sys.executable,
            str(self.runner_path),
            "--model",
            str(model_path),
            "--ctx",
            str(ctx),
            "--max-new",
            str(max_new_tokens),
            "--timeout",
            str(int(timeout_seconds)),
            "--prompt",
            self._build_prompt(prompt),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(self.project_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout_seconds + 5,
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(f"RKLLM runner timeout after {timeout_seconds}s")

        stdout = stdout_b.decode("utf-8", errors="ignore")
        stderr = stderr_b.decode("utf-8", errors="ignore")

        if proc.returncode != 0:
            raise RuntimeError(
                "RKLLM runner failed. "
                f"returncode={proc.returncode}, stderr={stderr}, stdout={stdout}"
            )

        text = self._extract_clean_text(stdout)

        return {
            "text": text,
            "backend": "rkllm-runner",
            "latency_ms": round((time.time() - start) * 1000, 3),
            "stderr": stderr.strip(),
        }
