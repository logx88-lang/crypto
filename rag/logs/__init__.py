"""통신 로그 분석 — HEX/자연어 자동 판별 + 장비별 파싱 프로파일 기반 해석.

설계: docs/design.md §7. 프로토콜 프레이밍/체크섬은 원칙적으로 사용자가 확인한 명세에서 오며,
여기서는 자동 감지값을 후보로 제시(확정은 UI 확인 단계).
"""
from .profiles import ParsingProfile, BUILTIN_PROFILES
from .detect import detect_log_type, detect_profile
from .parser import analyze_text_log, analyze_binary_log, reconstruct_bytes

__all__ = [
    "ParsingProfile", "BUILTIN_PROFILES",
    "detect_log_type", "detect_profile",
    "analyze_text_log", "analyze_binary_log", "reconstruct_bytes",
]
