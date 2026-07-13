"""Streamlit UI — 문서 QA / 로그 분석(업로드+확인단계) / 관리(인덱싱) (design.md §1·§7·§11).

실행: streamlit run rag/app/main.py --server.address 0.0.0.0 --server.port 8501
Ollama(`ollama serve`)와 인덱스(관리 탭에서 생성)가 필요하다.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import streamlit as st

from rag.config import CONFIG


# --- 리소스 캐시 (프로세스 1회 로드) --------------------------------------
@st.cache_resource(show_spinner=False)
def get_pipeline():
    from rag.generate.answer import build_pipeline
    return build_pipeline()


@st.cache_resource(show_spinner=False)
def get_retriever_llm():
    from rag.index.embed import EmbeddingClient
    from rag.index.store import VectorStore
    from rag.index.bm25 import BM25Index
    from rag.retrieve.hybrid import HybridRetriever
    from rag.generate.llm import LLMClient
    retriever = HybridRetriever(EmbeddingClient(), VectorStore(), BM25Index.load())
    return retriever, LLMClient()


st.set_page_config(page_title="사내 지식 RAG", layout="wide")
st.title("사내 지식 공유 · 통신로그 분석 플랫폼")

tab_qa, tab_log, tab_admin = st.tabs(["📄 문서 QA", "🔌 로그 분석", "⚙️ 관리"])


# ===========================================================================
# 문서 QA
# ===========================================================================
with tab_qa:
    st.subheader("문서 질의응답")
    query = st.text_input("질문", key="qa_query",
                          placeholder="예: XM-200 코인 투입 명령 코드는?")
    if st.button("검색", key="qa_btn") and query.strip():
        try:
            with st.spinner("검색·리랭킹·생성 중…"):
                res = get_pipeline().answer(query.strip())
            st.markdown("### 답변")
            st.write(res["answer"])
            if res["sources"]:
                st.markdown("### 출처")
                for s in res["sources"]:
                    st.markdown(f"**[{s['n']}]** {s['label']}")
                with st.expander("근거 원문 보기"):
                    for i, c in enumerate(res["contexts"], 1):
                        st.markdown(f"**[{i}]** {c['metadata'].get('doc_title','')}")
                        st.code(c["document"][:2000])
        except Exception as e:
            st.error(f"오류: {e}\nOllama(`ollama serve`)와 인덱스(관리 탭)를 확인하세요.")


# ===========================================================================
# 로그 분석 (업로드 → 자동감지 → 명세 후보 → 확인단계 → 해석)
# ===========================================================================
with tab_log:
    st.subheader("통신 로그 분석")
    st.caption("HEX/자연어 로그 업로드 → 프로토콜 명세 후보 확인 → 확정 명세 기반 해석 (자동 추측 없음)")
    up = st.file_uploader("로그 파일 (.txt/.dat/.log)", type=["txt", "dat", "log"],
                          key="log_up")
    log_q = st.text_input("질문(선택)", key="log_q",
                          placeholder="예: 이 로그의 통신 흐름과 이상 프레임을 설명해줘")

    if up is not None:
        raw = up.read()
        is_binary = up.name.lower().endswith(".dat")
        from rag.logs.detect import detect_log_type
        from rag.logs.workflow import analyze, find_spec_candidates, summarize_analysis, explain

        text = None if is_binary else raw.decode("utf-8", errors="replace")
        ltype = "hex(binary)" if is_binary else detect_log_type(text)
        st.info(f"감지된 로그 종류: **{ltype}**")

        try:
            analysis = analyze(raw if is_binary else text, is_binary=is_binary)
            st.markdown("#### 파싱 결과")
            st.code(summarize_analysis(analysis))
        except Exception as e:
            analysis = None
            st.warning(f"파싱 보류(명세 확정 후 재해석): {e}")

        # 명세 후보 검색 + 확인 단계 (필수)
        st.markdown("#### 프로토콜 명세 확인 (필수)")
        try:
            retriever, llm = get_retriever_llm()
            cands = find_spec_candidates(retriever, text or "", log_q, top_k=5)
        except Exception as e:
            cands, llm = [], None
            st.error(f"명세 후보 검색 실패: {e}")

        if cands:
            labels = [f"{c['metadata'].get('doc_title','?')} · "
                      f"{c['metadata'].get('page_no') or c['metadata'].get('section') or ''}"
                      for c in cands]
            picked = st.multiselect("이 로그에 해당하는 프로토콜 명세를 선택하세요",
                                    options=list(range(len(cands))),
                                    format_func=lambda i: labels[i], key="log_specs")
            with st.expander("후보 명세 원문"):
                for i, c in enumerate(cands):
                    st.markdown(f"**{labels[i]}**")
                    st.code(c["document"][:1500])
            if st.button("확정 명세로 해석", key="log_explain") and picked and analysis:
                chosen = [cands[i] for i in picked]
                try:
                    with st.spinner("LLM 해석 중…"):
                        out = explain(llm, log_q, analysis, chosen)
                    st.markdown("#### 해석")
                    st.write(out)
                except Exception as e:
                    st.error(f"해석 실패: {e}")
            elif not picked:
                st.caption("⚠️ 명세를 1개 이상 선택해야 해석할 수 있습니다(자동 추측 금지).")
        else:
            st.caption("명세 후보가 없습니다. 관리 탭에서 프로토콜 명세 문서를 먼저 인덱싱하세요.")


# ===========================================================================
# 관리 (인덱싱)
# ===========================================================================
with tab_admin:
    st.subheader("인덱스 관리")
    st.write(f"- 문서 폴더: `{CONFIG.data_dir}`")
    st.write(f"- 벡터 DB: `{CONFIG.chroma_dir}` · BM25: `{CONFIG.bm25_path}`")
    st.write(f"- 임베딩: `{CONFIG.embed_model}` ({CONFIG.embed_dim}d) · LLM: `{CONFIG.llm_model}`")

    col1, col2 = st.columns(2)
    if col1.button("증분 인덱싱", key="idx_inc"):
        try:
            from rag.index.indexer import Indexer
            with st.spinner("증분 인덱싱 중…"):
                stats = Indexer().reindex(full=False)
            st.success(f"완료: {stats}")
            get_pipeline.clear(); get_retriever_llm.clear()
        except Exception as e:
            st.error(f"인덱싱 실패: {e}")
    if col2.button("전체 재인덱싱", key="idx_full"):
        try:
            from rag.index.indexer import Indexer
            with st.spinner("전체 재인덱싱 중…"):
                stats = Indexer().reindex(full=True)
            st.success(f"완료: {stats}")
            get_pipeline.clear(); get_retriever_llm.clear()
        except Exception as e:
            st.error(f"인덱싱 실패: {e}")

    st.caption("먼저 문서를 data 폴더에 넣고 인덱싱하세요. 인덱싱 후 QA/로그 탭 사용 가능.")
