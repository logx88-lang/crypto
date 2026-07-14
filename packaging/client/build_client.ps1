# 클라이언트 실행파일 빌드 — **온라인 Windows PC에서 1회** (인터넷 필요)
#
# rag_client.py → dist\rag-client.exe (단일 실행파일). 이 exe + server.txt 를 개발 PC(B)에 배포.
# B PC는 설치 없이 exe 더블클릭 = 독립 창 앱(브라우저 아님, WebView2 사용).
#
# 사용:  .\packaging\client\build_client.ps1
# 사전:  Windows + Python 3.10~3.12. (Win11 은 WebView2 런타임 기본 내장)

$ErrorActionPreference = "Stop"
$Here = $PSScriptRoot
Set-Location $Here

# 격리 빌드 환경 (py -3.12 우선, 없으면 python)
$PY = $null
try { $exe = (& py -3.12 -c "import sys;print(sys.executable)" 2>$null); if ($exe) { $PY = $exe } } catch {}
if (-not $PY) { $PY = "python" }
& $PY -m venv .build
# ⚠️ setuptools 를 반드시 최신으로 — 구버전(65.x)의 pkg_resources 는 Python 3.12 에서
#    pkgutil.ImpImporter 제거로 깨져 PyInstaller hook-setuptools 가 실패한다.
.\.build\Scripts\python -m pip install --upgrade pip setuptools wheel
.\.build\Scripts\pip install pywebview pyinstaller

# 단일 exe 빌드 (--noconsole: 콘솔창 없음)
.\.build\Scripts\pyinstaller --onefile --noconsole --clean --name rag-client `
    --collect-all webview `
    rag_client.py
if ($LASTEXITCODE -ne 0 -or -not (Test-Path .\dist\rag-client.exe)) {
    throw "빌드 실패 — 위 PyInstaller 오류 확인(대개 setuptools 구버전). 로그를 확인하세요."
}

Write-Host ""
Write-Host "빌드 성공: $Here\dist\rag-client.exe"
Write-Host "서버 주소는 코드에 하드코딩됨(기본 http://192.168.155.89:8501) → server.txt 불필요."
Write-Host "배포: dist\rag-client.exe **한 개만** 각 개발 PC에 복사 → 더블클릭."
Write-Host "  · 주소가 바뀔 때만 exe 옆에 server.txt(한 줄) 두면 그 값으로 덮어씀(재빌드 불필요)."
Write-Host "  · 오프라인 동작. Win11 은 WebView2 내장(구형 Windows면 런타임 반입)."
