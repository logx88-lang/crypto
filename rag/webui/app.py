"""사내 지식 QnA 웹 UI — Starlette + HTMX. 백엔드(rag.chat/logs/index/feedback)를 그대로 사용.

실행:  uvicorn rag.webui.app:app --host 0.0.0.0 --port 8502
세션:  서버 메모리(쿠키 sid) — 간이 로그인. HTTPS 불필요(복사/이미지붙여넣기는 프론트 처리).
기능:  대화(멀티턴 RAG + 문서범위 트리 + 로그첨부 분석) · 개선기록(비식별 반출) · 관리(인덱싱).
"""
from __future__ import annotations

import base64
import html
import os
import re
import secrets
import urllib.parse
from datetime import datetime, timezone

from starlette.applications import Starlette
from starlette.responses import HTMLResponse, RedirectResponse, PlainTextResponse, FileResponse
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from .. import chat as chatmod  # noqa: F401  (패키지 로드)
from ..chat import store, engine
from . import scopetree

BASE = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE, "templates"))

SESSIONS: dict = {}     # sid -> {"user":..., "conv":cid, "scope":{cid:set}, "open":{cid:set}, "plog":{...}}
_PIPE: dict = {}

FB_CATS = ["표 추출 오류(표가 깨져 보임)", "표 희석(관련 표 누락/후순위)", "틀린 답변",
           "근거 못 찾음(문서엔 있음)", "출처 오류", "기타"]


def get_pipe():
    if "p" not in _PIPE:
        from ..generate.answer import build_pipeline
        _PIPE["p"] = build_pipeline()
    return _PIPE["p"]


def _now():
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def _sess(request):
    return SESSIONS.get(request.cookies.get("sid"))


def _current_conv(sess):
    user = sess["user"]
    cid = sess.get("conv")
    try:
        if cid:
            return store.load_conversation(user, cid)
    except Exception:
        pass
    cvs = store.list_conversations(user)
    conv = store.load_conversation(user, cvs[0]["id"]) if cvs else store.new_conversation(user)
    sess["conv"] = conv["id"]
    return conv


def _scope_set(sess, cid) -> set:
    return sess.setdefault("scope", {}).setdefault(cid, set())


def _open_set(sess, cid) -> set:
    return sess.setdefault("open", {}).setdefault(cid, set())


def _docs():
    from ..index.indexer import list_documents
    return list_documents()


# --- 답변 렌더(마크다운-라이트 + 표 + 인용 [N] 클릭 링크) ------------------
_SEP_ROW = re.compile(r"^[\s|:\-]+$")          # |:--:|---| 류 구분행


def _table_html(rows: list) -> str:
    """마크다운 표 행들(| a | b |)을 실제 <table> 로 렌더(구분행 제거, 1행=헤더)."""
    parsed = []
    for r in rows:
        if _SEP_ROW.match(r):
            continue
        cells = [c.strip() for c in r.strip().strip("|").split("|")]
        parsed.append(cells)
    if not parsed:
        return ""
    ncol = max(len(r) for r in parsed)
    out = ["<div class='overflow-x-auto my-2'><table class='text-sm border-collapse'>"]
    for i, r in enumerate(parsed):
        cells = r + [""] * (ncol - len(r))
        tag = "th" if i == 0 else "td"
        cls = ("bg-gray-100 font-semibold" if i == 0 else "") + \
              " border border-gray-300 px-2 py-1 text-left align-top"
        out.append("<tr>" + "".join(
            f"<{tag} class='{cls}'>{_bold(html.escape(c))}</{tag}>" for c in cells) + "</tr>")
    out.append("</table></div>")
    return "".join(out)


