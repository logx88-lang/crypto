"""하이브리드 검색 파라미터 튜닝 하네스 — Recall@k / MRR 로 구성 비교.

캐시 전략: 질문별로 (임베딩·dense·bm25·리랭커 점수)를 1회 계산 → 파라미터 조합은 인메모리 스윕.
필요: Ollama(bge-m3 임베딩) + 리랭커(bge-reranker). LLM 호출 없음(가벼움).

실행:
  RAG_EMBED=bge-m3 RAG_RERANKER=BAAI/bge-reranker-v2-m3 python3 eval/run_eval.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from rag.index.embed import EmbeddingClient
from rag.index.store import VectorStore
from rag.index.bm25 import BM25Index
from rag.retrieve.hybrid import rrf_fuse
from rag.retrieve.rerank import Reranker
from eval.eval_set import EVAL

POOL = 30            # 질문당 dense/bm25 후보 상한(캐시)
FINAL_KS = (3, 5)    # Recall@k 측정 지점


def _contains(text, sub):
    return sub.lower() in (text or "").lower()


def precompute():
    emb = EmbeddingClient()
    store = VectorStore()
    bm25 = BM25Index.load()
    rer = Reranker()

    all_ids, all_docs = store.all_documents()
    corpus = dict(zip(all_ids, all_docs))
    print(f"코퍼스 청크 수: {len(corpus)}")

    per_q = []
    for item in EVAL:
        q, mc = item["q"], item["must_contain"]
        answerable = any(_contains(t, mc) for t in all_docs)
        qvec = emb.embed_one(q)
        dense = [d["id"] for d in store.query(qvec, top_k=POOL)]
        sparse = [s["id"] for s in bm25.search(q, top_k=POOL)]
        cand = list(dict.fromkeys(dense + sparse))          # 순서보존 유니크
        texts = {cid: corpus.get(cid, "") for cid in cand}
        rel = {cid: _contains(texts[cid], mc) for cid in cand}
        # 리랭커 점수 캐시(후보 전체 1회)
        rr = rer.scores(q, [texts[cid] for cid in cand])
        rerank_score = dict(zip(cand, rr))
        per_q.append({"q": q, "mc": mc, "answerable": answerable,
                      "dense": dense, "sparse": sparse, "rel": rel,
                      "rerank_score": rerank_score})
        if not answerable:
            print(f"  ⚠️ 근거 없음(코퍼스에 must_contain 부재): {q[:40]} …")
    return per_q


def ranking(pq, cfg):
    """설정대로 최종 후보 순위(id 리스트) 생성."""
    wd, wb = cfg["w_dense"], cfg["w_bm25"]
    lists, weights = [], []
    if wd > 0:
        lists.append(pq["dense"][:cfg["top_k_dense"]]); weights.append(wd)
    if wb > 0:
        lists.append(pq["sparse"][:cfg["top_k_bm25"]]); weights.append(wb)
    fused = [cid for cid, _ in rrf_fuse(lists, k=cfg["rrf_k"], weights=weights)]
    if cfg["use_rerank"]:
        head = fused[:cfg["rerank_top_n"]]
        head = sorted(head, key=lambda c: -pq["rerank_score"].get(c, -1e9))
        fused = head + fused[cfg["rerank_top_n"]:]
    return fused


def evaluate(per_q, cfg):
    recall = {k: 0 for k in FINAL_KS}
    mrr = 0.0
    n = 0
    for pq in per_q:
        if not pq["answerable"]:
            continue
        n += 1
        order = ranking(pq, cfg)
        first = next((i for i, cid in enumerate(order, 1) if pq["rel"].get(cid)), None)
        if first:
            mrr += 1.0 / first
        for k in FINAL_KS:
            if any(pq["rel"].get(cid) for cid in order[:k]):
                recall[k] += 1
    return {"recall": {k: recall[k] / n for k in FINAL_KS}, "mrr": mrr / n, "n": n}


def main():
    per_q = precompute()
    base = dict(top_k_dense=20, top_k_bm25=20, rrf_k=60, rerank_top_n=20)

    configs = []
    # 앙상블 가중치 (dense:bm25)
    for (wd, wb), name in [((1, 0), "dense-only"), ((0, 1), "bm25-only"),
                           ((1, 1), "hybrid 1:1"), ((2, 1), "hybrid 2:1(dense↑)"),
                           ((1, 2), "hybrid 1:2(bm25↑)"), ((3, 1), "hybrid 3:1"),
                           ((1, 3), "hybrid 1:3")]:
        for rr in (False, True):
            configs.append({**base, "w_dense": wd, "w_bm25": wb, "use_rerank": rr,
                            "name": f"{name} | rerank={'on' if rr else 'off'}"})
    # rrf_k 변형 (1:1 + rerank on 기준)
    for rk in (10, 100):
        configs.append({**base, "rrf_k": rk, "w_dense": 1, "w_bm25": 1,
                        "use_rerank": True, "name": f"hybrid 1:1 rrf_k={rk} | rerank=on"})

    rows = []
    for cfg in configs:
        r = evaluate(per_q, cfg)
        rows.append((cfg["name"], r))
    rows.sort(key=lambda x: (-x[1]["recall"][5], -x[1]["mrr"]))

    print(f"\n{'구성':40} {'R@3':>6} {'R@5':>6} {'MRR':>6}")
    print("-" * 62)
    for name, r in rows:
        print(f"{name:40} {r['recall'][3]:>6.2f} {r['recall'][5]:>6.2f} {r['mrr']:>6.3f}")
    best = rows[0]
    print(f"\n최고 구성: {best[0]}  (R@5={best[1]['recall'][5]:.2f}, MRR={best[1]['mrr']:.3f}, n={best[1]['n']})")


if __name__ == "__main__":
    main()
