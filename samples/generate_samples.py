#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""더미 샘플 세트 생성기 (검토 게이트용).

실제 사내 자료가 없으므로, 실제와 유사한 구조의 **가상** 더미 문서를 생성한다.
- 가상 장비 2종의 통신 프로토콜 명세(PDF + Word) : 표 중심, 명령 코드 다수
- 그 명세를 따르는 HEX 통신 로그(.txt/.dat, 타임스탬프 유/무, [XX] 토큰/구분자)
- 일반 지식 문서(xlsx/docx/pptx/txt, 표·이미지 포함, 인코딩 혼합)
- OCR용 이미지(한/영 혼용 다이어그램 PNG)

주의: 모든 내용은 허구다. 실제 장비/규격과 무관하며 검토 게이트에서 사용자가 실제 자료와
대조해 수정 피드백을 준다. HEX 프레임은 명세의 체크섬 규칙에 맞게 생성되어 자체 정합성을 갖는다.

실행: python3 samples/generate_samples.py
출력: samples/dummy_set/{protocol,hex,docs,images}/
"""
import os
import struct

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dummy_set")
DIRS = {k: os.path.join(BASE, k) for k in ("protocol", "hex", "docs", "images")}


def ensure_dirs():
    for d in DIRS.values():
        os.makedirs(d, exist_ok=True)


# ----------------------------------------------------------------------------
# XM-200 코인 처리 컨트롤러 프로토콜 (HEX 로그가 따르는 규격)
#   프레임: [STX=0x02][LEN][CMD][DATA...][CHK][ETX=0x03]
#   LEN = 1(CMD) + len(DATA)
#   CHK = XOR( LEN, CMD, DATA... )   (STX/ETX 제외)
#   다바이트 값은 big-endian
# ----------------------------------------------------------------------------
STX, ETX = 0x02, 0x03

XM200_COMMANDS = [
    (0x10, "INIT",        "초기화 요청 / Initialize"),
    (0x11, "STATUS",      "상태 조회 / Query status"),
    (0x12, "COIN_IN",     "코인 투입 통지 / Coin inserted (DATA: 개수)"),
    (0x13, "COIN_OUT",    "코인 배출 / Coin payout (DATA: 개수)"),
    (0x14, "DISPENSE",    "금액 지급 / Dispense amount (DATA: 금액 2B)"),
    (0x15, "RESET",       "리셋 / Reset controller"),
    (0x16, "BALANCE",     "잔액 조회 / Query balance"),
    (0x17, "LOCK",        "투입구 잠금 / Lock acceptor"),
    (0x18, "UNLOCK",      "투입구 해제 / Unlock acceptor"),
    (0x20, "ERROR",       "에러 통지 / Error report (DATA: 코드)"),
    (0x21, "JAM",         "코인 잼 발생 / Coin jam"),
    (0x30, "CONFIG_SET",  "설정 쓰기 / Set config (DATA: key,val)"),
    (0x31, "CONFIG_GET",  "설정 읽기 / Get config (DATA: key)"),
    (0x40, "HEARTBEAT",   "하트비트 / Heartbeat"),
    (0x41, "ACK",         "정상 응답 / Acknowledge"),
    (0x42, "NAK",         "비정상 응답 / Negative ack (DATA: 사유)"),
    (0x50, "LOG_REQ",     "로그 요청 / Request log"),
]

XM200_ERRORS = [
    (0x01, "COIN_JAM",     "코인 걸림 / Coin jam detected"),
    (0x02, "OVERFLOW",     "호퍼 넘침 / Hopper overflow"),
    (0x03, "EMPTY",        "코인 부족 / Hopper empty"),
    (0x04, "SENSOR_FAIL",  "센서 오류 / Sensor failure"),
    (0x05, "CHKSUM_ERR",   "체크섬 오류 / Checksum error"),
    (0x06, "TIMEOUT",      "응답 시간 초과 / Timeout"),
]


def xm200_frame(cmd, data=b""):
    length = 1 + len(data)
    body = bytes([length, cmd]) + data
    chk = 0
    for b in body:
        chk ^= b
    return bytes([STX]) + body + bytes([chk, ETX])


def bracket(frame, sep=""):
    return sep.join(f"[{b:02x}]" for b in frame)


# --- TG-15 프레임(장비별 포맷이 다름을 보여주기 위한 다른 규격) -------------------
#   [SOH=0x01][ADDR][CMD][LEN(2,BE)][PAYLOAD][CRC16(2,BE)]  CRC-16/CCITT(SOH~PAYLOAD)
SOH = 0x01


def crc16_ccitt(data, crc=0xFFFF):
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if (crc & 0x8000) else (crc << 1) & 0xFFFF
    return crc


def tg15_frame(addr, cmd, payload=b""):
    body = bytes([SOH, addr, cmd]) + struct.pack(">H", len(payload)) + payload
    crc = crc16_ccitt(body)
    return body + struct.pack(">H", crc)


# ----------------------------------------------------------------------------
# 1) 프로토콜 명세 — PDF (XM-200) : reportlab, 한글 CID 폰트
# ----------------------------------------------------------------------------
def make_protocol_pdf():
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, PageBreak)

    pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
    FONT = "HYSMyeongJo-Medium"
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontName=FONT, fontSize=15)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName=FONT, fontSize=12)
    body = ParagraphStyle("body", parent=styles["Normal"], fontName=FONT, fontSize=9, leading=13)

    path = os.path.join(DIRS["protocol"], "XM-200_coin_controller_protocol.pdf")
    doc = SimpleDocTemplate(path, pagesize=A4, topMargin=18*mm, bottomMargin=18*mm)
    el = []

    el.append(Paragraph("XM-200 코인 처리 컨트롤러 통신 프로토콜 명세서", h1))
    el.append(Paragraph("XM-200 Coin Controller Serial Communication Protocol (v1.3)", body))
    el.append(Spacer(1, 6))
    el.append(Paragraph("본 문서는 가상의 장비 XM-200과 상위 제어기(Host) 간 RS-232 시리얼 통신 "
                        "규격을 정의한다. 통신 속도 9600bps, 8N1. 모든 다바이트 값은 big-endian이다.", body))

    el.append(Paragraph("1. 패킷 구조 (Packet Structure)", h2))
    pkt = [["필드", "크기(byte)", "값/설명"],
           ["STX", "1", "0x02 (프레임 시작)"],
           ["LEN", "1", "CMD+DATA 길이 = 1 + len(DATA)"],
           ["CMD", "1", "명령 코드 (2장 표 참조)"],
           ["DATA", "N", "명령별 파라미터 (가변)"],
           ["CHK", "1", "XOR(LEN, CMD, DATA...) — STX/ETX 제외"],
           ["ETX", "1", "0x03 (프레임 끝)"]]
    t = Table(pkt, colWidths=[70, 70, 300])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), FONT, 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfe7f2")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    el.append(t)
    el.append(Spacer(1, 8))

    el.append(Paragraph("2. 명령 코드 (Command Codes)", h2))
    rows = [["CMD(hex)", "이름", "설명"]]
    for code, name, desc in XM200_COMMANDS:
        rows.append([f"0x{code:02X}", name, desc])
    t = Table(rows, colWidths=[60, 90, 290])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), FONT, 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfe7f2")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6fa")])]))
    el.append(t)
    el.append(Spacer(1, 8))

    el.append(Paragraph("3. 에러 코드 (Error Codes) — CMD=0x20 ERROR 의 DATA", h2))
    rows = [["코드(hex)", "이름", "설명"]]
    for code, name, desc in XM200_ERRORS:
        rows.append([f"0x{code:02X}", name, desc])
    t = Table(rows, colWidths=[60, 90, 290])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), FONT, 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2e0e0")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey)]))
    el.append(t)
    el.append(Spacer(1, 8))

    el.append(Paragraph("4. 예시 (Examples)", h2))
    ex_init = xm200_frame(0x10)
    ex_coin = xm200_frame(0x12, bytes([0x01]))
    ex_disp = xm200_frame(0x14, struct.pack(">H", 500))
    ex_err = xm200_frame(0x20, bytes([0x03]))
    for label, fr in [("INIT 초기화", ex_init),
                      ("COIN_IN 코인 1개 투입", ex_coin),
                      ("DISPENSE 500원 지급", ex_disp),
                      ("ERROR 코인 부족(0x03)", ex_err)]:
        el.append(Paragraph(f"· {label} : {bracket(fr)}  "
                            f"(hex: {' '.join(f'{b:02X}' for b in fr)})", body))

    # --- 실제 자료 반영: 문서당 표·페이지가 많음 → 추가 표들을 여러 페이지로 확장 ---
    def styled(rows, widths, head="#dfe7f2"):
        t = Table(rows, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, -1), FONT, 7.5),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(head)),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6fa")])]))
        return t

    el.append(PageBreak())
    el.append(Paragraph("5. 레지스터 맵 (Register Map)", h2))
    reg = [["주소(hex)", "이름", "R/W", "설명"]]
    regdefs = [("코인 카운터", "R"), ("잔액 상위", "R"), ("잔액 하위", "R"),
               ("호퍼 레벨", "R"), ("잠금 상태", "RW"), ("에러 래치", "RW"),
               ("펌웨어 버전", "R"), ("시리얼 번호", "R"), ("설정 플래그", "RW"),
               ("하트비트 주기", "RW"), ("통신 속도", "RW"), ("장비 주소", "RW")]
    for i, (nm, rw) in enumerate(regdefs):
        reg.append([f"0x{0x40+i:02X}", nm, rw, f"{nm} 레지스터 / {nm} register"])
    el.append(styled(reg, [55, 90, 40, 255]))
    el.append(Spacer(1, 8))

    el.append(Paragraph("6. 상태 비트필드 (STATUS 응답 1바이트)", h2))
    bits = [["비트", "이름", "0", "1"]]
    bitdefs = [("READY 준비", "미준비", "준비완료"), ("BUSY 처리중", "대기", "처리중"),
               ("JAM 잼", "정상", "잼발생"), ("EMPTY 부족", "충분", "부족"),
               ("LOCK 잠금", "해제", "잠금"), ("ERROR 에러", "정상", "에러"),
               ("HOPPER 호퍼", "정상", "이상"), ("RSV 예약", "-", "-")]
    for i, (nm, z, o) in enumerate(bitdefs):
        bits.append([f"b{i}", nm, z, o])
    el.append(styled(bits, [40, 130, 135, 135]))
    el.append(Spacer(1, 8))

    el.append(Paragraph("7. 타이밍 파라미터 (Timing)", h2))
    tim = [["항목", "최소", "표준", "최대", "단위"],
           ["응답 지연 T_resp", "5", "20", "100", "ms"],
           ["프레임 간격 T_gap", "2", "10", "50", "ms"],
           ["재전송 대기 T_retry", "100", "200", "500", "ms"],
           ["하트비트 주기 T_hb", "5", "10", "30", "s"],
           ["타임아웃 T_out", "0.5", "1.0", "3.0", "s"]]
    el.append(styled(tim, [150, 70, 70, 70, 60]))
    el.append(Spacer(1, 8))

    el.append(PageBreak())
    el.append(Paragraph("8. 응답 코드 (Response / NAK 사유)", h2))
    nak = [["코드(hex)", "이름", "설명"]]
    nakdefs = [("BAD_CHK", "체크섬 불일치"), ("BAD_LEN", "길이 오류"),
               ("UNK_CMD", "미지원 명령"), ("BUSY", "장비 사용중"),
               ("RANGE", "파라미터 범위 초과"), ("NO_COIN", "코인 없음"),
               ("LOCKED", "투입구 잠김"), ("FAULT", "하드웨어 장애")]
    for i, (nm, desc) in enumerate(nakdefs):
        nak.append([f"0x{0x80+i:02X}", nm, desc])
    el.append(styled(nak, [60, 100, 280], head="#f2e0e0"))
    el.append(Spacer(1, 8))

    el.append(Paragraph("9. 설정 키 (CONFIG 키 목록)", h2))
    cfg = [["키(hex)", "이름", "기본값", "범위"]]
    cfgdefs = [("장비 주소", "0x01", "0x01~0x1F"), ("통신 속도", "9600", "9600~115200"),
               ("하트비트", "10s", "5~30s"), ("자동 잠금", "OFF", "ON/OFF"),
               ("코인 단위", "100", "10~1000"), ("호퍼 경보 레벨", "20", "0~100"),
               ("재시도 횟수", "3", "0~10"), ("로그 보관", "7일", "1~90일")]
    for i, (nm, dv, rng) in enumerate(cfgdefs):
        cfg.append([f"0x{0x10+i:02X}", nm, dv, rng])
    el.append(styled(cfg, [55, 120, 110, 150]))

    doc.build(el)
    return path


# ----------------------------------------------------------------------------
# 2) 프로토콜 명세 — Word (TG-15) : 구조가 다른 프레임(후보 구분 테스트용)
#   프레임: [SOH=0x01][ADDR][CMD][LEN(2)][PAYLOAD][CRC16(2)]
# ----------------------------------------------------------------------------
TG15_COMMANDS = [
    (0x41, "RD_TEMP",   "온도 읽기 / Read temperature (0.1도 단위, 2B)"),
    (0x42, "RD_HUMID",  "습도 읽기 / Read humidity (%RH, 2B)"),
    (0x43, "RD_ALL",    "전체 센서 읽기 / Read all sensors"),
    (0x50, "SET_TH",    "임계값 설정 / Set threshold (PAYLOAD: min,max)"),
    (0x51, "GET_TH",    "임계값 조회 / Get threshold"),
    (0x60, "ALARM",     "알람 통지 / Alarm event (PAYLOAD: 채널,상태)"),
    (0x61, "CLR_ALARM", "알람 해제 / Clear alarm"),
    (0x70, "PING",      "연결 확인 / Ping"),
    (0x71, "PONG",      "응답 / Pong"),
    (0x7F, "FAULT",     "장애 통지 / Fault report"),
]


def make_protocol_docx():
    from docx import Document
    from docx.shared import Pt, RGBColor
    doc = Document()
    doc.add_heading("TG-15 센서 게이트웨이 통신 프로토콜 명세서", level=0)
    p = doc.add_paragraph("TG-15 Sensor Gateway Communication Protocol (v2.0)")
    p.runs[0].italic = True
    doc.add_paragraph("본 문서는 가상의 온·습도 센서 게이트웨이 TG-15의 통신 규격을 정의한다. "
                      "RS-485 멀티드롭, 통신 속도 19200bps. XM-200과 달리 SOH 시작 + CRC16 검증을 사용한다.")

    doc.add_heading("1. 패킷 구조 (Packet Structure)", level=1)
    tbl = doc.add_table(rows=1, cols=3)
    tbl.style = "Light Grid Accent 1"
    hdr = tbl.rows[0].cells
    hdr[0].text, hdr[1].text, hdr[2].text = "필드", "크기(byte)", "값/설명"
    for f, sz, desc in [
        ("SOH", "1", "0x01 (프레임 시작)"),
        ("ADDR", "1", "슬레이브 주소 (0x01~0x1F)"),
        ("CMD", "1", "명령 코드 (2장 표 참조)"),
        ("LEN", "2", "PAYLOAD 길이 (big-endian)"),
        ("PAYLOAD", "N", "명령별 데이터"),
        ("CRC16", "2", "CRC-16/CCITT (SOH~PAYLOAD)"),
    ]:
        c = tbl.add_row().cells
        c[0].text, c[1].text, c[2].text = f, sz, desc

    doc.add_heading("2. 명령 코드 (Command Codes)", level=1)
    tbl = doc.add_table(rows=1, cols=3)
    tbl.style = "Light Grid Accent 1"
    h = tbl.rows[0].cells
    h[0].text, h[1].text, h[2].text = "CMD(hex)", "이름", "설명"
    for code, name, desc in TG15_COMMANDS:
        c = tbl.add_row().cells
        c[0].text, c[1].text, c[2].text = f"0x{code:02X}", name, desc

    doc.add_heading("3. 예시 (Examples)", level=1)
    doc.add_paragraph("· RD_TEMP 온도 읽기 요청: 01 05 41 00 00 <CRC16>  (ADDR=0x05)")
    doc.add_paragraph("· ALARM 알람 통지: 01 05 60 00 02 03 01 <CRC16>  (채널3, 상태=경보)")
    doc.add_paragraph("주의: 본 규격은 XM-200(STX/ETX/XOR)과 혼동하지 말 것. 프레임 시작 바이트가 "
                      "0x01(SOH)이면 TG-15, 0x02(STX)이면 XM-200이다.", )

    path = os.path.join(DIRS["protocol"], "TG-15_sensor_gateway_protocol.docx")
    doc.save(path)
    return path


# ----------------------------------------------------------------------------
# 3) HEX 로그 — XM-200 규격을 따르는 세션 (여러 포맷)
# ----------------------------------------------------------------------------
def build_session_frames():
    """코인 투입→잔액→지급→에러 시나리오 프레임 목록."""
    seq = [
        ("INIT",      xm200_frame(0x10)),
        ("ACK",       xm200_frame(0x41)),
        ("STATUS",    xm200_frame(0x11)),
        ("ACK",       xm200_frame(0x41)),
        ("COIN_IN 1", xm200_frame(0x12, bytes([0x01]))),
        ("COIN_IN 1", xm200_frame(0x12, bytes([0x01]))),
        ("BALANCE",   xm200_frame(0x16)),
        ("DISPENSE 500", xm200_frame(0x14, struct.pack(">H", 500))),
        ("HEARTBEAT", xm200_frame(0x40)),
        ("COIN_IN 1", xm200_frame(0x12, bytes([0x01]))),
        ("JAM",       xm200_frame(0x21)),
        ("ERROR JAM", xm200_frame(0x20, bytes([0x01]))),
        ("RESET",     xm200_frame(0x15)),
        ("ACK",       xm200_frame(0x41)),
        ("HEARTBEAT", xm200_frame(0x40)),
    ]
    return seq


def ts(i):
    base_m, base_s = 45, 5
    total = base_s + i * 2
    mm = base_m + total // 60
    ss = total % 60
    return f"07/08 00:{mm:02d}:{ss:02d}"


def make_hex_logs():
    seq = build_session_frames()
    paths = []

    # 포맷1: 타임스탬프 + [XX]-[XX] (구분자 '-')
    p1 = os.path.join(DIRS["hex"], "coin_log_dash.txt")
    with open(p1, "w", encoding="utf-8") as f:
        for i, (_, fr) in enumerate(seq):
            f.write(f"{ts(i)} {bracket(fr, '-')}\n")
    paths.append(p1)

    # 포맷2: 타임스탬프 + [XX][XX]
    p2 = os.path.join(DIRS["hex"], "coin_log_ts.txt")
    with open(p2, "w", encoding="utf-8") as f:
        for i, (_, fr) in enumerate(seq):
            f.write(f"{ts(i)} {bracket(fr)}\n")
    paths.append(p2)

    # 포맷3: 타임스탬프 없음 [XX][XX]  (짧은 예시, 사용자 예시 aee.txt 유사)
    p3 = os.path.join(DIRS["hex"], "aee.txt")
    with open(p3, "w", encoding="utf-8") as f:
        for _, fr in seq[:6]:
            f.write(f"{bracket(fr)}\n")
    paths.append(p3)

    # 포맷4: 바이너리 덤프 .dat (프레임 연속)
    p4 = os.path.join(DIRS["hex"], "eefe.dat")
    with open(p4, "wb") as f:
        for _, fr in seq:
            f.write(fr)
    paths.append(p4)

    # 포맷5: (장비별 상이) 공백 구분 + 0x 접두 — XM-200이라도 로거가 다르면 표기가 다름
    p5 = os.path.join(DIRS["hex"], "coin_log_space0x.txt")
    with open(p5, "w", encoding="utf-8") as f:
        for i, (_, fr) in enumerate(seq):
            f.write(f"{ts(i)} " + " ".join(f"0x{b:02X}" for b in fr) + "\n")
    paths.append(p5)

    # 포맷6: 다른 장비(TG-15) — 완전히 다른 프레임/구분자([TX]/[RX] 방향 표시, 공백 hex)
    p6 = os.path.join(DIRS["hex"], "sensor_log_tg15.txt")
    tg_seq = [
        ("TX", tg15_frame(0x05, 0x41)),                       # RD_TEMP 요청
        ("RX", tg15_frame(0x05, 0x41, struct.pack(">h", 250))),  # 25.0도
        ("TX", tg15_frame(0x05, 0x42)),                       # RD_HUMID 요청
        ("RX", tg15_frame(0x05, 0x42, struct.pack(">H", 47))),   # 47%RH
        ("RX", tg15_frame(0x05, 0x60, bytes([0x03, 0x01]))),     # ALARM ch3
    ]
    with open(p6, "w", encoding="utf-8") as f:
        for i, (dirn, fr) in enumerate(tg_seq):
            f.write(f"07/08 01:1{i}:00 [{dirn}] " + " ".join(f"{b:02X}" for b in fr) + "\n")
    paths.append(p6)

    # 포맷7: 자연어(사람이 읽는) 로그 — hex가 아님
    p7 = os.path.join(DIRS["hex"], "event_log_natural.txt")
    with open(p7, "w", encoding="utf-8") as f:
        f.write(
            "2024-07-08 09:12:03 [XM-200] 코인 투입 감지: 1개, 누적 잔액 500원\n"
            "2024-07-08 09:12:05 [XM-200] DISPENSE 요청 처리: 500원 지급 완료 (hopper level 63%)\n"
            "2024-07-08 09:12:31 [XM-200] WARN 코인 잼 감지(JAM), 사용자 재시도 유도\n"
            "2024-07-08 09:12:33 [XM-200] RESET 수행 후 정상 복귀\n"
            "2024-07-08 09:12:40 [TG-15] 온도 경보: 채널3 52.3도 (임계 50.0도 초과)\n"
            "2024-07-08 09:12:41 [TG-15] ALARM raised on CH3, status=WARN, ack required\n"
            "2024-07-08 09:13:10 [TG-15] 담당자 확인 후 알람 해제(CLR_ALARM)\n"
        )
    paths.append(p7)

    return paths, seq


# ----------------------------------------------------------------------------
# 4) 이미지 — 한/영 혼용 다이어그램 PNG (OCR 샘플)
# ----------------------------------------------------------------------------
def _font(size):
    from PIL import ImageFont
    for path in ["/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                 "/usr/share/fonts/opentype/unifont/unifont.otf"]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def make_images():
    from PIL import Image, ImageDraw
    paths = []
    img = Image.new("RGB", (760, 420), "white")
    d = ImageDraw.Draw(img)
    f_title = _font(26)
    f = _font(18)
    f_s = _font(15)
    d.text((20, 16), "시스템 구성도 / System Architecture", font=f_title, fill="black")
    # 박스들
    boxes = [((40, 90), (240, 170), "상위 제어기\nHost Controller"),
             ((300, 90), (500, 170), "XM-200\n코인 컨트롤러"),
             ((560, 90), (720, 170), "코인 호퍼\nHopper"),
             ((300, 250), (500, 330), "TG-15\n센서 게이트웨이")]
    for (x0, y0), (x1, y1), label in boxes:
        d.rectangle([x0, y0, x1, y1], outline="navy", width=2)
        d.multiline_text((x0 + 12, y0 + 18), label, font=f, fill="navy", spacing=4)
    d.line([240, 130, 300, 130], fill="black", width=2)
    d.line([500, 130, 560, 130], fill="black", width=2)
    d.line([400, 170, 400, 250], fill="black", width=2)
    d.text((250, 108), "RS-232", font=f_s, fill="darkred")
    d.text((250, 200), "RS-485", font=f_s, fill="darkred")
    p1 = os.path.join(DIRS["images"], "system_diagram.png")
    img.save(p1)
    paths.append(p1)
    return paths


# ----------------------------------------------------------------------------
# 5) 일반 지식 문서 — xlsx / docx / pptx / txt(인코딩 혼합)
# ----------------------------------------------------------------------------
def make_xlsx():
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "장비목록"
    # 다중 헤더 + 병합셀
    ws.merge_cells("A1:A2"); ws["A1"] = "자산번호\nAsset ID"
    ws.merge_cells("B1:C1"); ws["B1"] = "장비 정보 / Device"
    ws.merge_cells("D1:E1"); ws["D1"] = "설치 / Installation"
    ws["B2"] = "모델"; ws["C2"] = "제조사"; ws["D2"] = "위치"; ws["E2"] = "설치일"
    fill = PatternFill("solid", fgColor="DCE6F2")
    for c in ["A1", "B1", "D1", "B2", "C2", "D2", "E2"]:
        ws[c].font = Font(bold=True); ws[c].fill = fill
        ws[c].alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    rows = [
        ["EQ-1001", "XM-200", "가상코인테크 / VirtualCoinTech", "1층 로비 / Lobby", "2024-03-11"],
        ["EQ-1002", "TG-15", "센서웨이 / SensorWay", "2층 기계실 / Machine room", "2024-05-20"],
        ["EQ-1003", "XM-200", "가상코인테크 / VirtualCoinTech", "지하 주차장 / Parking B1", "2024-07-01"],
        ["EQ-1004", "PR-9", "프린텍 / Printech", "3층 사무실 / Office", "2023-12-05"],
    ]
    for r in rows:
        ws.append(r)
    # 병합셀 예시(같은 위치 그룹)
    ws2 = wb.create_sheet("사양")
    ws2.append(["항목 / Item", "XM-200", "TG-15"])
    for c in ws2[1]:
        c.font = Font(bold=True); c.fill = fill
    for r in [
        ["통신 / Interface", "RS-232 9600bps", "RS-485 19200bps"],
        ["프레임 시작 / Start", "STX 0x02", "SOH 0x01"],
        ["검증 / Checksum", "XOR", "CRC-16/CCITT"],
        ["전원 / Power", "DC 12V", "DC 24V"],
        ["동작온도 / Temp", "-10~50℃", "-20~60℃"],
    ]:
        ws2.append(r)
    path = os.path.join(DIRS["docs"], "equipment_list.xlsx")
    wb.save(path)
    return path


def make_docx_manual(image_path):
    from docx import Document
    from docx.shared import Inches
    doc = Document()
    doc.add_heading("코인 처리 시스템 운영 매뉴얼", level=0)
    doc.add_paragraph("Coin Processing System Operation Manual — 사내 배포용 (v1.1)")
    doc.add_heading("1. 개요 / Overview", level=1)
    doc.add_paragraph("본 매뉴얼은 XM-200 코인 컨트롤러와 TG-15 센서 게이트웨이로 구성된 "
                      "사내 코인 처리 시스템의 운영 절차를 설명한다. 장애 발생 시 4장 문제해결을 참조한다.")
    doc.add_heading("2. 시스템 구성 / Architecture", level=1)
    doc.add_paragraph("아래 구성도와 같이 상위 제어기(Host)가 RS-232로 XM-200을, RS-485로 TG-15를 제어한다.")
    if os.path.exists(image_path):
        doc.add_picture(image_path, width=Inches(5.2))
    doc.add_heading("3. 일일 점검 항목 / Daily Check", level=1)
    tbl = doc.add_table(rows=1, cols=3); tbl.style = "Light List Accent 1"
    h = tbl.rows[0].cells
    h[0].text, h[1].text, h[2].text = "항목 / Item", "정상 기준 / Normal", "비고 / Note"
    for a, b, c in [
        ("코인 투입 / Coin insert", "3초 이내 인식", "COIN_IN 응답 확인"),
        ("잔액 표시 / Balance", "실제와 일치", "BALANCE 명령"),
        ("온도 / Temperature", "-10~50℃", "TG-15 RD_TEMP"),
        ("하트비트 / Heartbeat", "10초 주기", "미수신 시 재연결"),
    ]:
        r = tbl.add_row().cells
        r[0].text, r[1].text, r[2].text = a, b, c
    doc.add_heading("4. 문제 해결 / Troubleshooting", level=1)
    doc.add_paragraph("· 코인 잼(JAM, 0x21) 발생 시: 전원을 끄고 호퍼를 청소한 뒤 RESET(0x15)을 전송한다.")
    doc.add_paragraph("· 체크섬 오류(0x05)가 반복되면 케이블 접촉 및 통신 속도(9600bps)를 확인한다.")
    path = os.path.join(DIRS["docs"], "operation_manual.docx")
    doc.save(path)
    return path


def make_pptx(image_path):
    from pptx import Presentation
    from pptx.util import Inches, Pt
    prs = Presentation()
    # 슬라이드1 제목
    s = prs.slides.add_slide(prs.slide_layouts[0])
    s.shapes.title.text = "코인 처리 시스템 교육 자료"
    s.placeholders[1].text = "Coin Processing System Training — 신입 교육용"
    # 슬라이드2 구성도(이미지)
    s = prs.slides.add_slide(prs.slide_layouts[5])
    s.shapes.title.text = "1. 시스템 구성 / Architecture"
    if os.path.exists(image_path):
        s.shapes.add_picture(image_path, Inches(1.0), Inches(1.6), width=Inches(7.5))
    # 슬라이드3 표
    s = prs.slides.add_slide(prs.slide_layouts[5])
    s.shapes.title.text = "2. 장비 비교 / Comparison"
    rows, cols = 4, 3
    tbl = s.shapes.add_table(rows, cols, Inches(0.8), Inches(1.8), Inches(8), Inches(2.5)).table
    data = [["항목", "XM-200", "TG-15"],
            ["통신", "RS-232", "RS-485"],
            ["시작바이트", "STX 0x02", "SOH 0x01"],
            ["검증", "XOR", "CRC-16"]]
    for i in range(rows):
        for j in range(cols):
            tbl.cell(i, j).text = data[i][j]
    # 슬라이드4 요약
    s = prs.slides.add_slide(prs.slide_layouts[1])
    s.shapes.title.text = "3. 요약 / Summary"
    tf = s.placeholders[1].text_frame
    tf.text = "프레임 시작 바이트로 장비를 구분한다"
    for line in ["XM-200: STX(0x02) + XOR 체크섬", "TG-15: SOH(0x01) + CRC-16",
                 "장애 시 매뉴얼 4장 참조"]:
        p = tf.add_paragraph(); p.text = line; p.level = 1
    path = os.path.join(DIRS["docs"], "training.pptx")
    prs.save(path)
    return path


def make_txt_files():
    paths = []
    # UTF-8 FAQ
    p1 = os.path.join(DIRS["docs"], "faq_utf8.txt")
    with open(p1, "w", encoding="utf-8") as f:
        f.write("자주 묻는 질문 / FAQ\n\n"
                "Q. 코인이 인식되지 않습니다.\n"
                "A. XM-200의 투입구 잠금(LOCK 0x17) 상태를 확인하고 UNLOCK(0x18)을 전송하세요.\n\n"
                "Q. 온도 값이 이상합니다.\n"
                "A. TG-15의 RD_TEMP(0x41) 응답은 0.1도 단위입니다. 250 = 25.0도.\n")
    paths.append(p1)
    # CP949(EUC-KR) 인코딩 — 인코딩 자동판별 테스트용
    p2 = os.path.join(DIRS["docs"], "notice_cp949.txt")
    text = ("[공지] 정기 점검 안내 / Maintenance Notice\n\n"
            "매월 첫째 주 월요일 09:00~10:00 정기 점검을 실시합니다.\n"
            "점검 중에는 코인 처리 시스템 사용이 제한됩니다.\n"
            "문의: 설비관리팀 (내선 1234)\n")
    with open(p2, "w", encoding="cp949") as f:
        f.write(text)
    paths.append(p2)
    return paths


def main():
    ensure_dirs()
    created = {}
    created["protocol_pdf"] = make_protocol_pdf()
    created["protocol_docx"] = make_protocol_docx()
    hex_paths, seq = make_hex_logs()
    created["hex"] = hex_paths
    imgs = make_images()
    created["images"] = imgs
    created["xlsx"] = make_xlsx()
    created["docx"] = make_docx_manual(imgs[0])
    created["pptx"] = make_pptx(imgs[0])
    created["txt"] = make_txt_files()

    print("=== 생성 완료 ===")
    for k, v in created.items():
        if isinstance(v, list):
            for p in v:
                print(f"  {k:14s} {os.path.relpath(p, BASE)}  ({os.path.getsize(p)} B)")
        else:
            print(f"  {k:14s} {os.path.relpath(v, BASE)}  ({os.path.getsize(v)} B)")

    # HEX 프레임 체크섬 자체검증
    print("\n=== HEX 프레임 자체검증 (XM-200 XOR) ===")
    ok = True
    for name, fr in seq:
        length, cmd = fr[1], fr[2]
        data = fr[3:-2]
        chk = fr[-2]
        calc = 0
        for b in fr[1:-2]:
            calc ^= b
        valid = (fr[0] == STX and fr[-1] == ETX and calc == chk and length == 1 + len(data))
        ok = ok and valid
        print(f"  {'OK' if valid else 'BAD':3s} {name:14s} {bracket(fr)}")
    print("모든 프레임 유효" if ok else "⚠️ 무효 프레임 존재")


if __name__ == "__main__":
    main()
