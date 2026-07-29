"""문서 범위(스코프) 체크박스 트리 → HTML 조각. Streamlit 비의존(웹 UI HTMX용).

선택의 '진짜 상태'는 선택된 파일(rel_path) 집합뿐이다. 폴더 체크 표시는 렌더할 때마다
그 폴더 하위 파일이 모두 선택됐는지로 재계산(up) → 문서 추가/삭제·대화 전환에도 어긋나지 않음.
폴더 토글=하위 전체(down). 미선택 = None(전체).
"""
from __future__ import annotations

import html
import json


def folder_set(files) -> set:
    """파일 rel_path 목록 → 등장하는 모든 (중첩) 폴더 경로 집합."""
    folders = set()
    for f in files:
        parts = f.split("/")
        for i in range(1, len(parts)):
            folders.add("/".join(parts[:i]))
    return folders


def tree_rows(files):
    """(폴더+파일)을 깊이우선 순서로 → (depth, path, is_folder, name)."""
    nodes = [(p, True) for p in folder_set(files)] + [(f, False) for f in files]
    nodes.sort(key=lambda x: x[0].split("/"))
    return [(p.count("/"), p, is_dir, p.split("/")[-1]) for p, is_dir in nodes]


def files_under(folder: str, files) -> list:
    pre = folder + "/"
    return [f for f in files if f.startswith(pre)]


def toggle_file(selected: set, path: str) -> None:
    selected.discard(path) if path in selected else selected.add(path)


def toggle_folder(selected: set, folder: str, files) -> None:
    kids = files_under(folder, files)
    if kids and all(f in selected for f in kids):
        selected.difference_update(kids)      # 전체 선택 상태 → 해제
    else:
        selected.update(kids)                 # 일부/미선택 → 전체 선택


def _vals(d: dict) -> str:
    return html.escape(json.dumps(d, ensure_ascii=False))


def render_tree(files, selected: set, open_set: set) -> str:
    """트리 행들의 HTML(#scopetree 내부). 각 체크박스/폴더토글은 HTMX로 서버 상태 갱신."""
    if not files:
        return "<p class='text-xs text-gray-400 px-1 py-2'>인덱싱된 문서가 없습니다. ‘관리’에서 먼저 인덱싱하세요.</p>"
    rows = tree_rows(files)
    out = []
    for depth, path, is_dir, name in rows:
        anc = path.split("/")[:-1]
        if not all("/".join(anc[:i + 1]) in open_set for i in range(len(anc))):
            continue                          # 조상 폴더가 접혀 있으면 숨김
        pad = 8 + depth * 16
        if is_dir:
            kids = files_under(path, files)
            checked = bool(kids) and all(f in selected for f in kids)
            some = (not checked) and any(f in selected for f in kids)
            arrow = "▼" if path in open_set else "▶"
            box = ("checked" if checked else "") + (" data-some='1'" if some else "")
            out.append(
                f"<div class='flex items-center gap-1 py-0.5 text-sm' style='padding-left:{pad}px'>"
                f"<button hx-post='/scope/fold' hx-vals='{_vals({'path': path})}' "
                f"hx-target='#scopetree' hx-swap='innerHTML' class='w-4 text-gray-400 hover:text-gray-700'>{arrow}</button>"
                f"<label class='flex items-center gap-1 cursor-pointer select-none truncate'>"
                f"<input type='checkbox' {box} hx-post='/scope/check' "
                f"hx-vals='{_vals({'path': path, 'folder': 1})}' hx-target='#scopetree' hx-swap='innerHTML' "
                f"class='accent-[#d6006a]'>"
                f"<span class='truncate'>📁 {html.escape(name)}</span></label></div>")
        else:
            checked = "checked" if path in selected else ""
            out.append(
                f"<div class='flex items-center gap-1 py-0.5 text-sm' style='padding-left:{pad + 20}px'>"
                f"<label class='flex items-center gap-1 cursor-pointer select-none truncate'>"
                f"<input type='checkbox' {checked} hx-post='/scope/check' "
                f"hx-vals='{_vals({'path': path, 'folder': 0})}' hx-target='#scopetree' hx-swap='innerHTML' "
                f"class='accent-[#d6006a]'>"
                f"<span class='truncate'>📄 {html.escape(name)}</span></label></div>")
    n = len([f for f in files if f in selected])
    cap = (f"<div class='text-xs text-[#d6006a] px-2 pt-1'>선택 {n}개 파일</div>"
           if n else "<div class='text-xs text-gray-400 px-2 pt-1'>미선택 = 전체 문서 대상</div>")
    return "".join(out) + cap
