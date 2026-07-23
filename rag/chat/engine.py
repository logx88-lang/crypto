"""대화형(멀티턴) RAG 엔진 — 인덱스 문서를 근거로 대화. 히스토리 반영 + 자동 요약.

한 턴 처리:
  1) 검색 질의 = 직전 사용자 질문 + 현재 질문(대명사/후속 지시 보정) → 스코프 검색·리랭킹
  2) 생성 = 시스템 + (요약) + 최근 대화 + [문서 발췌] + 현재 질문
  3) 히스토리가 길면 오래된 턴을 요약으로 압축(작업기억 유지)
파이프라인(retriever/reranker/llm)은 기존 build_pipeline 재사용.
"""
from __future__ import annotations

import re

from .store import save_conversation
from ..generate.prompt import source_label, sources_list

CHAT_SYSTEM = (
    "/no_think\n"
    "당신은 사내 문서 기반 **대화형** 질의응답 도우미입니다. 규칙:\n"
    "1. **현재 질문에 답하는 것이 최우선**입니다. [문서 발췌]에 근거해 한국어 공식체(합니다체)로 답합니다.\n"
    "2. 후속 질문('해당', '그 기록', '위의 것' 등)만 **앞선 대화**를 참고해 해석합니다. 현재 질문이"
    " 새로운 주제면 앞선 대화·이전 답변에 얽매이지 말고 [문서 발췌]만으로 새로 답하며,"
    " 이전 답변 내용을 근거 없이 반복하지 않습니다.\n"
    "3. 각 주장 뒤에 근거 출처를 [번호]로 표기합니다(예: …입니다 [1]).\n"
    "4. 여러 항목·값을 나열할 때는 마크다운 표(| 열 | … |)로 정리합니다(화면에 표로 렌더됨).\n"
    "5. 답변에 도면·그림·화면 등 시각 자료를 보여주는 것이 도움이 되면, 그 위치에 [그림 번호] 를"
    " 단독 표기합니다(예: 배선은 다음과 같습니다. [그림 2]) — 해당 근거의 이미지가 그 자리에 표시됩니다.\n"
    "6. 발췌·대화에 근거가 없으면 지어내지 말고 '제공된 문서에서 근거를 찾지 못했습니다'라고 답합니다."
)


def _recent_user_turns(conv: dict, n: int = 1) -> str:
    us = [m["content"] for m in conv.get("messages", []) if m["role"] == "user"]
    return " ".join(us[-n:]) if us else ""


# 후속 질문 판별 — 지시어/연결어가 있거나 아주 짧아 맥락 없이는 뜻이 안 서는 질문.
# 새 주제 질문까지 이전 질문을 검색어에 섞으면 이전 주제 문서가 계속 검색되는 문제(매몰)를 막는다.
_FOLLOWUP_RE = re.compile(
    r"그럼|그러면|그것|그거|그건|그중|그 중|해당|위의|위 |앞의|앞서|방금|아까|이어서|추가로|"
    r"더 자세|자세히|마저|나머지|둘 다|각각|이 명령|그 명령|그 필드|그 값|이 값|왜(요|\?|야)")


def _is_followup(question: str) -> bool:
    q = (question or "").strip()
    if len(q) <= 12:                      # 짧은 질문("몇 바이트야?")은 맥락 의존일 가능성 큼
        return True
    return bool(_FOLLOWUP_RE.search(q))


def _retrieval_query(conv: dict, question: str) -> str:
    """검색용 질의 — **후속 질문일 때만** 직전 사용자 질문을 붙여 맥락을 살린다.

    새 주제 질문은 질문 단독으로 검색해 이전 주제 문서가 검색을 오염시키지 않게 한다."""
    if not _is_followup(question):
        return question
    prev = _recent_user_turns(conv, 1)
    return (prev + " " + question).strip() if prev else question


def _history_messages(conv: dict, keep: int = 6) -> list:
    out = []
    if conv.get("summary"):
        out.append({"role": "system", "content": "이전 대화 요약:\n" + conv["summary"]})
    for m in conv.get("messages", [])[-keep:]:
        if m["role"] in ("user", "assistant"):
            out.append({"role": m["role"], "content": m["content"]})
    return out


def _context_block(chunks: list) -> str:
    blocks = []
    for i, c in enumerate(chunks, start=1):
        label = source_label(c.get("metadata", {}))
        blocks.append(f"[{i}] ({label})\n{c.get('document', '').strip()}")
    return "\n\n".join(blocks) or "(관련 문서 없음)"


# 문서 요약/개요/전체내용 류 질의 — 의미검색 top-k로는 못 잡으므로 문서 내용을 폭넓게 모아 준다.
_OVERVIEW_RE = re.compile(
    r"요약|정리해|개요|요점|핵심\s*(내용|정리)|전체\s*내용|무슨\s*(내용|문서|자료)|"
    r"어떤\s*(내용|문서|자료)|무엇에\s*대한|대략|전반|summary|overview|abstract", re.I)


def _is_overview(question: str) -> bool:
    return bool(_OVERVIEW_RE.search(question or ""))


