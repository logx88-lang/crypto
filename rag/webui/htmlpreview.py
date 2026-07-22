"""근거 문서 원본 미리보기 → HTML 조각(웹 UI 모달용). Streamlit 비의존.

xlsx→HTML 표, docx/pptx→문단+표, pdf→해당 페이지 이미지(base64), txt→텍스트.
이미 설치된 라이브러리(openpyxl·pdfplumber·python-docx·python-pptx·pandas) 사용.
"""
from __future__ import annotations

import base64
import html
import io
import os

from ..config import CONFIG

_MAX_ELEMENTS = 400


def _esc(s):
    return html.escape(str(s if s is not None else ""))


def _rows_to_html(rows) -> str:
    if not rows:
        return "<p class='text-gray-400'>(빈 표)</p>"
    ncol = max((len(r) for r in rows), default=0)
    out = ["<table class='min-w-full text-sm border-collapse'>"]
    for ri, r in enumerate(rows):
        cells = [("" if v is None else str(v)) for v in r] + [""] * (ncol - len(r))
        tag = "th" if ri == 0 else "td"
        cls = ("bg-gray-100 font-semibold" if ri == 0 else "") + " border border-gray-200 px-2 py-1 text-left"
        out.append("<tr>" + "".join(f"<{tag} class='{cls}'>{_esc(c)}</{tag}>" for c in cells) + "</tr>")
    out.append("</table>")
    return "".join(out)


def render_file(rel_path: str, loc: dict = None) -> str:
    loc = loc or {}
    if not rel_path:
        return "<p class='text-amber-600'>원본 경로 정보가 없습니다.</p>"
    path = os.path.join(CONFIG.data_dir, *rel_path.split("/"))
    if not os.path.exists(path):
        return f"<p class='text-amber-600'>파일을 찾을 수 없습니다: {_esc(rel_path)}</p>"
    ext = rel_path.rsplit(".", 1)[-1].lower() if "." in rel_path else ""
    head = f"<div class='text-xs text-gray-500 mb-3'>📄 {_esc(rel_path)}</div>"
    try:
        if ext == "xlsx":
            return head + _xlsx(path, loc)
        if ext == "pdf":
            return head + _pdf(path, loc)
        if ext == "docx":
            return head + _docx(path)
        if ext == "pptx":
            return head + _pptx(path)
        if ext in ("txt", "log", "csv"):
            return head + _txt(path)
        if ext == "doc":
            return head + "<p class='text-gray-500'>구형 .doc 는 미리보기를 지원하지 않습니다.</p>"
        return head + f"<p class='text-gray-500'>'{_esc(ext)}' 형식 미리보기 미지원.</p>"
    except Exception as e:
        return head + f"<p class='text-amber-600'>미리보기 실패: {_esc(type(e).__name__)}: {_esc(e)}</p>"


def _xlsx(path, loc):
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    sheets = wb.sheetnames
    target = loc.get("sheet_name") if loc.get("sheet_name") in sheets else sheets[0]
    tabs = "".join(
        f"<button class='px-2 py-1 text-xs rounded mr-1 mb-1 {'bg-[#d6006a] text-white' if s==target else 'bg-gray-100'}' "
        f"hx-get='/preview?rel_path={_url(path_relparam(path))}&sheet_name={_url(s)}' "
        f"hx-target='#modal-body'>{_esc(s)}</button>" for s in sheets)
    rows = [[c.value for c in row] for row in wb[target].iter_rows()]
    return f"<div class='mb-2'>{tabs}</div><div class='overflow-auto max-h-[65vh]'>{_rows_to_html(rows)}</div>"


def path_relparam(path):
    # data_dir 기준 상대경로 복원(시트 전환 링크용)
    rel = os.path.relpath(path, CONFIG.data_dir).replace("\\", "/")
    return rel


def _url(s):
    import urllib.parse
    return urllib.parse.quote(str(s))


def _pdf(path, loc):
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        n = len(pdf.pages)
        pno = min(max(int(loc.get("page_no") or 1), 1), n)
        img = pdf.pages[pno - 1].to_image(resolution=130)
        buf = io.BytesIO(); img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
    rel = path_relparam(path)
    nav = ""
    if n > 1:
        prev = f"<button class='px-2 py-1 bg-gray-100 rounded text-xs' hx-get='/preview?rel_path={_url(rel)}&page_no={pno-1}' hx-target='#modal-body' {'disabled' if pno<=1 else ''}>◀ 이전</button>"
        nxt = f"<button class='px-2 py-1 bg-gray-100 rounded text-xs' hx-get='/preview?rel_path={_url(rel)}&page_no={pno+1}' hx-target='#modal-body' {'disabled' if pno>=n else ''}>다음 ▶</button>"
        nav = f"<div class='flex items-center gap-2 mb-2 text-xs text-gray-500'>{prev}<span>{pno} / {n}</span>{nxt}</div>"
    return f"{nav}<div class='overflow-auto max-h-[70vh]'><img class='w-full border border-gray-200' src='data:image/png;base64,{b64}'></div>"


def _docx(path):
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    d = docx.Document(path)
    out, cnt = ["<div class='overflow-auto max-h-[70vh] space-y-2'>"], 0
    for ch in d.element.body.iterchildren():
        if cnt >= _MAX_ELEMENTS:
            out.append("<p class='text-gray-400 text-xs'>… (문서가 길어 이후 생략)</p>"); break
        if ch.tag.endswith("}p"):
            t = Paragraph(ch, d).text
            if t.strip():
                out.append(f"<p>{_esc(t)}</p>"); cnt += 1
        elif ch.tag.endswith("}tbl"):
            rows = [[c.text for c in r.cells] for r in Table(ch, d).rows]
            out.append(_rows_to_html(rows)); cnt += 1
    out.append("</div>")
    return "".join(out)


def _pptx(path):
    from pptx import Presentation
    prs = Presentation(path)
    out = ["<div class='overflow-auto max-h-[70vh] space-y-3'>"]
    for i, slide in enumerate(prs.slides, start=1):
        out.append(f"<div class='font-semibold text-gray-600'>— 슬라이드 {i} —</div>")
        for shape in slide.shapes:
            if shape.has_table:
                tbl = shape.table
                rows = [[tbl.cell(r, c).text for c in range(len(tbl.columns))]
                        for r in range(len(tbl.rows))]
                out.append(_rows_to_html(rows))
            elif shape.has_text_frame and shape.text_frame.text.strip():
                out.append(f"<p>{_esc(shape.text_frame.text)}</p>")
    out.append("</div>")
    return "".join(out)


def _txt(path):
    from charset_normalizer import from_path
    try:
        text = str(from_path(path).best())
    except Exception:
        text = open(path, encoding="utf-8", errors="replace").read()
    return f"<pre class='whitespace-pre-wrap text-xs overflow-auto max-h-[70vh] bg-gray-50 p-3 rounded'>{_esc(text[:20000])}</pre>"
