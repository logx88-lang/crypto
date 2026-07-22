"""대화에 '로그 첨부' → 멀티턴 로그 분석. 문서 QA 대화와 같은 창에서 동작.

흐름:
  attach_log: 선택 프로토콜 문서에서 프레임 규격 도출 → 로그 파싱 → 프레임/명령이름 보관.
  answer_with_log: 명령별 필드표를 검색해 프레임 DATA를 결정적 디코드 → 그 구조를 컨텍스트로
                   멀티턴 답변(Q1 명령찾기 / Q2 필드값 필터 / Q3 전문 필드해석).
결정적 디코드 덕에 '카드번호로 필터' 같은 질의를 신뢰성 있게 처리한다.
"""
from __future__ import annotations

from .store import save_conversation
from .engine import _history_messages, maybe_summarize
from ..logs.generic import analyze_by_spec
from ..logs.workflow import (summarize_analysis, gather_file_chunks,
                             resolve_command_names, extract_command_names,
                             _observed_cmd_keys)
from ..logs.fields import parse_field_schema, decode_data, format_decoded


def _file_chunks(retriever, files):
    """선택 파일들의 모든 (문서, 메타) 청크. 명령표·필드표 결정적 조회용(검색 recall 무관)."""
    try:
        got = retriever.store._col.get(
            where={"source_file": {"$in": list(files)}},
            include=["documents", "metadatas"])
        return got.get("documents", []), got.get("metadatas", [])
    except Exception:
        return [], []

LOG_SYSTEM = (
    "/no_think\n"
    "당신은 통신 로그 분석가입니다. 아래 [로그 명령 요약]과 [프레임 필드 디코드]는 이미 분석이 끝난"
    " **확정 사실**입니다. 명령·시각·필드값은 반드시 이 값만 사용하고 지어내지 마십시오.\n"
    "- '특정 명령 기록 찾기' → [로그 명령 요약]에서 그 명령의 발생 시각들을 나열합니다.\n"
    "- '특정 필드값(예: 카드번호)으로 필터' → [프레임 필드 디코드]에서 그 필드가 그 값인 프레임만 고릅니다.\n"
    "- '전문 파싱/해석' → [프레임 필드 디코드]의 해당 프레임 필드를 '이름 (타입,길이) : 값' 형식으로 제시합니다.\n"
    "- '앞뒤 N초' 등은 [프레임 필드 디코드]의 시각을 기준으로 그 범위의 프레임을 보여줍니다.\n"
    "- 앞선 대화의 '해당/그 기록/위의 것'은 대화 맥락으로 해석합니다. 근거가 없으면 없다고 답합니다."
)


def attach_log(conv: dict, log_text: str, files: list, retriever, llm,
               name: str = "log") -> dict:
    """로그를 파싱해 대화에 첨부(conv['log'])하고 저장. 반환: parsed."""
    derive = gather_file_chunks(
        retriever, files,
        "전문 포맷 프레임 구조 packet format Command Length Data 체크섬 요청전문 응답전문",
        top_k=10)
    parsed = analyze_by_spec(log_text, "\n\n".join(c.get("document", "") for c in derive), llm)
    names = dict(resolve_command_names(retriever, parsed, where={"source_file": {"$in": files}}))
    # 보강: 파일 명령표에서 ID→이름 직접 추출(검색이 놓친 명령 이름 채움)
    docs, _ = _file_chunks(retriever, files)
    for d in docs:
        for k, v in extract_command_names(d).items():
            names.setdefault(k, v)
    conv["log"] = {"parsed": parsed, "cmd_names": names, "files": list(files), "name": name}
    save_conversation(conv)
    return parsed


def _cmd_id(fr) -> str:
    if fr.get("cmd_ascii"):
        return fr["cmd_ascii"].strip().upper()
    c = fr.get("cmd")
    return f"0X{c:X}" if isinstance(c, int) else "?"


def _cmd_disp(fr) -> str:
    if fr.get("cmd_ascii"):
        return f"'{fr['cmd_ascii']}'"
    c = fr.get("cmd")
    return f"0x{c:02X}" if isinstance(c, int) else "?"


