"""문서 기반 범용 로그 파서 — 프레임 규격을 **설정(dict)**으로 표현하고, 그 설정은
선택한 프로토콜 문서에서 **LLM이 도출**한다. 포맷마다 코드를 하드코딩하지 않는다.

지원 프레이밍:
- "length": Command + Length + Data + Checksum (RF module류, 산업용 다수)
- "delimited": 시작바이트~끝바이트 (STX/ETX, SOH 등)

설정 스키마(LLM 출력 = 이 dict):
{
  "framing": "length" | "delimited",
  "byte_token": "bracket" | "0x" | "bare",
  "timestamp_regex": "...(선택)",
  "strip_regexes": ["...제거할 방향/명령 표기..."],
  # length:
  "cmd":    {"offset":0, "size":2, "type":"ascii"|"hex"},
  "length": {"offset":2, "size":2, "endian":"big"|"little"},
  "header_size": 4,           # 데이터 시작 오프셋(= cmd+length 등)
  "trailer_size": 1,          # 데이터 뒤 바이트 수(체크섬 등)
  "checksum": {"type":"xor"|"lrc"|"sum"|"crc16"|"none", "span":"header_and_data"|"data"},
  # delimited:
  "start_byte": 2, "end_byte": 3
}
"""
from __future__ import annotations

import re

from .profiles import TOK_BRACKET, TOK_0X, TOK_BARE

_TOKENS = {"bracket": TOK_BRACKET, "0x": TOK_0X, "bare": TOK_BARE}


def ascii_dump(data) -> str:
    """바이너리 데이터를 출력가능 문자만 표시(비출력은 '.')— 깨진 글자(�) 대신."""
    return "".join(chr(b) if 32 <= b < 127 else "." for b in data)


# LLM 구조화 출력용 JSON 스키마
PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "framing": {"type": "string", "enum": ["length", "delimited"]},
        "byte_token": {"type": "string", "enum": ["bracket", "0x", "bare"]},
        "strip_regexes": {"type": "array", "items": {"type": "string"}},
        "cmd": {"type": "object", "properties": {
            "offset": {"type": "integer"}, "size": {"type": "integer"},
            "type": {"type": "string", "enum": ["ascii", "hex"]}}},
        "length": {"type": "object", "properties": {
            "offset": {"type": "integer"}, "size": {"type": "integer"},
            "endian": {"type": "string", "enum": ["big", "little"]}}},
        "header_size": {"type": "integer"},
        "trailer_size": {"type": "integer"},
        "checksum": {"type": "object", "properties": {
            "type": {"type": "string", "enum": ["xor", "lrc", "sum", "crc16", "none"]},
            "span": {"type": "string", "enum": ["header_and_data", "data"]}}},
        "start_byte": {"type": "integer"}, "end_byte": {"type": "integer"},
    },
    "required": ["framing"],
}


def _int(bs, endian):
    return int.from_bytes(bytes(bs), "big" if endian == "big" else "little")


def _checksum(kind, data):
    if kind in ("xor", "lrc"):
        c = 0
        for b in data:
            c ^= b
        return c
    if kind == "sum":
        return sum(data) & 0xFF
    if kind == "crc16":
        crc = 0xFFFF
        for b in data:
            crc ^= b << 8
            for _ in range(8):
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF if (crc & 0x8000) else (crc << 1) & 0xFFFF
        return crc
    return None


def reconstruct_stream(text: str, profile: dict):
    """로그 전체에서 hex 바이트 스트림 복원 → (stream, times) 반환.

    times[k] = 스트림 k번째 바이트가 나온 줄의 타임스탬프 문자열(없으면 "").
    타임스탬프는 '제거'하기 전에 먼저 추출해 각 바이트에 꼬리표로 붙인다 →
    프레임이 언제 발생했는지(시간 질의) 답할 수 있게 한다.
    """
    token = _TOKENS.get(profile.get("byte_token", "bracket"), TOK_BRACKET)
    strips = list(profile.get("strip_regexes") or [])
    ts_rx = profile.get("timestamp_regex")
    out, times = [], []
    for ln in text.splitlines():
        ts = ""
        if ts_rx:
            try:
                m = re.search(ts_rx, ln)
                if m:
                    ts = m.group(0).strip()
            except re.error:
                pass
        body = ln
        for rx in strips + ([ts_rx] if ts_rx else []):
            try:
                body = re.sub(rx, " ", body)
            except re.error:
                pass
        bs = [int(h, 16) for h in re.findall(token, body)]
        out.extend(bs)
        times.extend([ts] * len(bs))
    return out, times