def _md_lite(text: str) -> str:
    lines = (text or "").split("\n")
    out, in_ul, tbl = [], False, []

    def flush_tbl():
        nonlocal tbl
        if tbl:
            out.append(_table_html(tbl)); tbl = []

    for ln in lines:
        s = ln.strip()
        if s.startswith("|") and s.count("|") >= 2:      # 표 행 수집
            if in_ul:
                out.append("</ul>"); in_ul = False
            tbl.append(s)
            continue
        flush_tbl()
        if s[:2] in ("- ", "• ", "* ") or s[:1] in ("•",) and len(s) > 1:
            if not in_ul:
                out.append("<ul class='list-disc pl-5 space-y-0.5 my-1'>"); in_ul = True
            out.append(f"<li>{_bold(html.escape(s.lstrip('-•* ').strip()))}</li>")
        else:
            if in_ul:
                out.append("</ul>"); in_ul = False
            if s:
                out.append(f"<p class='my-1'>{_bold(html.escape(s))}</p>")
    flush_tbl()
    if in_ul:
        out.append("</ul>")
    return "".join(out)


def _bold(s: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)


_IMG_EXTS = ("png", "jpg", "jpeg", "bmp", "tiff", "tif")


def _src_image_url(s: dict):
    """근거 s를 이미지로 보여줄 수 있으면 /srcimg URL, 아니면 None (이미지 파일 or PDF 페이지)."""
    rel = s.get("rel_path") or ""
    ext = rel.rsplit(".", 1)[-1].lower() if "." in rel else ""
    loc = s.get("loc") or {}
    if ext in _IMG_EXTS or (ext == "pdf" and loc.get("page_no")):
        params = {"rel_path": rel}
        if loc.get("page_no"):
            params["page_no"] = str(loc["page_no"])
        return "/srcimg?" + urllib.parse.urlencode(params)
    return None


def _link_citations(html_text: str, sources: list) -> str:
    smap = {int(s["n"]): s for s in sources if s.get("rel_path")}

    def cite(n):
        s = smap.get(n)
        if not s:
            return None
        params = {"rel_path": s["rel_path"]}
        params.update({k: str(v) for k, v in (s.get("loc") or {}).items()})
        url = "/preview?" + urllib.parse.urlencode(params)
        return (f"<sup class='cite' hx-get='{html.escape(url)}' hx-target='#modal-body' "
                f"onclick='openModal()' title='원본 미리보기'>[{n}]</sup>")

    def repl_img(m):
        """[그림 N]/[이미지 N] → 해당 근거의 그림/페이지를 답변 안에 인라인 표시(클릭=원본 팝업)."""
        n = int(m.group(1))
        s = smap.get(n)
        img = _src_image_url(s) if s else None
        if not img:
            return cite(n) or m.group(0)     # 이미지化 불가 → 일반 인용으로 강등
        pv = {"rel_path": s["rel_path"]}
        pv.update({k: str(v) for k, v in (s.get("loc") or {}).items()})
        pv_url = "/preview?" + urllib.parse.urlencode(pv)
        return (f"<span class='block my-2'><img src='{html.escape(img)}' "
                f"class='max-w-md w-full border border-gray-200 rounded-lg cursor-zoom-in' "
                f"hx-get='{html.escape(pv_url)}' hx-target='#modal-body' onclick='openModal()' "
                f"title='근거 [{n}] 원본 보기'>"
                f"<span class='block text-xs text-gray-400 mt-0.5'>그림: 근거 [{n}]</span></span>")

    def repl_num(m):
        return cite(int(m.group(1))) or m.group(0)

    html_text = re.sub(r"\[(?:그림|이미지)\s*(\d+)\]", repl_img, html_text)
    return re.sub(r"\[(\d+)\]", repl_num, html_text)


def _msg_html(request, m: dict, idx: int, cid: str) -> str:
    if m["role"] == "user":
        return templates.env.get_template("_user_msg.html").render(text=m["content"])
    body = _link_citations(_md_lite(m["content"]), m.get("sources") or [])
    return templates.env.get_template("_assistant_msg.html").render(
        body=body, sources=m.get("sources") or [], idx=idx, cid=cid,
        timing=m.get("timing"), answer_raw=m["content"], enc=urllib.parse.quote)


def _messages_html(request, conv):
    cid = conv["id"]
    return "".join(_msg_html(request, m, i, cid)
                   for i, m in enumerate(conv.get("messages", [])))


