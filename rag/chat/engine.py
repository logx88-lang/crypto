"""대화형(멀티턴) RAG 엔진 — 인덱스 문서를 근거로 대화. 히스토리 반영 + 자동 요약.

한 턴 처리:
  1) 검색 질의 = 직전 사용자 질문 + 현재 질문(대명사/후속 지시 보정) → 스코프 검색·리랭킹
  2) 생성 = 시스템 + (요약) + 최근 대화 + [문서 발췌] + 현재 질문
  3) 히스토리가 길면 오래된 턴을 요약으로 압축(작업기억 유지)
파이프라인(retriever/reranker/llm)은 기존 build_pipeline 재사용.
"""
from __future__ import annotations

from .store import save_conversation
from ..generate.prompt import source_label, sources_list

CHAT_SYSTEM = (
    "/no_think\n"
    "당신은 사내 문서 기반 **대화형** 질의응답 도우미입니다. 규칙:\n"
    "1. [문서 발췌]와 앞선 대화 맥락에 근거해 한국어 공식체(합니다체)로 답합니다.\n"
    "2. 후속 질문('해당', '그 기록', '위의 것' 등)은 **앞선 대화**를 참고해 해석합니다.\n"
    "3. 각 주장 뒤에 근거 출처를 [번호]로 표기합니다(예: …입니다 [1]).\n"
    "4. 발췌·대화에 근거가 없으면 지어내지 말고 '제공된 문서에서 근거를 찾지 못했습니다'라고 답합니다."
)


def _recent_user_turns(conv: dict, n: int = 1) -> str:
    us = [m["content"] for m in conv.get("messages", []) if m["role"] == "user"]
    return " ".join(us[-n:]) if us else ""


def _retrieval_query(conv: dict, question: str) -> str:
    """검색용 질의 — 직전 사용자 질문을 앞에 붙여 후속 질문의 맥락을 살린다."""
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
    cfg = pipeline.cfg
    k = final_k or cfg.final_k
    where = {"rel_path": {"$in": list(scope_files)}} if scope_files else None
    conv.setdefault("messages", [])

    # 검색·생성은 '직전까지의' 히스토리 기준(현재 질문은 아직 추가 안 함 → 중복 방지)
    cands = pipeline.retriever.search(_retrieval_query(conv, question), where=where)
    top = pipeline.reranker.rerank(question, cands, final_k=k) if cands else []

    messages = [{"role": "system", "content": CHAT_SYSTEM}]
    messages += _history_messages(conv)
    messages.append({"role": "user", "content":
                     f"[문서 발췌]\n{_context_block(top)}\n\n[질문]\n{question}"})
    text = pipeline.llm.chat(messages)
    if not (text or "").strip() and len(top) > 1:      # 빈 답변 방어(컨텍스트 축소 재시도)
        messages[-1]["content"] = (
            f"[문서 발췌]\n{_context_block(top[:max(1, len(top)//2)])}\n\n[질문]\n{question}")
        text = pipeline.llm.chat(messages)

    srcs = sources_list(top)
    conv["messages"].append({"role": "user", "content": question})
    conv["messages"].append({"role": "assistant", "content": text,
                             "sources": [s["label"] for s in srcs]})
    if conv.get("title", "새 대화") in ("새 대화", "") and len([m for m in conv["messages"]
                                                          if m["role"] == "user"]) == 1:
        conv["title"] = question[:30]      # 첫 질문을 대화 제목으로
    maybe_summarize(pipeline.llm, conv)
    save_conversation(conv)
    return {"answer": text, "sources": srcs, "contexts": top}