def _gather_scope_docs(pipeline, files: list, max_chars: int = 6000) -> list:
    """선택 파일들의 청크를 문서·순서대로 모아 예산 내에서 커버리지 컨텍스트 구성(요약용)."""
    try:
        got = pipeline.retriever.store._col.get(
            where={"rel_path": {"$in": list(files)}},
            include=["documents", "metadatas"])
        docs, metas = got.get("documents", []), got.get("metadatas", [])
    except Exception:
        return []
    order = sorted(range(len(docs)),
                   key=lambda i: (metas[i].get("rel_path", ""), str(metas[i].get("chunk_id", ""))))
    out, total = [], 0
    for i in order:
        d = docs[i] or ""
        if out and total + len(d) > max_chars:
            break
        out.append({"document": d, "metadata": metas[i]})
        total += len(d)
    return out


def maybe_summarize(llm, conv: dict, keep: int = 6, max_msgs: int = 14) -> None:
    """히스토리가 max_msgs 초과 시 오래된 턴을 요약으로 압축하고 최근 keep턴만 유지."""
    msgs = conv.get("messages", [])
    if len(msgs) <= max_msgs:
        return
    old = msgs[:-keep]
    convo = "\n".join(f"{m['role']}: {m['content']}" for m in old)
    prompt = [
        {"role": "system", "content": "/no_think\n다음 대화를 한국어로 간결히 요약하십시오. "
         "핵심 질문·답변·결정·언급된 문서/값 위주로 3~6문장. 새 정보 추가 금지."},
        {"role": "user", "content": ("[기존 요약]\n" + conv.get("summary", "") +
                                     "\n\n[추가 대화]\n" + convo).strip()},
    ]
    try:
        conv["summary"] = (llm.chat(prompt) or "").strip() or conv.get("summary", "")
        conv["messages"] = msgs[-keep:]
    except Exception:
        pass   # 요약 실패해도 대화는 계속


def answer(pipeline, conv: dict, question: str, scope_files=None,
           final_k: int = None) -> dict:
    """한 턴 답변 → {answer, sources, contexts}. conv 에 사용자/어시스턴트 메시지 추가·저장."""
    conv.setdefault("messages", [])
    if conv.get("log"):                       # 로그 첨부 대화 → 로그 분석 경로
        from .logchat import answer_with_log
        return answer_with_log(pipeline, conv, question)

    cfg = pipeline.cfg
    k = final_k or cfg.final_k
    where = {"rel_path": {"$in": list(scope_files)}} if scope_files else None

    # 요약/개요 류 질의 + 문서 선택 시: 의미검색(top-k) 대신 선택 문서 내용을 폭넓게 모아 종합.
    overview = scope_files and _is_overview(question)
    if overview:
        top = _gather_scope_docs(pipeline, scope_files)
        label = "선택 문서 내용"
    else:
        cands = pipeline.retriever.search(_retrieval_query(conv, question), where=where)
        top = pipeline.reranker.rerank(question, cands, final_k=k) if cands else []
        label = "문서 발췌"
    if overview and not top:                    # 수집 실패 시 일반 검색 폴백
        cands = pipeline.retriever.search(_retrieval_query(conv, question), where=where)
        top = pipeline.reranker.rerank(question, cands, final_k=k) if cands else []
        label = "문서 발췌"

    # 새 주제 질문이면 히스토리를 최소(2)로 줄여 이전 답변 앵커링(매몰)을 완화.
    messages = [{"role": "system", "content": CHAT_SYSTEM}]
    messages += _history_messages(conv, keep=6 if _is_followup(question) else 2)
    messages.append({"role": "user", "content":
                     f"[{label}]\n{_context_block(top)}\n\n[질문]\n{question}"})
    text = pipeline.llm.chat(messages)
    if not (text or "").strip() and len(top) > 1:      # 빈 답변 방어(컨텍스트 축소 재시도)
        messages[-1]["content"] = (
            f"[문서 발췌]\n{_context_block(top[:max(1, len(top)//2)])}\n\n[질문]\n{question}")
        text = pipeline.llm.chat(messages)

    srcs = sources_list(top)
    # 근거 원문 발췌 + 파일경로·위치를 메시지에 저장 → 턴별 펼쳐보기 + 원본 파일 미리보기.
    src_full = []
    for s, c in zip(srcs, top):
        m = c.get("metadata", {})
        src_full.append({
            "n": s["n"], "label": s["label"], "excerpt": c.get("document", "")[:1800],
            "rel_path": m.get("rel_path"),
            "loc": {k: m.get(k) for k in ("page_no", "sheet_name", "slide_no", "section")
                    if m.get(k)},
        })
    conv["messages"].append({"role": "user", "content": question})
    conv["messages"].append({"role": "assistant", "content": text, "sources": src_full})
    if conv.get("title", "새 대화") in ("새 대화", "") and len([m for m in conv["messages"]
                                                          if m["role"] == "user"]) == 1:
        conv["title"] = question[:30]      # 첫 질문을 대화 제목으로
    maybe_summarize(pipeline.llm, conv)
    save_conversation(conv)
    return {"answer": text, "sources": srcs, "contexts": top}
