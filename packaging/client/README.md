# 개발 PC(B) 클라이언트 — 독립 실행 앱 (브라우저 아님)

서버(A)의 Streamlit UI를 **자체 창 앱**으로 띄운다. 주소창·탭 없이 사내 전용 앱처럼 동작.
Windows 내장 **WebView2**(Edge Chromium 엔진)를 사용하고, 배포물은 단일 `rag-client.exe` 하나.

## 빌드 (온라인 Windows PC, 1회)
```powershell
.\packaging\client\build_client.ps1     # → packaging\client\dist\rag-client.exe
```
- 필요: Windows + Python 3.10~3.12 + 인터넷(pip). 결과 exe 자체는 오프라인 동작.
- WebView2 런타임: Windows 11 기본 내장. (구형 Windows면 MS WebView2 Evergreen 런타임을 별도 반입)

## 배포 (각 개발 PC B-1/B-2/…)
서버 주소가 **고정(`http://192.168.155.89:8501`)** 으로 코드에 하드코딩돼 있어 **exe 하나만** 배포하면 된다.
1. `dist\rag-client.exe` 를 B PC에 복사.
2. **더블클릭 → 독립 창으로 앱 실행.** (설치·설정 불필요)
   - 바탕화면 바로가기를 만들고 아이콘을 지정하면 완전한 앱 형태.

## 서버 주소 지정 우선순위 (바뀔 때만 활용)
1. 환경변수 `RAG_SERVER`
2. exe 옆 `server.txt` (한 줄)
3. 코드 기본값 `http://192.168.155.89:8501` (`rag_client.py` DEFAULT_URL)

→ 평소엔 3번(하드코딩)으로 충분. IP가 바뀌면 exe 옆에 `server.txt` 한 줄만 두거나 DEFAULT_URL 수정 후 재빌드.

## 연결 실패 시
앱이 "서버에 연결할 수 없습니다" 창을 띄운다. 확인:
- A 서버 실행 중인지(`start_server.ps1`), 방화벽 8501 허용, 같은 사내망, server.txt 주소.

## 무빌드 대안 (참고)
exe 빌드가 부담이면 `packaging\open_client.bat` 의 Edge 앱모드(`msedge --app=URL`)도
주소창 없는 창을 띄운다(단, Edge 사용). 완전한 별도 앱은 위 rag-client.exe 를 권장.
