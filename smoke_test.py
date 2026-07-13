"""E2E 스모크 테스트 (Ollama 연동) — design.md §10.

배포/개발 서버에서 파이프라인 왕복을 실측한다:
  import → Ollama 연결 + 임베딩 차원 → 인덱싱(샘플) → 하이브리드 검색 → 리랭킹 → LLM 답변
  + 통신로그 분석(명세 확정 → 해석).

사전조건: `ollama serve` 가동, `ollama pull bge-m3 qwen3:8b`(또는 CONFIG 태그), 2차 의존성 설치.
환경변수로 태그 조정: RAG_EMBED / RAG_LLM / RAG_LLM_FALLBACK.

실행: python3 smoke_test.py
"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from rag.config import CONFIG


def _step(msg):
    print(f"\n▶ {msg}")


def main() -> int:
    _step("모듈 임포트")
    from rag.index.embed import EmbeddingClient
    from rag.index.store import VectorStore
    from rag.index.bm25 import BM25Index
    from rag.index.indexer import Indexer
    from rag.retrieve.hybrid import HybridRetriever
    from rag.retrieve.rerank import Reranker
    from rag.generate.llm import LLMClient
    from rag.generate.answer import RAGPipeline
    from rag.logs.workflow import analyze, find_spec_candidates, explain
    print("  ok")

    _step(f"임베딩 연결 + 차원 검증 (모델={CONFIG.embed_model}, 기대={CONFIG.embed_dim}d)")
    emb = EmbeddingClient()
    v = emb.embed_one("통신 프로토콜 테스트 문장")
    assert len(v) == CONFIG.embed_dim, f"차원 {len(v)} != {CONFIG.embed_dim}"
    print(f"  ok (dim={len(v)})")

    # 임시 코퍼스: 샘플 문서 + 프로토콜 명세 (hex/이미지 제외)
    tmp = tempfile.mkdtemp(prefix="rag_smoke_")
    data_dir = os.path.join(tmp, "data")
    os.makedirs(data_dir)
    src = os.path.join(ROOT, "samples", "dummy_set")
    for sub in ("docs", "protocol"):
        for name in os.listdir(os.path.join(src, sub)):
            shutil.copy(os.path.join(src, sub, name), os.path.join(data_dir, name))

    try:
        _step("인덱싱 (샘플 문서 + 명세)")
        store = VectorStore(path=os.path.join(tmp, "chroma"))
        bm25 = BM25Index()
        ix = Indexer(embed_client=emb, store=store, bm25=bm25, data_dir=data_dir,
                     manifest_path=os.path.join(tmp, "manifest.json"),
                     )
        # BM25 저장 경로를 임시로
        CONFIG.bm25_path = os.path.join(tmp, "bm25.pkl")
        stats = ix.reindex(full=True)
        print(f"  ok {stats}")
        assert stats["total_chunks"] > 0

        _step("하이브리드 검색 + 리랭킹 + LLM 답변")
        bm25 = BM25Index.load(CONFIG.bm25_path)
        retriever = HybridRetriever(emb, store, bm25)
        pipe = RAGPipeline(retriever, Reranker(), LLMClient())
        res = pipe.answer("XM-200 코인 투입 명령 코드는 무엇입니까?")
        print(f"  답변: {res['answer'][:200]}")
        print(f"  출처: {[s['label'] for s in res['sources']]}")
        assert res["sources"], "출처 없음(검색/인덱싱 확인)"

        _step("근거 없는 질문 → '모른다' 확인")
        res2 = pipe.answer("화성의 대기 조성비를 알려줘")
        print(f"  답변: {res2['answer'][:120]}")

        _step("통신로그 분석 (명세 확정 → 해석)")
        hexlog = "07/08 00:45:05 [02][05][12][01][00][14][03]"
        analysis = analyze(hexlog)
        specs = find_spec_candidates(retriever, hexlog, "무슨 명령인가?", top_k=3)
        print(f"  명세 후보: {[s['metadata'].get('doc_title') for s in specs]}")
        if specs:
            out = explain(LLMClient(), "이 로그의 명령을 명세에 근거해 설명해줘",
                          analysis, specs[:1])
            print(f"  해석: {out[:200]}")

        print("\n✅ 스모크 테스트 통과")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n❌ 스모크 실패: {e}")
        sys.exit(1)
