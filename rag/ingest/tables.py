"""표 → 마크다운 직렬화 유틸 (LLM 가독성 + 검색 친화)."""
from __future__ import annotations

from typing import Sequence, Optional


def _cell(v) -> str:
    if v is None:
        return ""
    s = str(v).replace("\n", " ").replace("|", "\\|").strip()
    return s


def table_to_markdown(rows: Sequence[Sequence], header: bool = True) -> str:
    """2차원 표를 마크다운으로 직렬화.

    - 빈 행/전열 None 은 제거.
    - 열 수는 최대 열 기준으로 패딩.
    - header=True 면 첫 행을 헤더로.
    """
    clean = []
    for r in rows:
        cells = [_cell(c) for c in r]
        if any(c for c in cells):
            clean.append(cells)
    if not clean:
        return ""
    ncol = max(len(r) for r in clean)
    clean = [r + [""] * (ncol - len(r)) for r in clean]

    lines = []
    if header:
        head = clean[0]
        lines.append("| " + " | ".join(head) + " |")
        lines.append("| " + " | ".join(["---"] * ncol) + " |")
        body = clean[1:]
    else:
        lines.append("| " + " | ".join([""] * ncol) + " |")
        lines.append("| " + " | ".join(["---"] * ncol) + " |")
        body = clean
    for r in body:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def markdown_table_rows(rows: Sequence[Sequence], header_row: Optional[Sequence] = None) -> list:
    """큰 표를 행 단위로 분할할 때, 각 조각에 헤더를 반복 부착하기 위한 헬퍼.

    반환: [(md_string), ...] 형태가 아니라 여기서는 원자 행 리스트만 돌려주고
    분할은 청커가 table_max_chars 기준으로 수행한다.
    """
    return [list(r) for r in rows]
