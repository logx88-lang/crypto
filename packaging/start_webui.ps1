# 웹 UI(신규, Starlette+HTMX) 시작 — **업무 PC A(서버)에서 실행**
#
# 기존 Streamlit(start_server.ps1, 8501)과 **나란히** 띄워 디자인을 비교하기 위한 스크립트.
# 같은 백엔드(rag.chat/engine·인덱스·Ollama)를 그대로 재사용하며, 포트만 8502 로 분리한다.
# 정적 자산(htmx.min.js, tailwind.js)은 저장소에 동봉 → 인터넷/CDN 불필요(폐쇄망 OK).
# 복사·클립보드 이미지 붙여넣기는 프론트에서 처리하므로 HTTPS 불필요(HTTP로 동작).
#
# 사용:  .\packaging\start_webui.ps1
# 최초 1회 install.ps1 로 설치 + 인덱싱(관리) 후 사용. Streamlit과 동시에 켜도 무방.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

# --- 배포 PC에 맞게 수정할 값 (start_server.ps1 과 동일하게 맞출 것) ------
$env:RAG_LLM      = "qwen3_8b_ctx32998"              # 이 PC ollama list 의 실제 태그
$env:RAG_EMBED    = "bge-m3"                          # 정품 1024d
$env:RAG_RERANKER = "C:\models\bge-reranker-v2-m3"    # USB로 반입한 리랭커 로컬 경로
$env:RAG_LLM_TIMEOUT = "300"                          # GPU면 300, 느리면 상향
$env:OLLAMA_HOST  = "http://127.0.0.1:11434"
$env:RAG_NUM_CTX  = "8192"
$Port = 8502
# ------------------------------------------------------------------------

# 1) Ollama 확인
try {
    Invoke-RestMethod "http://localhost:11434/api/version" -TimeoutSec 5 | Out-Null
    Write-Host "Ollama OK"
} catch {
    Write-Warning "Ollama 미응답 → 'ollama serve' 실행 또는 Ollama 서비스 시작 필요."
}

# 2) 방화벽 인바운드 허용(최초 1회, 관리자 권한 필요). 이미 있으면 무시됨.
try {
    New-NetFirewallRule -DisplayName "RAG WebUI $Port" -Direction Inbound `
        -Action Allow -Protocol TCP -LocalPort $Port -ErrorAction SilentlyContinue | Out-Null
} catch { Write-Warning "방화벽 규칙 추가 실패(관리자 권한으로 1회 수동 허용): TCP $Port" }

# 3) 접속 주소 안내
$ip = (Get-NetIPAddress -AddressFamily IPv4 |
       Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.*" } |
       Select-Object -First 1).IPAddress
Write-Host ""
Write-Host "개발 PC(B)에서 접속할 주소:  http://$ip`:$Port   (신규 웹 UI)"
Write-Host "기존 Streamlit 은 http://$ip`:8501 (start_server.ps1)"
Write-Host ""

# 4) uvicorn 구동 (venv 우선)
$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (Test-Path $venvPy) { $py = $venvPy } else { $py = "python" }   # PS5.1 호환(삼항 ?: 미지원)
& $py -m uvicorn rag.webui.app:app --host 0.0.0.0 --port $Port
