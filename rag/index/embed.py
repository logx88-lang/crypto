"""임베딩 클라이언트 — Ollama `/api/embed` 래퍼 (bge-m3, 1024d).

설계 근거: design.md §5. 인제스천은 배치, 질의는 단건.
- HTTP는 표준 라이브러리(urllib)로 호출해 추가 의존성 없이 `ollama_host`를 존중한다.
- 차원은 `CONFIG.embed_dim`(기본 1024)으로 검증 → nomic(768) 오라벨 태그 조기 적발.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error

from ..config import CONFIG


class EmbeddingError(RuntimeError):
    pass


class EmbeddingClient:
    """Ollama 임베딩 래퍼. Ollama 미가동 시 embed() 호출에서만 실패한다(임포트는 안전)."""

    def __init__(self, model: str = None, host: str = None, dim: int = None,
                 timeout: float = 120.0):
        self.model = model or CONFIG.embed_model
        self.host = (host or CONFIG.ollama_host).rstrip("/")
        self.dim = dim or CONFIG.embed_dim
        self.timeout = timeout

    # --- 내부 HTTP ---
    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.host}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise EmbeddingError(
                f"Ollama 연결 실패({url}): {e}. `ollama serve` 및 모델 '{self.model}' 확인."
            ) from e

    # --- 공개 API ---
    def embed(self, texts) -> list:
        """문자열 리스트 → 벡터 리스트(배치). 빈 입력은 빈 리스트."""
        if isinstance(texts, str):
            texts = [texts]
        texts = [t if t is not None else "" for t in texts]
        if not texts:
            return []
        # 신 API(/api/embed, input=배열). 실패 시 구 API(/api/embeddings, prompt=단건) 폴백.
        try:
            out = self._post("/api/embed", {"model": self.model, "input": texts})
            vecs = out.get("embeddings")
            if vecs is None:
                raise EmbeddingError("응답에 embeddings 없음")
        except EmbeddingError:
            vecs = [self._post("/api/embeddings",
                               {"model": self.model, "prompt": t})["embedding"]
                    for t in texts]
        self._validate(vecs)
        return vecs

    def embed_one(self, text: str) -> list:
        return self.embed([text])[0]

    def _validate(self, vecs) -> None:
        if not vecs or not vecs[0]:
            raise EmbeddingError("빈 임베딩 반환")
        d = len(vecs[0])
        if d != self.dim:
            raise EmbeddingError(
                f"임베딩 차원 불일치: 기대 {self.dim}, 실제 {d}. "
                f"모델 '{self.model}' 태그 확인(768=nomic 오라벨 → 정품 bge-m3 재반입)."
            )