def parse_length(stream: list, profile: dict, times: list = None) -> dict:
    """length 프레이밍: Command + Length + Data + (checksum trailer)."""
    cmd = profile.get("cmd", {"offset": 0, "size": 2, "type": "ascii"})
    lenf = profile.get("length", {"offset": 2, "size": 2, "endian": "big"})
    header = int(profile.get("header_size", cmd.get("size", 2) + lenf.get("size", 2)))
    trailer = int(profile.get("trailer_size", 1))
    chk = profile.get("checksum", {"type": "none", "span": "header_and_data"})
    frames, valid = [], 0
    i, n = 0, len(stream)
    while i + header + trailer <= n:
        length = _int(stream[i + lenf["offset"]: i + lenf["offset"] + lenf["size"]],
                      lenf.get("endian", "big"))
        total = header + length + trailer
        if i + total > n:
            break
        fr = stream[i:i + total]
        cb = fr[cmd["offset"]: cmd["offset"] + cmd["size"]]
        cmd_ascii = bytes(cb).decode("ascii", "replace") if cmd.get("type") == "ascii" \
            else " ".join(f"{x:02X}" for x in cb)
        data = fr[header:header + length]
        ok, note = True, ""
        if chk.get("type", "none") != "none" and trailer >= 1:
            span = fr[0:header + length] if chk.get("span") == "header_and_data" else data
            calc = _checksum(chk["type"], span)
            got = _int(fr[header + length: header + length + trailer], "big")
            ok = (calc == got)
            if not ok:
                note = f"{chk['type'].upper()} 불일치(계산 0x{calc:02X}, 값 0x{got:02X})"
        frames.append({
            "bytes": fr, "hex": " ".join(f"{x:02X}" for x in fr),
            "cmd": None, "cmd_ascii": cmd_ascii, "length": length,
            "data": list(data), "data_ascii": ascii_dump(data),
            "time": (times[i] if times and i < len(times) else ""),
            "valid": ok, "note": note,
        })
        valid += int(ok)
        i += total
    return {"log_type": "hex", "profile": profile, "frames": frames,
            "valid_count": valid, "total": len(frames)}


def parse_delimited(stream: list, profile: dict, times: list = None) -> dict:
    """delimited 프레이밍: start_byte ~ end_byte 로 프레임 분할.

    길이 필드가 있으면 그것으로 프레임 끝을 계산한다 — DATA에 종료바이트(예: 0x03)가
    들어가도 프레임이 어긋나지 않게(STX+LEN+CMD+DATA+CHK+ETX 류 흔한 구조 대응).
    """
    sb, eb = profile.get("start_byte"), profile.get("end_byte")
    chk = profile.get("checksum", {"type": "none"})
    lenf = profile.get("length")
    hs, ts_ = profile.get("header_size"), profile.get("trailer_size")
    cmd_off = int(profile.get("cmd", {}).get("offset", 2))
    frames, valid = [], 0
    i, n = 0, len(stream)
    while i < n:
        if stream[i] != sb:
            i += 1
            continue
        j = None
        if lenf and hs is not None and ts_ is not None:      # 길이 기반 끝 계산
            lo = i + int(lenf["offset"])
            sz = int(lenf.get("size", 1))
            if lo + sz <= n:
                length = _int(stream[lo:lo + sz], lenf.get("endian", "big"))
                end = i + int(hs) + length + int(ts_) - 1
                if end < n and stream[end] == eb:
                    j = end
        if j is None:                                        # 폴백: 종료바이트 스캔
            j = i + 1
            while j < n and stream[j] != eb:
                j += 1
            if j >= n:
                break
        fr = stream[i:j + 1]
        ok, note = True, ""
        if chk.get("type", "none") != "none" and len(fr) >= 3:
            calc = _checksum(chk["type"], fr[1:-2])
            got = fr[-2]
            ok = (calc == got)
            if not ok:
                note = f"{chk['type'].upper()} 불일치"
        frames.append({"bytes": fr, "hex": " ".join(f"{x:02X}" for x in fr),
                       "cmd": fr[cmd_off] if len(fr) > cmd_off else None,
                       "time": (times[i] if times and i < len(times) else ""),
                       "valid": ok, "note": note})
        valid += int(ok)
        i = j + 1
    return {"log_type": "hex", "profile": profile, "frames": frames,
            "valid_count": valid, "total": len(frames)}


