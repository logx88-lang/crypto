# 네이티브 클라이언트 exe 빌드 — **온라인 Windows PC에서 1회**
#
# native/rag_app.py → dist\rag-native.exe (단일 실행파일, 브라우저 아님).
# tkinter는 파이썬 표준 내장, Pillow만 필요. 클립보드 이미지 붙여넣기 지원.
# 사용:  .\packaging\client\build_native.ps1

$ErrorActionPreference = "Stop"
$Here = $PSScriptRoot
$Root = Split-Path -Parent (Split-Path -Parent $Here)
Set-Location $Here

# py -3.12 우선
$PY = $null
try { $exe = (& py -3.12 -c "import sys;print(sys.executable)" 2>$null); if ($exe) { $PY = $exe } } catch {}
if (-not $PY) { $PY = "python" }

& $PY -m venv .nbuild
.\.nbuild\Scripts\python -m pip install --upgrade pip setuptools wheel
.\.nbuild\Scripts\pip install pyinstaller pillow

.\.nbuild\Scripts\pyinstaller --onefile --noconsole --clean --name rag-native `
    --collect-all PIL `
    "$Root\native\rag_app.py"
if ($LASTEXITCODE -ne 0 -or -not (Test-Path .\dist\rag-native.exe)) {
    throw "빌드 실패 — 위 PyInstaller 오류 확인"
}

if (-not (Test-Path .\dist\server.txt)) {
    Copy-Item .\native_server.txt.example .\dist\server.txt
}
Write-Host ""
Write-Host "빌드 성공: $Here\dist\rag-native.exe"
Write-Host "배포: dist\rag-native.exe + dist\server.txt(서버 API 주소) 를 개발 PC에 복사."
Write-Host "  server.txt 예: http://192.168.155.89:8600  (start_api.ps1 이 출력한 주소)"