# --- 페이지 ----------------------------------------------------------------
async def index(request):
    sess = _sess(request)
    if not sess:
        return templates.TemplateResponse(request, "login.html", {})
    conv = _current_conv(sess)
    cid = conv["id"]
    files = _docs()
    return templates.TemplateResponse(request, "chat.html", {
        "page": "chat", "user": sess["user"], "conv": conv,
        "convs": store.list_conversations(sess["user"]),
        "messages_html": _messages_html(request, conv),
        "scope_html": scopetree.render_tree(files, _scope_set(sess, cid), _open_set(sess, cid)),
    })


async def login(request):
    form = await request.form()
    ok, msg = store.login_or_register(form.get("username", ""), form.get("password", ""))
    if not ok:
        return templates.TemplateResponse(request, "login.html", {"error": msg})
    sid = secrets.token_hex(16)
    SESSIONS[sid] = {"user": form.get("username", "").strip()}
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


async def logout(request):
    SESSIONS.pop(request.cookies.get("sid"), None)
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("sid")
    return resp


async def new_conv(request):
    sess = _sess(request)
    if not sess:
        return RedirectResponse("/", 303)
    conv = store.new_conversation(sess["user"])
    sess["conv"] = conv["id"]
    return RedirectResponse("/", 303)


async def switch_conv(request):
    sess = _sess(request)
    if sess:
        sess["conv"] = request.path_params["cid"]
    return RedirectResponse("/", 303)


async def delete_conv(request):
    sess = _sess(request)
    if sess:
        store.delete_conversation(sess["user"], request.path_params["cid"])
        sess.pop("conv", None)
    return RedirectResponse("/", 303)


# --- 대화(채팅) ------------------------------------------------------------
async def chat(request):
    sess = _sess(request)
    if not sess:
        return PlainTextResponse("세션 만료", 401)
    conv = _current_conv(sess)
    form = await request.form()
    q = (form.get("message") or "").strip()
    if not q:
        return HTMLResponse("")
    scope = sorted(_scope_set(sess, conv["id"])) or None
    try:
        engine.answer(get_pipe(), conv, q, scope_files=scope)
    except Exception as e:
        err = html.escape(f"오류: {e} — Ollama·인덱스를 확인하세요.")
        conv["messages"].append({"role": "user", "content": q})
        conv["messages"].append({"role": "assistant", "content": err, "sources": []})
    msgs = conv.get("messages", [])
    return HTMLResponse("".join(_msg_html(request, m, len(msgs) - 2 + i, conv["id"])
                               for i, m in enumerate(msgs[-2:])))


# --- 문서 범위(스코프) 트리 ------------------------------------------------
async def scope_check(request):
    sess = _sess(request)
    if not sess:
        return PlainTextResponse("세션 만료", 401)
    conv = _current_conv(sess)
    form = await request.form()
    path = form.get("path", "")
    files = _docs()
    sel = _scope_set(sess, conv["id"])
    if form.get("folder") == "1":
        scopetree.toggle_folder(sel, path, files)
    else:
        scopetree.toggle_file(sel, path)
    return HTMLResponse(scopetree.render_tree(files, sel, _open_set(sess, conv["id"])))


async def scope_fold(request):
    sess = _sess(request)
    if not sess:
        return PlainTextResponse("세션 만료", 401)
    conv = _current_conv(sess)
    form = await request.form()
    path = form.get("path", "")
    ops = _open_set(sess, conv["id"])
    ops.discard(path) if path in ops else ops.add(path)
    return HTMLResponse(scopetree.render_tree(_docs(), _scope_set(sess, conv["id"]), ops))


# --- 로그 첨부(대화형 로그 분석) -------------------------------------------
def _logpanel_html(request, sess, conv):
    return templates.env.get_template("_logpanel.html").render(
        conv=conv, plog=sess.get("plog"), basename=os.path.basename)


def _prepare_plog(sess, text, name):
    """로그 텍스트로 명세 후보를 찾아 세션에 보관(파일 업로드/붙여넣기 공용)."""
    from ..logs.workflow import find_spec_candidates, spec_files
    cands = find_spec_candidates(get_pipe().retriever, text, "", top_k=15)
    sess["plog"] = {"text": text, "name": name, "specs": spec_files(cands)}


