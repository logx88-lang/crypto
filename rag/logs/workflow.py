"""통신 로그 분석 워크플로우 (design.md §7).

흐름: 업로드 로그 → 종류 판별 → (hex) 프로파일 자동감지 + 명세 후보 검색 →
**UI 확인 단계(필수)** → 확정 명세 + 파싱결과를 컨텍스트로 LLM 해석.

이 모듈은 조각(후보검색·요약·메시지조립·해석)을 제공하고, "확인 단계"는 UI(app)가 개입한다.
retrieve/generate 는 지연 임포트 → logs 결정적 코어는 Ollama 비의존 유지.
"""
from __future__ import annotations

import re
from typing import Optional

from .detect import detect_log_type, detect_profile
from .parser import analyze_text_log, analyze_binary_log
from .profiles import ParsingProfile

# 명령표 행: "SD" | LSAM 자료 요청 …  → (ID, 이름) 추출
_CMD_ROW_RE = re.compile(r"[“”\"']\s*([A-Za-z]{2})\s*[“”\"']\s*\|\s*([^|]+)")


def extract_command_names(spec_text: str) -> dict:
    """확정 명세 텍스트에서 명령 ID→이름 매핑을 결정적으로 추출.

    LLM이 표를 교차참조하다 명령 코드를 지어내는 문제를 없애기 위해, 파싱 요약에
    이름을 직접 붙여준다(예: 'SD' → 'LSAM 자료 요청').
    """
    out = {}
    for m in _CMD_ROW_RE.finditer(spec_text or ""):
        cid, name = m.group(1).upper(), m.group(2).strip()
        if name and cid not in out:
            out[cid] = name
    return out


def _looks_like_cmd_list(doc: str) -> bool:
    """명령 ID↔이름 매핑 행("SD" | LSAM 자료 요청 …)이 3개 이상 파싱되는 청크인지 판정.

    extract_command_names 와 동일 기준 → '명령표'라고 판정되면 실제로 이름을 뽑을 수 있음이
    보장된다(Error Code 표·목차 등 오탐 방지, 후보 보강이 파싱 가능한 청크를 고르게).
    """
    return len(extract_command_names(doc)) >= 3


# --- 1. 판별 & 파싱 --------------------------------------------------------
def analyze(data, profile: Optional[ParsingProfile] = None, is_binary: bool = False) -> dict:
    """텍스트/바이너리 로그 분석 디스패치."""
    if is_binary or isinstance(data, (bytes, bytearray)):
        prof = profile or detect_profile("")  # 바이너리는 명세 프로파일 필요
        return analyze_binary_log(bytes(data), prof)
    return analyze_text_log(data, profile)


# --- 2. 명세 후보 검색 (doc_type=protocol_spec) ----------------------------
def find_spec_candidates(retriever, log_text: str, question: str = "",
                         top_k: int = 5, folders=None, files=None) -> list:
    """로그 단서 + 질문으로 프로토콜 명세 후보를 하이브리드 검색.

    자동 해석 금지 — 반환 후보는 UI 확인 단계 입력이다.
    같은 (문서·섹션) 중복을 제거하고, 표 청크를 우선해 후보 다양성을 확보한다.
    files(전체경로) 또는 folders 지정 시 해당 범위로 제한(files 우선).
    """
    preview = "\n".join(log_text.splitlines()[:8])
    query = " ".join(p for p in (question, preview) if p).strip()
    where = {"doc_type": "protocol_spec"}
    if files:
        where["rel_path"] = {"$in": list(files)}
    elif folders:
        where["folder"] = {"$in": list(folders)}
    raw = retriever.search(query, top_k=max(top_k * 6, 30), where=where)

    def _doc(c):
        m = c.get("metadata", {})
        return m.get("source_file") or m.get("doc_title") or ""

    # 1차: 문서별 최상위 1개씩 — 관련 문서(발매/정산/충전 등)가 모두 후보에 뜨게
    out, docs_used = [], set()
    for c in raw:
        d = _doc(c)
        if d not in docs_used:
            docs_used.add(d)
            out.append(c)
            if len(out) >= top_k:
                break
    # 2차: 남은 슬롯을 (문서,섹션) 중복 제거하며 채움
    if len(out) < top_k:
        seen = {(_doc(c), c.get("metadata", {}).get("section", "")) for c in out}
        for c in raw:
            if len(out) >= top_k:
                break
            key = (_doc(c), c.get("metadata", {}).get("section", ""))
            if key not in seen:
                seen.add(key)
                out.append(c)

    # 3차: 명령 코드 목록(명령 ID↔이름 매핑) 청크를 최소 1개 보강 —
    # '특정 명령이 언제 발생?' 류 질의에서 로그의 명령 ID를 이름으로 해석하려면 필수인데,
    # 의미 검색만으론 상위에 안 뜨는 경우가 많다. 후보에 없으면 별도 검색해 덧붙인다.
    if not any(_looks_like_cmd_list(c.get("document", "")) for c in out):
        try:
            extra = retriever.search(
                "Command ID 명령 코드 목록 구분 설명 Protocol Control Code List",
                top_k=12, where=where)
        except Exception:
            extra = []
        for c in extra:
            if _looks_like_cmd_list(c.get("document", "")):
                out.append(c)     # top_k 초과해도 명령표는 항상 노출
                break
    return out