def analyze_with_profile(text: str, profile: dict) -> dict:
    """도출된 설정(dict)으로 로그 파싱 — 하드코딩 없는 범용 경로."""
    stream, times = reconstruct_stream(text, profile)
    if profile.get("framing") == "delimited":
        return parse_delimited(stream, profile, times)
    return parse_length(stream, profile, times)


# ---------------------------------------------------------------------------
# 로그 줄 형식 자동 감지 (토큰/타임스탬프/구조표기) — 코드가 담당
# ---------------------------------------------------------------------------
def detect_line_format(text: str) -> dict:
    """로그 샘플에서 byte_token·timestamp_regex·strip_regexes 를 추정한다."""
    from .profiles import (TS_MMDD, TS_ISO, TS_RF, DIR_TXRX, DIR_ARROW, CMD_MARKER)
    sample = "\n".join(text.splitlines()[:40])
    # 명시적 구분자(bracket/0x)를 우선 — bare 정규식은 [hh] 내부도 매칭해 과대계수됨
    if re.search(TOK_BRACKET, sample):
        token = "bracket"
    elif re.search(TOK_0X, sample):
        token = "0x"
    elif re.search(TOK_BARE, sample):
        token = "bare"
    else:
        token = "bracket"
    ts = None
    for pat in (TS_RF, TS_ISO, TS_MMDD):
        if re.search(pat, sample):
            ts = pat
            break
    strips = []
    if re.search(CMD_MARKER, sample):
        strips.append(CMD_MARKER)
    if re.search(DIR_ARROW, sample):
        strips.append(DIR_ARROW)
    if re.search(DIR_TXRX, sample):
        strips.append(DIR_TXRX)
    return {"byte_token": token, "timestamp_regex": ts, "strip_regexes": strips}


# ---------------------------------------------------------------------------
# 프레임 구조 도출 (LLM이 명세 표에서) — 하드코딩 대체
# ---------------------------------------------------------------------------
_DERIVE_SYSTEM = (
    "/no_think\n너는 통신 프로토콜 명세를 읽고 로그 파서 설정을 만드는 도구다. "
    "명세의 '전문/패킷 형식(프레임 구조)' 표를 읽고 아래 JSON만 출력한다(설명 금지).\n"
    "필드: framing('length'=명령+길이+데이터+체크섬 / 'delimited'=시작~끝바이트), "
    "cmd{offset,size,type(ascii|hex)}, length{offset,size,endian(big|little)}, "
    "header_size(데이터 시작 오프셋), trailer_size(데이터 뒤 체크섬 바이트수), "
    "checksum{type(xor|lrc|sum|crc16|none),span(header_and_data|data)}, "
    "delimited면 start_byte,end_byte(정수).\n"
    "예1(길이형) Command(2 Char)+Length(2 Hex)+Data(n)+LRC(1) →"
    ' {"framing":"length","cmd":{"offset":0,"size":2,"type":"ascii"},'
    '"length":{"offset":2,"size":2,"endian":"big"},"header_size":4,"trailer_size":1,'
    '"checksum":{"type":"lrc","span":"header_and_data"}}\n'
    "예2(구분+길이형) STX(0x02)+LEN(1=CMD+DATA 바이트수)+CMD(1)+DATA(n)+CHK(1,XOR,STX/ETX제외)"
    "+ETX(0x03) → 길이 필드가 있으면 length·header_size·trailer_size 를 반드시 포함:"
    ' {"framing":"delimited","start_byte":2,"end_byte":3,'
    '"cmd":{"offset":2,"size":1,"type":"hex"},"length":{"offset":1,"size":1,"endian":"big"},'
    '"header_size":2,"trailer_size":2,"checksum":{"type":"xor","span":"data"}}'
)


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return None
    import json
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def derive_frame_structure(llm, spec_text: str) -> dict:
    """LLM으로 명세에서 프레임 구조(JSON)를 도출. 실패 시 None."""
    user = f"[프로토콜 명세 발췌]\n{spec_text[:6000]}\n\n위 명세의 프레임 구조를 JSON으로만 출력:"
    resp = llm.chat([{"role": "system", "content": _DERIVE_SYSTEM},
                     {"role": "user", "content": user}])
    return _extract_json(resp)


