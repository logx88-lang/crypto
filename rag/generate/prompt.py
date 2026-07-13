"""프롬프트 조립 — 시스템 프롬프트(공식체·출처표기·근거없으면 모른다) + 컨텍스트 (design.md §6).

순수 로직(문자열 조립) → Ollama 없이 단위 테스트.
"""
from __future__ import annotations

NO_CONTEXT_ANSWER = "제공된 문서에서 근거를 찾지 못했습니다."

SYSTEM_PROMPT = (
    "/no_think\n"
    "당신은 사내 문서 기반 질의응답 도우미입니다. 다음 규칙을 반드시 지키십시오.\n"
    "1. 제공된 [문서 발췌]에 근거가 있을 때만 답변합니다.\n"
    "2. 답변은 한국어 공식체(합니다체)로 작성합니다.\n"
    "3. 각 주장 뒤에 근거 출처를 [번호] 형태로 표기합니다(예: ...입니다 [1]).\n"
    "4. 발췌에 근거가 없으면 추측하지 말고 정확히 다음과 같이 답합니다: "
    f"\"{NO_CONTEXT_ANSWER}\"\n"
    "5. 발췌에 없는 내용을 지어내지 않습니다."
)


def source_label(meta: dict) -> str:
    """청크 메타 → 사람이 읽는 출처 표기 (문서명 · 위치)."""
    parts = [meta.get("doc_title") or meta.get("source_file") or "문서"]
    if meta.get("page_no"):
        parts.append(f"p.{meta['page_no']}")
    if meta.get("sheet_name"):
        parts.append(f"시트:{meta['sheet_name']}")
    if meta.get("slide_no"):
        parts.append(f"슬라이드 {meta['slide_no']}")
    if meta.get("section"):
        parts.append(str(meta["section"]))
    return " · ".join(str(p) for p in parts if p)


def build_context(chunks: list) -> str:
    """[번호] (출처)\n본문 블록들을 이어붙인 컨텍스트 문자열."""
    blocks = []
    for i, c in enumerate(chunks, start=1):
        label = source_label(c.get("metadata", {}))
        blocks.append(f"[{i}] ({label})\n{c.get('document', '').strip()}")
    return "\n\n".join(blocks)


def build_messages(query: str, chunks: list) -> list:
    """Ollama chat 메시지 배열."""
    context = build_context(chunks)
    user = (
        "다음 문서 발췌만을 근거로 질문에 답하십시오.\n\n"
        f"[문서 발췌]\n{context}\n\n"
        f"[질문]\n{query}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def sources_list(chunks: list) -> list:
    """답변 하단 출처 목록 → [{n, label, metadata}]."""
    out = []
    for i, c in enumerate(chunks, start=1):
        out.append({"n": i, "label": source_label(c.get("metadata", {})),
                    "metadata": c.get("metadata", {})})
    return out
