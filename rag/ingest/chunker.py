"""표 보존 청킹.

규칙:
- 표(Element.kind=='table')는 청크 경계에서 분할하지 않는다. 단, table_max_chars 를 넘으면
  **행 단위로 분할하되 헤더(2줄)를 각 조각에 반복 부착**한다.
- 텍스트는 연속 텍스트 요소를 이어붙인 뒤 chunk_chars/overlap 윈도우로 분할(가능하면 개행/공백 경계).
- 모든 청크에 출처 메타(source_file/doc_title/page|sheet|slide/section/doc_type/kind) 부착.
"""
from __future__ import annotations

from typing import Optional

from ..config import CONFIG
from .models import ParsedDoc, Chunk, make_chunk


def _soft_window(text: str, size: int, overlap: int) -> list:
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []
    out = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:
            # 개행 우선, 없으면 공백에서 소프트 브레이크 (뒤로 최대 overlap 만큼 탐색)
            window = text[start:end]
            brk = max(window.rfind("\n"), window.rfind(" "))
            if brk > size - overlap:  # 너무 앞이면 무시
                end = start + brk + 1
        out.append(text[start:end].strip())
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return [c for c in out if c]


def _split_table_md(md: str, max_chars: int) -> list:
    if len(md) <= max_chars:
        return [md]
    lines = md.split("\n")
    if len(lines) < 3:
        return [md]
    header = lines[:2]           # 헤더 + 구분선
    body = lines[2:]
    header_len = len(header[0]) + len(header[1]) + 2
    pieces, cur, cur_len = [], [], header_len
    for row in body:
        if cur and cur_len + len(row) + 1 > max_chars:
            pieces.append("\n".join(header + cur))
            cur, cur_len = [], header_len
        cur.append(row)
        cur_len += len(row) + 1
    if cur:
        pieces.append("\n".join(header + cur))
    return pieces


def chunk_document(doc: ParsedDoc) -> list:
    cfg = CONFIG
    chunks: list = []
    idx = 0
    text_buf: list = []
    buf_loc: Optional[dict] = None

    def flush_text():
        nonlocal idx, text_buf, buf_loc
        if not text_buf:
            return
        joined = "\n".join(text_buf).strip()
        loc = buf_loc or {}
        for piece in _soft_window(joined, cfg.chunk_chars, cfg.chunk_overlap):
            chunks.append(make_chunk(piece, source_file=doc.source_file,
                                     doc_title=doc.doc_title, doc_type=doc.doc_type,
                                     kind="text", location=loc, index=idx))
            idx += 1
        text_buf = []
        buf_loc = None

    for el in doc.elements:
        if el.kind == "table":
            flush_text()
            # 표 희석 완화: 표 청크에 제목 경로(상위→하위)를 접두로 붙여 검색 노출↑
            # (예: "Card 정보 요청" 질의가 'Card 정보 요청 > 요청전문'의 표에 매칭되게)
            ctx = el.location.get("section_path") or el.location.get("section") or doc.doc_title or ""
            prefix = f"[{ctx}]\n" if ctx else ""
            for piece in _split_table_md(el.text, cfg.table_max_chars):
                text = prefix + piece
                chunks.append(make_chunk(text, source_file=doc.source_file,
                                         doc_title=doc.doc_title, doc_type=doc.doc_type,
                                         kind="table", location=el.location, index=idx))
                idx += 1
        elif el.kind == "text":
            if buf_loc is None:
                buf_loc = dict(el.location)
            text_buf.append(el.text)
        # image 등은 현재 스킵(Phase 3 OCR)
    flush_text()
    return chunks