# LLM 도출이 실패/부실할 때 시도하는 '일반적' 프레임형(문서별 하드코딩 아님, 흔한 산업 표준 형태).
_FALLBACK_STRUCTS = [
    # 길이형: Command(2 ASCII) + Length(2) + Data + LRC(1)  — RF 모듈류
    {"framing": "length", "cmd": {"offset": 0, "size": 2, "type": "ascii"},
     "length": {"offset": 2, "size": 2, "endian": "big"}, "header_size": 4,
     "trailer_size": 1, "checksum": {"type": "lrc", "span": "header_and_data"}},
    # 구분+길이형: STX + LEN(1) + CMD(1 hex) + Data + CHK(1 XOR) + ETX
    {"framing": "delimited", "start_byte": 2, "end_byte": 3,
     "cmd": {"offset": 2, "size": 1, "type": "hex"}, "length": {"offset": 1, "size": 1, "endian": "big"},
     "header_size": 2, "trailer_size": 2, "checksum": {"type": "xor", "span": "data"}},
]


def _quality(res: dict) -> float:
    t = res.get("total", 0) or 0
    return (res.get("valid_count", 0) / t) if t else 0.0


def analyze_by_spec(text: str, spec_text: str, llm) -> dict:
    """선택 문서 기반 파싱: 줄형식(자동감지) + 프레임구조(LLM도출) → 범용 파서.

    도출 프로파일로 파싱한 뒤, 프레임이 없거나 체크섬 유효율이 낮으면 일반적 프레임형
    후보로 재파싱해 가장 유효한(프레임 있고 유효율 높은) 결과를 채택한다 → 도출 변동에도 안정.
    반환에 'profile'·'derived' 포함.
    """
    line_fmt = detect_line_format(text)
    candidates = []
    structure = derive_frame_structure(llm, spec_text)
    if structure and "framing" in structure:
        r = analyze_with_profile(text, {**structure, **line_fmt})
        r["derived"] = True
        candidates.append(r)
    best = candidates[0] if candidates else None
    # 도출 결과가 부실하면(0프레임 또는 유효율<0.5) 일반 후보들과 비교해 더 나은 것 채택
    if best is None or best.get("total", 0) == 0 or _quality(best) < 0.5:
        for st in _FALLBACK_STRUCTS:
            r = analyze_with_profile(text, {**st, **line_fmt})
            r["derived"] = True
            candidates.append(r)
        # 채택 기준: 유효 프레임 수(유효율×총수)가 최대인 것
        best = max(candidates, key=lambda r: (_quality(r), r.get("total", 0)))
    if best is None:
        return {"derived": False, "profile": None, "frames": [], "total": 0,
                "valid_count": 0, "note": "프레임 구조 도출·자동감지 모두 실패"}
    return best
