"""벡터 저장소 — ChromaDB PersistentClient 래퍼 (design.md §5).

- 코사인 거리 컬렉션. add/query/delete + 메타데이터 필터(`where`).
- chromadb는 지연 임포트 → 순수 로직 테스트(RRF 등)는 이 모듈 없이도 실행 가능.
- Chroma 메타데이터는 스칼라만 허용 → None/컨테이너 값은 저장 전 제거·직렬화.
"""
from __future__ import annotations

from ..config import CONFIG


def _sanitize_meta(meta: dict) -> dict:
    out = {}
    for k, v in (meta or {}).items():
        if v is None or v == "":
            continue
        if isinstance(v, (str, int, float, bool)):
            out[k] = v
        else:
            out[k] = str(v)
    return out


class VectorStore:
    def __init__(self, path: str = None, collection: str = "docs"):
        import chromadb  # 지연 임포트
        self.path = path or CONFIG.chroma_dir
        self._client = chromadb.PersistentClient(path=self.path)
        self._col = self._client.get_or_create_collection(
            name=collection, metadata={"hnsw:space": "cosine"})

    def add(self, ids, embeddings, documents, metadatas) -> None:
        if not ids:
            return
        metas = [_sanitize_meta(m) for m in metadatas]
        # upsert: 동일 id 재인덱싱 시 덮어쓰기(증분 인덱싱 안전)
        self._col.upsert(ids=list(ids), embeddings=list(embeddings),
                         documents=list(documents), metadatas=metas)

    def query(self, embedding, top_k: int = None, where: dict = None) -> list:
        """단일 질의 벡터 → [{id, document, metadata, distance, rank}] (거리 오름차순)."""
        top_k = top_k or CONFIG.top_k_dense
        kw = {"query_embeddings": [embedding], "n_results": top_k}
        if where:
            kw["where"] = where
        res = self._col.query(**kw)
        out = []
        ids = (res.get("ids") or [[]])[0]
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        for rank, cid in enumerate(ids):
            out.append({
                "id": cid,
                "document": docs[rank] if rank < len(docs) else "",
                "metadata": metas[rank] if rank < len(metas) else {},
                "distance": dists[rank] if rank < len(dists) else None,
                "rank": rank,
            })
        return out

    def delete(self, ids=None, where: dict = None) -> None:
        if ids:
            self._col.delete(ids=list(ids))
        elif where:
            self._col.delete(where=where)

    def count(self) -> int:
        return self._col.count()

    def get(self, ids) -> dict:
        """ids → {id: {document, metadata}}. 존재하지 않는 id는 생략."""
        if not ids:
            return {}
        res = self._col.get(ids=list(ids), include=["documents", "metadatas"])
        got_ids = res.get("ids", [])
        docs = res.get("documents", [])
        metas = res.get("metadatas", [])
        out = {}
        for i, cid in enumerate(got_ids):
            out[cid] = {"document": docs[i] if i < len(docs) else "",
                        "metadata": metas[i] if i < len(metas) else {}}
        return out

    def all_documents(self) -> tuple:
        """전체 (ids, documents) — BM25 재구축용. 빈 컬렉션은 ([], [])."""
        res = self._col.get(include=["documents"])
        return res.get("ids", []), res.get("documents", [])

    def folders(self) -> list:
        """인덱싱된 청크의 distinct folder 목록(정렬)."""
        res = self._col.get(include=["metadatas"])
        fs = set()
        for m in res.get("metadatas", []) or []:
            if m and m.get("folder"):
                fs.add(m["folder"])
        return sorted(fs)
