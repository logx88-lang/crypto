"""장비별 파싱 프로파일 — 포맷이 장비마다 달라 하드코딩 대신 설정으로 표현한다."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsingProfile:
    name: str
    byte_token: str                      # 2-hex를 캡처하는 정규식(그룹1)
    timestamp_regex: Optional[str] = None
    direction_regex: Optional[str] = None   # 예: r"\[(TX|RX)\]"
    framing: str = "none"                # 'stx_etx' | 'soh_crc' | 'none'
    start_byte: Optional[int] = None
    end_byte: Optional[int] = None
    checksum: str = "none"               # 'xor' | 'crc16_ccitt' | 'none'
    endian: str = "big"


# 공통 정규식 조각
TS_MMDD = r"\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}"
TS_ISO = r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}"
TS_RF = r"\[\d{8}\s+\d{2}:\d{2}:\d{2}\]"        # [20260714 02:05:00]
DIR_TXRX = r"\[(TX|RX)\]"
DIR_ARROW = r"->(?:TX|RX)\s*:"                   # ->TX : / ->RX :
CMD_MARKER = r"CMD\[[A-Za-z]{2}\]"              # CMD[SD] (명령명 표기 줄)

TOK_BRACKET = r"\[([0-9a-fA-F]{2})\]"
TOK_0X = r"0x([0-9a-fA-F]{2})"
TOK_BARE = r"(?<![0-9a-fA-Fx])\b([0-9a-fA-F]{2})\b(?![0-9a-fA-F])"


BUILTIN_PROFILES = [
    ParsingProfile(
        name="xm200_bracket",
        byte_token=TOK_BRACKET, timestamp_regex=TS_MMDD,
        framing="stx_etx", start_byte=0x02, end_byte=0x03, checksum="xor",
    ),
    ParsingProfile(
        name="xm200_0x",
        byte_token=TOK_0X, timestamp_regex=TS_MMDD,
        framing="stx_etx", start_byte=0x02, end_byte=0x03, checksum="xor",
    ),
    ParsingProfile(
        name="tg15_space",
        byte_token=TOK_BARE, timestamp_regex=TS_MMDD, direction_regex=DIR_TXRX,
        framing="soh_crc", start_byte=0x01, checksum="crc16_ccitt",
    ),
    # RF module류: Command(2 ASCII) + Length(2) + Data(n) + LRC(1), STX/ETX 아님
    ParsingProfile(
        name="rf_cmd_len_lrc",
        byte_token=TOK_BRACKET, timestamp_regex=TS_RF,
        direction_regex=f"(?:{DIR_ARROW})|(?:{CMD_MARKER})",   # 방향표시+CMD명 줄 제거
        framing="cmd_len_lrc", checksum="lrc",
    ),
    # 프레이밍/체크섬 미상 — 토큰만 해석(사용자 명세 확인 후 프레이밍 확정)
    ParsingProfile(name="generic_bracket", byte_token=TOK_BRACKET, timestamp_regex=TS_MMDD),
    ParsingProfile(name="generic_0x", byte_token=TOK_0X, timestamp_regex=TS_MMDD),
    ParsingProfile(name="generic_space", byte_token=TOK_BARE,
                   timestamp_regex=TS_MMDD, direction_regex=DIR_TXRX),
]
