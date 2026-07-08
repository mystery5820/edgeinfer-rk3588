from __future__ import annotations

import os
import re
import select
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from server.scheduler.npu_resource_guard import npu_resource_guard


RUNTIME_NAME = "phase24-qwen3-vl-persistent-worker"
BACKEND_NAME = "qwen3-vl-rkllm-rknn-runner"

DEFAULT_MODEL_ID = "qwen3-vl-2b-instruct-rkllm-v123"
DEFAULT_DEMO_DIR = "/home/linaro/qwen3-vl-2b-npu"
DEFAULT_EXECUTABLE = f"{DEFAULT_DEMO_DIR}/VLM_NPU"
DEFAULT_WORKER_EXECUTABLE = f"{DEFAULT_DEMO_DIR}/VLM_NPU_WORKER"
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


def _tail_append(lines: List[str], line: str, *, limit: int = 80) -> None:
    lines.append(str(line).rstrip("\n"))
    if len(lines) > limit:
        del lines[:-limit]


class Qwen3VLPersistentWorker:
    def __init__(self) -> None:
        self.demo_dir = Path(os.environ.get("EDGEINFER_QWEN3_VL_DEMO_DIR", DEFAULT_DEMO_DIR))
        self.executable = Path(os.environ.get("EDGEINFER_QWEN3_VL_WORKER_EXECUTABLE", DEFAULT_WORKER_EXECUTABLE))
        self.library_dir = Path(os.environ.get("EDGEINFER_QWEN3_VL_LIBRARY_DIR", DEFAULT_LIBRARY_DIR))
        self.vision_model = Path(os.environ.get("EDGEINFER_QWEN3_VL_VISION_MODEL", DEFAULT_VISION_MODEL))
        self.llm_model = Path(os.environ.get("EDGEINFER_QWEN3_VL_LLM_MODEL", DEFAULT_LLM_MODEL))

        self.process: Optional[subprocess.Popen[str]] = None
        self.lock = threading.Lock()
        self.logs_tail: List[str] = []
        self.started_at: Optional[float] = None
        self.last_started_at: Optional[float] = None
        self.last_finished_at: Optional[float] = None
        self.init_ms: Optional[float] = None
        self.request_count = 0
        self.failed_request_count = 0
        self.restart_count = 0
        self.last_latency_ms: Optional[float] = None
        self.last_error: Optional[str] = None
        self.worker_max_new_tokens = int(os.environ.get("EDGEINFER_QWEN3_VL_WORKER_MAX_NEW", "128"))
        self.worker_context_length = int(os.environ.get("EDGEINFER_QWEN3_VL_WORKER_CTX", "1024"))

    def snapshot(self) -> Dict[str, Any]:
        proc = self.process
        return {
            "started": self.is_alive(),
            "pid": proc.pid if proc is not None else None,
            "demo_dir": str(self.demo_dir),
            "executable": str(self.executable),
            "vision_model": str(self.vision_model),
            "llm_model": str(self.llm_model),
            "init_ms": self.init_ms,
            "worker_max_new_tokens": self.worker_max_new_tokens,
            "worker_context_length": self.worker_context_length,
            "request_count": self.request_count,
            "failed_request_count": self.failed_request_count,
            "restart_count": self.restart_count,
            "last_latency_ms": self.last_latency_ms,
            "last_error": self.last_error,
            "started_at": self.started_at,
            "last_started_at": self.last_started_at,
            "last_finished_at": self.last_finished_at,
            "logs_tail": list(self.logs_tail[-20:]),
        }

    def is_alive(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def _check_assets(self, *, image_path: Optional[str] = None) -> None:
        checks = {
            "demo_dir": self.demo_dir,
            "worker_executable": self.executable,
            "library_dir": self.library_dir,
            "vision_model": self.vision_model,
            "llm_model": self.llm_model,
        }
        if image_path is not None:
            checks["image_path"] = Path(image_path)

        missing = {name: str(path) for name, path in checks.items() if not path.exists()}
        if missing:
            raise Qwen3VLBackendError(
                code="qwen3_vl_worker_asset_missing",
                message="Qwen3-VL persistent worker asset is missing",
                status_code=500,
                retryable=False,
                extra={"missing": missing},
            )

    def _env(self) -> Dict[str, str]:
        env = os.environ.copy()
        old_ld = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = str(self.library_dir) + (":" + old_ld if old_ld else "")
        return env

    @staticmethod
    def _readline_with_timeout(stream: Any, timeout_seconds: float) -> Optional[str]:
        if stream is None:
            return None
        ready, _, _ = select.select([stream], [], [], max(0.0, timeout_seconds))
        if not ready:
            return None
        return stream.readline()

    def _terminate_locked(self) -> None:
        proc = self.process
        if proc is None:
            return
        try:
            if proc.poll() is None:
                try:
                    if proc.stdin:
                        proc.stdin.write("exit\n")
                        proc.stdin.flush()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
        finally:
            self.process = None

    def _start_locked(self, *, startup_timeout_seconds: float = 90.0) -> None:
        if self.is_alive():
            return

        self._check_assets()
        self._terminate_locked()

        cmd = [
            str(self.executable),
            str(self.vision_model),
            str(self.llm_model),
            str(self.worker_max_new_tokens),
            str(self.worker_context_length),
        ]

        started = time.time()
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(self.demo_dir),
            env=self._env(),
        )
        self.restart_count += 1
        self.started_at = started
        self.last_error = None

        assert self.process.stdout is not None
        deadline = time.time() + startup_timeout_seconds
        while time.time() < deadline:
            if self.process.poll() is not None:
                raise Qwen3VLBackendError(
                    code="qwen3_vl_worker_start_failed",
                    message=f"Qwen3-VL worker exited during startup with code {self.process.returncode}",
                    status_code=500,
                    retryable=True,
                    extra={"worker": self.snapshot()},
                )

            remaining = deadline - time.time()
            line = self._readline_with_timeout(self.process.stdout, min(1.0, remaining))
            if line is None:
                continue

            clean = line.rstrip("\n")
            _tail_append(self.logs_tail, clean)

            if clean.startswith("init_ms:"):
                try:
                    self.init_ms = float(clean.split(":", 1)[1].strip())
                except ValueError:
                    pass

            if clean == "EDGEINFER_VLM_WORKER_READY":
                return

        self._terminate_locked()
        raise Qwen3VLBackendError(
            code="qwen3_vl_worker_start_timeout",
            message=f"Qwen3-VL worker did not become ready within {startup_timeout_seconds}s",
            status_code=504,
            retryable=True,
            extra={"worker": self.snapshot()},
        )

    @staticmethod
    def _sanitize_request_field(value: str) -> str:
        return str(value).replace("\r", " ").replace("\n", " ").replace("\t", " ").strip()

    def infer(self, *, image_path: str, prompt: str, timeout_seconds: int) -> Dict[str, Any]:
        with self.lock:
            self._check_assets(image_path=image_path)
            self._start_locked()

            if not self.is_alive() or self.process is None or self.process.stdin is None or self.process.stdout is None:
                raise Qwen3VLBackendError(
                    code="qwen3_vl_worker_not_running",
                    message="Qwen3-VL worker is not running",
                    status_code=500,
                    retryable=True,
                    extra={"worker": self.snapshot()},
                )

            image_path_clean = self._sanitize_request_field(image_path)
            prompt_clean = self._sanitize_request_field(prompt)
            line = image_path_clean + "\t" + prompt_clean + "\n"

            self.last_started_at = time.time()
            answer_lines: List[str] = []
            metadata: Dict[str, Any] = {}
            in_answer = False
            saw_begin = False
            saw_error = False
            error_lines: List[str] = []

            try:
                self.process.stdin.write(line)
                self.process.stdin.flush()
            except Exception as exc:
                self._terminate_locked()
                self.failed_request_count += 1
                self.last_error = f"write_failed: {exc}"
                raise Qwen3VLBackendError(
                    code="qwen3_vl_worker_write_failed",
                    message=f"failed to write request to Qwen3-VL worker: {exc}",
                    status_code=500,
                    retryable=True,
                    extra={"worker": self.snapshot()},
                ) from exc

            deadline = time.time() + float(timeout_seconds)
            while time.time() < deadline:
                if self.process.poll() is not None:
                    break

                remaining = deadline - time.time()
                out_line = self._readline_with_timeout(self.process.stdout, min(1.0, remaining))
                if out_line is None:
                    continue

                clean = out_line.rstrip("\n")
                _tail_append(self.logs_tail, clean)

                if clean == "EDGEINFER_VLM_BEGIN":
                    saw_begin = True
                    in_answer = False
                    continue

                if clean == "EDGEINFER_VLM_END":
                    latency = metadata.get("latency_ms")
                    self.last_latency_ms = float(latency) if latency not in (None, "") else None
                    self.last_finished_at = time.time()
                    self.request_count += 1
                    self.last_error = None
                    answer = "\n".join(answer_lines).strip()
                    if not answer:
                        self.failed_request_count += 1
                        self.last_error = "empty_answer"
                        raise Qwen3VLBackendError(
                            code="qwen3_vl_worker_empty_answer",
                            message="Qwen3-VL persistent worker returned an empty answer",
                            status_code=500,
                            retryable=True,
                            extra={"worker": self.snapshot()},
                        )
                    return {
                        "answer": answer,
                        "worker_latency_ms": self.last_latency_ms,
                        "metadata": metadata,
                        "worker": self.snapshot(),
                    }

                if clean == "EDGEINFER_VLM_ERROR_BEGIN":
                    saw_error = True
                    error_lines = []
                    continue

                if clean == "EDGEINFER_VLM_ERROR_END":
                    self.failed_request_count += 1
                    self.last_finished_at = time.time()
                    self.last_error = "\n".join(error_lines)[-300:]
                    raise Qwen3VLBackendError(
                        code="qwen3_vl_worker_runtime_error",
                        message="Qwen3-VL persistent worker returned an error",
                        status_code=500,
                        retryable=True,
                        extra={"worker_error": error_lines, "worker": self.snapshot()},
                    )

                if saw_error:
                    error_lines.append(clean)
                    continue

                if saw_begin and clean == "answer:":
                    in_answer = True
                    continue

                if saw_begin and in_answer:
                    answer_lines.append(clean)
                    continue

                if saw_begin and ":" in clean:
                    key, value = clean.split(":", 1)
                    metadata[key.strip()] = value.strip()

            self.failed_request_count += 1
            self.last_finished_at = time.time()
            self.last_error = "timeout_or_worker_exit"
            self._terminate_locked()
            raise Qwen3VLBackendError(
                code="qwen3_vl_worker_timeout",
                message=f"Qwen3-VL persistent worker did not return a complete response within {timeout_seconds}s",
                status_code=504,
                retryable=True,
                extra={"worker": self.snapshot(), "saw_begin": saw_begin},
            )


