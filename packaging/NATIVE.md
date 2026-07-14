# 네이티브 앱 배포 (백엔드 API + 데스크톱 클라이언트)

브라우저 대신 **네이티브 데스크톱 앱**으로 동작. 클립보드 이미지 붙여넣기 지원.
RAG 로직은 서버 A가 그대로 처리(GPU/모델/인덱스 유지), 클라이언트는 API만 호출.

```
[서버 A]  rag.api.server (:8600, 표준 http.server) + Ollama + 인덱스
   ▲ JSON API
[개발 PC B]  rag-native.exe (Tkinter, 네이티브 클립보드)
```

의존성: 백엔드=표준 라이브러리(추가 0). 클라이언트=tkinter(표준 내장)+Pillow(이미 있음). 오프라인 안전.

## 서버 A
1. 코드 반영(`rag\` 폴더 — `rag\api\` 포함) + 인덱스 준비(관리/CLI).
2. 백엔드 실행:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\packaging\start_api.ps1
   ```
   → 출력된 `http://192.168.155.89:8600` 주소 확인. 방화벽 8600 인바운드 허용.
3. 자동시작: 작업 스케줄러로 `start_api.ps1` 등록(기존 방식과 동일).
   (Streamlit(:8501)과 병행 가능 — 포트 다름)

## 클라이언트 exe 빌드 (온라인 Windows PC, 1회)
```powershell
.\packaging\client\build_native.ps1     # → packaging\client\dist\rag-native.exe
```

## 개발 PC B 배포
1. `rag-native.exe` + `server.txt`(내용: `http://192.168.155.89:8600`)를 같은 폴더에 복사.
2. **rag-native.exe 더블클릭** → 네이티브 창 앱 실행.
3. 개선 기록 탭/QA·로그 탭 하단에서 **📋 클립보드 붙여넣기** 또는 이미지 파일 첨부 가능.

## 기능
- 문서 QA: 질문 → 답변 + 출처
- 로그 분석: 로그 파일 열기 → 질문 → 명세 후보(파일명 구분) 다중선택 → **확정 명세로 파싱·해석**
  (선택 문서에서 프레임 규격 자동 도출 → 파싱 → 해석)
- 개선 기록: 유형/심각도/메모 + **클립보드/파일 이미지** + 비식별화 옵션 → 저장/내보내기
- 관리: 문서 업로드+인덱싱, 증분/전체 재인덱싱, 문서 목록

## 참고
- 서버 주소 변경: `server.txt` 수정(재빌드 불필요) 또는 환경변수 `RAG_API`.
- 데이터(로그·QA 흐름)는 서버 A에서 처리·저장. 개선기록/인덱스도 A에 공유.
