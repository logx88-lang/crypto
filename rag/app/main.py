"""Streamlit UI — 문서 QA / 로그 분석 / 개선 기록(비식별 반출) / 관리 (design.md §1·§7·§11).

실행: streamlit run rag/app/main.py --server.address 0.0.0.0 --server.port 8501
Ollama(`ollama serve`)와 인덱스(관리 탭)가 필요하다.
"""
import faulthandler
import os
import sys
from datetime import datetime, timezone

faulthandler.enable()   # 네이티브 크래시(SIGSEGV/SIGABRT 등) 시 stderr에 스택 덤프

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


def _folder_set(files):
    """파일 rel_path 목록 → 등장하는 모든 (중첩) 폴더 경로 집합."""
    folders = set()
    for f in files:
        parts = f.split("/")
        for i in range(1, len(parts)):
            folders.add("/".join(parts[:i]))
    return folders


def _tree_rows(files):
    """(폴더+파일)을 트리 순서로 정렬한 행 리스트 → (depth, path, is_folder, name)."""
    nodes = [(p, True) for p in _folder_set(files)] + [(f, False) for f in files]
    # 전체 경로 세그먼트 기준 정렬 → 폴더가 자식보다 앞서는 깊이우선(depth-first) 순서
    nodes.sort(key=lambda x: x[0].split("/"))
    return [(p.count("/"), p, is_dir, p.split("/")[-1]) for p, is_dir in nodes]


def _tree_scope(label, key):
    """접이식 + 상·하위 동기화 체크박스 트리 → 선택된 파일(rel_path) 목록.

    폴더 체크=하위 전체 체크(down), 하위 전체 체크 시 상위 자동 체크(up). 기본 접힘(▶).
    미선택 시 None(=전체)."""
    from rag.index.indexer import list_documents
    files = list_documents()
    if not files:
        st.caption("인덱싱된 문서가 없습니다. 관리 탭에서 먼저 인덱싱하세요.")
        return None

    rows = _tree_rows(files)
    folders = [p for _, p, is_dir, _ in rows if is_dir]
    children = {f: [] for f in folders}          # 직속 자식(폴더+파일)
    for _, pth, _, _ in rows:
        parent = "/".join(pth.split("/")[:-1])
        if parent in children:
            children[parent].append(pth)

    def _ck(pth):
        return f"{key}::{pth}"

    def _descendants(f):
        out = []
        for c in children.get(f, []):
            out.append(c); out += _descendants(c)
        return out

    def _on_toggle(pth):
        v = st.session_state.get(_ck(pth), False)
        if pth in children:                       # 폴더 → 하위 전체 동기화(down)
            for d in _descendants(pth):
                st.session_state[_ck(d)] = v
        cur = pth                                 # 상위 재조정(up): 직속 자식 모두 체크면 체크
        while "/" in cur:
            par = "/".join(cur.split("/")[:-1])
            if par not in children:
                break
            st.session_state[_ck(par)] = all(
                st.session_state.get(_ck(c), False) for c in children[par])
            cur = par

    open_key = f"{key}__open"
    open_set = st.session_state.setdefault(open_key, set())
    with st.expander(label):
        st.caption("▶ 펼치기 · 상·하위 체크 동기화(하위 전체 체크 시 상위 체크) · 미선택=전체")
        for depth, path, is_dir, name in rows:
            anc = path.split("/")[:-1]
            if not all("/".join(anc[:i + 1]) in open_set for i in range(len(anc))):
                continue
            indent = " " * depth
            c1, c2 = st.columns([1, 18])
            if is_dir:
                if c1.button("▼" if path in open_set else "▶", key=f"{key}_tg_{path}"):
                    open_set.symmetric_difference_update({path}); st.rerun()
                c2.checkbox(f"{indent}📁 {name}", key=_ck(path),
                            on_change=_on_toggle, args=(path,))
            else:
                c1.write("")
                c2.checkbox(f"{indent}📄 {name}", key=_ck(path),
                            on_change=_on_toggle, args=(path,))

    chosen = sorted(f for f in files if st.session_state.get(_ck(f)))
    if chosen:
        st.caption(f"선택: {len(chosen)}개 파일")
    return chosen or None


