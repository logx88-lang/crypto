"""백엔드 JSON API — 네이티브 클라이언트가 호출. 표준 라이브러리만 사용(의존성 0).

RAG 로직(rag/*)을 그대로 재사용한다. 서버 A에서 실행하며 Ollama·인덱스와 함께 상주.

엔드포인트(모두 POST, body=JSON; GET은 조회):
  GET  /health                         → {"ok":true, ...}
  POST /qa            {question}        → {answer, sources, contexts}
  POST /log/candidates {log_text, question} → {candidates:[{id,file,section,preview,document,metadata}]}
  POST /log/analyze   {log_text, spec_docs:[document...], question} → {summary, derived, profile, out}
  POST /index         {full}            → {stats}
  GET  /docs                            → {docs:[...], count}
  POST /upload        {name, content_b64}→ {saved}
  POST /feedback      {record, image_b64?}→ {ok, saved}
  GET  /feedback/list                   → {records:[...]}
  POST /feedback/export                 → {path, markdown}

실행: python -m rag.api.server   (환경변수 RAG_* / OLLAMA_HOST 는 기존과 동일)
"""
from __future__ import annotations

import base64
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ..config import CONFIG


# --- 리소스 지연 초기화(프로세스 1회) -------------------------------------
_LOCK = threading.Lock()
_STATE: dict = {}


def _pipeline():
    with _LOCK:
        if "pipeline" not in _STATE:
            from ..generate.answer import build_pipeline
            _STATE["pipeline"] = build_pipeline()
        return _STATE["pipeline"]


def _retriever_llm():
    with _LOCK:
        if "retr" not in _STATE:
            from ..index.embed import EmbeddingClient
            from ..index.store import VectorStore
            from ..index.bm25 import BM25Index
            from ..retrieve.hybrid import HybridRetriever
            from ..generate.llm import LLMClient
            _STATE["retr"] = HybridRetriever(EmbeddingClient(), VectorStore(), BM25Index.load())
            _STATE["llm"] = LLMClient()
        return _STATE["retr"], _STATE["llm"]


def _reset_caches():
    with _LOCK:
        _STATE.pop("pipeline", None)
        _STATE.pop("retr", None)
        _STATE.pop("llm", None)


# --- 핸들러 로직 -----------------------------------------------------------
def h_health(_body):
    return {"ok": True, "embed": CONFIG.embed_model, "llm": CONFIG.llm_model,
            "data_dir": CONFIG.data_dir}


def _scope_where(body):
    """범위 필터: files(전체경로) 우선 → rel_path $in, 없으면 folders → folder $in."""
    files = body.get("files") or []
    if files:
        return {"rel_path": {"$in": list(files)}}
    folders = body.get("folders") or []
    if folders:
        return {"folder": {"$in": list(folders)}}
    return None


def h_qa(body):
    q = (body.get("question") or "").strip()
    if not q:
        return {"error": "question 필요"}
    return _pipeline().answer(q, where=_scope_where(body))


def h_folders(_body):
    from ..index.store import VectorStore
    try:
        return {"folders": VectorStore().folders()}
    except Exception:
        return {"folders": []}


def h_log_candidates(body):
    from ..logs.workflow import find_spec_candidates
    retr, _llm = _retriever_llm()
    cands = find_spec_candidates(retr, body.get("log_text", ""),
                                 body.get("question", ""), top_k=body.get("top_k", 5),
                                 folders=body.get("folders") or None,
                                 files=body.get("files") or None)
    out = []
    for c in cands:
        m = c.get("metadata", {})
        out.append({
            "file": os.path.basename(str(m.get("source_file") or m.get("doc_title") or "")),
            "section": m.get("section") or m.get("page_no") or "",
            "preview": (c.get("document", "")[:60].replace("\n", " ")).strip(),
            "document": c.get("document", ""), "metadata": m,
        })
    return {"candidates": out}


