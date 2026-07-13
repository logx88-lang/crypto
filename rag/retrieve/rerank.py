"""리랭커 — bge-reranker-v2-m3 CrossEncoder, CPU 실행 (design.md §5, Q5).

질의 시 GPU는 LLM+임베딩 전용으로 유지하기 위해 CPU에서 top-N 재정렬.
sentence-transformers 는 지연 임포트(최초 rerank 호출 시 로드).
"""
from __future__ import annotations

from ..config import CONFIG


class Reranker:
    def __init__(self, model_path: str = None, device: str = "cpu"):
        self.model_path = model_path or CONFIG.reranker_path
        self.device = device
        self._model = None

    def _ensure(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder  # 지연 임포트
            self._model = CrossEncoder(self.model_path, device=self.device)
        return self._model

    def rerank(self, query: str, candidates: list, final_k: int = None) -> list:
        """[{document, ...}] 후보를 (query, document) 관련도로 재정렬 → 상위 final_k.

        각 결과에 `rerank_score` 부착. 후보 비면 그대로 반환.
        """
        final_k = final_k or CONFIG.final_k
        if not candidates:
            return []
        model = self._ensure()
        pairs = [(query, c.get("document", "")) for c in candidates]
        scores = model.predict(pairs)
        ranked = sorted(zip(candidates, scores), key=lambda cs: -float(cs[1]))
        out = []
        for cand, score in ranked[:final_k]:
            item = dict(cand)
            item["rerank_score"] = float(score)
            out.append(item)
        return out
