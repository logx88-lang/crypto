"""답변 파이프라인 — retrieve → rerank → 컨텍스트 조립 → LLM (design.md §1·§6)."""
from __future__ import annotations

from ..config import CONFIG
from .prompt import build_messages, sources_list, NO_CONTEXT_ANSWER


class RAGPipeline:
    def __init__(self, retriever, reranker, llm, cfg=CONFIG):
        self.retriever = retriever
        self.reranker = reranker
        self.llm = llm
        self.cfg = cfg

    def answer(self, query: str, where: dict = None) -> dict:
        """질문 → {answer, sources, contexts}. 근거 없으면 LLM 미호출."""
        candidates = self.retriever.search(query, where=where)
        if not candidates:
            return {"answer": NO_CONTEXT_ANSWER, "sources": [], "contexts": []}
        top = self.reranker.rerank(query, candidates, final_k=self.cfg.final_k)
        messages = build_messages(query, top)
        text = self.llm.chat(messages)
        return {"answer": text, "sources": sources_list(top), "contexts": top}


def build_pipeline(cfg=CONFIG) -> RAGPipeline:
    """실 클라이언트(Ollama/Chroma/BM25/리랭커)로 파이프라인 구성."""
    from ..index.embed import EmbeddingClient
    from ..index.store import VectorStore
    from ..index.bm25 import BM25Index
    from ..retrieve.hybrid import HybridRetriever
    from ..retrieve.rerank import Reranker
    from .llm import LLMClient

    embed = EmbeddingClient()
    store = VectorStore()
    bm25 = BM25Index.load()
    retriever = HybridRetriever(embed, store, bm25, cfg=cfg)
    reranker = Reranker()
    llm = LLMClient()
    return RAGPipeline(retriever, reranker, llm, cfg=cfg)
