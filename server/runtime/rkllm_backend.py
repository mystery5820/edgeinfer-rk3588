from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict


class RKLLMBackend:
    def __init__(self):
        self.fake_llm = os.environ.get("EDGEINFER_FAKE_LLM", "0") == "1"

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

        Qwen3-4B 在 no-template RKLLM 后端下对 /no_think 更稳定。
        这里默认要求只输出最终答案，避免思考过程、自我检查和特殊符号。
        """
        return (
            "/no_think "
            "请只输出最终答案，不要输出思考过程、解释、注释或特殊符号。\n"
            f"{prompt}"
        )

    @staticmethod
    def _extract_clean_text(stdout: str) -> str:
        begin = "=== CLEAN_TEXT_BEGIN ==="
        end = "=== CLEAN_TEXT_END ==="

        if begin in stdout and end in stdout:
            body = stdout.split(begin, 1)[1].split(end, 1)[0]
            return body.strip()

        return stdout.strip()

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
