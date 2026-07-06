from __future__ import annotations

import json
import os
import select
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional


EDGEINFER_JSON_PREFIX = "__EDGEINFER_JSON__ "


class RKNNYoloWorkerClient:
    """Long-running RKNN YOLO worker process client.

    The worker process owns cv2 / numpy / RKNNLite imports and keeps the RKNN
    model loaded between requests. FastAPI talks to it with one JSON line per
    request. Non-prefixed RKNN logs are ignored; only lines beginning with
    EDGEINFER_JSON_PREFIX are parsed as protocol messages.
    """

    def __init__(
        self,
        *,
        python_bin: str,
        worker_script: str,
        model_path: str,
        input_width: int = 640,
        input_height: int = 640,
        startup_timeout: float = 60.0,
        request_timeout: float = 60.0,
    ) -> None:
        self.python_bin = str(python_bin)
        self.worker_script = str(worker_script)
        self.model_path = str(model_path)
        self.input_width = int(input_width)
        self.input_height = int(input_height)
        self.startup_timeout = float(startup_timeout)
        self.request_timeout = float(request_timeout)

        self.proc: Optional[subprocess.Popen[str]] = None
        self.started_at: Optional[float] = None
        self.startup_ms: Optional[float] = None
        self.last_started_at: Optional[float] = None
        self.last_finished_at: Optional[float] = None
        self.last_latency_ms: Optional[float] = None
        self.last_error: Optional[str] = None
        self.request_count = 0
        self.failed_request_count = 0
        self.restart_count = 0

        self._lock = threading.Lock()
        self._read_buffer = ""
        self._log_tail: list[str] = []

    def _record_log_line(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        self._log_tail.append(line)
        self._log_tail = self._log_tail[-80:]

    def _cmd(self) -> list[str]:
        return [
            self.python_bin,
            self.worker_script,
            "--model-path",
            self.model_path,
            "--input-width",
            str(self.input_width),
            "--input-height",
            str(self.input_height),
            "--runtime",
            "rknnlite",
        ]

    def _read_json_message(
        self,
        *,
        timeout_s: float,
        expected_type: str,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if self.proc is None or self.proc.stdout is None:
            raise RuntimeError("RKNN YOLO worker is not started")

        fd = self.proc.stdout.fileno()
        deadline = time.time() + timeout_s

        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(
                    "RKNN YOLO worker exited unexpectedly, "
                    f"returncode={self.proc.returncode}, logs={self._log_tail[-20:]}"
                )

            while "\n" in self._read_buffer:
                line, self._read_buffer = self._read_buffer.split("\n", 1)
                line = line.rstrip("\r")

                if not line.startswith(EDGEINFER_JSON_PREFIX):
                    self._record_log_line(line)
                    continue

                raw = line[len(EDGEINFER_JSON_PREFIX):]
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    self._record_log_line(line)
                    continue

                if payload.get("type") != expected_type:
                    # Protocol messages are sequential because the client holds
                    # a request lock. Unexpected messages are useful debug logs.
                    self._record_log_line(line)
                    continue

                if request_id is not None and payload.get("id") != request_id:
                    self._record_log_line(line)
                    continue

                return payload

            remaining = max(0.0, deadline - time.time())
            rlist, _, _ = select.select([fd], [], [], min(0.2, remaining))
            if not rlist:
                continue

            chunk = os.read(fd, 65536).decode("utf-8", errors="replace")
            if not chunk:
                continue
            self._read_buffer += chunk

        raise TimeoutError(
            f"timeout waiting for worker message type={expected_type!r}, "
            f"request_id={request_id!r}, logs={self._log_tail[-20:]}"
        )

    def start(self) -> bool:
        """Start worker if needed. Return True when a new process was started."""

        if self.proc is not None and self.proc.poll() is None:
            return False

        worker_script = Path(self.worker_script)
        model_path = Path(self.model_path)

        if not worker_script.exists():
            raise FileNotFoundError(f"RKNN YOLO worker script not found: {worker_script}")

        if not model_path.exists():
            raise FileNotFoundError(f"RKNN YOLO model file not found: {model_path}")

        started = time.time()
        self._read_buffer = ""
        self._log_tail = []

        self.proc = subprocess.Popen(
            self._cmd(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=False,
            bufsize=0,
        )

        ready = self._read_json_message(
            timeout_s=self.startup_timeout,
            expected_type="ready",
        )

        self.started_at = started
        self.startup_ms = float(ready.get("startup_ms", round((time.time() - started) * 1000.0, 3)))
        self.restart_count += 1
        self.last_error = None

        return True

    def detect(
        self,
        *,
        image_path: str,
        confidence_threshold: float,
        iou_threshold: float,
        timeout_s: Optional[float] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            started_now = self.start()

            if self.proc is None or self.proc.stdin is None:
                raise RuntimeError("RKNN YOLO worker stdin is not available")

            request_id = f"vision-{uuid.uuid4().hex[:12]}"
            timeout = self.request_timeout if timeout_s is None else float(timeout_s)

            payload = {
                "id": request_id,
                "image_path": image_path,
                "conf_thres": float(confidence_threshold),
                "iou_thres": float(iou_threshold),
            }

            started = time.time()
            self.last_started_at = started
            self.last_finished_at = None
            self.last_error = None

            try:
                line = json.dumps(payload, ensure_ascii=False) + "\n"
                self.proc.stdin.write(line.encode("utf-8"))
                self.proc.stdin.flush()

                response = self._read_json_message(
                    timeout_s=timeout,
                    expected_type="response",
                    request_id=request_id,
                )

                latency_ms = round((time.time() - started) * 1000.0, 3)
                self.last_latency_ms = latency_ms
                self.last_finished_at = time.time()

                if not response.get("ok"):
                    self.failed_request_count += 1
                    self.last_error = str(response.get("error") or "worker request failed")
                    raise RuntimeError(json.dumps(response, ensure_ascii=False))

                self.request_count += 1

                response["worker_pid"] = self.proc.pid
                response["worker_reused"] = not started_now
                response["worker_startup_ms"] = self.startup_ms if started_now else 0.0
                response["worker_total_startup_ms"] = self.startup_ms
                response["worker_request_latency_ms"] = latency_ms
                response["worker_restart_count"] = self.restart_count
                response["subprocess"] = {
                    "pid": self.proc.pid,
                    "reused": not started_now,
                    "startup_ms": self.startup_ms,
                    "request_latency_ms": latency_ms,
                    "logs_tail": self._log_tail[-20:],
                }
                return response

            except Exception as exc:
                self.failed_request_count += 1
                self.last_error = repr(exc)
                self.last_finished_at = time.time()
                raise

    def stop(self) -> None:
        proc = self.proc
        if proc is None:
            return

        try:
            if proc.poll() is None and proc.stdin is not None:
                try:
                    proc.stdin.write((json.dumps({"command": "stop"}) + "\n").encode("utf-8"))
                    proc.stdin.flush()
                except Exception:
                    pass

                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)
        finally:
            self.proc = None
            self._read_buffer = ""

    def snapshot(self) -> Dict[str, Any]:
        proc = self.proc
        alive = proc is not None and proc.poll() is None

        return {
            "started": alive,
            "pid": proc.pid if alive else None,
            "model_path": self.model_path,
            "input_width": self.input_width,
            "input_height": self.input_height,
            "startup_ms": self.startup_ms,
            "request_count": self.request_count,
            "failed_request_count": self.failed_request_count,
            "restart_count": self.restart_count,
            "last_latency_ms": self.last_latency_ms,
            "last_error": self.last_error,
            "started_at": self.started_at,
            "last_started_at": self.last_started_at,
            "last_finished_at": self.last_finished_at,
            "logs_tail": self._log_tail[-20:],
        }

    def __del__(self) -> None:
        try:
            self.stop()
        except Exception:
            pass
