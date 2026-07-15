"""RAG 데스크톱 클라이언트 — 서버(A)의 Streamlit UI를 **독립 창(앱)**으로 표시.

브라우저가 아니라 pywebview(Windows: 내장 WebView2/Edge Chromium 엔진)로 자체 창을 띄운다.
주소창·탭 없음 → 사내 전용 앱처럼 동작. PyInstaller로 `rag-client.exe` 단일 실행파일로 빌드한다.

서버 주소 우선순위:
  1) 환경변수 RAG_SERVER
  2) 실행파일 옆의 server.txt (한 줄, 예: http://192.168.0.10:8501)
  3) 기본값(아래 DEFAULT_URL)
→ 서버 IP가 바뀌어도 server.txt 만 고치면 되고, 재빌드 불필요.
"""
import os
import sys
import urllib.request

import webview

DEFAULT_URL = "https://192.168.155.89:8501"  # 고정 서버 주소(하드코딩). HTTPS=클립보드 붙여넣기 가능.
WINDOW_TITLE = "사내 지식 RAG"


def _base_dir() -> str:
    # PyInstaller 실행파일이면 exe 위치, 아니면 스크립트 위치
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def server_url() -> str:
    url = os.environ.get("RAG_SERVER", "").strip()
    if not url:
        p = os.path.join(_base_dir(), "server.txt")
        if os.path.exists(p):
            try:
                url = open(p, encoding="utf-8").read().strip()
            except Exception:
                url = ""
    return (url or DEFAULT_URL).rstrip("/")


def _reachable(url: str, timeout: float = 3.0) -> bool:
    try:
        urllib.request.urlopen(url + "/_stcore/health", timeout=timeout)
        return True
    except Exception:
        return False


def main():
    url = server_url()
    if _reachable(url):
        webview.create_window(WINDOW_TITLE, url, width=1280, height=900)
    else:
        html = (
            "<div style='font-family:sans-serif;padding:40px;color:#333'>"
            "<h2>서버에 연결할 수 없습니다</h2>"
            f"<p>접속 주소: <b>{url}</b></p><ul>"
            "<li>업무 PC A(서버)에서 서버가 실행 중인지 확인하세요.</li>"
            "<li>같은 사내망인지, 방화벽에서 8501 포트가 허용됐는지 확인하세요.</li>"
            "<li>주소가 다르면 실행파일 옆 <b>server.txt</b> 를 수정하세요.</li>"
            "</ul></div>"
        )
        webview.create_window(f"{WINDOW_TITLE} — 연결 실패", html=html,
                              width=720, height=420)
    webview.start()


if __name__ == "__main__":
    main()
