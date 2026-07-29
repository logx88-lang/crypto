"""MVP 결정적 코어 검증 — dummy_set 샘플 대조.

pytest 또는 `python3 tests/test_core.py` 로 실행. Ollama 불필요.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from rag.ingest import parse_file, chunk_document, SUPPORTED_EXTS
from rag.config import CONFIG
from rag.logs import (detect_log_type, detect_profile, analyze_text_log,
                      analyze_binary_log)
from rag.logs.profiles import BUILTIN_PROFILES

SAMPLES = os.path.join(ROOT, "samples", "dummy_set")
DOCS = os.path.join(SAMPLES, "docs")
PROTO = os.path.join(SAMPLES, "protocol")
HEX = os.path.join(SAMPLES, "hex")


# ---------------------------------------------------------------------------
# 파서
# ---------------------------------------------------------------------------
def test_pdf_protocol():
    doc = parse_file(os.path.join(PROTO, "XM-200_coin_controller_protocol.pdf"))
    assert doc.ext == "pdf"
    assert doc.doc_type == "protocol_spec"
    tables = [e for e in doc.elements if e.kind == "table"]
    assert len(tables) >= 5, f"표 요소 부족: {len(tables)}"
    assert all("page_no" in e.location for e in doc.elements if e.location.get("page_no"))
    # 명령 코드 텍스트가 표에 존재
    assert any("0x12" in e.text or "0X12" in e.text.upper() for e in tables)


def test_docx_protocol():
    doc = parse_file(os.path.join(PROTO, "TG-15_sensor_gateway_protocol.docx"))
    assert doc.doc_type == "protocol_spec"
    assert any(e.kind == "table" for e in doc.elements)


def test_xlsx_merged_multiheader():
    doc = parse_file(os.path.join(DOCS, "equipment_list.xlsx"))
    tables = [e for e in doc.elements if e.kind == "table"]
    assert len(tables) == 2  # 장비목록 + 사양
    assert any(e.location.get("sheet_name") == "장비목록" for e in tables)
    # 병합셀 fill-forward: 헤더 값이 마크다운에 존재
    joined = "\n".join(e.text for e in tables)
    assert "자산번호" in joined and "XM-200" in joined


def test_pptx_slides():
    doc = parse_file(os.path.join(DOCS, "training.pptx"))
    assert any(e.location.get("slide_no") for e in doc.elements)
    assert any(e.kind == "table" for e in doc.elements)


def test_txt_encoding_detection():
    doc_utf8 = parse_file(os.path.join(DOCS, "faq_utf8.txt"))
    assert doc_utf8.elements and "FAQ" in doc_utf8.elements[0].text.upper() or \
        "질문" in doc_utf8.elements[0].text
    doc_cp = parse_file(os.path.join(DOCS, "notice_cp949.txt"))
    enc = doc_cp.elements[0].location.get("encoding", "").lower()
    assert enc in ("cp949", "euc_kr", "euc-kr"), f"인코딩 감지: {enc}"
    assert "점검" in doc_cp.elements[0].text


# ---------------------------------------------------------------------------
# 청킹
# ---------------------------------------------------------------------------
def test_chunk_preserves_tables_and_meta():
    doc = parse_file(os.path.join(PROTO, "XM-200_coin_controller_protocol.pdf"))
    chunks = chunk_document(doc)
    assert chunks
    table_chunks = [c for c in chunks if c.metadata["kind"] == "table"]
    assert table_chunks, "표 청크 없음"
    # 표 청크는 마크다운 표 형태 유지(파이프 포함)
    assert all("|" in c.text for c in table_chunks)
    # 메타데이터 필수 키
    for c in chunks:
        for key in ("source_file", "doc_title", "doc_type", "kind", "chunk_id", "content_hash"):
            assert key in c.metadata
    # 표 청크 상한 준수(분할 시 헤더 반복)
    for c in table_chunks:
        assert len(c.text) <= CONFIG.table_max_chars + 200


def test_chunk_text_window():
    doc = parse_file(os.path.join(DOCS, "faq_utf8.txt"))
    chunks = chunk_document(doc)
    assert chunks
    assert all(len(c.text) <= CONFIG.chunk_chars + CONFIG.chunk_overlap for c in chunks)


# ---------------------------------------------------------------------------
# 통신 로그 분석
# ---------------------------------------------------------------------------
def _read(p, binary=False):
    mode = "rb" if binary else "r"
    kw = {} if binary else {"encoding": "utf-8"}
    with open(os.path.join(HEX, p), mode, **kw) as f:
        return f.read()


def test_detect_hex_vs_natural():
    for name in ["coin_log_ts.txt", "coin_log_dash.txt", "aee.txt",
                 "coin_log_space0x.txt", "sensor_log_tg15.txt"]:
        assert detect_log_type(_read(name)) == "hex", name
    assert detect_log_type(_read("event_log_natural.txt")) == "natural"


def test_xm200_bracket_all_valid():
    for name in ["coin_log_ts.txt", "coin_log_dash.txt", "aee.txt"]:
        res = analyze_text_log(_read(name))
        assert res["log_type"] == "hex"
        assert res["total"] > 0
        assert res["valid_count"] == res["total"], f"{name}: {res['valid_count']}/{res['total']}"
        # COIN_IN(0x12) 프레임 존재
    res = analyze_text_log(_read("coin_log_ts.txt"))
    assert any(fr["cmd"] == 0x12 for fr in res["frames"])


def test_xm200_0x_variant():
    res = analyze_text_log(_read("coin_log_space0x.txt"))
    assert res["profile"].byte_token.endswith("2})")  # 0x 토큰 감지
    assert res["valid_count"] == res["total"] > 0


def test_tg15_crc_and_direction():
    res = analyze_text_log(_read("sensor_log_tg15.txt"))
    assert res["log_type"] == "hex"
    assert res["profile"].framing == "soh_crc"
    assert res["profile"].direction_regex is not None
    assert res["valid_count"] == res["total"] > 0


def test_binary_dat_length_framing():
    from rag.logs.profiles import BUILTIN_PROFILES
    xm = next(p for p in BUILTIN_PROFILES if p.name == "xm200_bracket")
    res = analyze_binary_log(_read("eefe.dat", binary=True), xm)
    assert res["total"] == 15, f"프레임 수: {res['total']}"
    assert res["valid_count"] == 15
    # DISPENSE(0x14) 프레임(내부에 0x03 포함)도 정확히 프레이밍
    assert any(fr["cmd"] == 0x14 for fr in res["frames"])


# ---------------------------------------------------------------------------
def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS {fn.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(fns)} 통과")
    return passed == len(fns)


def test_rf_cmd_len_lrc():
    """RF module류 Command(2)+Length(2)+Data+LRC 프레이밍 파싱."""
    from rag.logs.detect import detect_profile
    # SD 프레임: 53 44(=SD) 00 02(len) 31 32(='12') 16(LRC=XOR)
    log = ("[20260714 02:05:00]->TX : CMD[SD]\n"
           "[20260714 02:05:00]->TX : [53][44][00][02][31][32][16]\n")
    p = detect_profile(log)
    assert p and p.framing == "cmd_len_lrc", p
    res = analyze_text_log(log)
    assert res["total"] == 1 and res["valid_count"] == 1, res
    fr = res["frames"][0]
    assert fr["cmd_ascii"] == "SD" and fr["length"] == 2 and fr["data_ascii"] == "12"


def test_generic_config_parser():
    """문서 기반 범용 파서: 설정(dict)만으로 프레임 파싱(하드코딩 없음)."""
    from rag.logs.generic import analyze_with_profile, detect_line_format
    profile = {
        "framing": "length", "byte_token": "bracket",
        "cmd": {"offset": 0, "size": 2, "type": "ascii"},
        "length": {"offset": 2, "size": 2, "endian": "big"},
        "header_size": 4, "trailer_size": 1,
        "checksum": {"type": "lrc", "span": "header_and_data"},
    }
    log = "[53][44][00][02][31][32][16]"   # SD + len2 + '12' + LRC 0x16
    res = analyze_with_profile(log, profile)
    assert res["total"] == 1 and res["valid_count"] == 1, res
    fr = res["frames"][0]
    assert fr["cmd_ascii"] == "SD" and fr["length"] == 2 and fr["data_ascii"] == "12"
    # 줄형식 자동감지
    lf = detect_line_format("[20260714 02:05:00]->TX : CMD[SD]\n[53][44][00][00][17]")
    assert lf["byte_token"] == "bracket" and lf["timestamp_regex"]


if __name__ == "__main__":
    ok = _run_all()
    sys.exit(0 if ok else 1)
