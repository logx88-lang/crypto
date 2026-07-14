"""로그 종류(HEX/자연어) 및 파싱 프로파일 자동 감지.

주의: framing/checksum 은 확정 명세에서 오는 것이 원칙. 여기서는 시작 바이트로 후보만 추정하며,
최종 확정은 UI 확인 단계에서 이뤄진다(docs/design.md §7).
"""
from __future__ import annotations

import re
from typing import Optional

from .profiles import (ParsingProfile, BUILTIN_PROFILES, TOK_BRACKET, TOK_0X,
                       TOK_BARE, TS_MMDD, TS_ISO, TS_RF, DIR_TXRX, DIR_ARROW,
                       CMD_MARKER)

_TS_ANY = re.compile(f"(?:{TS_MMDD})|(?:{TS_ISO})|(?:{TS_RF})")
_CMD_MARKER = re.compile(CMD_MARKER)
_DIR = re.compile(DIR_TXRX)
_DIR_ANY = re.compile(f"(?:{DIR_TXRX})|(?:{DIR_ARROW})|(?:{CMD_MARKER})")
_HANGUL_WORD = re.compile(r"[가-힣]{2,}")
_LONG_WORD = re.compile(r"[A-Za-z가-힣]{4,}")


def _strip_meta(line: str) -> str:
    line = _TS_ANY.sub(" ", line)
    line = _DIR_ANY.sub(" ", line)   # [TX]/[RX], ->TX:, CMD[XX] 등 구조 표기 제거
    return line


def _count(pattern: str, text: str) -> int:
    return len(re.findall(pattern, text))


def detect_log_type(text: str) -> str:
    """'hex' 또는 'natural' 반환.

    각 라인에서 타임스탬프/방향표시 제거 후 hex 토큰 수와 자연어 단어 수를 비교한다.
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return "natural"
    hex_lines, nat_lines = 0, 0
    for ln in lines:
        body = _strip_meta(ln)
        hex_tokens = max(_count(TOK_BRACKET, body), _count(TOK_0X, body), _count(TOK_BARE, body))
        words = len(_LONG_WORD.findall(body)) + len(_HANGUL_WORD.findall(body))
        if hex_tokens >= 2 and hex_tokens >= words:
            hex_lines += 1
        elif words >= 2:
            nat_lines += 1
        # 그 외(메타/CMD 마커만 남은 줄)는 중립 — 어느 쪽으로도 세지 않음
    return "hex" if hex_lines > nat_lines and hex_lines > 0 else "natural"


def detect_profile(text: str) -> Optional[ParsingProfile]:
    """HEX 로그의 토큰/타임스탬프/방향표시를 감지해 프로파일 후보를 고른다.

    시작 바이트로 framing/checksum 을 추정(0x02→XM-200류, 0x01→TG-15류).
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return None
    sample = "\n".join(lines[:30])

    # RF module류: CMD[XX] 명령 마커가 있으면 Command(2)+Length(2)+Data+LRC 프레이밍
    if _CMD_MARKER.search(sample):
        for p in BUILTIN_PROFILES:
            if p.name == "rf_cmd_len_lrc":
                return p

    counts = {
        "bracket": _count(TOK_BRACKET, sample),
        "0x": _count(TOK_0X, sample),
        "bare": _count(TOK_BARE, _DIR.sub(" ", _TS_ANY.sub(" ", sample))),
    }
    kind = max(counts, key=counts.get)
    if counts[kind] == 0:
        return None
    token = {"bracket": TOK_BRACKET, "0x": TOK_0X, "bare": TOK_BARE}[kind]
    has_ts = bool(_TS_ANY.search(sample))
    has_dir = bool(_DIR.search(sample))

    # 첫 라인의 첫 바이트로 framing/checksum 추정
    first_bytes = _line_bytes(lines[0], token, has_ts, has_dir)
    framing, start, end, chk = "none", None, None, "none"
    if first_bytes:
        b0 = first_bytes[0]
        if b0 == 0x02:
            framing, start, end, chk = "stx_etx", 0x02, 0x03, "xor"
        elif b0 == 0x01:
            framing, start, chk = "soh_crc", 0x01, "crc16_ccitt"

    return ParsingProfile(
        name=f"detected_{kind}",
        byte_token=token,
        timestamp_regex=TS_MMDD if has_ts else None,
        direction_regex=DIR_TXRX if has_dir else None,
        framing=framing, start_byte=start, end_byte=end, checksum=chk,
    )


def _line_bytes(line: str, token: str, has_ts: bool, has_dir: bool) -> list:
    body = line
    if has_ts:
        body = _TS_ANY.sub(" ", body)
    if has_dir:
        body = _DIR.sub(" ", body)
    return [int(h, 16) for h in re.findall(token, body)]