_persistent_worker = Qwen3VLPersistentWorker()


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
        self.worker_executable = Path(os.environ.get("EDGEINFER_QWEN3_VL_WORKER_EXECUTABLE", DEFAULT_WORKER_EXECUTABLE))
        self.library_dir = Path(os.environ.get("EDGEINFER_QWEN3_VL_LIBRARY_DIR", DEFAULT_LIBRARY_DIR))
        self.vision_model = Path(os.environ.get("EDGEINFER_QWEN3_VL_VISION_MODEL", DEFAULT_VISION_MODEL))
        self.llm_model = Path(os.environ.get("EDGEINFER_QWEN3_VL_LLM_MODEL", DEFAULT_LLM_MODEL))

    def _check_oneshot_assets(self, *, image_path: str) -> None:
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

    def _generate_oneshot(
        self,
        *,
        image_path: str,
        prompt: str,
        model_id: str,
        max_new_tokens: int,
        context_length: int,
        timeout_seconds: int,
    ) -> Dict[str, Any]:
        self._check_oneshot_assets(image_path=image_path)

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

        started = time.time()
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

        return {
            "answer": answer,
            "latency_ms": latency_ms,
            "mode": "oneshot",
            "raw": {"returncode": proc.returncode, "stdout_tail": stdout[-3000:]},
            "worker": None,
        }

    def _generate_worker(self, *, image_path: str, prompt: str, timeout_seconds: int) -> Dict[str, Any]:
        result = _persistent_worker.infer(
            image_path=image_path,
            prompt=prompt,
            timeout_seconds=timeout_seconds,
        )
        return {
            "answer": result["answer"],
            "latency_ms": result.get("worker_latency_ms"),
            "mode": "persistent-worker",
            "raw": {
                "metadata": result.get("metadata", {}),
                "logs_tail": result.get("worker", {}).get("logs_tail", []),
            },
            "worker": result.get("worker"),
        }

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
        prompt = self._normalize_prompt(prompt)
        model_id = model_id or self.default_model_id()

        mode = os.environ.get("EDGEINFER_QWEN3_VL_BACKEND_MODE", "worker").strip().lower()
        use_worker = mode in {"worker", "persistent-worker", "auto"} and self.worker_executable.exists()
        if mode == "oneshot":
            use_worker = False

        lease = npu_resource_guard.acquire_nowait(
            task=task,
            owner="qwen3-vl",
            model_id=model_id,
        )

        started = time.time()
        try:
            if use_worker:
                result = self._generate_worker(
                    image_path=image_path,
                    prompt=prompt,
                    timeout_seconds=int(timeout_seconds),
                )
            else:
                result = self._generate_oneshot(
                    image_path=image_path,
                    prompt=prompt,
                    model_id=model_id,
                    max_new_tokens=max_new_tokens,
                    context_length=context_length,
                    timeout_seconds=timeout_seconds,
                )

            total_latency_ms = round((time.time() - started) * 1000.0, 3)
            backend_latency_ms = result.get("latency_ms")
            answer = str(result.get("answer", "")).strip()

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
                "latency_ms": backend_latency_ms if backend_latency_ms is not None else total_latency_ms,
                "total_latency_ms": total_latency_ms,
                "edgeinfer": {
                    "backend": self.backend_name(),
                    "runtime": self.runtime_name(),
                    "mode": result.get("mode"),
                    "demo_dir": str(self.demo_dir),
                    "executable": str(self.worker_executable if use_worker else self.executable),
                    "vision_model": str(self.vision_model),
                    "llm_model": str(self.llm_model),
                    "request_max_new_tokens": int(max_new_tokens),
                    "request_context_length": int(context_length),
                    "timeout_seconds": int(timeout_seconds),
                    "worker": result.get("worker"),
                    "npu_resource": npu_resource_guard.snapshot(),
                },
                "raw": result.get("raw", {}),
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
