from __future__ import annotations

import argparse
import fcntl
import os
import select
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path


DEFAULT_WORKER_BIN = (
    "/home/linaro/edgeinfer-rk3588-board/tools/rkllm_enhanced/"
    "rkllm_enhanced_no_template_no_history"
)

DEFAULT_MODEL = (
    "/userdata/edgeinfer-assets/models/llm/rkllm_outputs/"
    "Qwen3-4B-w8a8-npu.rkllm"
)


@dataclass
class WorkerGenerateResult:
    text: str
    latency_ms: float
    backend: str
    startup_ms: float
    model_path: str


class RKLLMPersistentWorker:
    """
    Minimal persistent RKLLM worker.

    This class is intentionally not wired into FastAPI by default yet.
    It is used to validate a long-running RKLLM process before replacing
    the one-shot subprocess backend.
    """

    def __init__(
        self,
        *,
        worker_bin: str = DEFAULT_WORKER_BIN,
        model_path: str = DEFAULT_MODEL,
        ctx: int = 1024,
        max_new_tokens: int = 96,
        startup_timeout: float = 60.0,
        request_timeout: float = 90.0,
    ) -> None:
        self.worker_bin = str(worker_bin)
        self.model_path = str(model_path)
        self.ctx = int(ctx)
        self.max_new_tokens = int(max_new_tokens)
        self.startup_timeout = float(startup_timeout)
        self.request_timeout = float(request_timeout)

        self.proc: subprocess.Popen[bytes] | None = None
        self.startup_ms: float = 0.0
        self.started_at: float | None = None
        self.last_started_at: float | None = None
        self.last_finished_at: float | None = None
        self.request_count: int = 0
        self.failed_request_count: int = 0
        self.last_latency_ms: float | None = None
        self.last_error: str | None = None
        self._start_count: int = 0
        self._lock = threading.Lock()
        self._stats_lock = threading.Lock()

    @staticmethod
    def _set_nonblocking(fd: int) -> None:
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    @staticmethod
    def _normalize_prompt(prompt: str) -> str:
        return " ".join(prompt.replace("\r", " ").replace("\n", " ").split())

    @staticmethod
    def _clean_response(raw: str) -> str:
        text = raw

        if "LLM:" in text:
            text = text.rsplit("LLM:", 1)[1]

        for marker in ("<|im_end|>", "\r\nYou:", "\nYou:", "You:"):
            if marker in text:
                text = text.split(marker, 1)[0]

        for token in (
            "<|im_end|>",
            "<|endoftext|>",
            "<think>",
            "</think>",
            "＜|End of Input|＞",
            "<|End of Input|>",
        ):
            text = text.replace(token, "")

        return " ".join(text.strip().split())

    def _read_until(
        self,
        *,
        markers: tuple[str, ...],
        timeout_s: float,
        label: str,
    ) -> str:
        if self.proc is None or self.proc.stdout is None:
            raise RuntimeError("worker is not started")

        fd = self.proc.stdout.fileno()
        end = time.time() + timeout_s
        chunks: list[bytes] = []

        while time.time() < end:
            if self.proc.poll() is not None:
                partial = b"".join(chunks).decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"worker exited while waiting for {label}, "
                    f"returncode={self.proc.returncode}, partial={partial[-1000:]}"
                )

            remaining = max(0.0, end - time.time())
            rlist, _, _ = select.select([fd], [], [], min(0.2, remaining))
            if not rlist:
                continue

            try:
                data = os.read(fd, 65536)
            except BlockingIOError:
                continue

            if not data:
                continue

            chunks.append(data)
            text = b"".join(chunks).decode("utf-8", errors="replace")

            if any(marker in text for marker in markers):
                return text

        partial = b"".join(chunks).decode("utf-8", errors="replace")
        raise TimeoutError(
            f"timeout waiting for {label}, markers={markers!r}, partial={partial[-1000:]}"
        )


    def _drain_stdout(self, *, timeout_s: float = 0.2) -> str:
        """
        Drain stale stdout bytes such as the idle "You:" prompt printed after
        the previous request. Without this, the next request may immediately
        match a leftover "\nYou:" marker and return an empty response.
        """
        if self.proc is None or self.proc.stdout is None:
            return ""

        fd = self.proc.stdout.fileno()
        end = time.time() + timeout_s
        chunks: list[bytes] = []

        while time.time() < end:
            remaining = max(0.0, end - time.time())
            rlist, _, _ = select.select([fd], [], [], min(0.05, remaining))
            if not rlist:
                continue

            try:
                data = os.read(fd, 65536)
            except BlockingIOError:
                continue

            if not data:
                break

            chunks.append(data)

        return b"".join(chunks).decode("utf-8", errors="replace")

    def start(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            return

        worker_path = Path(self.worker_bin)
        model_path = Path(self.model_path)

        if not worker_path.exists():
            raise FileNotFoundError(f"worker binary not found: {worker_path}")

        if not model_path.exists():
            raise FileNotFoundError(f"model file not found: {model_path}")

        cmd = [
            str(worker_path),
            str(model_path),
            str(self.ctx),
            str(self.max_new_tokens),
        ]

        start = time.time()
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
        )

        assert self.proc.stdout is not None
        self._set_nonblocking(self.proc.stdout.fileno())

        startup_log = self._read_until(
            markers=("You:",),
            timeout_s=self.startup_timeout,
            label="worker startup",
        )

        self.startup_ms = round((time.time() - start) * 1000.0, 3)

        with self._stats_lock:
            self._start_count += 1
            self.started_at = start
            self.last_error = None

        if "loading rkllm model" not in startup_log:
            raise RuntimeError(
                "worker started but startup log did not contain model loading marker"
            )

    def generate(self, prompt: str, *, timeout_s: float | None = None) -> WorkerGenerateResult:
        with self._lock:
            self.start()

            if self.proc is None or self.proc.stdin is None:
                raise RuntimeError("worker is not started")

            prompt_line = self._normalize_prompt(prompt)
            timeout = self.request_timeout if timeout_s is None else float(timeout_s)

            # Clear stale idle prompt from the previous turn before sending
            # the next request.
            self._drain_stdout(timeout_s=0.3)

            start = time.time()
            with self._stats_lock:
                self.last_started_at = start
                self.last_finished_at = None
                self.last_error = None

            try:
                self.proc.stdin.write((prompt_line + "\n").encode("utf-8"))
                self.proc.stdin.flush()

                raw = self._read_until(
                    markers=("<|im_end|>", "\r\nYou:", "\nYou:"),
                    timeout_s=timeout,
                    label="worker response",
                )

                latency_ms = round((time.time() - start) * 1000.0, 3)
                text = self._clean_response(raw)

                with self._stats_lock:
                    self.request_count += 1
                    self.last_latency_ms = latency_ms
                    self.last_finished_at = time.time()
                    self.last_error = None

                return WorkerGenerateResult(
                    text=text,
                    latency_ms=latency_ms,
                    backend="rkllm-persistent-worker",
                    startup_ms=self.startup_ms,
                    model_path=self.model_path,
                )

            except Exception as exc:
                latency_ms = round((time.time() - start) * 1000.0, 3)
                with self._stats_lock:
                    self.request_count += 1
                    self.failed_request_count += 1
                    self.last_latency_ms = latency_ms
                    self.last_finished_at = time.time()
                    self.last_error = str(exc)
                raise

    def snapshot(self) -> dict:
        proc = self.proc
        started = proc is not None and proc.poll() is None

        with self._stats_lock:
            return {
                "started": started,
                "pid": proc.pid if started and proc is not None else None,
                "startup_ms": self.startup_ms if self.startup_ms else None,
                "request_count": self.request_count,
                "failed_request_count": self.failed_request_count,
                "last_latency_ms": self.last_latency_ms,
                "last_error": self.last_error,
                "restart_count": max(0, self._start_count - 1),
                "started_at": self.started_at,
                "last_started_at": self.last_started_at,
                "last_finished_at": self.last_finished_at,
                "model_path": self.model_path,
                "ctx": self.ctx,
                "max_new_tokens": self.max_new_tokens,
            }

    def stop(self) -> None:
        proc = self.proc
        self.proc = None

        if proc is None:
            return

        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass

        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bin", default=DEFAULT_WORKER_BIN)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--ctx", type=int, default=1024)
    parser.add_argument("--max-new", type=int, default=96)
    parser.add_argument("--startup-timeout", type=float, default=60.0)
    parser.add_argument("--request-timeout", type=float, default=90.0)
    args = parser.parse_args()

    worker = RKLLMPersistentWorker(
        worker_bin=args.bin,
        model_path=args.model,
        ctx=args.ctx,
        max_new_tokens=args.max_new,
        startup_timeout=args.startup_timeout,
        request_timeout=args.request_timeout,
    )

    prompts = [
        "/no_think 已知事实：RK3588 是瑞芯微 Rockchip 推出的高性能 AIoT SoC，采用四核 Cortex-A76 加四核 Cortex-A55 架构，内置 NPU。请用一句话介绍 RK3588。",
        "/no_think 已知事实：RK3588 内置 NPU，可用于端侧 AI 推理。请用一句话说明 RK3588 为什么适合端侧 AI。",
    ]

    try:
        print("=== RKLLM persistent worker backend probe ===")
        print("worker_bin:", args.bin)
        print("model:", args.model)
        print("ctx:", args.ctx)
        print("max_new:", args.max_new)
        print()

        for idx, prompt in enumerate(prompts, start=1):
            result = worker.generate(prompt)
            print(f"request_{idx}_latency_ms:", result.latency_ms)
            print(f"request_{idx}_text:", result.text)
            if not result.text:
                raise RuntimeError(f"request_{idx} returned empty text")
            print()

        print("startup_ms:", worker.startup_ms)
        print("backend: rkllm-persistent-worker")
        print("probe_status: ok")
        return 0

    finally:
        worker.stop()


if __name__ == "__main__":
    raise SystemExit(main())