def _cmd_data_lens(parsed: dict) -> dict:
    """명령별 DATA 길이 대표값(최빈) → {cmd_id: len}. 전문표 선택의 '정답 길이' 기준."""
    from collections import Counter
    per = {}
    for fr in parsed.get("frames", []):
        if fr.get("data"):
            per.setdefault(_cmd_id(fr), Counter())[len(fr["data"])] += 1
    return {c: cnt.most_common(1)[0][0] for c, cnt in per.items()}


def _build_schemas(retriever, files, cmd_names: dict, observed, target_len: dict = None) -> dict:
    """관측 명령별 필드표를 {cmd_id: [fields]} 로.

    의미검색은 recall이 나쁘므로 선택 파일의 '전체 청크'를 가져와 section_path 에 그 명령
    이름이 있는(= 그 명령의 전문) 필드표를 결정적으로 찾는다. 한 명령에 여러 전문표(요청/응답/타사)가
    있으면 그 명령 프레임의 DATA 길이에 필드 합계 길이가 가장 근접한 표를 채택(실제 데이터에 정렬).
    """
    docs, metas = _file_chunks(retriever, files)
    target_len = target_len or {}
    schemas = {}
    for cid in observed:
        nmkey = (cmd_names.get(cid, "") or "").replace(" ", "")
        if not nmkey:
            continue
        cands = []
        for d, m in zip(docs, metas):
            sp = (m.get("section_path", "") or "").replace(" ", "")
            if nmkey not in sp:
                continue
            sch = parse_field_schema(d)
            if len(sch) >= 2:
                cands.append(sch)
        if not cands:
            continue
        tl = target_len.get(cid)
        if tl:
            schemas[cid] = min(cands, key=lambda s: abs(sum(f["len"] for f in s) - tl))
        else:
            schemas[cid] = max(cands, key=len)
    return schemas


def _decoded_block(parsed: dict, cmd_names: dict, schemas: dict, max_frames: int = 60) -> str:
    frames = parsed.get("frames", [])
    lines = []
    for fr in frames[:max_frames]:
        cid = _cmd_id(fr)
        nm = cmd_names.get(cid, "")
        head = f"{fr.get('time', '')} CMD {_cmd_disp(fr)}" + (f" {nm}" if nm else "")
        lines.append(head)
        sch = schemas.get(cid)
        if sch and fr.get("data"):
            lines.append(format_decoded(decode_data(fr["data"], sch)))
        elif fr.get("data"):
            lines.append("  DATA=[" + " ".join(f"{b:02X}" for b in fr["data"]) + "]")
    if len(frames) > max_frames:
        lines.append(f"… (외 {len(frames) - max_frames} 프레임 생략)")
    return "\n".join(lines)


def answer_with_log(pipeline, conv: dict, question: str) -> dict:
    log = conv["log"]
    parsed, names, files = log["parsed"], log["cmd_names"], log["files"]
    observed = _observed_cmd_keys(parsed)
    schemas = _build_schemas(pipeline.retriever, files, names, observed,
                             target_len=_cmd_data_lens(parsed))

    digest = summarize_analysis(parsed, cmd_names=names)
    decoded = _decoded_block(parsed, names, schemas)
    spec = gather_file_chunks(pipeline.retriever, files,
                              f"{question} 요청전문 응답전문 필드 전문 포맷 TYPE LEN", top_k=8)
    spec_ctx = "\n\n".join(c.get("document", "") for c in spec) or "(명세 없음)"

    messages = [{"role": "system", "content": LOG_SYSTEM}]
    messages += _history_messages(conv)
    messages.append({"role": "user", "content":
                     f"[로그 명령 요약]\n{digest}\n\n"
                     f"[프레임 필드 디코드]\n{decoded}\n\n"
                     f"[참고 명세]\n{spec_ctx}\n\n[질문]\n{question}"})
    text = pipeline.llm.chat(messages)

    conv["messages"].append({"role": "user", "content": question})
    conv["messages"].append({"role": "assistant", "content": text})
    maybe_summarize(pipeline.llm, conv)
    save_conversation(conv)
    return {"answer": text, "sources": [], "contexts": []}
