@echo off
REM 클라이언트 실행 — **개발 PC(B-1/B-2/…)에 복사해 더블클릭**.
REM 설치 불필요. 서버(업무 PC A)의 RAG 웹 UI를 브라우저로 연다.
REM
REM 배포 방법: 아래 SERVER 를 A 서버 주소로 바꾼 뒤, 이 .bat 를 각 개발 PC 바탕화면에 복사.

REM ↓↓↓ 업무 PC A(서버) 고정 주소 (HTTPS=클립보드 이미지 붙여넣기 가능) ↓↓↓
REM  ※ 최초 1회 각 개발 PC에 서버의 certs\cert.crt 를 '신뢰할 수 있는 루트 인증 기관'에
REM    설치해야 경고 없이 열림 (자세히: packaging\HTTPS.md)
set SERVER=https://192.168.155.89:8501

REM 기본 브라우저로 열기
start "" "%SERVER%"

REM (선택) 앱처럼 창모드로 열려면 위 줄 대신 아래 중 하나를 사용:
REM start "" msedge --app=%SERVER%
REM start "" chrome --app=%SERVER%
