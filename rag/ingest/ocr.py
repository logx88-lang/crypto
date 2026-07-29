"""OCR 백엔드 — PaddleOCR(kor+eng), 인제스천 시점 전용 (design.md §8, Q4).

- 질의 시점이 아니라 인제스천 배치 시점에만 동작 → 질의 LLM VRAM과 무경합.
- PaddleOCR 은 지연 임포트. 미설치/비활성 시 `available()==False` → 파서는 마커만 남기고 진행
  (결정적 코어는 OCR 없이도 동작). 백엔드 주입 가능 → 순수 라우팅 로직 단위테스트.
"""
from __future__ import annotations

from ..config import CONFIG


class OCRBackend:
    """인터페이스. available() 로 사용 가능 여부, image_to_text() 로 인식."""
    def available(self) -> bool:
        raise NotImplementedError

    def image_to_text(self, image) -> str:
        raise NotImplementedError


class PaddleOCRBackend(OCRBackend):
    """PaddleOCR CrossEncoder 래퍼. image: 파일경로 | numpy.ndarray | PIL.Image."""
    def __init__(self, lang: str = None):
        self.lang = lang or CONFIG.ocr_lang
        self._ocr = None
        self._avail = None

    def available(self) -> bool:
        if self._avail is None:
            try:
                import paddleocr  # noqa: F401
                self._avail = True
            except Exception:
                self._avail = False
        return self._avail

    def _ensure(self):
        if self._ocr is None:
            from paddleocr import PaddleOCR
            # 3.x 우선(use_textline_orientation). enable_mkldnn=False 로 일부 CPU의 oneDNN/PIR
            # 런타임 버그(ConvertPirAttribute2RuntimeAttribute) 회피 — 실측 확인.
            # 2.x 는 use_angle_cls/show_log 인자 → TypeError 시 순차 폴백.
            for kw in ({"use_textline_orientation": True, "lang": self.lang,
                        "enable_mkldnn": False},
                       {"use_angle_cls": True, "lang": self.lang, "show_log": False},
                       {"lang": self.lang}):
                try:
                    self._ocr = PaddleOCR(**kw)
                    break
                except (TypeError, ValueError):
                    continue
            if self._ocr is None:
                self._ocr = PaddleOCR(lang=self.lang)
        return self._ocr

    def image_to_text(self, image) -> str:
        if not self.available():
            return ""
        ocr = self._ensure()
        img = self._to_ndarray(image)
        # PaddleOCR 3.x: predict(img) → [dict(rec_texts=[...])] (검출 순서)
        if hasattr(ocr, "predict"):
            try:
                lines = []
                for res in ocr.predict(img):
                    texts = res.get("rec_texts") if isinstance(res, dict) \
                        else getattr(res, "rec_texts", None)
                    if texts:
                        lines.extend(t.strip() for t in texts if t and t.strip())
                if lines:
                    return "\n".join(lines)
            except Exception:
                pass  # 2.x 경로로 폴백
        # PaddleOCR 2.x: ocr(img, cls=True) → [[ [box, (text, conf)], ... ]]
        try:
            result = ocr.ocr(img, cls=True)
        except TypeError:
            result = ocr.ocr(img)
        lines = []
        for page in (result or []):
            for entry in (page or []):
                try:
                    txt = entry[1][0]
                except (IndexError, TypeError):
                    continue
                if txt and txt.strip():
                    lines.append(txt.strip())
        return "\n".join(lines)

    @staticmethod
    def _to_ndarray(image):
        import numpy as np
        if isinstance(image, str):
            from PIL import Image
            return np.array(Image.open(image).convert("RGB"))
        try:
            from PIL import Image
            if isinstance(image, Image.Image):
                return np.array(image.convert("RGB"))
        except Exception:
            pass
        return image  # 이미 ndarray 로 가정


_DEFAULT = None


def get_ocr_backend() -> OCRBackend:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = PaddleOCRBackend()
    return _DEFAULT


def set_ocr_backend(backend: OCRBackend) -> None:
    """테스트/대체 백엔드 주입용."""
    global _DEFAULT
    _DEFAULT = backend


def ocr_image(image, backend: OCRBackend = None) -> str:
    """이미지 → 인식 텍스트. OCR 비활성/미설치면 빈 문자열."""
    if not CONFIG.ocr_enabled:
        return ""
    backend = backend or get_ocr_backend()
    if not backend.available():
        return ""
    return backend.image_to_text(image)
