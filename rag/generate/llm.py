"""LLM 클라이언트 — Ollama `/api/chat` 래퍼 (design.md §6).

- 표준 라이브러리(urllib)로 호출, `ollama_host`/`num_ctx` 존중.
- 주 모델 실패(모델 없음/연결) 시 경량 폴백(qwen3.5:2b) 1회 재시도.
- Qwen3 thinking 잔재(<think>...</think>) 제거.
"""
from __future__ import annotations

import json
import re
import urllib.request
import urllib.error

from ..config import CONFIG

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, model: str = None, fallback: str = None, host: str = None,
                 num_ctx: int = None, timeout: float = 300.0):
        self.model = model or CONFIG.llm_model
        self.fallback = fallback or CONFIG.llm_fallback
        self.host = (host or CONFIG.ollama_host).rstrip("/")
        self.num_ctx = num_ctx or CONFIG.num_ctx
        self.timeout = timeout

    def _post(self, model: str, messages: list) -> str:
        payload = {
            "model": model, "messages": messages, "stream": False,
            "options": {"num_ctx": self.num_ctx, "temperature": 0.0},
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(f"{self.host}/api/chat", data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            out = json.loads(resp.read().decode("utf-8"))
        return out.get("message", {}).get("content", "")

    def chat(self, messages: list, model: str = None) -> str:
        primary = model or self.model
        try:
            text = self._post(primary, messages)
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            if primary == self.fallback:
                raise LLMError(f"LLM 호출 실패({primary}): {e}") from e
            try:
                text = self._post(self.fallback, messages)
            except (urllib.error.URLError, urllib.error.HTTPError) as e2:
                raise LLMError(
                    f"LLM 호출 실패(주 {primary}, 폴백 {self.fallback}): {e2}"
                ) from e2
        return _THINK_RE.sub("", text).strip()
