"""대화에 '로그 첨부' → 멀티턴 로그 분석. 문서 QA 대화와 같은 창에서 동작.

흐름:
  attach_log: 선택 프로토콜 문서에서 프레임 규격 도출 → 로그 파싱 → 프레임/명령이름 보관.
  answer_with_log: 명령별 필드표를 검색해 프레임 DATA를 결정적 디코드 → 그 구조를 컨텍스트로
                   멀티턴 답변(Q1 명령찾기 / Q2 필드값 필터 / Q3 전문 필드해석).
결정적 디코드 덕에 '카드번호로 필터' 같은 질의를 신뢰성 있게 처리한다.
"""
from __future__ import annotations

import re

from .store import save_conversation
from .engine import _history_messages, maybe_summarize, _is_followup
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
    except Exception as e:
        print(f"[경고] 명세 청크 조회 실패(스키마 없이 진행): {e}", flush=True)
        return [], []

LOG_SYSTEM = (
    "/no_think\n"
    "당신은 통신 로그 분석가입니다. 아래 자료는 첨부 로그를 이미 파싱한 **확정 사실**입니다."
    " 명령·시각·필드값은 반드시 이 값만 사용하고 지어내지 마십시오.\n"
    "- [로그 명령 요약]: 명령별 발생 횟수·시각(전체). '특정 명령 찾기'는 여기서 답합니다.\n"
    "- [전체 프레임 목록]: 로그의 모든 프레임(#번호·시각·명령). '세 번째', '11:25 것' 같은 지목은"
    " 이 목록의 번호·시각으로 찾습니다.\n"
    "- [질문 관련 프레임 필드 디코드]: 질문에서 지목된 프레임을 명세 필드표대로 잘라 놓은 것."
    " 프레임 내용 질문은 이 디코드 값을 그대로 제시합니다.\n"
    "- 특정 필드값(카드번호 등)으로 필터할 때도 이 디코드에서 그 값인 프레임을 고릅니다.\n"
    "- 앞선 대화의 '해당/그/위의 것'은 대화 맥락으로 해석합니다. 자료에 없으면 없다고 답합니다.\n"
    "금지 사항(사족 금지):\n"
    "1. 명령·필드 이름(CR, RC, MLDA 등)은 자료에 적힌 그대로만 쓰고, **약어의 원어·의미를"
    " 추측해 풀어 쓰지 마십시오**(예: 'RC=Rail Charge' 같은 임의 해석 금지). 자료에 정의가"
    " 없으면 이름 그대로 둡니다.\n"
    "2. **요청받은 것만** 답합니다. 묻지 않은 파생 계산(합계·수수료 환산·비율 계산), 화폐·단위"
    " 추측, 부가 해설·권고·요약을 덧붙이지 마십시오.\n"
    "3. 값은 디코드에 있는 그대로 옮깁니다 — 반올림·변환·재해석 금지."
)

# '그냥 파싱해줘' 류 요청 — LLM을 거치지 않고 결정적 디코드 결과를 그대로 표로 반환
# (소형 모델이 약어 임의 해석·파생 계산 사족을 붙이는 것을 원천 차단 + 즉답).
_PARSE_RE = re.compile(r"파싱|디코드|필드(로|별|\s*단위)?\s*(잘라|분해|나눠|보여|정리|해석)|전문\s*(분해|해석)")


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
    # 스키마(명령별 필드표)는 로그·명세가 고정이면 불변 → 첨부 시 1회 계산해 캐시.
    # (기존: 질문마다 전체 청크 재조회+정규식 재파싱 → 큰 명세에서 턴마다 수 초 낭비)
    schemas = _build_schemas(retriever, list(files), names,
                             _observed_cmd_keys(parsed),
                             target_len=_cmd_data_lens(parsed))
    conv["log"] = {"parsed": parsed, "cmd_names": names, "files": list(files),
                   "name": name, "schemas": schemas}
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


def frame_index(parsed: dict) -> str:
    """전체 프레임 한 줄 목록(#번호 시각 CMD 이름) — '명령 먼저 읽기' 완전 목록. 어떤 프레임이든 지목 가능."""
    lines = []
    for i, fr in enumerate(parsed.get("frames", []), start=1):
        nm = ""  # 이름은 요약(digest)에서 제공하므로 여기선 간결히
        lines.append(f"#{i} {fr.get('time', '')} CMD {_cmd_disp(fr)}")
    return "\n".join(lines)


