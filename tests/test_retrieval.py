"""2차 증분 순수 로직 검증 — RRF·증분 매니페스트·하이브리드·인덱서·프롬프트·로그워크플로우.

Ollama/Chroma/torch 불필요(전부 인메모리 페이크 주입). `python3 tests/test_retrieval.py`.
"""
import os
import sys
import tempfile
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from rag.retrieve.hybrid import rrf_fuse, HybridRetriever
from rag.index.indexer import diff_manifest, Indexer
from rag.index.bm25 import BM25Index
from rag.generate.prompt import (build_messages, build_context, source_label,
                                 sources_list, NO_CONTEXT_ANSWER, SYSTEM_PROMPT)
from rag.generate.answer import RAGPipeline
from rag.logs.workflow import summarize_analysis, build_log_messages, find_spec_candidates
from rag.logs.parser import analyze_text_log


# ---------------------------------------------------------------------------
# 인메모리 페이크
# ---------------------------------------------------------------------------
class FakeEmbed:
    def embed(self, texts):
        return [[float(len(t)), 1.0, 0.0] for t in texts]
    def embed_one(self, text):
        return self.embed([text])[0]


class FakeStore:
    def __init__(self):
        self.docs = {}   # id -> {document, metadata}
        self._order = []  # query가 반환할 순서(테스트 제어)
    def add(self, ids, embeddings, documents, metadatas):
        for i, cid in enumerate(ids):
            self.docs[cid] = {"document": documents[i], "metadata": metadatas[i]}
    def query(self, embedding, top_k=None, where=None):
        out = []
        for rank, cid in enumerate(self._order[:(top_k or 20)]):
            d = self.docs[cid]
            if where and any(d["metadata"].get(k) != v for k, v in where.items()):
                continue
            out.append({"id": cid, "document": d["document"],
                        "metadata": d["metadata"], "distance": rank * 0.1, "rank": rank})
        return out
    def get(self, ids):
        return {cid: self.docs[cid] for cid in ids if cid in self.docs}
    def delete(self, ids=None, where=None):
        for cid in (ids or []):
            self.docs.pop(cid, None)
    def all_documents(self):
        ids = list(self.docs)
        return ids, [self.docs[i]["document"] for i in ids]


class FakeBM25:
    def __init__(self):
        self.ids, self.texts, self._results = [], [], []
    def build(self, ids, texts):
        self.ids, self.texts = list(ids), list(texts)
    def search(self, query, top_k=None):
        return [{"id": cid, "score": 1.0 - r * 0.1, "rank": r}
                for r, cid in enumerate(self._results[:(top_k or 20)])]
    def save(self, path=None):
        pass


# ---------------------------------------------------------------------------
# RRF
# ---------------------------------------------------------------------------
def test_rrf_basic_order():
    # A: dense 1위 & bm25 2위 → 최상위. C: 한쪽에만.
    fused = rrf_fuse([["A", "B", "C"], ["B", "A", "D"]], k=60)
    ids = [cid for cid, _ in fused]
    assert ids[0] in ("A", "B")
    assert set(["A", "B", "C", "D"]) == set(ids)
    # 양쪽 상위에 등장한 A,B가 한쪽만 등장한 C,D보다 앞
    assert ids.index("A") < ids.index("C")
    assert ids.index("B") < ids.index("D")


def test_rrf_weights_and_scores():
    fused = rrf_fuse([["X"], ["Y"]], k=1, weights=[2.0, 1.0])
    d = dict(fused)
    assert d["X"] > d["Y"]            # X 가중치 2배
    assert abs(d["X"] - 2.0 / (1 + 1)) < 1e-9


# ---------------------------------------------------------------------------
# 하이브리드 리트리버
# ---------------------------------------------------------------------------
def test_hybrid_fuses_and_hydrates_bm25_only():
    store = FakeStore()
    store.add(["c1", "c2", "c3"], None,
              ["dense doc", "shared", "bm25 only doc"],
              [{"doc_type": "general"}] * 3)
    store._order = ["c1", "c2"]          # dense가 c3를 안 봄
    bm25 = FakeBM25(); bm25._results = ["c2", "c3"]  # bm25가 c3를 봄
    r = HybridRetriever(FakeEmbed(), store, bm25)
    res = r.search("q", top_k=5)
    ids = [x["id"] for x in res]
    assert "c3" in ids                    # bm25 전용 후보가 store.get으로 보강됨
    assert all(x["document"] for x in res)


def test_hybrid_where_postfilter_on_sparse():
    store = FakeStore()
    store.add(["s1", "g1"], None, ["spec doc", "general doc"],
              [{"doc_type": "protocol_spec"}, {"doc_type": "general"}])
    store._order = ["s1"]                 # dense는 필터로 s1만
    bm25 = FakeBM25(); bm25._results = ["g1", "s1"]  # bm25는 general g1도 반환
    r = HybridRetriever(FakeEmbed(), store, bm25)
    res = r.search("q", where={"doc_type": "protocol_spec"})
    ids = [x["id"] for x in res]
    assert ids == ["s1"], ids             # g1은 사후필터로 제거


