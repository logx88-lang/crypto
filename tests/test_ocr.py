"""OCR 라우팅 검증 — 가짜 백엔드 주입(PaddleOCR 미설치에도 실행). `python3 tests/test_ocr.py`."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from rag.ingest import parse_file, parse_image, SUPPORTED_EXTS, OCRBackend, ocr_image
from rag.ingest.ocr import get_ocr_backend
from rag.config import CONFIG


class FakeOCR(OCRBackend):
    def __init__(self, text="시스템 구성도 OCR 인식 텍스트", avail=True):
        self._text, self._avail = text, avail
        self.calls = 0
    def available(self):
        return self._avail
    def image_to_text(self, image):
        self.calls += 1
        return self._text


def test_supported_exts_includes_images():
    for e in ("png", "jpg", "jpeg", "bmp", "tiff", "tif"):
        assert e in SUPPORTED_EXTS, e


def test_parse_image_with_ocr_text():
    f = FakeOCR("코인 컨트롤러 배선도\nXM-200 전원부")
    doc = parse_image("diagram.png", ocr_backend=f)
    assert doc.ext == "png" and f.calls == 1
    assert doc.elements and doc.elements[0].text.startswith("코인 컨트롤러")
    assert doc.elements[0].location.get("source") == "ocr"


def test_parse_image_backend_unavailable_marker():
    doc = parse_image("photo.jpg", ocr_backend=FakeOCR(avail=False))
    assert doc.elements[0].location.get("section") == "_ocr_unavailable"
    assert "OCR" in doc.elements[0].text


def test_ocr_image_respects_disabled_flag():
    orig = CONFIG.ocr_enabled
    try:
        CONFIG.ocr_enabled = False
        assert ocr_image("x.png", backend=FakeOCR("무시됨")) == ""  # 비활성 → 빈 문자열
        CONFIG.ocr_enabled = True
        assert ocr_image("x.png", backend=FakeOCR("인식")) == "인식"
    finally:
        CONFIG.ocr_enabled = orig


def test_parse_file_dispatches_image_gracefully():
    # 실제 샘플 이미지 → 기본 백엔드(PaddleOCR 미설치)면 마커, 설치면 텍스트. 크래시 없어야.
    png = os.path.join(ROOT, "samples", "dummy_set", "images", "system_diagram.png")
    if os.path.exists(png):
        doc = parse_file(png)
        assert doc.ext == "png" and doc.elements  # 최소 1개 요소(텍스트 또는 마커)


def test_default_backend_is_paddle_type():
    from rag.ingest.ocr import PaddleOCRBackend
    assert isinstance(get_ocr_backend(), PaddleOCRBackend)


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
