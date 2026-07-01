from __future__ import annotations

import asyncio
import os
import time
from typing import Dict, Any


class RKLLMBackend:
    def __init__(self):
        self.fake_llm = os.environ.get("EDGEINFER_FAKE_LLM", "0") == "1"
        self.command_template = os.environ.get("EDGEINFER_RKLLM_COMMAND_TEMPLATE", "").strip()

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

        if not self.command_template:
            raise RuntimeError(
                "RKLLM backend is not configured. "
                "Set EDGEINFER_FAKE_LLM=1 for API smoke test, or set "
                "EDGEINFER_RKLLM_COMMAND_TEMPLATE to a wrapper command."
            )

        model_file = model.get("model_file") or ""
        cmd = self.command_template.format(
            model_id=model.get("id", ""),
            model_file=model_file,
            max_new_tokens=max_new_tokens,
        )

        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=prompt.encode("utf-8")),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(f"RKLLM command timeout after {timeout_seconds}s")

        if proc.returncode != 0:
            raise RuntimeError(
                "RKLLM command failed. "
                f"returncode={proc.returncode}, stderr={stderr.decode('utf-8', errors='ignore')}"
            )

        return {
            "text": stdout.decode("utf-8", errors="ignore").strip(),
            "backend": "rkllm-subprocess",
            "latency_ms": round((time.time() - start) * 1000, 3),
        }