def h_log_analyze(body):
    from ..logs.generic import analyze_by_spec
    from ..logs.workflow import summarize_analysis, explain, resolve_command_names
    from ..logs.detect import detect_log_type
    retr, llm = _retriever_llm()
    text = body.get("log_text", "")
    spec_docs = body.get("spec_docs", []) or []
    spec_text = "\n\n".join(spec_docs)
    q = body.get("question", "")
    parsed = analyze_by_spec(text, spec_text, llm) if spec_text else {"derived": False}
    if not parsed.get("derived"):
        from ..logs.parser import analyze_text_log
        parsed = analyze_text_log(text)
        parsed["derived"] = False
    # 관측 명령을 정의하는 명령표를 검색으로 찾아 이름 매핑 확보(문서 추측 없이).
    cmd_names = resolve_command_names(retr, parsed)
    summary = summarize_analysis(parsed, cmd_names=cmd_names)
    out = explain(llm, q, parsed, [{"document": d, "metadata": {}} for d in spec_docs],
                  cmd_names=cmd_names)
    return {"log_type": detect_log_type(text), "derived": parsed.get("derived", False),
            "profile": parsed.get("profile"), "summary": summary, "out": out,
            "total": parsed.get("total"), "valid_count": parsed.get("valid_count")}


def h_index(body):
    from ..index.indexer import Indexer
    stats = Indexer().reindex(full=bool(body.get("full", False)))
    _reset_caches()
    return {"stats": stats}


def h_docs(_body):
    from ..index.indexer import list_documents
    docs = list_documents()
    return {"docs": docs, "count": len(docs)}


def h_upload(body):
    name = os.path.basename(body.get("name", "").strip())
    if not name or "content_b64" not in body:
        return {"error": "name/content_b64 필요"}
    folder = os.path.basename((body.get("folder") or "").strip())   # 하위폴더(선택)
    dest_dir = os.path.join(CONFIG.data_dir, folder) if folder else CONFIG.data_dir
    os.makedirs(dest_dir, exist_ok=True)
    with open(os.path.join(dest_dir, name), "wb") as f:
        f.write(base64.b64decode(body["content_b64"]))
    return {"saved": name, "folder": folder or "미분류"}


def h_feedback(body):
    from ..feedback import FeedbackLog, sanitize_record, readable_record
    rec = body.get("record", {})
    safe = sanitize_record(rec) if body.get("redact") else readable_record(rec)
    img = base64.b64decode(body["image_b64"]) if body.get("image_b64") else None
    saved = FeedbackLog().add(safe, already_sanitized=True, image_bytes=img)
    return {"ok": True, "saved": saved}


def h_feedback_list(_body):
    from ..feedback import FeedbackLog
    return {"records": FeedbackLog().load_all()}


def h_feedback_export(_body):
    from ..feedback import FeedbackLog
    log = FeedbackLog()
    path = log.export_markdown()
    with open(path, encoding="utf-8") as f:
        return {"path": path, "markdown": f.read()}


ROUTES = {
    ("GET", "/health"): h_health,
    ("GET", "/folders"): h_folders,
    ("POST", "/qa"): h_qa,
    ("POST", "/log/candidates"): h_log_candidates,
    ("POST", "/log/analyze"): h_log_analyze,
    ("POST", "/index"): h_index,
    ("GET", "/docs"): h_docs,
    ("POST", "/upload"): h_upload,
    ("POST", "/feedback"): h_feedback,
    ("GET", "/feedback/list"): h_feedback_list,
    ("POST", "/feedback/export"): h_feedback_export,
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle(self, method):
        fn = ROUTES.get((method, self.path.split("?")[0]))
        if not fn:
            return self._send({"error": "not found"}, 404)
        body = {}
        if method == "POST":
            n = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(n) if n else b""
            try:
                body = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                return self._send({"error": "bad json"}, 400)
        try:
            self._send(fn(body))
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._send({"error": f"{type(e).__name__}: {e}"}, 500)

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def log_message(self, fmt, *args):
        sys.stderr.write("[api] " + (fmt % args) + "\n")


def main(host="0.0.0.0", port=None):
    port = port or int(os.environ.get("RAG_API_PORT", "8600"))
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"[api] RAG 백엔드 API 실행: http://{host}:{port}  (Ctrl+C 종료)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
