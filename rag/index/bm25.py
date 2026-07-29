"""희소 검색(BM25) — kiwipiepy 형태소 토큰화 + bm25s 인덱스 (design.md §5).

- 한국어는 kiwipiepy 형태소, 영어/숫자는 소문자 정규화. kiwipiepy 미설치 시 정규식 폴백.
- bm25s / kiwipiepy 는 지연 임포트. 토크나이저 폴백 경로는 순수 파이썬이라 단독 테스트 가능.
- 증분은 인덱서가 Chroma 코퍼스 전체로 BM25를 재구축하는 방식(§indexer). 저장/로드 지원.
"""
from __future__ import annotations

import json
import os
import re

from ..config import CONFIG

# 한글 음절/자모 + 영숫자 토큰(폴백용)
_TOKEN_RE = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]+|[a-zA-Z0-9]+")


class BM25Index:
    def __init__(self):
        self._bm25 = None
        self.ids: list = []
        self._kiwi = None
        self._kiwi_tried = False

    # --- 토큰화 ---
    def _get_kiwi(self):
        if self._kiwi_tried:
            return self._kiwi
        self._kiwi_tried = True
        try:
            from kiwipiepy import Kiwi
            self._kiwi = Kiwi()
        except Exception as e:
            # 무음 폴백 금지: kiwi가 없으면 한글이 통짜 토큰이 되어 BM25 recall이 크게
            # 떨어진다. 원인을 서버 콘솔에 1회 노출해 조치(휠 반입 등)를 유도한다.
            print(f"[경고] kiwipiepy 로드 실패 → 한국어 BM25 품질 저하(정규식 폴백): "
                  f"{type(e).__name__}: {e}", flush=True)
            self._kiwi = None
        return self._kiwi

    def tokenize(self, text: str) -> list:
        text = (text or "").strip()
        if not text:
            return []
        kiwi = self._get_kiwi()
        if kiwi is not None:
            toks = [t.form.lower() for t in kiwi.tokenize(text) if t.form.strip()]
            return toks or _TOKEN_RE.findall(text.lower())
        return _TOKEN_RE.findall(text.lower())

    # --- 구축/검색 ---
    def build(self, ids, texts) -> None:
        import bm25s  # 지연 임포트
        self.ids = list(ids)
        if not self.ids:            # 빈 코퍼스: bm25s.index([])가 max() 크래시 → 스킵
            self._bm25 = None
            return
        corpus_tokens = [self.tokenize(t) for t in texts]
        self._bm25 = bm25s.BM25()
        self._bm25.index(corpus_tokens)

    def search(self, query: str, top_k: int = None) -> list:
        """질의 → [{id, score, rank}] (점수 내림차순)."""
        top_k = top_k or CONFIG.top_k_bm25
        if self._bm25 is None or not self.ids:
            return []
        q_tokens = self.tokenize(query)
        if not q_tokens:
            return []
        k = min(top_k, len(self.ids))
        results, scores = self._bm25.retrieve([q_tokens], corpus=self.ids, k=k)
        out = []
        for rank in range(len(results[0])):
            out.append({"id": str(results[0][rank]), "score": float(scores[0][rank]),
                        "rank": rank})
        return out

    # --- 영속화 ---
    def save(self, path: str = None) -> None:
        path = path or CONFIG.bm25_path
        base = path[:-4] if path.endswith(".pkl") else path
        os.makedirs(os.path.dirname(base) or ".", exist_ok=True)
        with open(base + "_ids.json", "w", encoding="utf-8") as f:
            json.dump(self.ids, f, ensure_ascii=False)
        if self._bm25 is None:      # 빈 인덱스: bm25s 디렉토리 없이 ids만 저장
            return
        os.makedirs(base + "_bm25s", exist_ok=True)
        self._bm25.save(base + "_bm25s")

    @classmethod
    def load(cls, path: str = None) -> "BM25Index":
        import bm25s
        path = path or CONFIG.bm25_path
        base = path[:-4] if path.endswith(".pkl") else path
        obj = cls()
        ids_file = base + "_ids.json"
        if not os.path.exists(ids_file):
            return obj  # 아직 인덱스 없음 → 빈 인덱스
        with open(ids_file, encoding="utf-8") as f:
            obj.ids = json.load(f)
        if obj.ids and os.path.exists(base + "_bm25s"):
            obj._bm25 = bm25s.BM25.load(base + "_bm25s")
        return obj
