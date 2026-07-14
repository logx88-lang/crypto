# 서버 시작 — **업무 PC A(서버)에서 실행** (design.md §1, Q2)
#
# 이 PC에서 Ollama + Streamlit(RAG)을 구동해, 개발 PC(B)들이 브라우저로 접속하게 한다.
# 최초 1회 install.ps1 로 설치 + 인덱싱(관리 탭) 후, 이 스크립트로 서버를 켠다.
#
# 사용:  .\packaging\start_server.ps1
# 상시 구동(부팅 시 자동): 아래 "자동 시작" 주석 참고.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

# --- 배포 PC에 맞게 수정할 값 -------------------------------------------
$env:RAG_LLM      = "qwen3_8b_ctx32998"              # 이 PC ollama list 의 실제 태그
$env:RAG_EMBED    = "bge-m3"                          # 정품 1024d
$env:RAG_RERANKER = "C:\models\bge-reranker-v2-m3"    # USB로 반입한 리랭커 로컬 경로
$env:RAG_LLM_TIMEOUT = "300"                          # GPU면 300, 느리면 상향
$env:OLLAMA_HOST  = "http://127.0.0.1:11434"          # 클라이언트 접속용(시스템 0.0.0.0 설정 무시)
$env:RAG_NUM_CTX  = "8192"                            # 표 다수 컨텍스트 수용(32k 모델). VRAM 여유시 16384/32768
$Port = 8501
# ------------------------------------------------------------------------

# 1) Ollama 확인 (Windows는 보통 서비스로 자동 실행)
try {
    Invoke-RestMethod "http://localhost:11434/api/version" -TimeoutSec 5 | Out-Null
    Write-Host "Ollama OK"
} catch {
    Write-Warning "Ollama 미응답 → 'ollama serve' 실행 또는 Ollama 서비스 시작 필요."
}

# 2) 방화벽 인바운드 허용(최초 1회, 관리자 권한 필요). 이미 있으면 무시됨.
try {
    New-NetFirewallRule -DisplayName "RAG Streamlit $Port" -Direction Inbound `
        -Action Allow -Protocol TCP -LocalPort $Port -ErrorAction SilentlyContinue | Out-Null
} catch { Write-Warning "방화벽 규칙 추가 실패(관리자 권한으로 1회 수동 허용 필요): TCP $Port" }

# 3) 이 PC의 접속 주소 안내
$ip = (Get-NetIPAddress -AddressFamily IPv4 |
       Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.*" } |
       Select-Object -First 1).IPAddress
Write-Host ""
Write-Host "개발 PC(B)에서 접속할 주소:  http://$ip`:$Port"
Write-Host "  → open_client.bat 의 SERVER 값을 이 주소로 설정해 배포하세요."
Write-Host ""

# 4) Streamlit 구동 (0.0.0.0 바인딩 = 사내망 공개)
& ".\.venv\Scripts\streamlit.exe" run rag\app\main.py `
    --server.address 0.0.0.0 --server.port $Port --server.headless true

# --- 자동 시작(부팅 시) 방법 ---------------------------------------------
#  (a) 작업 스케줄러: 트리거=로그온/시작 시, 동작=powershell -File <이 스크립트> (가장 간단)
#  (b) 서비스화: NSSM(nssm install RAG-Server) 로 이 스크립트를 서비스 등록
#  Ollama 는 Windows 설치 시 자동 서비스로 상주하므로 별도 조치 불필요.
