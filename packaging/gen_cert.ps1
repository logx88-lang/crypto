# 자체서명 HTTPS 인증서 생성 — **서버 PC A에서 최초 1회 실행**.
#
# 클립보드 이미지 붙여넣기(Ctrl+V)는 브라우저 보안 컨텍스트(HTTPS)에서만 동작한다.
# 이 스크립트로 서버 IP를 담은 인증서를 만들면 start_server.ps1 이 자동으로 HTTPS로 뜬다.
#
# 사용:  .\packaging\gen_cert.ps1              (기본 IP 192.168.155.89)
#        .\packaging\gen_cert.ps1 192.168.1.50 (다른 IP 지정)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$IP = if ($args.Count -ge 1) { $args[0] } else { "192.168.155.89" }

& ".\.venv\Scripts\python.exe" packaging\gen_cert.py $IP certs
if ($LASTEXITCODE -ne 0) { Write-Error "인증서 생성 실패"; exit 1 }

Write-Host ""
Write-Host "다음 단계:"
Write-Host "  1) 이 서버:   .\packaging\start_server.ps1  재실행 → https://${IP}:8501 로 뜸"
Write-Host "  2) 각 개발PC: certs\cert.crt 를 복사 → '신뢰할 수 있는 루트 인증 기관'에 설치"
Write-Host "               (자세히: packaging\HTTPS.md)"
Write-Host "  3) 클라이언트: server.txt 를 https://${IP}:8501 로 설정"
