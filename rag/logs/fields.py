"""명세의 '필드표'(필드 | TYPE | LEN | 설명)를 스키마로 파싱하고, 프레임 DATA를 결정적 디코드.

카드번호 등 특정 필드값으로 필터링(Q2)하려면 LLM이 아니라 결정적 디코드가 필요하다.
필드표 예:  | 필드 | TYPE | LEN | 비고 |
            | 응답코드 | HEX | 1 | 0x00 : 정상 |
            | MLDA | ASCII | 7 | 충전 요청 금액 |
설명(비고) 열은 '문서에 적힌 필드 의미'로 보존해 해석 표기에 쓴다(모델 추측 대체).
"""
from __future__ import annotations

import re

# | 이름 | TYPE | LEN | 설명…   (파이프 표) — TYPE 키워드로 헤더/잡음 배제.
# LEN 뒤 셀(비고/설명)이 있으면 함께 캡처.
_FIELD_ROW = re.compile(
    r"\|\s*([^|]+?)\s*\|\s*(ASCII|HEX|BCD|BIN|CHAR|BYTE)\s*\|\s*(\d+)\s*(?:\|([^|\n]*))?",
    re.IGNORECASE)
_SKIP = {"필드", "field", "type", "len", "이름"}


def parse_field_schema(text: str) -> list:
    """필드표 텍스트 → [{'name','type','len','desc'}] (표 등장 순서 유지, 중복 이름 허용)."""
    out = []
    for m in _FIELD_ROW.finditer(text or ""):
        name = m.group(1).strip()
        if not name or name.lower() in _SKIP or name.strip("-") == "":
            continue
        desc = (m.group(4) or "").strip()
        if set(desc) <= set("-: "):          # 마크다운 구분선/빈 셀은 설명 아님
            desc = ""
        out.append({"name": name, "type": m.group(2).upper(), "len": int(m.group(3)),
                    "desc": desc})
    return out


def _numeric(t: str, seg: list, val: str):
    """값의 기계적 숫자 해석(창작 없음): ASCII 숫자열·BCD → int, HEX/BIN/BYTE → big-endian int."""
    try:
        if t in ("ASCII", "CHAR"):
            v = val.strip()
            return int(v) if v.isdigit() else None       # "0002000" → 2000
        if t == "BCD":
            return int(val) if val.isdigit() else None
        if seg:                                          # HEX/BIN/BYTE → 10진수
            return int.from_bytes(bytes(seg), "big")
    except Exception:
        pass
    return None


def decode_data(data, schema: list) -> list:
    """DATA 바이트를 스키마 순서대로 잘라 [{name,type,len,desc,hex,value,num}] 반환.

    ASCII/CHAR → 문자열, HEX/BIN/BYTE → 대문자 hex, BCD → 숫자열. num = 기계적 숫자 해석
    (숫자로 볼 수 있을 때만; 선행 0 제거 효과). 남는 바이트는 무시, 모자라면 있는 만큼만.
    """
    data = list(data or [])
    out, i = [], 0
    for f in schema:
        seg = data[i:i + f["len"]]
        i += f["len"]
        hx = " ".join(f"{b:02X}" for b in seg)
        t = f["type"]
        if t in ("ASCII", "CHAR"):
            val = "".join(chr(b) if 32 <= b < 127 else "." for b in seg)
        elif t == "BCD":
            val = "".join(f"{b:02X}" for b in seg)      # BCD는 니블 그대로
        else:
            val = hx
        out.append({"name": f["name"], "type": t, "len": f["len"],
                    "desc": f.get("desc", ""), "hex": hx, "value": val,
                    "num": _numeric(t, seg, val)})
        if i >= len(data):
            break
    return out


def format_decoded(decoded: list) -> str:
    """디코드 결과 → '이름[=의미] (타입,길이) : 값' 여러 줄 (LLM 컨텍스트용)."""
    lines = []
    for d in decoded:
        label = d["name"] + (f"={d['desc']}" if d.get("desc") else "")
        tail = f"  {d['hex']}"
        if d["type"] in ("ASCII", "CHAR"):
            tail += f"  ({d['value']})"
        if d.get("num") is not None and str(d["num"]) != d["value"].strip():
            tail += f"  [숫자해석: {d['num']}]"
        lines.append(f"  {label} ({d['type']},{d['len']}) :{tail}")
    return "\n".join(lines)
