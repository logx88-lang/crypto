"""비식별화(구조 보존 가명화) — 폐쇄망 밖으로 개선기록을 반출하기 위한 안전장치.

원칙: **양식/구조는 남기고 실제 데이터는 제거**한다.
- 표의 파이프(|)·구분선(---)·행/열 배치, 브라켓/오프셋 형태, 문장·질문의 골격은 유지.
- 한글 어휘·영문 식별자·숫자·HEX 값은 **결정적 가명**으로 치환(같은 값→같은 가명, 레코드 내 일관).
  → 외부에서 "6열 표의 4행 필드를 물었는데 희석됨" 같은 **구조/증상**은 분석 가능하되 실제 값은 없음.
- 매핑은 레코드 단위로 새로 생성(레코드 간 상관 불가). 원본 매핑은 저장하지 않는다.
"""
from __future__ import annotations

import hashlib
import os
import re

# 토큰 우선순위: 0x-HEX → 브라켓HEX([NN]) → 식별자(RS-485/COIN_IN) → 한글 → 숫자
_HEX0X = r"0[xX][0-9A-Fa-f]+"
_HEXBR = r"\[[0-9A-Fa-f]{2}\]"
_IDENT = r"[A-Za-z][A-Za-z0-9_]*(?:-[A-Za-z0-9_]+)*"
_HANGUL = r"[가-힣]+"
_NUM = r"[0-9]+"
_TOKEN = re.compile("|".join([_HEX0X, _HEXBR, _IDENT, _HANGUL, _NUM]))


def _stable_hex(seed: str, n: int) -> str:
    h = hashlib.sha1(("hex" + seed).encode()).hexdigest().upper()
    return (h * ((n // len(h)) + 1))[:max(n, 1)]


def _stable_digits(seed: str) -> str:
    """같은 자릿수, 다른 숫자(결정적)."""
    h = hashlib.sha1(("num" + seed).encode()).hexdigest()
    digs = [str(int(c, 16) % 10) for c in h]
    return "".join((digs * ((len(seed) // len(digs)) + 1))[:len(seed)])


class Pseudonymizer:
    """레코드 1건에 대해 일관된 가명 치환."""
    def __init__(self):
        self.map: dict = {}
        self._n = {"han": 0, "id": 0}

    def _next(self, kind: str) -> int:
        self._n[kind] += 1
        return self._n[kind]

    def _pseudo(self, tok: str) -> str:
        if tok in self.map:
            return self.map[tok]
        if re.fullmatch(_HEX0X, tok):
            rep = tok[:2] + _stable_hex(tok, len(tok) - 2)
        elif re.fullmatch(_HEXBR, tok):
            rep = "[" + _stable_hex(tok, 2) + "]"
        elif re.fullmatch(_HANGUL, tok):
            rep = f"어휘{self._next('han')}"
        elif re.fullmatch(_NUM, tok):
            rep = _stable_digits(tok)
        else:  # 영문 식별자/단어
            rep = f"ID{self._next('id')}"
        self.map[tok] = rep
        return rep

    def sub(self, text: str) -> str:
        if not text:
            return text or ""
        return _TOKEN.sub(lambda m: self._pseudo(m.group(0)), text)


def sanitize(text: str, pseudo: Pseudonymizer = None) -> str:
    """단일 문자열 비식별화(구조 보존). pseudo 공유 시 레코드 내 일관."""
    return (pseudo or Pseudonymizer()).sub(text or "")


def table_shape(md: str) -> dict:
    """마크다운 표의 구조 요약(값 없이 형태만). 표가 아니면 rows/cols=0."""
    lines = [ln for ln in (md or "").splitlines() if "|" in ln]
    if not lines:
        return {"is_table": False, "rows": 0, "cols": 0, "has_header_sep": False}
    cols = max(ln.count("|") - 1 for ln in lines)
    has_sep = any(set(ln.replace("|", "").replace(" ", "")) <= set("-:") and "-" in ln
                  for ln in lines)
    return {"is_table": True, "rows": len(lines), "cols": max(cols, 0),
            "has_header_sep": has_sep}


# 비식별화 유지(값 아님) 안전 메타 키
_SAFE_META = {"kind", "doc_type", "ext", "page_no", "slide_no", "source"}
# 값이 들어갈 수 있어 가명화할 메타 키
_SENS_META = {"doc_title", "source_file", "sheet_name", "section"}


def sanitize_metadata(meta: dict, pseudo: Pseudonymizer) -> dict:
    out = {}
    for k, v in (meta or {}).items():
        if k in _SAFE_META:
            out[k] = v
        elif k in _SENS_META:
            out[k] = sanitize(str(v), pseudo)
    return out


_KEEP_META = ("kind", "doc_type", "page_no", "slide_no", "sheet_name",
              "section", "source_file", "doc_title")


def _context_entry(c: dict, pseudo: Pseudonymizer = None) -> dict:
    """컨텍스트 1건 → 구조 메타 + (가명화 or 원문) 문서. 표는 형태(행×열) 부착."""
    meta = c.get("metadata", {}) or {}
    doc = c.get("document", "") or ""
    if pseudo is not None:
        entry = {"metadata": sanitize_metadata(meta, pseudo),
                 "document": sanitize(doc, pseudo)}
    else:
        m = {k: meta[k] for k in _KEEP_META if meta.get(k) not in (None, "")}
        if m.get("source_file"):
            m["source_file"] = os.path.basename(str(m["source_file"]))
        entry = {"metadata": m, "document": doc[:800]}   # 원문(과대 방지 트림)
    if meta.get("kind") == "table":
        entry["table_shape"] = table_shape(doc)          # 값 무관 형태
    return entry


def _structural_summary(contexts: list) -> dict:
    """검색된 근거의 진단 요약(표 유무 등) — 표 희석 진단에 유용."""
    kinds = [(c.get("metadata", {}) or {}).get("kind") for c in (contexts or [])]
    return {"n": len(kinds), "table": kinds.count("table"), "text": kinds.count("text")}


def sanitize_record(record: dict) -> dict:
    """개선기록 레코드 전체를 비식별화(레코드당 매핑 1개 공유)."""
    p = Pseudonymizer()
    note = record.get("note", "")
    out = {
        "ts": record.get("ts"),
        "kind": record.get("kind"),
        "category": record.get("category"),      # 구조 enum(안전)
        "severity": record.get("severity"),      # 구조 enum(안전)
        "question": sanitize(record.get("question", ""), p),
        "note": sanitize(note, p) if record.get("sanitize_note", True) else note,
        "answer": sanitize(record.get("answer", ""), p),
        "context_summary": _structural_summary(record.get("contexts", [])),
        "contexts": [_context_entry(c, p) for c in record.get("contexts", []) or []],
    }
    return out


def readable_record(record: dict) -> dict:
    """비식별화 없이 원문 그대로(구조 요약·표형태 포함). 사용자 정책=원문 저장 시."""
    return {
        "ts": record.get("ts"),
        "kind": record.get("kind"),
        "category": record.get("category"),
        "severity": record.get("severity"),
        "question": record.get("question", ""),
        "note": record.get("note", ""),
        "answer": record.get("answer", ""),
        "context_summary": _structural_summary(record.get("contexts", [])),
        "contexts": [_context_entry(c, None) for c in record.get("contexts", []) or []],
    }
