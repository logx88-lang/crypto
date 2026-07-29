"""사내 지식 RAG — 네이티브 데스크톱 클라이언트 (Tkinter).

서버 A의 백엔드 API(:8600)를 호출한다. 브라우저가 아니라 네이티브 창이라
**클립보드 이미지 붙여넣기**(PIL.ImageGrab)가 가능하다.

의존성: 표준 tkinter + urllib(내장) + Pillow(이미 배포에 포함). PyInstaller로 exe 빌드.
서버 주소: 환경변수 RAG_API 또는 exe 옆 server.txt 또는 아래 DEFAULT_API.
"""
import base64
import io
import json
import os
import sys
import threading
import urllib.request
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

DEFAULT_API = "http://192.168.155.89:8600"
CATS = {
    "qa": ["표 추출 오류", "표 희석(관련 표 누락)", "틀린 답변", "근거 못 찾음(문서엔 있음)",
           "출처 오류", "기타"],
    "log": ["명세 표 참조 부정확", "필드 오프셋/폭 해석 오류", "프레임 파싱 오류",
            "명세 후보 검색 실패", "틀린 해석", "기타"],
}


def api_base():
    v = os.environ.get("RAG_API", "").strip()
    if not v:
        base = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else __file__)
        p = os.path.join(base, "server.txt")
        if os.path.exists(p):
            try:
                v = open(p, encoding="utf-8").read().strip()
            except Exception:
                v = ""
    return (v or DEFAULT_API).rstrip("/")


def _req(method, path, body=None, timeout=600):
    url = api_base() + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


