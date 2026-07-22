"""근거 문서 '원본 미리보기' — 청크 텍스트가 아니라 원본을 형식별로 읽기 좋게 렌더.

새 의존성 없이 이미 설치된 라이브러리 사용:
- xlsx: openpyxl → pandas DataFrame(st.dataframe)  (표가 안 깨짐)
- pdf : pdfplumber → 해당 페이지를 이미지로 렌더(표·도형 그대로)
- docx/pptx: python-docx/pptx → 문단 + 표(st.table)
- txt : 텍스트
청크 위치(loc: page_no/sheet_name/slide_no/section)를 기본 선택으로 잡아준다.
"""
from __future__ import annotations

import os

import streamlit as st

from ..config import CONFIG

_MAX_ELEMENTS = 400   # 대용량 문서 렌더 상한(과부하 방지)


def _rows_to_df(rows):
    """표 행렬 → pandas DataFrame. 열 이름을 항상 고유하게 하고 행 길이를 정규화한다.

    Streamlit(Arrow)은 '중복 열 이름'이면 표시에 실패하므로, 헤더가 유효(중복·빈칸 없음)할
    때만 헤더로 쓰고, 아니면 '열1, 열2…' 로 대체한다. 짧은 행은 빈칸으로 채운다.
    """
    import pandas as pd
    rows = list(rows or [])
    if not rows:
        return pd.DataFrame()
    ncol = max((len(r) for r in rows), default=0)
    norm = [[("" if v is None else str(v)) for v in r] + [""] * (ncol - len(r)) for r in rows]
    header = [c.strip() for c in norm[0]]
    if len(norm) > 1 and all(header) and len(set(header)) == len(header):
        return pd.DataFrame(norm[1:], columns=header)
    return pd.DataFrame(norm, columns=[f"열{i + 1}" for i in range(ncol)])


def render_file(rel_path: str, loc: dict = None) -> None:
    loc = loc or {}
    if not rel_path:
        st.warning("원본 경로 정보가 없어 미리보기를 열 수 없습니다(재인덱싱하면 경로가 저장됩니다).")
        return
    path = os.path.join(CONFIG.data_dir, *rel_path.split("/"))
    if not os.path.exists(path):
        st.warning(f"파일을 찾을 수 없습니다: {rel_path}")
        return
    ext = rel_path.rsplit(".", 1)[-1].lower() if "." in rel_path else ""
    st.caption(f"📄 {rel_path}")
    try:
        if ext == "xlsx":
            _xlsx(path, loc)
        elif ext == "pdf":
            _pdf(path, loc)
        elif ext == "docx":
            _docx(path)
        elif ext == "pptx":
            _pptx(path)
        elif ext in ("txt", "log", "csv"):
            _txt(path)
        elif ext == "doc":
            st.info("구형 .doc 는 원본 미리보기를 지원하지 않습니다. 아래 근거 발췌를 참고하세요.")
        else:
            st.info(f"'{ext}' 형식은 원본 미리보기를 지원하지 않습니다.")
    except Exception as e:
        st.warning(f"미리보기 실패: {type(e).__name__}: {e}")


def _xlsx(path, loc):
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    sheets = wb.sheetnames
    default = loc.get("sheet_name") if loc.get("sheet_name") in sheets else sheets[0]
    sel = st.selectbox("시트", sheets, index=sheets.index(default),
                       key=f"pv_sheet_{path}")
    rows = [[c.value for c in row] for row in wb[sel].iter_rows()]
    if not rows:
        st.info("(빈 시트)")
        return
    df = _rows_to_df(rows)
    st.dataframe(df, use_container_width=True, height=min(600, 40 + 28 * len(df)))


def _pdf(path, loc):
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        n = len(pdf.pages)
        default = int(loc.get("page_no") or 1)
        default = min(max(default, 1), n)
        pno = st.number_input(f"페이지 (1~{n})", 1, n, default, key=f"pv_pg_{path}")
        img = pdf.pages[pno - 1].to_image(resolution=130)
        st.image(img.original, use_container_width=True)


def _docx(path):
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    d = docx.Document(path)
    cnt = 0
    for ch in d.element.body.iterchildren():
        if cnt >= _MAX_ELEMENTS:
            st.caption("… (문서가 길어 이후 생략)")
            break
        if ch.tag.endswith("}p"):
            t = Paragraph(ch, d).text
            if t.strip():
                st.markdown(t); cnt += 1
        elif ch.tag.endswith("}tbl"):
            rows = [[c.text for c in r.cells] for r in Table(ch, d).rows]
            if rows:
                st.table(_rows_to_df(rows))
            cnt += 1


def _pptx(path):
    from pptx import Presentation
    prs = Presentation(path)
    for i, slide in enumerate(prs.slides, start=1):
        st.markdown(f"**— 슬라이드 {i} —**")
        for shape in slide.shapes:
            if shape.has_table:
                tbl = shape.table
                rows = [[tbl.cell(r, c).text for c in range(len(tbl.columns))]
                        for r in range(len(tbl.rows))]
                if rows:
                    st.table(_rows_to_df(rows))
            elif shape.has_text_frame and shape.text_frame.text.strip():
                st.markdown(shape.text_frame.text)


def _txt(path):
    from charset_normalizer import from_path
    try:
        text = str(from_path(path).best())
    except Exception:
        text = open(path, encoding="utf-8", errors="replace").read()
    st.code(text[:20000])
