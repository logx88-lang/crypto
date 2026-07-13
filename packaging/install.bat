@echo off
REM 폐쇄망(오프라인) 설치 — Windows cmd (design.md §10)
REM 전제: 인터넷 없음. wheelhouse\ 순수 wheel, models\ Ollama/리랭커 가중치 USB 반입.
REM 사용: 프로젝트 루트에서  packaging\install.bat

setlocal
cd /d "%~dp0.."

for /f %%v in ('python -c "import sys;print('%%d%%d'%%sys.version_info[:2])"') do set PYTAG=%%v
set WHEELDIR=wheelhouse\win_amd64_py%PYTAG%
if not exist "%WHEELDIR%" set WHEELDIR=wheelhouse\win_amd64_py311
echo wheelhouse: %WHEELDIR%

if not exist .venv python -m venv .venv
set VPY=.venv\Scripts\python.exe

"%VPY%" -m pip install --no-index --find-links "%WHEELDIR%" --upgrade pip
"%VPY%" -m pip install --no-index --find-links "%WHEELDIR%" -r requirements.txt
if errorlevel 1 (
  echo [ERROR] 오프라인 설치 실패 — wheelhouse 누락 wheel 확인
  exit /b 1
)

"%VPY%" -c "import openpyxl, docx, pptx, pdfplumber, charset_normalizer, chromadb, kiwipiepy, bm25s, ollama, streamlit, torch, sentence_transformers, transformers; print('import OK')"

echo.
echo 설치 완료. 다음:
echo   1) ollama list  (bge-m3=1024d, qwen3 계열 확인)
echo   2) set RAG_RERANKER=C:\models\bge-reranker-v2-m3
echo   3) .venv\Scripts\python smoke_test.py
echo   4) .venv\Scripts\streamlit run rag\app\main.py --server.address 0.0.0.0 --server.port 8501
endlocal
