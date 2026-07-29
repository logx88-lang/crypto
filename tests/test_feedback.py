"""비식별화 안전성 + 개선기록 저장 검증. `python3 tests/test_feedback.py` (외부 의존성 없음)."""
import os
import sys
import tempfile
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from rag.feedback.sanitize import (sanitize, sanitize_record, table_shape, Pseudonymizer)
from rag.feedback.log import FeedbackLog


REAL_HANGUL = ["코인", "투입", "명령", "센서", "게이트웨이", "삼성", "잔액", "슬레이브"]
REAL_IDENT = ["XM-200", "TG-15", "COIN_IN", "OVERFLOW", "RS-485", "EQ-1001", "STX"]


def test_sanitize_removes_real_hangul_and_identifiers():
    text = ("XM-200의 코인 투입 명령 COIN_IN(0x12), TG-15 센서 게이트웨이 RS-485 "
            "잔액 레지스터 0x41, 통신 9600bps, EQ-1001 삼성")
    out = sanitize(text)
    for tok in REAL_HANGUL + REAL_IDENT:
        assert tok not in out, f"실제 값 잔존: {tok}\n → {out}"
    # 원문 그대로가 아니어야
    assert out != text and out.strip()


def test_sanitize_preserves_table_structure():
    md = "| 필드 | 크기 | 값 |\n| --- | --- | --- |\n| STX | 1 | 0x02 |\n| CMD | 1 | 0x12 |"
    out = sanitize(md)
    # 파이프 수/줄 수/구분선 보존
    assert out.count("\n") == md.count("\n")
    for a, b in zip(md.splitlines(), out.splitlines()):
        assert a.count("|") == b.count("|"), (a, b)
    assert "---" in out                      # 구분선 유지
    assert "필드" not in out and "STX" not in out


def test_sanitize_deterministic_within_record():
    p = Pseudonymizer()
    a = p.sub("코인 코인 XM-200 XM-200")
    toks = a.split()
    assert toks[0] == toks[1]                # 같은 한글 → 같은 가명
    assert toks[2] == toks[3]                # 같은 식별자 → 같은 가명
    assert toks[0] != toks[2]


def test_number_length_preserved_but_changed():
    out = sanitize("9600 250 0x41")
    parts = out.split()
    assert len(parts[0]) == 4 and parts[0] != "9600"
    assert len(parts[1]) == 3 and parts[1] != "250"
    assert parts[2].startswith("0x") and parts[2] != "0x41"


def test_table_shape():
    md = "| a | b | c |\n| --- | --- | --- |\n| 1 | 2 | 3 |"
    s = table_shape(md)
    assert s["is_table"] and s["rows"] == 3 and s["cols"] == 3 and s["has_header_sep"]
    assert table_shape("그냥 문장")["is_table"] is False


def test_sanitize_record_keeps_safe_meta_masks_content():
    rec = {
        "ts": "2026-07-13T10:00", "kind": "qa", "category": "표 희석",
        "severity": "중간", "question": "XM-200 CMD 필드 의미는?",
        "answer": "COIN_IN 코인 투입입니다.", "note": "삼성 표가 깨짐",
        "contexts": [{"document": "| 필드 | 값 |\n| --- | --- |\n| CMD | 0x12 |",
                      "metadata": {"kind": "table", "doc_type": "protocol_spec",
                                   "page_no": 2, "doc_title": "XM-200 명세서"}}],
    }
    s = sanitize_record(rec)
    assert s["category"] == "표 희석" and s["severity"] == "중간"   # 구조 enum 유지
    assert "XM-200" not in s["question"] and "COIN_IN" not in s["answer"]
    assert "삼성" not in s["note"]
    c = s["contexts"][0]
    assert c["metadata"]["page_no"] == 2 and c["metadata"]["kind"] == "table"  # 안전메타 유지
    assert "XM-200" not in c["metadata"]["doc_title"]                          # 민감메타 가명화
    assert c["table_shape"]["rows"] == 3 and c["table_shape"]["cols"] == 2     # 형태 보존
    assert "CMD" not in c["document"] and "|" in c["document"]                 # 값 제거·구조 유지


def test_feedback_log_roundtrip_and_export():
    tmp = tempfile.mkdtemp()
    try:
        log = FeedbackLog(path=tmp)
        rec = {"ts": "t", "kind": "qa", "category": "틀린 답변", "severity": "높음",
               "question": "코인 투입 명령?", "answer": "0x12", "note": "XM-200 오류",
               "contexts": []}
        saved = log.add(rec)                 # 방어적 재-비식별화
        assert "코인" not in saved["question"] and "XM-200" not in saved["note"]
        assert log.count() == 1
        md = log.export_markdown()
        assert os.path.exists(md)
        content = open(md, encoding="utf-8").read()
        assert "코인" not in content and "XM-200" not in content   # 반출물에 실데이터 없음
        assert "틀린 답변" in content                              # 카테고리는 남음
    finally:
        shutil.rmtree(tmp)


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn(); print(f"  PASS {fn.__name__}"); passed += 1
        except Exception as e:
            import traceback; print(f"  FAIL {fn.__name__}: {type(e).__name__}: {e}"); traceback.print_exc()
    print(f"\n{passed}/{len(fns)} 통과")
    return passed == len(fns)


if __name__ == "__main__":
    sys.exit(0 if _run_all() else 1)
