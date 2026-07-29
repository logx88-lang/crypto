# 폐쇄망(오프라인) 설치 스크립트 — Windows PowerShell (design.md §10)
#
# 전제: 인터넷 없음. wheelhouse\ 에 순수 wheel, models\ 에 Ollama/리랭커 가중치가 USB로 반입됨.
# 사용: PowerShell에서  .\packaging\install.ps1   (필요시  Set-ExecutionPolicy -Scope Process Bypass)
#
# 산출: .venv 생성 → wheelhouse에서만 오프라인 설치(--no-index) → import 스모크.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

# --- Python 확인 (3.10~3.12) ---
# Python 3.12 우선 해석(다중 파이썬 환경 대응). wheelhouse(cp312)와 일치시켜야 함.
$py = $null
try { $exe = (& py -3.12 -c "import sys;print(sys.executable)" 2>$null); if ($exe) { $py = $exe } } catch {}
if (-not $py) { $py = "python" }        # 3.12 런처 없으면 기본 python
$ver = & $py -c "import sys;print('%d.%d'%sys.version_info[:2])"
Write-Host "Python: $py ($ver)"
if ($ver -ne "3.12") {
    Write-Warning "현재 $ver — 서버는 3.12여야 wheelhouse(cp312)와 맞습니다. 'py -3.12' 사용 권장."
}

# --- wheelhouse 경로 (파이썬 버전에 맞춰 선택) ---
$WheelDir = Join-Path $Root ("wheelhouse\win_amd64_py" + $ver.Replace(".",""))
if (-not (Test-Path $WheelDir)) {
    $WheelDir = Join-Path $Root "wheelhouse\win_amd64_py312"
    Write-Warning "버전별 wheelhouse 없음 → $WheelDir 사용(호환 안 되면 해당 버전 wheelhouse 반입 필요)."
}
Write-Host "wheelhouse: $WheelDir"

# --- venv 생성 ---
if (-not (Test-Path ".venv")) { & $py -m venv .venv }
$vpy = ".\.venv\Scripts\python.exe"

# --- 오프라인 설치 (인터넷 접근 금지: --no-index) ---
& $vpy -m pip install --no-index --find-links "$WheelDir" --upgrade pip
& $vpy -m pip install --no-index --find-links "$WheelDir" -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "오프라인 설치 실패 — wheelhouse 누락 wheel 확인" }

# --- import 스모크 (Ollama 불필요) ---
& $vpy -c "import openpyxl, docx, pptx, pdfplumber, charset_normalizer, chromadb, kiwipiepy, bm25s, ollama, streamlit, torch, sentence_transformers, transformers; print('import OK (core)')"
# 신규 웹 UI(rag/webui, 8502) 의존성도 검증 — 누락 시 여기서 실패
& $vpy -c "import starlette, uvicorn, jinja2, multipart; print('import OK (web ui)')"

Write-Host ""
Write-Host "설치 완료. 다음 단계:"
Write-Host "  1) Ollama 모델 반입 확인:  ollama list  (bge-m3=1024d, qwen3 계열)"
Write-Host "  2) 리랭커 가중치 경로 지정:  set RAG_RERANKER=C:\models\bge-reranker-v2-m3"
Write-Host "  3) E2E 점검:  .\.venv\Scripts\python smoke_test.py"
Write-Host "  4) 서버 기동(신규 웹 UI):  .\packaging\start_webui.ps1        # http://<IP>:8502"
Write-Host "     (폴백/기존 Streamlit):  .\packaging\start_server.ps1       # http://<IP>:8501"
