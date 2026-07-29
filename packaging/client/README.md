# 개발 PC(B) 클라이언트 — 독립 실행 앱 (브라우저 아님)

서버(A)의 **신규 웹 UI(rag.webui, :8502)** 를 **자체 창 앱**으로 띄운다. 주소창·탭 없이 사내 전용 앱처럼 동작.
Windows 내장 **WebView2**(Edge Chromium 엔진)를 사용하고, 배포물은 단일 `rag-client.exe` 하나.

## 왜 이 방식인가 (사내 브라우저에서 파일 업로드/다운로드가 막힐 때의 근본 해법)
사내 보안(브라우저 그룹정책/DLP)은 **관리 대상 브라우저(Edge/Chrome)** 안에서의 파일 첨부·다운로드·
클립보드를 막는다. 이 클라이언트는 **자체 EXE(네이티브 앱)** 이라 그 브라우저 정책의 적용을 받지 않아,
같은 서버 PC에서도 **파일 업로드/다운로드·클립보드 이미지 붙여넣기가 정상 동작**한다(사내에서 검증된
동일 방식의 메신저 툴 존재). 즉 "웹이라서" 막힌 게 아니라 "관리 브라우저를 통해서"가 문제였다.

## 빌드 (온라인 Windows PC, 1회)
```powershell
.\packaging\client\build_client.ps1     # → packaging\client\dist\rag-client.exe
```
- 필요: Windows + Python 3.10~3.12 + 인터넷(pip). 결과 exe 자체는 오프라인 동작.
- WebView2 런타임: Windows 11 기본 내장. (구형 Windows면 MS WebView2 Evergreen 런타임을 별도 반입)

## 배포 (각 개발 PC B-1/B-2/…)
서버 주소가 **고정(`http://192.168.155.89:8502`)** 으로 코드에 하드코딩돼 있어 **exe 하나만** 배포하면 된다.
1. `dist\rag-client.exe` 를 B PC에 복사.
2. **더블클릭 → 독립 창으로 앱 실행.** (설치·설정 불필요)
   - 바탕화면 바로가기를 만들고 아이콘을 지정하면 완전한 앱 형태.

## 서버 주소 지정 우선순위 (바뀔 때만 활용)
1. 환경변수 `RAG_SERVER`
2. exe 옆 `server.txt` (한 줄)
3. 코드 기본값 `http://192.168.155.89:8502` (`rag_client.py` DEFAULT_URL)

→ 평소엔 3번(하드코딩)으로 충분. IP가 바뀌면 exe 옆에 `server.txt` 한 줄만 두거나 DEFAULT_URL 수정 후 재빌드.

## 연결 실패 시
앱이 "서버에 연결할 수 없습니다" 창을 띄운다. 확인:
- A 서버 실행 중인지(`start_webui.ps1`), 방화벽 8502 허용, 같은 사내망, server.txt 주소.

## 무빌드 대안 (참고)
exe 빌드가 부담이면 `packaging\open_client.bat` 의 Edge 앱모드(`msedge --app=URL`)도
주소창 없는 창을 띄운다(단, Edge 사용). 완전한 별도 앱은 위 rag-client.exe 를 권장.
