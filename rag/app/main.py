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
from rag.feedback import FeedbackLog, sanitize_record, readable_record


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
    with st.expander("🚩 개선 기록"):
        cat = st.selectbox("유형", CATS[kind], key=f"{key}_cat")
        sev = st.radio("심각도", ["낮음", "중간", "높음"], index=1, horizontal=True,
                       key=f"{key}_sev")
        note = st.text_area("증상/메모 — 무엇이 잘못됐는지 구체적으로 적어주세요.",
                            key=f"{key}_note")

        # 이미지 첨부: 클립보드 붙여넣기(컴포넌트 있으면) 또는 파일 업로드
        img_key = f"{key}_imgbytes"
        try:
            from streamlit_paste_button import paste_image_button as _paste
            pasted = _paste("📋 클립보드 이미지 붙여넣기", key=f"{key}_paste")
            if pasted is not None and getattr(pasted, "image_data", None) is not None:
                import io
                _buf = io.BytesIO(); pasted.image_data.save(_buf, format="PNG")
                st.session_state[img_key] = _buf.getvalue()
        except Exception:
            st.caption("클립보드 붙여넣기 미지원 — 아래 파일 업로드를 이용하세요.")
        up_img = st.file_uploader("또는 이미지 파일 첨부", type=["png", "jpg", "jpeg", "bmp"],
                                  key=f"{key}_img")
        if up_img is not None:
            st.session_state[img_key] = up_img.getvalue()
        img_bytes = st.session_state.get(img_key)
        if img_bytes:
            st.image(img_bytes, width=280, caption="첨부 이미지")
            if st.button("이미지 제거", key=f"{key}_imgclr"):
                st.session_state.pop(img_key, None); img_bytes = None

        redact = st.checkbox("🔒 비식별화(외부 반출 시 민감하면 체크)", value=False,
                             key=f"{key}_redact")
        record = {"ts": _now(), "kind": kind, "category": cat, "severity": sev,
                  "question": prefill.get("question", ""),
                  "answer": prefill.get("answer", ""),
                  "note": note, "contexts": prefill.get("contexts", [])}
        rec = sanitize_record(record) if redact else readable_record(record)
        if st.checkbox("🔍 저장될 내용 미리보기", key=f"{key}_pv"):
            st.json(rec)
        if st.button("개선 기록 저장", key=f"{key}_save"):
            FeedbackLog().add(rec, already_sanitized=True, image_bytes=img_bytes)
            st.session_state.pop(img_key, None)
            st.success(("비식별화되어 " if redact else "") + "저장되었습니다. '개선 기록' 탭에서 반출하세요.")


def _scope_files(label, key):
    """폴더/파일 통합 멀티셀렉트 → 선택된 파일(rel_path) 목록. 폴더 선택=하위 전체."""
    from rag.index.indexer import list_documents
    files = list_documents()
    folders = set()
    for f in files:
        parts = f.split("/")
        for i in range(1, len(parts)):
            folders.add("/".join(parts[:i]) + "/")
    sel = st.multiselect(label, sorted(folders) + files, key=key)
    chosen = set()
    for s in sel:
        if s.endswith("/"):
            chosen.update(f for f in files if f.startswith(s))
        else:
            chosen.add(s)
    return sorted(chosen) or None


st.set_page_config(page_title="사내 지식 RAG", layout="wide")
st.title("사내 지식 공유 · 통신로그 분석 플랫폼")

tab_qa, tab_log, tab_fb, tab_admin = st.tabs(
    ["📄 문서 QA", "🔌 로그 분석", "🚩 개선 기록", "⚙️ 관리"])


