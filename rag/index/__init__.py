"""인덱싱 계층 — 임베딩(bge-m3)·벡터저장(ChromaDB)·희소검색(BM25)·증분 인덱서."""
from .embed import EmbeddingClient, EmbeddingError
from .bm25 import BM25Index
from .indexer import Indexer, diff_manifest

__all__ = [
    "EmbeddingClient", "EmbeddingError", "BM25Index", "Indexer", "diff_manifest",
    "VectorStore",
]


def __getattr__(name):
    # VectorStore 는 chromadb 지연 임포트 → 접근 시에만 로드
    if name == "VectorStore":
        from .store import VectorStore
        return VectorStore
    raise AttributeError(name)