# ---------------------------------------------------------------------------
# 증분 매니페스트
# ---------------------------------------------------------------------------
def test_diff_manifest():
    old = {"a.txt": {"content_hash": "h1"}, "b.txt": {"content_hash": "h2"}}
    cur = {"a.txt": {"content_hash": "h1"},          # 동일 → skip
           "b.txt": {"content_hash": "hX"},          # 변경 → reindex
           "c.txt": {"content_hash": "h3"}}          # 신규 → reindex
    to_index, to_delete = diff_manifest(old, cur)
    assert set(to_index) == {"b.txt", "c.txt"}
    assert to_delete == []
    # a.txt 삭제 케이스
    to_index2, to_delete2 = diff_manifest(old, {"b.txt": {"content_hash": "h2"}})
    assert to_delete2 == ["a.txt"]
    assert to_index2 == []


def test_indexer_incremental_reindex():
    tmp = tempfile.mkdtemp()
    try:
        data_dir = os.path.join(tmp, "data")
        os.makedirs(data_dir)
        f1 = os.path.join(data_dir, "doc.txt")
        with open(f1, "w", encoding="utf-8") as f:
            f.write("장비 XM-200 코인 컨트롤러 안내 문서입니다.\n두 번째 문단.\n")
        store, bm25 = FakeStore(), FakeBM25()
        ix = Indexer(embed_client=FakeEmbed(), store=store, bm25=bm25,
                     data_dir=data_dir, manifest_path=os.path.join(tmp, "manifest.json"))
        st1 = ix.reindex()
        assert st1["indexed"] == 1 and st1["chunks"] >= 1
        assert store.docs and bm25.ids
        # 재실행 → 변경 없음 → skip
        st2 = ix.reindex()
        assert st2["indexed"] == 0
        # 파일 수정 → 재인덱싱, 옛 청크 제거
        old_ids = set(store.docs)
        with open(f1, "w", encoding="utf-8") as f:
            f.write("완전히 다른 내용으로 교체된 문서.\n")
        st3 = ix.reindex()
        assert st3["indexed"] == 1
        assert set(store.docs) != old_ids   # 청크 id 교체됨
        # 파일 삭제 → 청크 제거
        os.remove(f1)
        st4 = ix.reindex()
        assert st4["deleted"] == 1
        assert store.docs == {}
    finally:
        shutil.rmtree(tmp)


# ---------------------------------------------------------------------------
# 프롬프트
# ---------------------------------------------------------------------------
def test_source_label():
    assert source_label({"doc_title": "XM-200", "page_no": 3}) == "XM-200 · p.3"
    assert "시트:사양" in source_label({"doc_title": "목록", "sheet_name": "사양"})
    assert source_label({"source_file": "x.txt"}) == "x.txt"


def test_build_messages_grounding():
    chunks = [{"document": "코인 투입 명령은 0x12 입니다.",
               "metadata": {"doc_title": "XM-200", "page_no": 2}}]
    msgs = build_messages("코인 투입 명령 코드는?", chunks)
    assert msgs[0]["role"] == "system" and "근거" in msgs[0]["content"]
    assert "[1]" in msgs[1]["content"] and "0x12" in msgs[1]["content"]
    assert "XM-200 · p.2" in msgs[1]["content"]
    assert NO_CONTEXT_ANSWER in SYSTEM_PROMPT


def test_pipeline_no_context_shortcircuits_llm():
    class BoomLLM:
        def chat(self, messages):
            raise AssertionError("근거 없을 때 LLM을 호출하면 안 된다")
    class EmptyRetriever:
        def search(self, q, where=None):
            return []
    pipe = RAGPipeline(EmptyRetriever(), None, BoomLLM())
    out = pipe.answer("아무거나")
    assert out["answer"] == NO_CONTEXT_ANSWER and out["sources"] == []


# ---------------------------------------------------------------------------
# 로그 워크플로우
# ---------------------------------------------------------------------------
def test_summarize_hex_analysis():
    text = "07/08 00:45:05 [02][05][12][01][00][14][03]"
    analysis = analyze_text_log(text)
    summ = summarize_analysis(analysis)
    assert "HEX 로그" in summ and "프레임" in summ


def test_build_log_messages_uses_spec():
    analysis = analyze_text_log("07/08 00:45:05 [02][05][12][01][00][14][03]")
    specs = [{"document": "0x12 = COIN_IN", "metadata": {"doc_title": "XM-200", "page_no": 1}}]
    msgs = build_log_messages("무슨 명령?", analysis, specs)
    assert "[명세1]" in msgs[1]["content"] and "COIN_IN" in msgs[1]["content"]
    assert "파싱 결과" in msgs[1]["content"]


def test_find_spec_candidates_filters_protocol():
    captured = {}
    class RecRetriever:
        def search(self, q, top_k=None, where=None):
            captured["where"] = where
            return [{"id": "s1", "document": "spec", "metadata": {"doc_type": "protocol_spec"}}]
    out = find_spec_candidates(RecRetriever(), "07/08 [02][12][03]", "질문")
    assert captured["where"] == {"doc_type": "protocol_spec"}
    assert out and out[0]["id"] == "s1"


# ---------------------------------------------------------------------------
def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS {fn.__name__}")
            passed += 1
        except Exception as e:
            import traceback
            print(f"  FAIL {fn.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
    print(f"\n{passed}/{len(fns)} 통과")
    return passed == len(fns)


if __name__ == "__main__":
    sys.exit(0 if _run_all() else 1)