# ===========================================================================
# 문서 QA
# ===========================================================================
with tab_qa:
    st.subheader("문서 질의응답")
    qa_files = _scope_files("범위 (폴더/파일 체크, 미선택=전체)", "qa_scope")
    query = st.text_input("질문", key="qa_query",
                          placeholder="예: XM-200 코인 투입 명령 코드는?")
    if st.button("검색", key="qa_btn") and query.strip():
        try:
            with st.spinner("검색·리랭킹·생성 중…"):
                _w = {"rel_path": {"$in": qa_files}} if qa_files else None
                st.session_state["qa_result"] = get_pipeline().answer(query.strip(), where=_w)
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
    st.caption("HEX/자연어 로그 업로드 → 프로토콜 명세 선택 → **선택 문서에서 프레임 규격을 자동 도출**해 "
               "파싱 → 해석. 모듈마다 형식이 달라도 해당 명세만 있으면 됩니다(하드코딩 없음).")
    up = st.file_uploader("로그 파일 (.txt/.dat/.log)", type=["txt", "dat", "log"],
                          key="log_up")
    log_q = st.text_input("질문(선택)", key="log_q",
                          placeholder="예: 이 로그의 통신 흐름과 이상 프레임을 설명해줘")
    log_files = _scope_files("범위 (폴더/파일 체크, 미선택=전체)", "log_scope")

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
            cands = find_spec_candidates(retriever, text or "", log_q, top_k=5,
                                         files=log_files)
        except Exception as e:
            cands, llm = [], None
            st.error(f"명세 후보 검색 실패: {e}")

        chosen = []
        if cands:
            def _clabel(i):
                m = cands[i]["metadata"]
                fn = os.path.basename(str(m.get("source_file") or m.get("doc_title") or "문서"))
                sec = m.get("section") or m.get("page_no") or ""
                snip = (cands[i].get("document", "")[:35].replace("\n", " ")).strip()
                return f"[{i+1}] {fn} · {sec} · {snip}…"
            picked = st.multiselect("이 로그에 해당하는 프로토콜 명세를 선택하세요 (파일명·섹션으로 구분)",
                                    options=list(range(len(cands))),
                                    format_func=_clabel, key="log_specs")
            chosen = [cands[i] for i in picked]
            with st.expander("후보 명세 원문 (파일명·섹션·내용)"):
                for i, c in enumerate(cands):
                    m = c["metadata"]
                    fn = os.path.basename(str(m.get("source_file") or "문서"))
                    st.markdown(f"**[{i+1}] {fn}** · {m.get('section','')}")
                    st.code(c["document"][:1500])
            if st.button("확정 명세로 파싱·해석", key="log_explain") and chosen:
                try:
                    with st.spinner("명세에서 프레임 구조 도출 → 파싱 → 해석 중…"):
                        use = analysis
                        if text is not None:      # 텍스트 로그: 선택 문서 기반 파싱
                            from rag.logs.generic import analyze_by_spec
                            spec_text = "\n\n".join(c.get("document", "") for c in chosen)
                            parsed = analyze_by_spec(text, spec_text, llm)
                            if parsed.get("derived"):
                                use = parsed
                                st.session_state["log_profile"] = parsed.get("profile")
                        st.session_state["log_parsed"] = use
                        st.session_state["log_out"] = explain(llm, log_q, use, chosen)
                except Exception as e:
                    st.error(f"해석 실패: {e}")
            elif not picked:
                st.caption("⚠️ 명세를 1개 이상 선택해야 해석할 수 있습니다(자동 추측 금지).")
        else:
            st.caption("명세 후보가 없습니다. 관리 탭에서 프로토콜 명세 문서를 먼저 인덱싱하세요.")

        prof = st.session_state.get("log_profile")
        parsed = st.session_state.get("log_parsed")
        if prof:
            with st.expander("📐 명세에서 도출한 파싱 규격 (자동)"):
                st.json(prof)
        if parsed and parsed is not analysis:
            st.markdown("#### 명세 기반 파싱 결과")
            st.code(summarize_analysis(parsed))
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
    st.caption("QA/로그 결과 아래 '🚩 개선 기록'에서 남긴 내용입니다. 기본은 원문 저장이며, "
               "저장 시 '🔒 비식별화'를 체크하면 값·명칭이 가명으로 치환됩니다. 반출 전 내용을 확인하세요.")
    log = FeedbackLog()
    records = log.load_all()
    st.write(f"기록 건수: **{len(records)}**")
    if records:
        for i, r in enumerate(reversed(records[-30:]), 1):
            st.markdown(f"**{r.get('category','')}** · {r.get('severity','')} · "
                        f"[{r.get('kind')}] · {r.get('ts','')}")
            if r.get("question"):
                st.caption(f"질문: {r['question'][:160]}")
            if r.get("note"):
                st.caption(f"메모: {r['note'][:160]}")
            cs = r.get("context_summary")
            if cs:
                st.caption(f"검색 근거: 총 {cs.get('n',0)}개 (표 {cs.get('table',0)} / 텍스트 {cs.get('text',0)})")
            if r.get("image"):
                _imgp = os.path.join(CONFIG.feedback_dir, r["image"])
                if os.path.exists(_imgp):
                    st.image(_imgp, width=320)
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
    from rag.ingest import SUPPORTED_EXTS
    _EXTS = ["xlsx", "docx", "doc", "pptx", "pdf", "txt", "png", "jpg", "jpeg", "bmp", "tiff", "tif"]

    def _run_index(full: bool):
        from rag.index.indexer import Indexer
        with st.spinner("전체 재인덱싱 중…" if full else "인덱싱 중…"):
            stats = Indexer().reindex(full=full)
        st.success(f"인덱싱 완료: {stats}")
        get_pipeline.clear(); get_retriever_llm.clear()

    # --- 문서 업로드 → 저장 + 인덱싱 ---
    st.markdown("#### 문서 업로드")
    st.caption(f"지원: {', '.join(_EXTS)}  (.doc 는 서버 Word/LibreOffice 필요)")
    up_folder = st.text_input("업로드 폴더(분류, 비우면 미분류)", key="up_folder",
                              placeholder="예: 발매 / 정산 / 충전")
    ups = st.file_uploader("사내 문서 업로드 (여러 개 선택 가능)", type=_EXTS,
                           accept_multiple_files=True, key="doc_up")
    if st.button("⬆️ 업로드 저장 + 인덱싱", key="up_index"):
        if not ups:
            st.warning("먼저 파일을 선택하세요.")
        else:
            try:
                dest = os.path.join(CONFIG.data_dir, os.path.basename(up_folder.strip())) \
                    if up_folder.strip() else CONFIG.data_dir
                os.makedirs(dest, exist_ok=True)
                saved = []
                for f in ups:
                    with open(os.path.join(dest, f.name), "wb") as out:
                        out.write(f.getbuffer())
                    saved.append(f.name)
                st.info(f"저장 {len(saved)}개: {', '.join(saved[:20])}")
                _run_index(full=False)
            except Exception as e:
                st.error(f"실패: {e}")

    # --- 현재 인덱싱 대상 문서 ---
    st.markdown("#### 현재 문서")
    from rag.index.indexer import list_documents
    docs = list_documents()
    st.write(f"인덱싱 대상 문서 **{len(docs)}개**")
    if docs:
        with st.expander("문서 목록 보기"):
            st.write("\n".join(f"- {d}" for d in sorted(docs)))

    # --- 재인덱싱 / 관리 ---
    st.markdown("#### 재인덱싱")
    col1, col2 = st.columns(2)
    if col1.button("증분 인덱싱(변경분만)", key="idx_inc"):
        try:
            _run_index(full=False)
        except Exception as e:
            st.error(f"인덱싱 실패: {e}")
    if col2.button("전체 재인덱싱", key="idx_full"):
        try:
            _run_index(full=True)
        except Exception as e:
            st.error(f"인덱싱 실패: {e}")

    with st.expander("경로/모델 정보"):
        st.write(f"- 문서 폴더: `{CONFIG.data_dir}` · 벡터DB `{CONFIG.chroma_dir}` · BM25 `{CONFIG.bm25_path}`")
        st.write(f"- 임베딩 `{CONFIG.embed_model}` ({CONFIG.embed_dim}d) · LLM `{CONFIG.llm_model}`")
    st.caption("업로드하면 서버 data 폴더에 저장되고 바로 인덱싱됩니다. 인덱싱 후 QA/로그 탭에서 사용.")
