"""명세의 '필드표'(필드 | TYPE | LEN)를 스키마로 파싱하고, 프레임 DATA를 필드로 결정적 디코드.

카드번호 등 특정 필드값으로 필터링(Q2)하려면 LLM이 아니라 결정적 디코드가 필요하다.
필드표 예:  | 필드 | TYPE | LEN | 비고 |
            | 응답코드 | HEX | 1 | 0x00 : 정상 |
            | IDLSAM | ASCII | 16 | LSAM ID |
"""
from __future__ import annotations

import re

# | 이름 | TYPE | LEN | ...   (파이프 표) — TYPE 키워드로 헤더/잡음 배제
_FIELD_ROW = re.compile(
    r"\|\s*([^|]+?)\s*\|\s*(ASCII|HEX|BCD|BIN|CHAR|BYTE)\s*\|\s*(\d+)",
    re.IGNORECASE)
_SKIP = {"필드", "field", "type", "len", "이름"}


def parse_field_schema(text: str) -> list:
    """필드표 텍스트 → [{'name','type','len'}] (표 등장 순서 유지, 중복 이름 허용)."""
    out = []
    for m in _FIELD_ROW.finditer(text or ""):
        name = m.group(1).strip()
        if not name or name.lower() in _SKIP or name.strip("-") == "":
            continue
        out.append({"name": name, "type": m.group(2).upper(), "len": int(m.group(3))})
    return out


def decode_data(data, schema: list) -> list:
    """DATA 바이트를 스키마 순서대로 잘라 [{name,type,len,hex,value}] 반환.

    ASCII/CHAR → 문자열, HEX/BIN/BYTE → 대문자 hex, BCD → 숫자열. 남는 바이트는 무시,
    모자라면 있는 만큼만.
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
        out.append({"name": f["name"], "type": t, "len": f["len"], "hex": hx, "value": val})
        if i >= len(data):
            break
    return out


def format_decoded(decoded: list) -> str:
    """디코드 결과 → '이름 (타입,길이) : 값' 여러 줄."""
    return "\n".join(
        f"  {d['name']} ({d['type']},{d['len']}) : {d['hex']}"
        + (f"  ({d['value']})" if d["type"] in ("ASCII", "CHAR") else "")
        for d in decoded)