class CheckTree(ttk.Frame):
    """폴더/파일 계층 체크박스 트리. 폴더 체크 = 하위 전체 체크. selected_files() = 체크된 파일."""
    CHK = {True: "☑", False: "☐"}

    def __init__(self, master, height=6):
        super().__init__(master)
        self.tree = ttk.Treeview(self, show="tree", height=height, selectmode="none")
        sb = ttk.Scrollbar(self, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Button-1>", self._click)
        self._state, self._isfile, self._path = {}, {}, {}

    def build(self, paths):
        self.tree.delete(*self.tree.get_children())
        self._state.clear(); self._isfile.clear(); self._path.clear()
        nodes = {}
        for p in sorted(paths):
            parts = p.split("/")
            cur, parent = "", ""
            for i, part in enumerate(parts):
                cur = cur + "/" + part if cur else part
                if cur not in nodes:
                    iid = self.tree.insert(nodes.get(parent, ""), "end",
                                           text=f"{self.CHK[False]} {part}", open=True)
                    nodes[cur] = iid
                    self._state[iid] = False
                    self._isfile[iid] = (i == len(parts) - 1)
                    self._path[iid] = cur
                parent = cur

    def _set(self, iid, val):
        self._state[iid] = val
        name = self.tree.item(iid, "text")[2:]
        self.tree.item(iid, text=f"{self.CHK[val]} {name}")
        for ch in self.tree.get_children(iid):
            self._set(ch, val)

    def _click(self, e):
        if self.tree.identify("element", e.x, e.y) == "Treeitem.indicator":
            return   # 펼치기 삼각형은 토글 안 함
        iid = self.tree.identify_row(e.y)
        if iid:
            self._set(iid, not self._state.get(iid, False))
            return "break"

    def selected_files(self):
        return [self._path[iid] for iid, isf in self._isfile.items()
                if isf and self._state.get(iid)]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("사내 지식 RAG (네이티브)")
        self.geometry("1100x820")
        self.img_bytes = {}          # feedback 이미지 캐시(kind별)
        self.log_text_cache = ""
        self.candidates = []
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)
        self.tab_qa = ttk.Frame(nb); nb.add(self.tab_qa, text="📄 문서 QA")
        self.tab_log = ttk.Frame(nb); nb.add(self.tab_log, text="🔌 로그 분석")
        self.tab_fb = ttk.Frame(nb); nb.add(self.tab_fb, text="🚩 개선 기록")
        self.tab_admin = ttk.Frame(nb); nb.add(self.tab_admin, text="⚙️ 관리")
        self.status = tk.StringVar(value=f"서버: {api_base()}")
        ttk.Label(self, textvariable=self.status, relief="sunken", anchor="w").pack(fill="x")
        self._build_qa()
        self._build_log()
        self._build_fb()
        self._build_admin()
        self._load_tree()

    # --- 폴더/파일 범위 트리 ---
    def _scope_box(self, parent):
        fr = ttk.LabelFrame(parent, text="범위 선택 (폴더/파일 체크, 미선택=전체)")
        tree = CheckTree(fr, height=5)
        tree.pack(fill="x", padx=4, pady=2)
        return fr, tree

    def _load_tree(self):
        def done(res):
            paths = res.get("docs", [])
            for tr in (getattr(self, "qa_tree", None), getattr(self, "log_tree", None)):
                if tr is not None:
                    tr.build(paths)
        self._async(lambda: _req("GET", "/docs"), done, "문서 트리 조회…")

    # --- 공통: 비동기 실행(GUI 멈춤 방지) ---
    def _async(self, fn, on_done, busy="처리 중…"):
        self.status.set(busy)

        def run():
            try:
                res = fn()
                err = None
            except Exception as e:
                res, err = None, f"{type(e).__name__}: {e}"
            self.after(0, lambda: self._done(on_done, res, err))
        threading.Thread(target=run, daemon=True).start()

    def _done(self, on_done, res, err):
        self.status.set(f"서버: {api_base()}")
        if err:
            messagebox.showerror("오류", err)
            return
        on_done(res)

    @staticmethod
    def _text(parent, height=12):
        fr = ttk.Frame(parent)
        t = tk.Text(fr, height=height, wrap="word")
        sb = ttk.Scrollbar(fr, command=t.yview)
        t.configure(yscrollcommand=sb.set)
        t.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        return fr, t

    def _set(self, widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text or "")

    # =========================== 문서 QA ===========================
    def _build_qa(self):
        f = self.tab_qa
        fbf, self.qa_tree = self._scope_box(f); fbf.pack(fill="x", padx=8, pady=(6, 0))
        top = ttk.Frame(f); top.pack(fill="x", padx=8, pady=6)
        self.qa_q = ttk.Entry(top)
        self.qa_q.pack(side="left", fill="x", expand=True)
        ttk.Button(top, text="검색", command=self._qa_search).pack(side="left", padx=4)
        ttk.Label(f, text="답변").pack(anchor="w", padx=8)
        fr, self.qa_ans = self._text(f, 12); fr.pack(fill="both", expand=True, padx=8)
        ttk.Label(f, text="출처").pack(anchor="w", padx=8)
        fr2, self.qa_src = self._text(f, 8); fr2.pack(fill="both", expand=True, padx=8)
        self._build_fb_inline(f, "qa", get_ctx=lambda: {
            "question": self.qa_q.get(), "answer": self.qa_ans.get("1.0", "end").strip()})

    def _qa_search(self):
        q = self.qa_q.get().strip()
        if not q:
            return
        body = {"question": q, "files": self.qa_tree.selected_files()}
        self._async(lambda: _req("POST", "/qa", body), self._qa_show, "검색·생성 중…")

    def _qa_show(self, res):
        self._set(self.qa_ans, res.get("answer", ""))
        src = "\n".join(f"[{s['n']}] {s['label']}" for s in res.get("sources", []))
        self._set(self.qa_src, src or "(출처 없음)")

    # =========================== 로그 분석 ===========================
    def _build_log(self):
        f = self.tab_log
        top = ttk.Frame(f); top.pack(fill="x", padx=8, pady=6)
        ttk.Button(top, text="로그 파일 열기", command=self._log_open).pack(side="left")
        self.log_name = ttk.Label(top, text="(파일 없음)"); self.log_name.pack(side="left", padx=6)
        fbf, self.log_tree = self._scope_box(f); fbf.pack(fill="x", padx=8)
        q = ttk.Frame(f); q.pack(fill="x", padx=8)
        ttk.Label(q, text="질문:").pack(side="left")
        self.log_q = ttk.Entry(q); self.log_q.pack(side="left", fill="x", expand=True)
        ttk.Button(q, text="명세 후보 찾기", command=self._log_cands).pack(side="left", padx=4)
        ttk.Label(f, text="프로토콜 명세 선택 (여러 개 가능)").pack(anchor="w", padx=8)
        self.log_list = tk.Listbox(f, selectmode="multiple", height=6)
        self.log_list.pack(fill="x", padx=8)
        ttk.Button(f, text="확정 명세로 파싱·해석", command=self._log_analyze).pack(anchor="w", padx=8, pady=4)
        ttk.Label(f, text="파싱/해석 결과").pack(anchor="w", padx=8)
        fr, self.log_out = self._text(f, 16); fr.pack(fill="both", expand=True, padx=8)
        self._build_fb_inline(f, "log", get_ctx=lambda: {
            "question": self.log_q.get(), "answer": self.log_out.get("1.0", "end").strip()})

    def _log_open(self):
        p = filedialog.askopenfilename(filetypes=[("로그", "*.txt *.log *.dat"), ("모든 파일", "*.*")])
        if not p:
            return
        with open(p, "r", encoding="utf-8", errors="replace") as fh:
            self.log_text_cache = fh.read()
        self.log_name.configure(text=os.path.basename(p))

    def _log_cands(self):
        if not self.log_text_cache:
            messagebox.showwarning("알림", "먼저 로그 파일을 여세요."); return
        self._async(lambda: _req("POST", "/log/candidates",
                                 {"log_text": self.log_text_cache, "question": self.log_q.get(),
                                  "files": self.log_tree.selected_files()}),
                    self._log_cands_show, "명세 후보 검색 중…")

    def _log_cands_show(self, res):
        self.candidates = res.get("candidates", [])
        self.log_list.delete(0, "end")
        for c in self.candidates:
            self.log_list.insert("end", f"{c['file']} · {c['section']} · {c['preview']}")

    def _log_analyze(self):
        sel = self.log_list.curselection()
        if not sel:
            messagebox.showwarning("알림", "명세를 1개 이상 선택하세요."); return
        docs = [self.candidates[i]["document"] for i in sel]
        self._async(lambda: _req("POST", "/log/analyze",
                                 {"log_text": self.log_text_cache, "spec_docs": docs,
                                  "question": self.log_q.get()}),
                    self._log_analyze_show, "명세 도출→파싱→해석 중…")

    def _log_analyze_show(self, res):
        parts = [f"[로그종류 {res.get('log_type')}  프레임 {res.get('total')} 유효 {res.get('valid_count')}"
                 f"  문서기반도출={res.get('derived')}]"]
        if res.get("profile"):
            parts.append("도출 규격: " + json.dumps(res["profile"], ensure_ascii=False))
        parts.append("\n[파싱 결과]\n" + (res.get("summary") or ""))
        parts.append("\n[해석]\n" + (res.get("out") or ""))
        self._set(self.log_out, "\n".join(parts))

    # =========================== 개선 기록 ===========================
    def _build_fb_inline(self, parent, kind, get_ctx):
        """QA/로그 탭 하단 개선기록 캡처."""
        box = ttk.LabelFrame(parent, text="🚩 개선 기록")
        box.pack(fill="x", padx=8, pady=6)
        row = ttk.Frame(box); row.pack(fill="x")
        cat = ttk.Combobox(row, values=CATS[kind], state="readonly", width=24)
        cat.current(0); cat.pack(side="left", padx=2)
        sev = ttk.Combobox(row, values=["낮음", "중간", "높음"], state="readonly", width=6)
        sev.current(1); sev.pack(side="left", padx=2)
        ttk.Button(row, text="📋 클립보드 붙여넣기",
                   command=lambda: self._paste_clip(kind, prev)).pack(side="left", padx=2)
        ttk.Button(row, text="이미지 파일",
                   command=lambda: self._pick_img(kind, prev)).pack(side="left", padx=2)
        redact = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text="🔒 비식별화", variable=redact).pack(side="left", padx=6)
        note = tk.Text(box, height=3, wrap="word"); note.pack(fill="x", pady=2)
        prev = ttk.Label(box, text="(이미지 없음)"); prev.pack(anchor="w")
        ttk.Button(box, text="개선 기록 저장",
                   command=lambda: self._fb_save(kind, cat, sev, note, redact, get_ctx, prev)
                   ).pack(anchor="w", pady=2)

    def _paste_clip(self, kind, prev):
        try:
            from PIL import ImageGrab
            im = ImageGrab.grabclipboard()
            if im is None or isinstance(im, list):
                messagebox.showinfo("알림", "클립보드에 이미지가 없습니다."); return
            buf = io.BytesIO(); im.save(buf, format="PNG")
            self.img_bytes[kind] = buf.getvalue()
            prev.configure(text=f"이미지 첨부됨 ({im.width}x{im.height})")
        except Exception as e:
            messagebox.showerror("오류", f"클립보드 읽기 실패: {e}")

    def _pick_img(self, kind, prev):
        p = filedialog.askopenfilename(filetypes=[("이미지", "*.png *.jpg *.jpeg *.bmp")])
        if not p:
            return
        with open(p, "rb") as fh:
            self.img_bytes[kind] = fh.read()
        prev.configure(text=f"이미지 첨부됨 ({os.path.basename(p)})")

    def _fb_save(self, kind, cat, sev, note, redact, get_ctx, prev):
        ctx = get_ctx()
        rec = {"ts": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M"),
               "kind": kind, "category": cat.get(), "severity": sev.get(),
               "question": ctx.get("question", ""), "answer": ctx.get("answer", ""),
               "note": note.get("1.0", "end").strip(), "contexts": []}
        body = {"record": rec, "redact": redact.get()}
        if self.img_bytes.get(kind):
            body["image_b64"] = base64.b64encode(self.img_bytes[kind]).decode()
        self._async(lambda: _req("POST", "/feedback", body),
                    lambda r: (messagebox.showinfo("완료", "저장되었습니다."),
                               self.img_bytes.pop(kind, None), prev.configure(text="(이미지 없음)")),
                    "저장 중…")

    def _build_fb(self):
        f = self.tab_fb
        ttk.Label(f, text="개선 기록 (서버 저장) — 반출은 아래 내보내기").pack(anchor="w", padx=8, pady=6)
        top = ttk.Frame(f); top.pack(fill="x", padx=8)
        ttk.Button(top, text="새로고침", command=self._fb_refresh).pack(side="left")
        ttk.Button(top, text="📤 Markdown 내보내기", command=self._fb_export).pack(side="left", padx=4)
        fr, self.fb_view = self._text(f, 28); fr.pack(fill="both", expand=True, padx=8, pady=6)

    def _fb_refresh(self):
        self._async(lambda: _req("GET", "/feedback/list"), self._fb_show, "불러오는 중…")

    def _fb_show(self, res):
        lines = []
        for i, r in enumerate(res.get("records", []), 1):
            cs = r.get("context_summary", {})
            lines.append(f"{i}. [{r.get('kind')}] {r.get('category')} ({r.get('severity')}) {r.get('ts')}")
            if r.get("question"): lines.append(f"   질문: {r['question'][:120]}")
            if r.get("note"): lines.append(f"   메모: {r['note'][:120]}")
            if cs: lines.append(f"   근거: 표 {cs.get('table',0)}/텍스트 {cs.get('text',0)}")
            if r.get("image"): lines.append(f"   이미지: {r['image']}")
            lines.append("")
        self._set(self.fb_view, "\n".join(lines) or "(기록 없음)")

    def _fb_export(self):
        self._async(lambda: _req("POST", "/feedback/export"),
                    lambda r: messagebox.showinfo("내보냄", f"서버 경로:\n{r.get('path')}"), "내보내는 중…")

    # =========================== 관리 ===========================
    def _build_admin(self):
        f = self.tab_admin
        fr0 = ttk.Frame(f); fr0.pack(fill="x", padx=8, pady=(8, 0))
        ttk.Label(fr0, text="업로드 폴더(분류):").pack(side="left")
        self.upload_folder = ttk.Entry(fr0, width=20)
        self.upload_folder.pack(side="left", padx=4)
        ttk.Label(fr0, text="(비우면 미분류)").pack(side="left")
        top = ttk.Frame(f); top.pack(fill="x", padx=8, pady=8)
        ttk.Button(top, text="문서 업로드 + 인덱싱", command=self._admin_upload).pack(side="left")
        ttk.Button(top, text="증분 인덱싱", command=lambda: self._admin_index(False)).pack(side="left", padx=4)
        ttk.Button(top, text="전체 재인덱싱", command=lambda: self._admin_index(True)).pack(side="left")
        ttk.Button(top, text="문서 목록", command=self._admin_docs).pack(side="left", padx=4)
        ttk.Button(top, text="범위 새로고침", command=self._load_tree).pack(side="left")
        fr, self.admin_view = self._text(f, 26); fr.pack(fill="both", expand=True, padx=8, pady=6)

    def _admin_upload(self):
        paths = filedialog.askopenfilenames(
            filetypes=[("문서", "*.xlsx *.docx *.doc *.pptx *.pdf *.txt *.png *.jpg *.jpeg *.bmp *.tiff")])
        if not paths:
            return

        folder = self.upload_folder.get().strip()

        def do():
            for p in paths:
                with open(p, "rb") as fh:
                    _req("POST", "/upload", {"name": os.path.basename(p), "folder": folder,
                                             "content_b64": base64.b64encode(fh.read()).decode()})
            return _req("POST", "/index", {"full": False})
        self._async(do, lambda r: (self._set(self.admin_view, f"업로드+인덱싱 완료:\n{r.get('stats')}"),
                                    self._admin_docs(), self._load_tree()), "업로드·인덱싱 중…")

    def _admin_index(self, full):
        self._async(lambda: _req("POST", "/index", {"full": full}),
                    lambda r: self._set(self.admin_view, f"인덱싱 완료:\n{r.get('stats')}"),
                    "인덱싱 중…")

    def _admin_docs(self):
        self._async(lambda: _req("GET", "/docs"),
                    lambda r: self._set(self.admin_view,
                                        f"문서 {r.get('count')}개:\n" + "\n".join(r.get("docs", []))),
                    "조회 중…")


if __name__ == "__main__":
    App().mainloop()
