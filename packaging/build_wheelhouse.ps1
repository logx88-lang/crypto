# wheelhouse 생성 — **온라인 Windows PC에서 실행** (design.md §10)
#
# 왜 Windows에서? 리눅스에서 `pip download --platform win_amd64` 는 환경마커(sys_platform)를
# 호스트 기준으로 평가해, uvicorn[standard]→uvloop(Unix 전용) 때문에 해석이 깨진다(실측 확인).
# Windows 네이티브 pip download 는 마커를 올바로 평가(uvloop 자동 제외)하고 win wheel을 받는다.
#
# 사용:  .\packaging\build_wheelhouse.ps1        # 현재 파이썬 버전 기준
# 배포 PC가 3.10/3.12 면 해당 버전 파이썬으로 각각 재실행.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$ver = & python -c "import sys;print('%d.%d'%sys.version_info[:2])"
$tag = $ver.Replace(".","")
$WD = Join-Path $Root "wheelhouse\win_amd64_py$tag"
New-Item -ItemType Directory -Force -Path $WD | Out-Null
Write-Host "wheelhouse: $WD  (Python $ver)"

# 1) kiwipiepy_model 은 sdist-only → py3-none-any 유니버설 wheel로 미리 빌드(순수 데이터, 컴파일 불필요)
Write-Host "[1/3] kiwipiepy_model wheel 빌드"
& python -m pip wheel kiwipiepy_model==0.23.0 --no-deps -w $WD

# 2) torch 는 CPU wheel 고정 (질의 GPU는 LLM 전용)
Write-Host "[2/3] torch (CPU) 다운로드"
& python -m pip download torch==2.13.0 --only-binary=:all: `
    --index-url https://download.pytorch.org/whl/cpu -d $WD

# 3) 나머지 전부 (네이티브 → 마커 정상, uvloop 자동 제외)
Write-Host "[3/3] 나머지 의존성 다운로드"
& python -m pip download -r requirements.txt --only-binary=:all: `
    --find-links $WD -d $WD

Write-Host ""
Write-Host "완료. wheel 개수:"
(Get-ChildItem $WD -Filter *.whl).Count
Write-Host "→ 이 wheelhouse 폴더를 USB로 배포 PC에 반입 후 packaging\install.ps1 실행."
