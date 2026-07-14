# 백엔드 API 실행 — **업무 PC A(서버)에서** (네이티브 클라이언트용, 표준 http.server)
#
# 네이티브 앱(rag-native.exe)이 이 API(:8600)를 호출한다. Ollama·인덱스와 함께 상주.
# 사용:  powershell -ExecutionPolicy Bypass -File .\packaging\start_api.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

# --- 배포 PC에 맞게 ---
$env:RAG_LLM      = "qwen3_8b_ctx32998"            # ollama list 실제 태그
$env:RAG_EMBED    = "bge-m3"
$env:RAG_RERANKER = "C:\models\bge-reranker-v2-m3"
$env:OLLAMA_HOST  = "http://127.0.0.1:11434"
$env:RAG_NUM_CTX  = "8192"
$env:RAG_API_PORT = "8600"
# OCR 안 쓰면:  $env:RAG_OCR = "0"

# 방화벽 인바운드 8600 (관리자 권한 1회)
try {
    New-NetFirewallRule -DisplayName "RAG API 8600" -Direction Inbound -Action Allow `
        -Protocol TCP -LocalPort 8600 -ErrorAction SilentlyContinue | Out-Null
} catch { Write-Warning "방화벽 규칙 수동 허용 필요: netsh advfirewall firewall add rule name=RAG8600 dir=in action=allow protocol=TCP localport=8600" }

$ip = (Get-NetIPAddress -AddressFamily IPv4 |
       Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.*" } |
       Select-Object -First 1).IPAddress
Write-Host "네이티브 앱 server.txt 에 넣을 주소:  http://$ip`:8600"
Write-Host ""

& ".\.venv\Scripts\python.exe" -m rag.api.server
