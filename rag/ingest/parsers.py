"""포맷별 파서 — 등장 순서 보존 추출, 표 마크다운 직렬화, doc_type 분류.

지원: xlsx / docx / pptx / pdf / txt  (hex/이미지는 별도 경로)
공통 원칙: 표준 양식 비의존. 스타일 이름에 의존하지 않고 텍스트·표를 범용 추출한다.
"""
from __future__ import annotations

import os
from typing import Optional

from ..config import CONFIG
from .models import Element, ParsedDoc
from .tables import table_to_markdown

SUPPORTED_EXTS = {"xlsx", "docx", "pptx", "pdf", "txt"}


# ---------------------------------------------------------------------------
def _classify(doc_title: str, sample_text: str) -> str:
    hay = (doc_title + "\n" + sample_text).lower()
    for kw in CONFIG.protocol_keywords:
        if kw.lower() in hay:
            return "protocol_spec"
    return "general"


def _title_from_name(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


# ---------------------------------------------------------------------------
# xlsx
# ---------------------------------------------------------------------------
def parse_xlsx(path: str) -> ParsedDoc:
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=True)
    elements: list = []
    sample = []
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        if not rows:
            continue
        # 병합셀 fill-forward
        maxc = max((len(r) for r in rows), default=0)
        rows = [r + [None] * (maxc - len(r)) for r in rows]
        for rng in list(ws.merged_cells.ranges):
            tl = rows[rng.min_row - 1][rng.min_col - 1]
            for r in range(rng.min_row, rng.max_row + 1):
                for c in range(rng.min_col, rng.max_col + 1):
                    if 0 <= r - 1 < len(rows) and 0 <= c - 1 < len(rows[r - 1]):
                        rows[r - 1][c - 1] = tl
        md = table_to_markdown(rows, header=True)
        if md:
            elements.append(Element("table", md, {"sheet_name": ws.title}))
            sample.append(md[:200])
    title = _title_from_name(path)
    return ParsedDoc(source_file=os.path.basename(path), doc_title=title,
                     doc_type=_classify(title, "\n".join(sample)), ext="xlsx",
                     elements=elements)


# ---------------------------------------------------------------------------
# docx
# ---------------------------------------------------------------------------
def parse_docx(path: str) -> ParsedDoc:
    from docx import Document
    from docx.oxml.text.paragraph import CT_P
    from docx.oxml.table import CT_Tbl
    from docx.text.paragraph import Paragraph
    from docx.table import Table

    doc = Document(path)
    elements: list = []
    section = ""
    first_heading = ""
    for child in doc.element.body.iterchildren():
        if isinstance(child, CT_P):
            p = Paragraph(child, doc)
            txt = (p.text or "").strip()
            if not txt:
                continue
            style = (p.style.name or "") if p.style else ""
            if style.startswith("Heading") or style.startswith("Title"):
                section = txt
                if not first_heading:
                    first_heading = txt
            elements.append(Element("text", txt, {"section": section}))
        elif isinstance(child, CT_Tbl):
            t = Table(child, doc)
            rows = [[c.text for c in row.cells] for row in t.rows]
            md = table_to_markdown(rows, header=True)
            if md:
                elements.append(Element("table", md, {"section": section}))
    title = first_heading or _title_from_name(path)
    sample = "\n".join(e.text[:200] for e in elements[:8])
    return ParsedDoc(source_file=os.path.basename(path), doc_title=title,
                     doc_type=_classify(title, sample), ext="docx", elements=elements)


# ---------------------------------------------------------------------------
# pptx
# ---------------------------------------------------------------------------
def parse_pptx(path: str) -> ParsedDoc:
    from pptx import Presentation
    prs = Presentation(path)
    elements: list = []
    sample = []
    for idx, slide in enumerate(prs.slides, start=1):
        for shape in slide.shapes:
            if shape.has_table:
                tbl = shape.table
                rows = [[tbl.cell(r, c).text for c in range(len(tbl.columns))]
                        for r in range(len(tbl.rows))]
                md = table_to_markdown(rows, header=True)
                if md:
                    elements.append(Element("table", md, {"slide_no": idx}))
            elif shape.has_text_frame:
                txt = "\n".join(p.text for p in shape.text_frame.paragraphs).strip()
                if txt:
                    elements.append(Element("text", txt, {"slide_no": idx}))
                    if len(sample) < 8:
                        sample.append(txt[:120])
    title = _title_from_name(path)
    return ParsedDoc(source_file=os.path.basename(path), doc_title=title,
                     doc_type=_classify(title, "\n".join(sample)), ext="pptx",
                     elements=elements)


# ---------------------------------------------------------------------------
# pdf
# ---------------------------------------------------------------------------
def parse_pdf(path: str) -> ParsedDoc:
    import pdfplumber
    elements: list = []
    sample = []
    scanned_pages = []
    with pdfplumber.open(path) as pdf:
        for idx, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()
            tables = page.extract_tables() or []
            if not text and not tables:
                scanned_pages.append(idx)   # 스캔 PDF 가능성 → OCR(Phase 3)
                continue
            if text:
                elements.append(Element("text", text, {"page_no": idx}))
                if len(sample) < 5:
                    sample.append(text[:200])
            for t in tables:
                md = table_to_markdown(t, header=True)
                if md:
                    elements.append(Element("table", md, {"page_no": idx}))
    title = _title_from_name(path)
    doc = ParsedDoc(source_file=os.path.basename(path), doc_title=title,
                    doc_type=_classify(title, "\n".join(sample)), ext="pdf",
                    elements=elements)
    if scanned_pages:
        # 스캔 페이지 메모(구현 Phase 3 OCR 대상)
        doc.elements.append(Element("text",
                                    f"[OCR 필요 페이지: {scanned_pages}]",
                                    {"page_no": scanned_pages[0], "section": "_ocr_todo"}))
    return doc


# ---------------------------------------------------------------------------
# txt (인코딩 자동 판별)
# ---------------------------------------------------------------------------
def parse_txt(path: str) -> ParsedDoc:
    from charset_normalizer import from_path
    best = from_path(path).best()
    text = str(best) if best else ""
    enc = best.encoding if best else "unknown"
    title = _title_from_name(path)
    elements = [Element("text", text.strip(), {"section": "", "encoding": enc})] if text.strip() else []
    return ParsedDoc(source_file=os.path.basename(path), doc_title=title,
                     doc_type=_classify(title, text[:400]), ext="txt", elements=elements)


# ---------------------------------------------------------------------------
_DISPATCH = {
    "xlsx": parse_xlsx, "docx": parse_docx, "pptx": parse_pptx,
    "pdf": parse_pdf, "txt": parse_txt,
}


def parse_file(path: str) -> ParsedDoc:
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if ext not in _DISPATCH:
        raise ValueError(f"지원하지 않는 확장자: .{ext} (지원: {sorted(SUPPORTED_EXTS)})")
    return _DISPATCH[ext](path)
