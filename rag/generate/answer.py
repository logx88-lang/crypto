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

    def answer(self, query: str, where: dict = None, final_k: int = None) -> dict:
        """질문 → {answer, sources, contexts}. 근거 없으면 LLM 미호출.

        final_k: 답변에 넣을 최종 근거(=출처) 개수. 미지정 시 설정값(cfg.final_k).
        빈 답변(컨텍스트 초과로 생성 여유 부족 등) 시 근거 수를 줄여 1회 재시도한다.
        """
        k = final_k or self.cfg.final_k
        candidates = self.retriever.search(query, where=where)
        if not candidates:
            return {"answer": NO_CONTEXT_ANSWER, "sources": [], "contexts": []}
        top = self.reranker.rerank(query, candidates, final_k=k)
        text = self.llm.chat(build_messages(query, top))
        if not (text or "").strip() and len(top) > 1:   # 빈 답변 → 컨텍스트 축소 재시도
            fewer = top[: max(1, len(top) // 2)]
            text = self.llm.chat(build_messages(query, fewer))
        return {"answer": text, "sources": sources_list(top), "contexts": top}


def build_pipeline(cfg=CONFIG) -> RAGPipeline:
    """실 클라이언트(Ollama/Chroma/BM25/리랭커)로 파이프라인 구성."""
    from ..index.embed import EmbeddingClient
    from ..index.store import VectorStore
    from ..index.bm25 import BM25Index
    from ..retrieve.hybrid import HybridRetriever
    from ..retrieve.rerank import Reranker, PassthroughReranker
    from .llm import LLMClient

    embed = EmbeddingClient()
    store = VectorStore()
    bm25 = BM25Index.load()
    retriever = HybridRetriever(embed, store, bm25, cfg=cfg)
    # 리랭커 비활성 시 torch 를 아예 로드하지 않음(RAM/네이티브 크래시 회피).
    reranker = Reranker() if cfg.rerank_enabled else PassthroughReranker()
    llm = LLMClient()
    return RAGPipeline(retriever, reranker, llm, cfg=cfg)