st.set_page_config(page_title="사내 지식 RAG", layout="wide")

from rag import chat as chatmod

# --- 로그인 게이트(이름별 대화 분리용 간이 로그인) ---
if not st.session_state.get("user"):
    st.title("사내 지식 공유 · 통신로그 분석 플랫폼")
    st.subheader("로그인")
    st.caption("사내 전용 간이 로그인 — 이름별로 대화를 분리합니다(처음 쓰는 이름은 자동 등록).")
    with st.form("login"):
        _u = st.text_input("사용자 이름")
        _pw = st.text_input("비밀번호", type="password")
        if st.form_submit_button("로그인 / 등록"):
            _ok, _msg = chatmod.login_or_register(_u, _pw)
            if _ok:
                st.session_state["user"] = _u.strip()
                st.rerun()
            else:
                st.error(_msg)
    st.stop()

USER = st.session_state["user"]
if "conv" not in st.session_state:
    _cvs = chatmod.list_conversations(USER)
    st.session_state["conv"] = (chatmod.load_conversation(USER, _cvs[0]["id"])
                                if _cvs else chatmod.new_conversation(USER))

# --- 사이드바: 대화 관리(여러 대화창 전환/삭제/새로) ---
with st.sidebar:
    st.markdown(f"**👤 {USER}**")
    if st.button("로그아웃", use_container_width=True):
        st.session_state.pop("user", None); st.session_state.pop("conv", None)
        st.rerun()
    st.divider()
    if st.button("➕ 새 대화", use_container_width=True):
        st.session_state["conv"] = chatmod.new_conversation(USER); st.rerun()
    st.caption("대화 목록")
    for _cv in chatmod.list_conversations(USER):
        _cur = _cv["id"] == st.session_state["conv"]["id"]
        if st.button(("● " if _cur else "") + (_cv["title"] or "대화")[:24],
                     key=f"cv_{_cv['id']}", use_container_width=True):
            st.session_state["conv"] = chatmod.load_conversation(USER, _cv["id"]); st.rerun()
    st.divider()
    if st.button("🗑 현재 대화 삭제", use_container_width=True):
        chatmod.delete_conversation(USER, st.session_state["conv"]["id"])
        st.session_state.pop("conv", None); st.rerun()

st.title("사내 지식 공유 · 통신로그 분석 플랫폼")


@st.dialog("📄 원본 미리보기", width="large")
def _open_preview(rel_path, loc, excerpt):
    from rag.app.preview import render_file
    render_file(rel_path, loc)
    if excerpt:
        with st.expander("이 답변이 참고한 근거 발췌(청크)"):
            st.code(excerpt)


tab_qa, tab_log, tab_fb, tab_admin = st.tabs(
    ["💬 대화", "🔌 로그 분석", "🚩 개선 기록", "⚙️ 관리"])