def _kor(s: str) -> str:
    """문자열에서 한글만 이어붙임(영문 접두어 Card/카드 차이 등 무관하게 이름 매칭용)."""
    return "".join(ch for ch in (s or "") if "가" <= ch <= "힣")


def _select_indices(parsed: dict, cmd_names: dict, query: str) -> list:
    """질문에 언급된 명령(ID/이름)·시각에 해당하는 프레임 인덱스 선택. 특정 안 되면 [](=전체 판단).

    이름은 한글 부분으로 매칭(명세는 'Card 충전 요청', 사용자는 '카드 충전 요청' → '충전요청'으로 일치).
    """
    frames = parsed.get("frames", [])
    q = query or ""
    qu = q.upper()
    q_kor = _kor(q)
    times = [t.replace("시", ":").replace(" ", "") for t in re.findall(r"\d{1,2}\s*[:시]\s*\d{2}", q)]
    sel = set()
    # 프레임 번호 직접 지목: '#3', '3번째', '세 번째' → 해당 인덱스
    _ORD = {"첫": 1, "두": 2, "둘": 2, "세": 3, "셋": 3, "네": 4, "넷": 4,
            "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10}
    for m in re.findall(r"#(\d+)|(\d+)\s*번째", q):
        n = int(m[0] or m[1])
        if 1 <= n <= len(frames):
            sel.add(n - 1)
    for w, n in _ORD.items():
        if re.search(rf"{w}\s*번째", q) and n <= len(frames):
            sel.add(n - 1)
    for i, fr in enumerate(frames):
        cid = _cmd_id(fr)
        nk = _kor(cmd_names.get(cid, ""))
        by_cmd = (cid and cid != "?" and re.search(rf"(?<![A-Z0-9]){re.escape(cid)}(?![A-Z0-9])", qu)) \
            or (len(nk) >= 3 and nk in q_kor)
        by_time = any(t and t in (fr.get("time", "") or "").replace(" ", "") for t in times)
        if by_cmd or by_time:
            sel.add(i)
    return sorted(sel)


def _decoded_block(parsed: dict, cmd_names: dict, schemas: dict,
                   indices: list, cap: int = 40) -> str:
    """선택된(질문 관련) 프레임만 필드 디코드. 온디맨드 → 큰 로그도 확장."""
    frames = parsed.get("frames", [])
    if not indices:                                  # 특정 명령/시각 언급 없음 → 앞부분 표본
        indices = list(range(min(len(frames), cap)))
    lines, shown = [], 0
    for idx in indices:
        if shown >= cap:
            lines.append(f"… (관련 프레임 {len(indices)}개 중 {cap}개 표시)")
            break
        if idx >= len(frames):
            continue
        fr = frames[idx]
        cid = _cmd_id(fr)
        nm = cmd_names.get(cid, "")
        lines.append(f"#{idx + 1} {fr.get('time', '')} CMD {_cmd_disp(fr)}" + (f" {nm}" if nm else ""))
        sch = schemas.get(cid)
        if sch and fr.get("data"):
            lines.append(format_decoded(decode_data(fr["data"], sch)))
        elif fr.get("data"):
            lines.append("  DATA=[" + " ".join(f"{b:02X}" for b in fr["data"]) + "]")
        shown += 1
    return "\n".join(lines) or "(관련 프레임 없음)"


def _parse_answer(parsed: dict, cmd_names: dict, schemas: dict, idxs: list,
                  cap: int = 8) -> str:
    """지목된 프레임들의 결정적 파싱 결과를 마크다운 표로. LLM 미사용(사족·추측 0)."""
    frames = parsed.get("frames", [])
    out = []
    for k, idx in enumerate(idxs):
        if k >= cap:
            out.append(f"… 관련 프레임 {len(idxs)}개 중 {cap}개만 표시했습니다. "
                       "나머지는 시각/번호로 지목해 다시 요청하십시오.")
            break
        if idx >= len(frames):
            continue
        fr = frames[idx]
        cid = _cmd_id(fr)
        nm = cmd_names.get(cid, "")
        out.append(f"**#{idx + 1} {fr.get('time', '')} CMD {_cmd_disp(fr)}"
                   + (f" — {nm}" if nm else "") + "**")
        sch = schemas.get(cid)
        data = fr.get("data")
        if sch and data:
            decoded = decode_data(data, sch)
            out.append("| 필드 | 의미(문서 기준) | 타입·길이 | 해석값 | HEX |")
            out.append("|---|---|---|---|---|")
            for d in decoded:
                # 해석값: 숫자로 볼 수 있으면 숫자(선행 0 제거: '0002000'→2000),
                # 아니면 문자값. 의미는 명세 필드표의 설명 열 그대로(모델 추측 아님).
                if d.get("num") is not None:
                    shown = str(d["num"])
                elif d["type"] in ("ASCII", "CHAR", "BCD"):
                    shown = d["value"]
                else:
                    shown = ""
                out.append(f"| {d['name']} | {d.get('desc') or ''} | "
                           f"{d['type']}·{d['len']} | {shown} | {d['hex']} |")
            used = sum(f["len"] for f in sch[:len(decoded)])
            if used < len(data):
                rest = " ".join(f"{b:02X}" for b in data[used:])
                out.append(f"잔여 바이트(필드표 범위 밖): {rest}")
        elif data:
            out.append("(이 명령의 필드표를 명세에서 찾지 못해 원시 DATA만 표시합니다)")
            out.append("DATA: " + " ".join(f"{b:02X}" for b in data))
        else:
            out.append("(DATA 없음)")
        out.append("")
    out.append("※ 명세 필드표 기준 결정적 파싱 결과입니다(모델 해석 미개입).")
    return "\n".join(out)


def answer_with_log(pipeline, conv: dict, question: str) -> dict:
    log = conv["log"]
    parsed, names, files = log["parsed"], log["cmd_names"], log["files"]
    schemas = log.get("schemas")
    if not schemas:                      # 구버전 첨부(캐시 없음) 호환 → 1회 계산 후 저장
        schemas = _build_schemas(pipeline.retriever, files, names,
                                 _observed_cmd_keys(parsed),
                                 target_len=_cmd_data_lens(parsed))
        log["schemas"] = schemas
        save_conversation(conv)

    # 질문에서 언급된 명령/시각의 프레임만 골라 상세 디코드(온디맨드) → 큰 로그도 확장.
    # 최근 대화는 **후속 질문일 때만** 섞는다(새 질문까지 이전 명령에 매몰되는 것 방지).
    hist = ""
    if _is_followup(question):
        hist = " ".join(m["content"] for m in conv.get("messages", [])[-4:] if m["role"] == "user")
    idxs = _select_indices(parsed, names, question + " " + hist)

    # '파싱해줘' 요청 + 대상 프레임 특정됨 → LLM 없이 결정적 디코드를 그대로 답변.
    # (모델이 약어를 임의 해석하거나 수수료 환산 같은 사족을 붙이는 것 원천 차단 + 즉답)
    if _PARSE_RE.search(question) and idxs:
        text = _parse_answer(parsed, names, schemas, idxs)
        conv["messages"].append({"role": "user", "content": question})
        conv["messages"].append({"role": "assistant", "content": text})
        save_conversation(conv)
        return {"answer": text, "sources": [], "contexts": []}

    digest = summarize_analysis(parsed, cmd_names=names)     # 명령별 발생 시각(전체)
    findex = frame_index(parsed)                             # 전체 프레임 목록(#번호·시각·명령)
    decoded = _decoded_block(parsed, names, schemas, idxs)   # 관련 프레임 필드 디코드
    spec = gather_file_chunks(pipeline.retriever, files,
                              f"{question} 요청전문 응답전문 필드 전문 포맷 TYPE LEN", top_k=8)
    spec_ctx = "\n\n".join(c.get("document", "") for c in spec) or "(명세 없음)"

    messages = [{"role": "system", "content": LOG_SYSTEM}]
    messages += _history_messages(conv)
    messages.append({"role": "user", "content":
                     f"[로그 명령 요약]\n{digest}\n\n"
                     f"[전체 프레임 목록]\n{findex[:6000]}\n\n"
                     f"[질문 관련 프레임 필드 디코드]\n{decoded}\n\n"
                     f"[참고 명세]\n{spec_ctx}\n\n[질문]\n{question}"})
    text = pipeline.llm.chat(messages)

    conv["messages"].append({"role": "user", "content": question})
    conv["messages"].append({"role": "assistant", "content": text})
    maybe_summarize(pipeline.llm, conv)
    save_conversation(conv)
    return {"answer": text, "sources": [], "contexts": []}
