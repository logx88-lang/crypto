"""하이브리드 검색 — dense(ChromaDB) + sparse(BM25) → RRF 융합 (design.md §5).

- `rrf_fuse` 는 순수 로직 → Ollama/DB 없이 단위 테스트.
- `HybridRetriever` 는 embed/store/bm25 주입. where 필터는 dense 는 네이티브,
  sparse-only 후보는 메타데이터 사후 필터로 일관 적용(BM25는 필터 미지원).
"""
from __future__ import annotations

from ..config import CONFIG


def rrf_fuse(ranked_lists, k: int = 60, weights=None) -> list:
    """여러 순위 리스트(각각 id의 순서열)를 RRF로 융합.

    score(id) = Σ_l  w_l / (k + rank_l)   (rank 1-based)
    반환: [(id, score)] 점수 내림차순.
    """
    if weights is None:
        weights = [1.0] * len(ranked_lists)
    scores = {}
    for lst, w in zip(ranked_lists, weights):
        for rank, cid in enumerate(lst, start=1):
            scores[cid] = scores.get(cid, 0.0) + w / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


def _matches_where(meta: dict, where: dict) -> bool:
    if not where:
        return True
    for key, val in where.items():
        if meta.get(key) != val:
            return False
    return True


class HybridRetriever:
    def __init__(self, embed_client, store, bm25, cfg=CONFIG):
        self.embed = embed_client
        self.store = store
        self.bm25 = bm25
        self.cfg = cfg

    def search(self, query: str, top_k: int = None, where: dict = None) -> list:
        """[{id, document, metadata, rrf_score}] (융합 점수 내림차순, 상위 top_k)."""
        top_k = top_k or self.cfg.rerank_top_n
        qvec = self.embed.embed_one(query)
        dense = self.store.query(qvec, top_k=self.cfg.top_k_dense, where=where)
        sparse = self.bm25.search(query, top_k=self.cfg.top_k_bm25)

        dense_ids = [d["id"] for d in dense]
        sparse_ids = [s["id"] for s in sparse]
        fused = rrf_fuse([dense_ids, sparse_ids], k=self.cfg.rrf_k)

        # 문서/메타 조립: dense 결과 먼저, 부족분(BM25 전용)은 store.get 으로 보강
        info = {d["id"]: {"document": d["document"], "metadata": d["metadata"]}
                for d in dense}
        missing = [cid for cid, _ in fused if cid not in info]
        if missing:
            info.update(self.store.get(missing))

        out = []
        for cid, score in fused:
            item = info.get(cid)
            if item is None:
                continue
            if where and not _matches_where(item["metadata"], where):
                continue  # sparse-only 후보의 필터 사후 적용
            out.append({"id": cid, "document": item["document"],
                        "metadata": item["metadata"], "rrf_score": score})
            if len(out) >= top_k:
                break
        return out
