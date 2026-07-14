"""로그 → 바이트 복원 + 프레이밍/체크섬 검증 + 최소 필드 해석.

프레이밍/체크섬 규칙은 프로파일(확정 명세 유래)에서 온다. 텍스트 로그는 '라인=1프레임'을 기본으로 하고,
바이너리(.dat)는 시작/종료 바이트로 스트림을 프레이밍한다.
"""
from __future__ import annotations

import re
from typing import Optional

from .profiles import ParsingProfile
from .detect import detect_log_type, detect_profile, _TS_ANY, _DIR


# --- 체크섬 ---------------------------------------------------------------
def xor_checksum(data: bytes) -> int:
    c = 0
    for b in data:
        c ^= b
    return c


def crc16_ccitt(data: bytes, crc: int = 0xFFFF) -> int:
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if (crc & 0x8000) else (crc << 1) & 0xFFFF
    return crc


def lrc_checksum(data: bytes) -> int:
    """LRC = 바이트 XOR 누적 (RF module 등). Command+Length+Data 대상."""
    c = 0
    for b in data:
        c ^= b
    return c


def reconstruct_bytes(line: str, profile: ParsingProfile) -> list:
    """한 라인에서 타임스탬프/방향표시/구분자를 제거하고 hex 바이트 리스트로 복원."""
    body = line
    if profile.timestamp_regex:
        body = re.sub(profile.timestamp_regex, " ", body)
    if profile.direction_regex:
        body = re.sub(profile.direction_regex, " ", body)
    return [int(h, 16) for h in re.findall(profile.byte_token, body)]


# --- 프레임 검증 -----------------------------------------------------------
def verify_frame(frame: list, profile: ParsingProfile) -> dict:
    """프로파일 규칙으로 프레임 유효성 검증 + 최소 필드 추출."""
    b = bytes(frame)
    res = {"bytes": frame, "hex": " ".join(f"{x:02X}" for x in frame),
           "valid": False, "cmd": None, "note": ""}
    if profile.framing == "stx_etx" and profile.checksum == "xor":
        if len(b) >= 5 and b[0] == 0x02 and b[-1] == 0x03:
            calc = xor_checksum(b[1:-2])
            res["valid"] = (calc == b[-2])
            res["cmd"] = b[2]
            res["data"] = list(b[3:-2])
            if not res["valid"]:
                res["note"] = f"XOR 불일치(calc=0x{calc:02X}, chk=0x{b[-2]:02X})"
        else:
            res["note"] = "STX/ETX 프레이밍 불일치"
    elif profile.framing == "soh_crc" and profile.checksum == "crc16_ccitt":
        if len(b) >= 7 and b[0] == 0x01:
            calc = crc16_ccitt(b[:-2])
            rx = (b[-2] << 8) | b[-1]
            res["valid"] = (calc == rx)
            res["cmd"] = b[2]
            res["data"] = list(b[5:-2])
            if not res["valid"]:
                res["note"] = f"CRC16 불일치(calc=0x{calc:04X}, rx=0x{rx:04X})"
        else:
            res["note"] = "SOH 프레이밍 불일치"
    else:
        # 프레이밍 미상: 바이트만 복원(사용자 명세 확인 필요)
        res["note"] = "프레이밍 미확정(명세 확인 필요)"
        res["cmd"] = b[2] if len(b) >= 3 else None
    return res


# --- 상위 진입점 -----------------------------------------------------------
def analyze_text_log(text: str, profile: Optional[ParsingProfile] = None) -> dict:
    """텍스트 로그 분석. profile 미지정 시 자동 감지.

    반환: {log_type, profile, frames|lines, valid_count, total}
    """
    log_type = detect_log_type(text)
    if log_type == "natural":
        lines = [ln for ln in text.splitlines() if ln.strip()]
        return {"log_type": "natural", "profile": None,
                "lines": lines, "total": len(lines),
                "note": "자연어 로그 — 바이트 파싱 없이 텍스트+명세로 LLM 해석 경로."}

    profile = profile or detect_profile(text)
    if profile and profile.framing == "cmd_len_lrc":
        return analyze_cmd_len_log(text, profile)   # 프레임이 여러 줄에 걸침 → 스트림 파싱
    frames = []
    valid = 0
    for ln in text.splitlines():
        if not ln.strip():
            continue
        bts = reconstruct_bytes(ln, profile)
        if not bts:
            continue
        fr = verify_frame(bts, profile)
        frames.append(fr)
        if fr["valid"]:
            valid += 1
    return {"log_type": "hex", "profile": profile, "frames": frames,
            "valid_count": valid, "total": len(frames)}


def analyze_cmd_len_log(text: str, profile: ParsingProfile) -> dict:
    """Command(2 ASCII)+Length(2)+Data(n)+LRC(1) 프레이밍 (RF module류).

    프레임이 여러 줄에 걸치므로 전체 [hh] 바이트를 이어붙여 하나의 스트림으로 만든 뒤
    Length 필드로 프레임을 분할한다(STX/ETX 불필요). LRC = Command+Length+Data 의 XOR.
    """
    stream = []
    for ln in text.splitlines():
        if ln.strip():
            stream.extend(reconstruct_bytes(ln, profile))
    frames, valid = [], 0
    i, n = 0, len(stream)
    while i + 5 <= n:                      # 최소 프레임 = Cmd2+Len2+LRC1
        length = (stream[i + 2] << 8) | stream[i + 3]
        total = length + 5                # Cmd2 + Len2 + Data(length) + LRC1
        if i + total > n:
            break
        frame = stream[i:i + total]
        cmd_ascii = bytes(frame[0:2]).decode("ascii", "replace")
        data = frame[4:4 + length]
        lrc = frame[-1]
        calc = lrc_checksum(frame[0:4 + length])   # Command+Length+Data
        ok = (calc == lrc)
        frames.append({
            "bytes": frame, "hex": " ".join(f"{x:02X}" for x in frame),
            "cmd": None, "cmd_ascii": cmd_ascii, "length": length,
            "data": list(data),
            "data_ascii": "".join(chr(b) if 32 <= b < 127 else "." for b in data),
            "lrc": lrc, "valid": ok,
            "note": "" if ok else f"LRC 불일치(계산 0x{calc:02X}, 값 0x{lrc:02X})",
        })
        valid += int(ok)
        i += total
    return {"log_type": "hex", "profile": profile, "frames": frames,
            "valid_count": valid, "total": len(frames)}


def analyze_binary_log(data: bytes, profile: ParsingProfile) -> dict:
    """바이너리(.dat) 스트림을 프레이밍(현재 stx_etx, 길이필드 기반).

    STX/ETX 프레임은 DATA/LEN 안에 ETX(0x03) 바이트가 나타날 수 있으므로 ETX 검색이 아니라
    LEN 필드로 프레임 길이를 계산한다: 전체길이 = LEN + 4 (STX+LEN+...+CHK+ETX).
    """
    frames = []
    valid = 0
    if profile.framing == "stx_etx" and profile.start_byte is not None:
        i = 0
        n = len(data)
        while i < n:
            if data[i] != profile.start_byte:
                i += 1
                continue
            if i + 1 >= n:
                break
            length = data[i + 1]
            flen = length + 4  # STX + LEN + (CMD+DATA=length) + CHK + ETX
            frame = list(data[i:i + flen])
            if len(frame) == flen and frame[-1] == profile.end_byte:
                fr = verify_frame(frame, profile)
                frames.append(fr)
                valid += int(fr["valid"])
                i += flen
            else:
                i += 1
    return {"log_type": "hex", "profile": profile, "frames": frames,
            "valid_count": valid, "total": len(frames)}
