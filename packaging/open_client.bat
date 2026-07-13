@echo off
REM 클라이언트 실행 — **개발 PC(B-1/B-2/…)에 복사해 더블클릭**.
REM 설치 불필요. 서버(업무 PC A)의 RAG 웹 UI를 브라우저로 연다.
REM
REM 배포 방법: 아래 SERVER 를 A 서버 주소로 바꾼 뒤, 이 .bat 를 각 개발 PC 바탕화면에 복사.

REM ↓↓↓ 업무 PC A(서버) 주소로 수정 (start_server.ps1 이 출력한 주소) ↓↓↓
set SERVER=http://192.168.0.10:8501

REM 기본 브라우저로 열기
start "" "%SERVER%"

REM (선택) 앱처럼 창모드로 열려면 위 줄 대신 아래 중 하나를 사용:
REM start "" msedge --app=%SERVER%
REM start "" chrome --app=%SERVER%