# --- 3. 파싱결과 요약 (LLM/UI 표시용, 컨텍스트 초과 방지 §7-3) --------------
def summarize_analysis(analysis: dict, max_frames: int = 40, cmd_names: dict = None) -> str:
    cmd_names = cmd_names or {}
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
    has_time = any(fr.get("time") for fr in frames)

    def _cmd_key(fr):
        cmd = fr.get("cmd")
        if fr.get("cmd_ascii"):
            return f"'{fr['cmd_ascii']}'"
        return f"0x{cmd:02X}" if isinstance(cmd, int) else "?"

    # 명령별 집계(발생 횟수 + 시각) — 프레임이 많아도 특정 명령/발생시각을 놓치지 않게.
    agg = {}
    for fr in frames:
        k = _cmd_key(fr)
        e = agg.setdefault(k, {"count": 0, "times": []})
        e["count"] += 1
        if fr.get("time"):
            e["times"].append(fr["time"])
    agg_lines = []
    for k, e in sorted(agg.items(), key=lambda kv: -kv[1]["count"]):
        ts = e["times"]
        tail = f" @ {', '.join(ts[:12])}{' …' if len(ts) > 12 else ''}" if ts else ""
        name = cmd_names.get(k.strip("'\"").upper())   # 명세에서 뽑은 명령 이름 주입
        label = f"{k} ({name})" if name else k
        agg_lines.append(f"  {label}: {e['count']}회{tail}")

    rows = []
    for i, fr in enumerate(frames[:max_frames], start=1):
        cmd = fr.get("cmd")
        if fr.get("cmd_ascii"):           # RF류: 2글자 ASCII 명령 + 길이 + 데이터
            da = fr.get("data_ascii", "")
            cmd_s = f"'{fr['cmd_ascii']}' len={fr.get('length')} data='{da[:48]}'"
        else:
            cmd_s = f"CMD=0x{cmd:02X}" if isinstance(cmd, int) else "CMD=?"
        tpre = f"{fr['time']} " if fr.get("time") else ""
        flag = "OK" if fr.get("valid") else f"✗({fr.get('note','')})"
        rows.append(f"{i:>3}. {tpre}{cmd_s} [{fr.get('hex','')[:60]}] {flag}")
    body = "\n".join(rows)
    if total > max_frames:
        body += f"\n… (총 {total} 프레임 중 {max_frames} 표시)"
    head = f"[HEX 로그 · 프레임 {total}개, 유효 {valid}/{total}" + \
           (", 시각 포함" if has_time else "") + "]"
    return (head + "\n[명령별 발생" + (" 시각" if has_time else "") + "]\n"
            + "\n".join(agg_lines) + "\n[프레임 상세]\n" + body)


# --- 4. LLM 해석 메시지 조립 ----------------------------------------------
def build_log_messages(question: str, analysis: dict, spec_chunks: list) -> list:
    from ..generate.prompt import source_label  # 지연 임포트

    # 명령표(구분|ID|설명) 청크를 앞에 배치 → 명령 이름 매핑이 프롬프트 상단에 오게.
    ordered = sorted(spec_chunks,
                     key=lambda c: 0 if _looks_like_cmd_list(c.get("document", "")) else 1)
    spec_blocks = []
    for i, c in enumerate(ordered, start=1):
        label = source_label(c.get("metadata", {}))
        spec_blocks.append(f"[명세{i}] ({label})\n{c.get('document', '').strip()}")
    spec_ctx = "\n\n".join(spec_blocks) or "(확정 명세 없음)"

    # 명세에서 명령 ID→이름을 결정적으로 추출해 파싱 요약에 직접 주입(LLM 교차참조 불필요).
    cmd_names = extract_command_names("\n".join(c.get("document", "") for c in spec_chunks))
    parsed = summarize_analysis(analysis, cmd_names=cmd_names)

    system = (
        "/no_think\n"
        "당신은 통신 프로토콜 로그 분석가입니다. 아래 [확정 명세]의 패킷 구조·필드·명령 코드에만"
        " 근거하여 [파싱 결과] 로그를 한국어 공식체로 해석하십시오.\n"
        "- [파싱 결과]의 '명령별 발생 시각'에는 로그에서 실제로 관측된 명령 ID와 (명세에서 찾은)"
        " 명령 이름, 그리고 발생 시각이 있습니다. 명령·이름·시각은 반드시 이 값을 그대로 사용하고,"
        " 명령 코드/이름/시각을 지어내지 마십시오.\n"
        "- 질문이 명령을 이름(예: 'LSAM 정보 요청')으로 지칭하면, [파싱 결과]의 '명령별 발생 시각'에서"
        " 같은(또는 가장 가까운) 이름의 항목을 찾아 그 발생 시각을 답하십시오. '정보 요청'과 '자료 요청'"
        " 처럼 표기가 달라도 같은 명령이면 연결합니다.\n"
        "- 해당 이름의 명령이 파싱 결과에 없으면 '해당 명령이 로그에 관측되지 않음'이라고 답하십시오.\n"
        "- 각 해석에 근거 명세를 [명세N]으로 표기합니다.\n"
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