async def log_upload(request):
    sess = _sess(request)
    if not sess:
        return PlainTextResponse("세션 만료", 401)
    conv = _current_conv(sess)
    form = await request.form()
    up = form.get("logfile")
    if up is None or not getattr(up, "filename", ""):
        return HTMLResponse(_logpanel_html(request, sess, conv))
    text = (await up.read()).decode("utf-8", errors="replace")
    try:
        _prepare_plog(sess, text, up.filename)
    except Exception as e:
        return HTMLResponse(f"<p class='text-red-500 text-sm'>로그 준비 실패: {html.escape(str(e))}</p>")
    return HTMLResponse(_logpanel_html(request, sess, conv))


async def log_paste(request):
    sess = _sess(request)
    if not sess:
        return PlainTextResponse("세션 만료", 401)
    conv = _current_conv(sess)
    form = await request.form()
    text = (form.get("logtext") or "").strip()
    if not text:
        return HTMLResponse(_logpanel_html(request, sess, conv))
    try:
        _prepare_plog(sess, text, "붙여넣은 로그")
    except Exception as e:
        return HTMLResponse(f"<p class='text-red-500 text-sm'>로그 준비 실패: {html.escape(str(e))}</p>")
    return HTMLResponse(_logpanel_html(request, sess, conv))


async def log_attach(request):
    sess = _sess(request)
    if not sess:
        return PlainTextResponse("세션 만료", 401)
    conv = _current_conv(sess)
    form = await request.form()
    sel = form.getlist("specfiles")
    plog = sess.get("plog")
    if plog and sel:
        try:
            from ..chat import logchat
            pipe = get_pipe()
            logchat.attach_log(conv, plog["text"], sel, pipe.retriever, pipe.llm, name=plog["name"])
            sess.pop("plog", None)
        except Exception as e:
            return HTMLResponse(f"<p class='text-red-500 text-sm'>로그 첨부 실패: {html.escape(str(e))}</p>")
    return HTMLResponse(_logpanel_html(request, sess, conv))


async def log_detach(request):
    sess = _sess(request)
    if not sess:
        return PlainTextResponse("세션 만료", 401)
    conv = _current_conv(sess)
    conv.pop("log", None)
    store.save_conversation(conv)
    sess.pop("plog", None)
    return HTMLResponse(_logpanel_html(request, sess, conv))


# --- 개선 기록(피드백) -----------------------------------------------------
async def fb_form(request):
    sess = _sess(request)
    if not sess:
        return PlainTextResponse("세션 만료", 401)
    conv = _current_conv(sess)
    idx = int(request.query_params.get("idx", -1))
    msgs = conv.get("messages", [])
    ans = msgs[idx]["content"] if 0 <= idx < len(msgs) else ""
    q = msgs[idx - 1]["content"] if idx > 0 and msgs[idx - 1]["role"] == "user" else ""
    return templates.TemplateResponse(request, "_fbform.html",
                                      {"cats": FB_CATS, "question": q, "answer": ans})


async def fb_save(request):
    sess = _sess(request)
    if not sess:
        return PlainTextResponse("세션 만료", 401)
    form = await request.form()
    from ..feedback import FeedbackLog, sanitize_record, readable_record
    record = {"ts": _now(), "kind": "qa", "category": form.get("category", ""),
              "severity": form.get("severity", "중간"), "question": form.get("question", ""),
              "answer": form.get("answer", ""), "note": form.get("note", ""), "contexts": []}
    redact = form.get("redact") == "on"
    rec = sanitize_record(record) if redact else readable_record(record)
    img_bytes = None
    b64 = form.get("image64") or ""
    if b64 and "," in b64:
        try:
            img_bytes = base64.b64decode(b64.split(",", 1)[1])
        except Exception:
            img_bytes = None
    up = form.get("imagefile")
    if up is not None and getattr(up, "filename", ""):
        img_bytes = await up.read()
    FeedbackLog().add(rec, already_sanitized=True, image_bytes=img_bytes)
    tag = "비식별화되어 " if redact else ""
    return HTMLResponse(
        f"<div class='text-green-600 text-sm py-6 text-center'>✅ {tag}저장되었습니다.<br>"
        "‘개선 기록’ 메뉴에서 확인·반출하세요.</div>"
        "<div class='text-center'><button onclick='closeModal()' "
        "class='mt-2 px-4 py-1.5 bg-gray-100 rounded-lg text-sm'>닫기</button></div>")


