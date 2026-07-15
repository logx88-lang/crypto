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
_DANGLING_THINK_RE = re.compile(r"<think>.*$", re.DOTALL)   # 잘린 미완결 <think>


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, model: str = None, fallback: str = None, host: str = None,
                 num_ctx: int = None, timeout: float = None):
        self.model = model or CONFIG.llm_model
        self.fallback = fallback or CONFIG.llm_fallback
        self.host = (host or CONFIG.ollama_host).rstrip("/")
        self.num_ctx = num_ctx or CONFIG.num_ctx
        self.timeout = timeout or CONFIG.llm_timeout

    def _post(self, model: str, messages: list, think: bool = False) -> str:
        payload = {
            "model": model, "messages": messages, "stream": False,
            "keep_alive": "10m",   # 호출 간 모델 상주 유지(CPU 재적재 회피)
            "options": {"num_ctx": self.num_ctx, "temperature": 0.0},
        }
        if think is not None:
            payload["think"] = think   # 사고 비활성화 → 생성 예산을 답변에 온전히 사용
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(f"{self.host}/api/chat", data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                out = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # think 파라미터 미지원 모델(400 등) → think 없이 1회 재시도
            if think is not None and e.code < 500:
                return self._post(model, messages, think=None)
            raise
        msg = out.get("message", {})
        content = msg.get("content", "")
        # content 가 비면(사고만 하고 답이 잘림 등) thinking 필드라도 반환해 공백 답변 방지
        if not (content or "").strip():
            content = msg.get("thinking", "") or ""
        return content

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
        cleaned = _DANGLING_THINK_RE.sub("", _THINK_RE.sub("", text)).strip()
        # <think>만 있고 실제 답이 비면(컨텍스트 초과로 잘림 등) 원문을 반환해 공백 답변 방지
        return cleaned or text.strip()