# ===========================================================================
# 문서 QA
# ===========================================================================
with tab_qa:
    conv = st.session_state["conv"]
    st.subheader(f"💬 대화형 문서 QA — {conv.get('title', '새 대화')}")
    st.caption("후속 질문이 가능합니다(예: '그 명령의 데이터 필드는?'). 대화 전환·초기화는 왼쪽 사이드바.")
    scope = _tree_scope("📂 문서 범위 (폴더/파일 체크 · 미선택=전체)", "chat_scope")

    # 🔌 로그 첨부(선택) — 붙이면 이 대화가 로그 분석 모드로 동작
    with st.expander("🔌 로그 첨부 (통신 로그를 대화로 분석)", expanded=bool(conv.get("log"))):
        if conv.get("log"):
            _lg = conv["log"]
            st.success(f"첨부됨: **{_lg.get('name')}** · 프레임 {_lg['parsed'].get('total', 0)}개 · "
                       f"명세 {[os.path.basename(str(f)) for f in _lg['files']]}")
            st.caption("아래 대화창에서 질문하세요. 예) '카드 충전 요청 기록 찾아줘' → "
                       "'그 중 카드번호 1010… 기록' → '해당 앞뒤 10초 전문 필드로 파싱해줘'")
            if st.button("로그 분리(문서 QA로 전환)"):
                conv.pop("log", None); chatmod.save_conversation(conv); st.rerun()
        else:
            _uplog = st.file_uploader("로그 파일 (.txt/.log/.dat)", type=["txt", "log", "dat"],
                                      key="chat_logup")
            if _uplog is not None:
                _ltext = _uplog.read().decode("utf-8", errors="replace")
                try:
                    _pipe = get_pipeline()
                    from rag.logs.workflow import spec_files, find_spec_candidates
                    _cands = find_spec_candidates(_pipe.retriever, _ltext, "", top_k=15)
                    _fopts = spec_files(_cands)
                    _sel = st.multiselect("이 로그의 프로토콜 명세 파일", _fopts,
                                          format_func=lambda f: os.path.basename(str(f)),
                                          key="chat_logfiles")
                    if st.button("로그 첨부·파싱") and _sel:
                        from rag.chat import logchat
                        with st.spinner("명세에서 규격 도출 → 로그 파싱 중…"):
                            logchat.attach_log(conv, _ltext, _sel, _pipe.retriever,
                                               _pipe.llm, name=_uplog.name)
                        st.rerun()
                except Exception as e:
                    st.error(f"로그 준비 실패: {e}")

    if conv.get("summary"):
        with st.expander("🧠 이전 대화 요약(자동 압축)"):
            st.caption(conv["summary"])

    def _render_excerpt(txt):
        # 표(마크다운) 청크는 st.markdown 으로 렌더해 가독성↑(이슈4), 그 외는 코드블록
        if txt.count("|") >= 6 and "---" in txt:
            st.markdown(txt)
        else:
            st.code(txt)

    def _render_sources(srcs, key):
        if not srcs:
            return
        st.caption("출처: " + " · ".join(s["label"] for s in srcs))
        with st.expander("근거 원문 보기"):     # 턴별 개별 expander → 다음 질문해도 유지(이슈3)
            for s in srcs:
                _c1, _c2 = st.columns([5, 1])
                _c1.markdown(f"**[{s['n']}]** {s['label']}")
                if s.get("rel_path") and _c2.button("📄 원본", key=f"{key}_pv_{s['n']}"):
                    _open_preview(s["rel_path"], s.get("loc"), s.get("excerpt", ""))
                _render_excerpt(s.get("excerpt", ""))

    # 히스토리 표시(턴별 근거 원문 포함)
    for _i, m in enumerate(conv.get("messages", [])):
        with st.chat_message("user" if m["role"] == "user" else "assistant"):
            st.write(m["content"])
            _render_sources(m.get("sources"), key=f"src_{_i}")

    # 입력 → 생성 → rerun(입력창 재생성·히스토리 갱신: 이슈2)
    if _q := st.chat_input("질문을 입력하세요 (후속 질문 가능)"):
        try:
            with st.spinner("검색·리랭킹·생성 중…"):
                chatmod.answer(get_pipeline(), conv, _q, scope_files=scope)
        except Exception as e:
            st.session_state["chat_err"] = str(e)
        st.rerun()
    _err = st.session_state.pop("chat_err", None)
    if _err:
        st.error(f"오류: {_err}\nOllama(`ollama serve`)와 인덱스(관리 탭)를 확인하세요.")


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
                          placeholder="예: LSAM 정보 요청 커맨드가 발생한 시각을 알려줘")

    if up is not None:
        raw = up.read()
        is_binary = up.name.lower().endswith(".dat")
        from rag.logs.detect import detect_log_type
        from rag.logs.workflow import (find_spec_candidates,
                                        summarize_analysis, explain)

        text = None if is_binary else raw.decode("utf-8", errors="replace")
        ltype = "hex(binary)" if is_binary else detect_log_type(text)
        st.info(f"감지된 로그 종류: **{ltype}**")

        # 원문 미리보기만 표시(파싱은 명세 확정 후 1회만).
        with st.expander("📄 로그 미리보기 (원문 앞부분)"):
            _prev = (text or "").splitlines()[:20]
            st.code("\n".join(_prev) if _prev else "(바이너리 로그 — 미리보기 생략)")

        # --- 프로토콜 명세 '파일' 선택 (이슈4: 청크 아닌 파일 단위) ---
        st.markdown("#### 프로토콜 명세 선택 (필수)")
        st.caption("이 로그에 해당하는 프로토콜 **문서(파일)**를 고르세요. 선택 문서에서 프레임 규격·필드표를 찾아 파싱·해석합니다.")
        from rag.logs.workflow import (spec_files, gather_file_chunks,
                                       resolve_command_names, _observed_cmd_keys)
        try:
            retriever, llm = get_retriever_llm()
            cands = find_spec_candidates(retriever, text or "", log_q, top_k=15)
        except Exception as e:
            cands, llm = [], None
            st.error(f"명세 후보 검색 실패: {e}")

        files_opt = spec_files(cands)
        if files_opt:
            chosen_files = st.multiselect(
                "프로토콜 명세 파일", options=files_opt,
                format_func=lambda f: os.path.basename(str(f)), key="log_spec_files")
            if st.button("확정 명세로 파싱·해석", key="log_explain") and chosen_files and text is not None:
                try:
                    with st.spinner("명세에서 프레임 규격 도출 → 파싱 → 필드 해석 중…"):
                        from rag.logs.generic import analyze_by_spec
                        # 1) 프레임 구조 청크로 파싱
                        derive_chunks = gather_file_chunks(
                            retriever, chosen_files,
                            "전문 포맷 프레임 구조 packet format Command Length Data 체크섬 요청전문 응답전문",
                            top_k=10)
                        spec_text = "\n\n".join(c.get("document", "") for c in derive_chunks)
                        parsed = analyze_by_spec(text, spec_text, llm)
                        st.session_state["log_profile"] = (
                            parsed.get("profile") if parsed.get("derived") else None)
                        # 2) 관측 명령 기반 필드표·해석 청크 수집(선택 파일 범위)
                        obs = " ".join(("0x" + k[2:] if k.startswith("0X") else k)
                                       for k in sorted(_observed_cmd_keys(parsed)))
                        explain_chunks = gather_file_chunks(
                            retriever, chosen_files,
                            f"{log_q} {obs} 요청전문 응답전문 전문 포맷 필드 TYPE LEN 비고 DATA",
                            top_k=16)
                        _where = {"source_file": {"$in": chosen_files}}
                        _names = resolve_command_names(retriever, parsed, where=_where)
                        st.session_state["log_cmd_names"] = _names
                        st.session_state["log_parsed"] = parsed
                        st.session_state["log_chosen"] = explain_chunks
                        st.session_state["log_out"] = explain(
                            llm, log_q, parsed, explain_chunks, cmd_names=_names)
                except Exception as e:
                    st.error(f"해석 실패: {e}")
            elif not chosen_files:
                st.caption("⚠️ 명세 파일을 1개 이상 선택해야 해석할 수 있습니다(자동 추측 금지).")
        else:
            st.caption("명세 후보가 없습니다. 관리 탭에서 프로토콜 명세 문서를 먼저 인덱싱하세요.")

        # --- 결과: 파싱 결과 1개 + 규격 + 해석 ---
        prof = st.session_state.get("log_profile")
        parsed = st.session_state.get("log_parsed")
        if parsed:
            _cmd_names = st.session_state.get("log_cmd_names") or {}
            st.markdown("#### 파싱 결과")
            st.code(summarize_analysis(parsed, cmd_names=_cmd_names))
        if prof:
            with st.expander("📐 명세에서 도출한 파싱 규격 (자동)"):
                st.json(prof)
        if st.session_state.get("log_out"):
            st.markdown("#### 해석")
            st.write(st.session_state["log_out"])

        feedback_form("log", {"question": log_q or "(로그 분석)",
                              "answer": st.session_state.get("log_out", ""),
                              "contexts": st.session_state.get("log_chosen", [])},
                      key="fb_log")


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
                    try:
                        st.image(_imgp, width=320)
                    except Exception:
                        st.caption(f"🖼️ 첨부 이미지: {r['image']} (표시 불가 — 파일 손상/미지원)")
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
        failed = stats.pop("failed", [])
        st.success(f"인덱싱 완료: {stats}")
        if failed:                     # .doc 변환 실패 등 — 왜 안 됐는지 노출
            st.error(f"⚠️ {len(failed)}개 파일 실패:")
            for f in failed:
                st.caption(f"• {f['file']} — {f['error']}")
        get_pipeline.clear(); get_retriever_llm.clear()

    # --- 문서 업로드 → 저장 + 인덱싱 ---
    from rag.index.indexer import list_documents
    st.markdown("#### 문서 업로드")
    st.caption(f"지원: {', '.join(_EXTS)}  (.doc 는 서버 Word/LibreOffice 필요)")

    # 기존 폴더에 추가하거나 새 폴더를 만들어 업로드 대상 선택(구조는 아래 드롭다운에서 확인)
    _all_files = list_documents()
    _folders = sorted(_folder_set(_all_files))
    _ROOT, _NEW = "\x00root", "\x00new"
    _opts = [_ROOT] + _folders + [_NEW]

    def _flabel(o):
        if o == _ROOT:
            return "📂 (루트 = 미분류)"
        if o == _NEW:
            return "➕ 새 폴더 만들기…"
        return " " * o.count("/") + "📁 " + o.split("/")[-1]

    _sel = st.selectbox("업로드 대상 폴더 (기존 선택 또는 새로 만들기)", _opts,
                        format_func=_flabel, key="up_folder_sel")
    if _sel == _NEW:
        target_folder = st.text_input("새 폴더 경로 (하위폴더는 / 로 구분)", key="up_folder_new",
                                       placeholder="예: 발매  또는  발매/2024").strip()
    elif _sel == _ROOT:
        target_folder = ""
    else:
        target_folder = _sel

    ups = st.file_uploader("사내 문서 업로드 (여러 개 선택 가능)", type=_EXTS,
                           accept_multiple_files=True, key="doc_up")
    if st.button("⬆️ 업로드 저장 + 인덱싱", key="up_index"):
        if not ups:
            st.warning("먼저 파일을 선택하세요.")
        else:
            try:
                # 중첩 경로 허용 + 경로 이탈(..) 방지
                parts = [p for p in target_folder.replace("\\", "/").split("/")
                         if p and p not in (".", "..")]
                dest = os.path.join(CONFIG.data_dir, *parts) if parts else CONFIG.data_dir
                os.makedirs(dest, exist_ok=True)
                saved = []
                for f in ups:
                    with open(os.path.join(dest, f.name), "wb") as out:
                        out.write(f.getbuffer())
                    saved.append(f.name)
                st.info(f"저장 위치: **{'/'.join(parts) or '(루트)'}** · {len(saved)}개: "
                        f"{', '.join(saved[:20])}")
                _run_index(full=False)
            except Exception as e:
                st.error(f"실패: {e}")

    # --- 현재 인덱싱 대상 문서 ---
    st.markdown("#### 현재 문서")
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