async def fb_page(request):
    sess = _sess(request)
    if not sess:
        return RedirectResponse("/", 303)
    from ..feedback import FeedbackLog
    from ..config import CONFIG
    records = FeedbackLog().load_all()
    return templates.TemplateResponse(request, "feedback.html", {
        "page": "fb", "user": sess["user"], "conv": _current_conv(sess),
        "convs": store.list_conversations(sess["user"]),
        "records": list(reversed(records[-50:])), "total": len(records),
        "feedback_dir": CONFIG.feedback_dir, "basename": os.path.basename,
        "exists": os.path.exists,
    })


async def fb_export(request):
    sess = _sess(request)
    if not sess:
        return PlainTextResponse("세션 만료", 401)
    from ..feedback import FeedbackLog
    path = FeedbackLog().export_markdown()
    return FileResponse(path, filename="feedback_export.md", media_type="text/markdown")


async def fb_image(request):
    sess = _sess(request)
    if not sess:
        return PlainTextResponse("세션 만료", 401)
    from ..config import CONFIG
    rel = request.query_params.get("f", "")
    path = os.path.normpath(os.path.join(CONFIG.feedback_dir, rel))
    if not path.startswith(os.path.abspath(CONFIG.feedback_dir)) or not os.path.exists(path):
        return PlainTextResponse("not found", 404)
    return FileResponse(path)


# --- 관리(인덱싱) ----------------------------------------------------------
_EXTS = ["xlsx", "docx", "doc", "pptx", "pdf", "txt", "png", "jpg", "jpeg", "bmp", "tiff", "tif"]


def _admin_ctx(request, sess, result=""):
    files = _docs()
    folders = sorted(scopetree.folder_set(files))
    from ..config import CONFIG
    return {"page": "admin", "user": sess["user"], "conv": _current_conv(sess),
            "convs": store.list_conversations(sess["user"]),
            "docs": sorted(files), "folders": folders, "exts": _EXTS, "result": result,
            "cfg": CONFIG}


async def admin_page(request):
    sess = _sess(request)
    if not sess:
        return RedirectResponse("/", 303)
    return templates.TemplateResponse(request, "admin.html", _admin_ctx(request, sess))


def _reindex(full: bool) -> str:
    from ..index.indexer import Indexer
    stats = Indexer().reindex(full=full)
    failed = stats.pop("failed", [])
    _PIPE.clear()                              # 인덱스 갱신 → 파이프라인 재빌드 유도
    msg = f"인덱싱 완료: {html.escape(str(stats))}"
    if failed:
        msg += "<br><span class='text-red-500'>⚠️ 실패 " + str(len(failed)) + "건: " + \
               "; ".join(html.escape(f"{f['file']} — {f['error']}") for f in failed[:10]) + "</span>"
    return msg


async def admin_reindex(request):
    sess = _sess(request)
    if not sess:
        return PlainTextResponse("세션 만료", 401)
    full = request.query_params.get("full") == "1"
    try:
        result = _reindex(full)
    except Exception as e:
        result = f"<span class='text-red-500'>인덱싱 실패: {html.escape(str(e))}</span>"
    return templates.TemplateResponse(request, "_admin_main.html", _admin_ctx(request, sess, result))


