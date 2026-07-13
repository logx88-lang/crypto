"""Streamlit UI — 문서 QA / 로그 분석 / 개선 기록(비식별 반출) / 관리 (design.md §1·§7·§11).

실행: streamlit run rag/app/main.py --server.address 0.0.0.0 --server.port 8501
Ollama(`ollama serve`)와 인덱스(관리 탭)가 필요하다.
"""
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import streamlit as st

from rag.config import CONFIG
from rag.feedback import FeedbackLog, sanitize_record


# --- 리소스 캐시 ----------------------------------------------------------
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


CATS = {
    "qa": ["표 추출 오류(표가 깨져 보임)", "표 희석(관련 표 누락/후순위)", "틀린 답변",
           "근거 못 찾음(문서엔 있음)", "출처 오류", "기타"],
    "log": ["명세 표 참조 부정확", "필드 오프셋/폭 해석 오류", "프레임 파싱 오류",
            "명세 후보 검색 실패", "틀린 해석", "기타"],
}


def _now():
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def feedback_form(kind: str, prefill: dict, key: str):
    """개선기록 캡처 폼 — 저장 전 비식별화 미리보기 제공."""
    with st.expander("🚩 개선 기록 (반출용으로 **자동 비식별화**되어 저장)"):
        cat = st.selectbox("유형", CATS[kind], key=f"{key}_cat")
        sev = st.radio("심각도", ["낮음", "중간", "높음"], index=1, horizontal=True,
                       key=f"{key}_sev")
        note = st.text_area("증상/메모 — 구조·증상 위주로. (저장 시 자동 비식별화됨)",
                            key=f"{key}_note")
        san_note = st.checkbox("메모도 비식별화(권장)", value=True, key=f"{key}_san")
        record = {"ts": _now(), "kind": kind, "category": cat, "severity": sev,
                  "question": prefill.get("question", ""),
                  "answer": prefill.get("answer", ""),
                  "note": note, "sanitize_note": san_note,
                  "contexts": prefill.get("contexts", [])}
        safe = sanitize_record(record)
        if st.checkbox("🔍 저장·반출될 비식별 내용 미리보기(실데이터 없음 확인)", key=f"{key}_pv"):
            st.json(safe)
        if st.button("개선 기록 저장", key=f"{key}_save"):
            FeedbackLog().add(safe, already_sanitized=True)
            st.success("비식별화되어 저장되었습니다. '개선 기록' 탭에서 반출하세요.")


st.set_page_config(page_title="사내 지식 RAG", layout="wide")
st.title("사내 지식 공유 · 통신로그 분석 플랫폼")

tab_qa, tab_log, tab_fb, tab_admin = st.tabs(
    ["📄 문서 QA", "🔌 로그 분석", "🚩 개선 기록", "⚙️ 관리"])


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
                st.session_state["qa_result"] = get_pipeline().answer(query.strip())
                st.session_state["qa_q"] = query.strip()
        except Exception as e:
            st.error(f"오류: {e}\nOllama(`ollama serve`)와 인덱스(관리 탭)를 확인하세요.")

    res = st.session_state.get("qa_result")
    if res:
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
        feedback_form("qa", {"question": st.session_state.get("qa_q", ""),
                             "answer": res["answer"], "contexts": res["contexts"]},
                      key="fb_qa")


# ===========================================================================
# 로그 분석
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
        from rag.logs.workflow import (analyze, find_spec_candidates,
                                        summarize_analysis, explain)

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

        st.markdown("#### 프로토콜 명세 확인 (필수)")
        try:
            retriever, llm = get_retriever_llm()
            cands = find_spec_candidates(retriever, text or "", log_q, top_k=5)
        except Exception as e:
            cands, llm = [], None
            st.error(f"명세 후보 검색 실패: {e}")

        chosen = []
        if cands:
            labels = [f"{c['metadata'].get('doc_title','?')} · "
                      f"{c['metadata'].get('page_no') or c['metadata'].get('section') or ''}"
                      for c in cands]
            picked = st.multiselect("이 로그에 해당하는 프로토콜 명세를 선택하세요",
                                    options=list(range(len(cands))),
                                    format_func=lambda i: labels[i], key="log_specs")
            chosen = [cands[i] for i in picked]
            with st.expander("후보 명세 원문"):
                for i, c in enumerate(cands):
                    st.markdown(f"**{labels[i]}**")
                    st.code(c["document"][:1500])
            if st.button("확정 명세로 해석", key="log_explain") and chosen and analysis:
                try:
                    with st.spinner("LLM 해석 중…"):
                        st.session_state["log_out"] = explain(llm, log_q, analysis, chosen)
                except Exception as e:
                    st.error(f"해석 실패: {e}")
            elif not picked:
                st.caption("⚠️ 명세를 1개 이상 선택해야 해석할 수 있습니다(자동 추측 금지).")
        else:
            st.caption("명세 후보가 없습니다. 관리 탭에서 프로토콜 명세 문서를 먼저 인덱싱하세요.")

        if st.session_state.get("log_out"):
            st.markdown("#### 해석")
            st.write(st.session_state["log_out"])

        feedback_form("log", {"question": log_q or "(로그 분석)",
                              "answer": st.session_state.get("log_out", ""),
                              "contexts": chosen}, key="fb_log")


# ===========================================================================
# 개선 기록 (비식별 반출)
# ===========================================================================
with tab_fb:
    st.subheader("개선 기록 — 비식별화 반출")
    st.caption("폐쇄망 밖에서 개선을 진행할 수 있도록, 실제 프로토콜 값·명칭은 가명으로 치환되고 "
               "표는 형태(행×열)만 남깁니다. 아래 내용이 그대로 반출됩니다.")
    log = FeedbackLog()
    records = log.load_all()
    st.write(f"기록 건수: **{len(records)}**")
    if records:
        for i, r in enumerate(reversed(records[-30:]), 1):
            st.markdown(f"**{r.get('category','')}** · {r.get('severity','')} · "
                        f"[{r.get('kind')}] · {r.get('ts','')}")
            if r.get("question"):
                st.caption(f"질문(비식별): {r['question'][:160]}")
            if r.get("note"):
                st.caption(f"메모(비식별): {r['note'][:160]}")
            for c in r.get("contexts", []):
                s = c.get("table_shape")
                if s and s.get("is_table"):
                    st.caption(f"  · 표 {s['rows']}행×{s['cols']}열")
        if st.button("📤 Markdown 내보내기(USB 반출용)"):
            path = log.export_markdown()
            st.success(f"내보냄: `{path}` — 이 파일만 반출하세요(실데이터 없음).")
            with open(path, encoding="utf-8") as f:
                st.download_button("파일 다운로드", f.read(),
                                   file_name="feedback_export.md")
    else:
        st.info("아직 기록이 없습니다. QA/로그 탭 결과 아래 '🚩 개선 기록'에서 남기세요.")


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
