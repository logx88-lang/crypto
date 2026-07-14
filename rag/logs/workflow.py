"""통신 로그 분석 워크플로우 (design.md §7).

흐름: 업로드 로그 → 종류 판별 → (hex) 프로파일 자동감지 + 명세 후보 검색 →
**UI 확인 단계(필수)** → 확정 명세 + 파싱결과를 컨텍스트로 LLM 해석.

이 모듈은 조각(후보검색·요약·메시지조립·해석)을 제공하고, "확인 단계"는 UI(app)가 개입한다.
retrieve/generate 는 지연 임포트 → logs 결정적 코어는 Ollama 비의존 유지.
"""
from __future__ import annotations

from typing import Optional

from .detect import detect_log_type, detect_profile
from .parser import analyze_text_log, analyze_binary_log
from .profiles import ParsingProfile


# --- 1. 판별 & 파싱 --------------------------------------------------------
def analyze(data, profile: Optional[ParsingProfile] = None, is_binary: bool = False) -> dict:
    """텍스트/바이너리 로그 분석 디스패치."""
    if is_binary or isinstance(data, (bytes, bytearray)):
        prof = profile or detect_profile("")  # 바이너리는 명세 프로파일 필요
        return analyze_binary_log(bytes(data), prof)
    return analyze_text_log(data, profile)


# --- 2. 명세 후보 검색 (doc_type=protocol_spec) ----------------------------
def find_spec_candidates(retriever, log_text: str, question: str = "",
                         top_k: int = 5) -> list:
    """로그 단서 + 질문으로 프로토콜 명세 후보를 하이브리드 검색.

    자동 해석 금지 — 반환 후보는 UI 확인 단계 입력이다.
    같은 (문서·섹션) 중복을 제거하고, 표 청크를 우선해 후보 다양성을 확보한다.
    """
    preview = "\n".join(log_text.splitlines()[:8])
    query = " ".join(p for p in (question, preview) if p).strip()
    raw = retriever.search(query, top_k=max(top_k * 4, 20),
                           where={"doc_type": "protocol_spec"})
    # (문서, 섹션) 기준 중복 제거 — 같은 섹션 반복 방지
    seen, out = set(), []
    for c in raw:
        m = c.get("metadata", {})
        key = (m.get("doc_title", ""), m.get("section", ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
        if len(out) >= top_k:
            break
    return out


# --- 3. 파싱결과 요약 (LLM/UI 표시용, 컨텍스트 초과 방지 §7-3) --------------
def summarize_analysis(analysis: dict, max_frames: int = 40) -> str:
    lt = analysis.get("log_type")
    if lt == "natural":
        lines = analysis.get("lines", [])
        head = lines[:max_frames]
        body = "\n".join(head)
        if len(lines) > max_frames:
            body += f"\n… (총 {len(lines)}줄 중 {max_frames}줄 표시)"
        return f"[자연어 로그 · {len(lines)}줄]\n{body}"

    frames = analysis.get("frames", [])
    total = analysis.get("total", len(frames))
    valid = analysis.get("valid_count", 0)
    rows = []
    for i, fr in enumerate(frames[:max_frames], start=1):
        cmd = fr.get("cmd")
        if fr.get("cmd_ascii"):           # RF류: 2글자 ASCII 명령 + 길이 + 데이터
            da = fr.get("data_ascii", "")
            cmd_s = f"'{fr['cmd_ascii']}' len={fr.get('length')} data='{da[:48]}'"
        else:
            cmd_s = f"CMD=0x{cmd:02X}" if isinstance(cmd, int) else "CMD=?"
        flag = "OK" if fr.get("valid") else f"✗({fr.get('note','')})"
        rows.append(f"{i:>3}. {cmd_s} [{fr.get('hex','')[:60]}] {flag}")
    body = "\n".join(rows)
    if total > max_frames:
        body += f"\n… (총 {total} 프레임 중 {max_frames} 표시)"
    return f"[HEX 로그 · 프레임 {total}개, 유효 {valid}/{total}]\n{body}"


# --- 4. LLM 해석 메시지 조립 ----------------------------------------------
def build_log_messages(question: str, analysis: dict, spec_chunks: list) -> list:
    from ..generate.prompt import source_label  # 지연 임포트

    spec_blocks = []
    for i, c in enumerate(spec_chunks, start=1):
        label = source_label(c.get("metadata", {}))
        spec_blocks.append(f"[명세{i}] ({label})\n{c.get('document', '').strip()}")
    spec_ctx = "\n\n".join(spec_blocks) or "(확정 명세 없음)"
    parsed = summarize_analysis(analysis)

    system = (
        "/no_think\n"
        "당신은 통신 프로토콜 로그 분석가입니다. 아래 [확정 명세]의 패킷 구조·필드·명령 코드에만"
        " 근거하여 [파싱 결과] 로그를 한국어 공식체로 해석하십시오.\n"
        "- 각 해석에 근거 명세를 [명세N]으로 표기합니다.\n"
        "- 명세에 없는 명령/필드는 추측하지 말고 '명세 미기재'로 표시합니다.\n"
        "- 체크섬 불일치(✗) 프레임은 이상 징후로 명시합니다."
    )
    user = (
        f"[확정 명세]\n{spec_ctx}\n\n"
        f"[파싱 결과]\n{parsed}\n\n"
        f"[질문]\n{question or '이 로그의 통신 흐름을 명세에 근거해 설명하십시오.'}"
    )
    return [{"role": "system", "content": system},
            {"role": "user", "content": user}]


def explain(llm, question: str, analysis: dict, spec_chunks: list) -> str:
    """확정 명세 기반 LLM 해석 실행."""
    messages = build_log_messages(question, analysis, spec_chunks)
    return llm.chat(messages)