async def admin_upload(request):
    sess = _sess(request)
    if not sess:
        return PlainTextResponse("세션 만료", 401)
    from ..config import CONFIG
    form = await request.form()
    ups = [f for f in form.getlist("docs") if getattr(f, "filename", "")]
    folder = (form.get("folder_new") or form.get("folder") or "").strip()
    if not ups:
        return templates.TemplateResponse(request, "_admin_main.html",
                                          _admin_ctx(request, sess, "먼저 파일을 선택하세요."))
    try:
        parts = [p for p in folder.replace("\\", "/").split("/") if p and p not in (".", "..")]
        dest = os.path.join(CONFIG.data_dir, *parts) if parts else CONFIG.data_dir
        os.makedirs(dest, exist_ok=True)
        saved = []
        for f in ups:
            with open(os.path.join(dest, f.filename), "wb") as out:
                out.write(await f.read())
            saved.append(f.filename)
        result = (f"저장: <b>{'/'.join(parts) or '(루트)'}</b> · {len(saved)}개 "
                  f"({html.escape(', '.join(saved[:20]))})<br>" + _reindex(full=False))
    except Exception as e:
        result = f"<span class='text-red-500'>실패: {html.escape(str(e))}</span>"
    return templates.TemplateResponse(request, "_admin_main.html", _admin_ctx(request, sess, result))


# --- 미리보기 --------------------------------------------------------------
async def health(request):
    return PlainTextResponse("ok")             # 네이티브 클라이언트 도달성 확인용


async def srcimg(request):
    """근거 문서를 이미지로 서빙 — 이미지 파일은 원본, PDF는 해당 페이지를 PNG 렌더."""
    sess = _sess(request)
    if not sess:
        return PlainTextResponse("세션 만료", 401)
    from ..config import CONFIG
    rel = request.query_params.get("rel_path", "")
    path = os.path.normpath(os.path.join(CONFIG.data_dir, *rel.split("/")))
    if not path.startswith(os.path.abspath(CONFIG.data_dir)) or not os.path.exists(path):
        return PlainTextResponse("not found", 404)
    ext = rel.rsplit(".", 1)[-1].lower() if "." in rel else ""
    if ext in _IMG_EXTS:
        return FileResponse(path)
    if ext == "pdf":
        try:
            import io
            import pdfplumber
            from starlette.responses import Response
            with pdfplumber.open(path) as pdf:
                pno = min(max(int(request.query_params.get("page_no") or 1), 1), len(pdf.pages))
                img = pdf.pages[pno - 1].to_image(resolution=110)
                buf = io.BytesIO(); img.save(buf, format="PNG")
            return Response(buf.getvalue(), media_type="image/png")
        except Exception as e:
            return PlainTextResponse(f"render fail: {e}", 500)
    return PlainTextResponse("unsupported", 415)


async def preview(request):
    from .htmlpreview import render_file
    qp = dict(request.query_params)
    rel_path = qp.pop("rel_path", "")
    return HTMLResponse(render_file(rel_path, qp))


app = Starlette(routes=[
    Route("/", index),
    Route("/login", login, methods=["POST"]),
    Route("/logout", logout, methods=["POST"]),
    Route("/conv/new", new_conv, methods=["POST"]),
    Route("/conv/{cid}", switch_conv),
    Route("/conv/{cid}/delete", delete_conv, methods=["POST"]),
    Route("/chat", chat, methods=["POST"]),
    Route("/scope/check", scope_check, methods=["POST"]),
    Route("/scope/fold", scope_fold, methods=["POST"]),
    Route("/log/upload", log_upload, methods=["POST"]),
    Route("/log/paste", log_paste, methods=["POST"]),
    Route("/log/attach", log_attach, methods=["POST"]),
    Route("/log/detach", log_detach, methods=["POST"]),
    Route("/feedback", fb_page),
    Route("/feedback/form", fb_form),
    Route("/feedback/save", fb_save, methods=["POST"]),
    Route("/feedback/export", fb_export),
    Route("/feedback/image", fb_image),
    Route("/admin", admin_page),
    Route("/admin/reindex", admin_reindex, methods=["POST"]),
    Route("/admin/upload", admin_upload, methods=["POST"]),
    Route("/health", health),
    Route("/srcimg", srcimg),
    Route("/preview", preview),
    Mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static"),
])
