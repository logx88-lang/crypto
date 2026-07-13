# 설치 런북 (폐쇄망 · 1 서버 + N 클라이언트)

대상 구조:
- **업무 PC A(서버)** — 폐쇄망 Windows 11, RAM 12GB, RTX 3060 Ti 8GB, Python 3.10~3.12,
  Ollama 기설치. 여기에만 전체 설치하고 Streamlit을 상시 구동한다.
- **개발 PC B-1/B-2/…(클라이언트)** — **설치 없음.** 브라우저로 `http://A:8501` 접속.

> 순서: **0단계(온라인 Windows PC에서 반입물 만들기)** → **1단계(서버 A 설치·구동)** →
> **2단계(개발 PC B 바로가기)** → **3단계(운영/문제해결)**.
> 명령은 PowerShell 기준. `C:\rag` 를 설치 경로 예시로 쓴다(원하는 경로로 대체 가능).

---

## 0단계 — 온라인 Windows PC에서 반입물 준비 (USB에 담기)

인터넷이 되는 **Windows** PC에서 1회 수행한다. (⚠️ 리눅스에서 만들면 `uvloop` 마커 문제로 실패 —
반드시 Windows. `packaging/README.md` 참고.)

### 0-1. 사전 설치
- **Python 3.11**(권장; A와 같은 마이너 버전) — 설치 시 "Add to PATH" 체크.
- **Ollama** (https://ollama.com) — 모델 내려받기용.
- (선택) Git. 없으면 GitHub에서 리포 ZIP 다운로드.

### 0-2. 소스 가져오기
```powershell
git clone https://github.com/logx88-lang/crypto.git C:\build\crypto
cd C:\build\crypto
git checkout claude/claude-md-docs-xtu1qe
```

### 0-3. wheelhouse 생성 (오프라인 pip 패키지)
```powershell
.\packaging\build_wheelhouse.ps1        # kiwipiepy_model 사전빌드 + torch CPU + 나머지 자동
# 완료 후 wheel 개수 출력. 결과: wheelhouse\win_amd64_py311\
```
> A의 파이썬이 3.10/3.12면 그 버전 파이썬으로 이 스크립트를 각각 실행해 해당 wheelhouse도 생성.

### 0-4. 모델 내려받기 (A에 **없는 것만** 반입 예정 — 대개 아래 3종)
```powershell
# (1) 정품 bge-m3 임베딩 (A의 기존 bge-m3-FP16 은 nomic 오라벨 → 필수 반입)
ollama pull bge-m3
ollama show bge-m3          # embedding length = 1024 확인 (768이면 잘못된 것)

# (2) 리랭커 (약 2.2GB)
pip install huggingface_hub
huggingface-cli download BAAI/bge-reranker-v2-m3 --local-dir C:\build\models\bge-reranker-v2-m3

# (3) OCR 모델 (이미지/스캔 문서 쓸 때만) — 1회 실행이 ~\.paddlex 를 채움
py -m venv C:\build\ocrtmp; C:\build\ocrtmp\Scripts\pip install paddlepaddle paddleocr
C:\build\ocrtmp\Scripts\python -c "from paddleocr import PaddleOCR; PaddleOCR(use_textline_orientation=True, lang='korean', enable_mkldnn=False).predict('crypto/samples/dummy_set/images/system_diagram.png')"
```

### 0-4b. 개발 PC용 클라이언트 앱 빌드 (독립 실행 exe)
```powershell
.\packaging\client\build_client.ps1     # → packaging\client\dist\rag-client.exe (+ server.txt)
```
> 이 `rag-client.exe`(+`server.txt`)를 USB에 함께 담아 각 개발 PC에 배포한다(2단계).

### 0-5. USB 폴더 구성
아래를 USB에 복사(폴더명 그대로):
```
반입/
  crypto\                              ← 소스(0-2). wheelhouse\ 포함
  ollama-models\                       ← %USERPROFILE%\.ollama\models 전체 (blobs+manifests)
  bge-reranker-v2-m3\                  ← 0-4(2)
  paddlex\                             ← %USERPROFILE%\.paddlex 전체 (0-4(3), OCR 쓸 때만)
```
> `ollama-models` 는 통째 복사가 가장 안전(중복 blob은 파일명이 해시라 충돌 없음).

---

## 1단계 — 업무 PC A(서버) 설치 · 구동

### 1-1. 파이썬 버전 확인 (wheelhouse 태그와 일치해야 함)
```powershell
python --version        # 예: 3.11.x  → wheelhouse\win_amd64_py311 과 일치
```

### 1-2. 소스 복사 + 오프라인 설치
```powershell
# USB 의 crypto 폴더를 C:\rag 로 복사한 뒤:
cd C:\rag
.\packaging\install.ps1        # .venv 생성 → wheelhouse 에서만(--no-index) 설치 → import OK 출력
```
`import OK` 가 나오면 성공. 실패 시 wheelhouse 파이썬 버전/누락 wheel 확인.

### 1-3. 모델 배치
```powershell
# (1) Ollama 모델: USB\ollama-models 의 내용을 A 의 %USERPROFILE%\.ollama\models 에 병합 복사
#     (blobs\ 와 manifests\ 를 기존 폴더에 덮어쓰기 없이 추가)
ollama list                 # bge-m3, qwen3 계열 보이는지 확인
ollama show bge-m3          # embedding length = 1024 확인

# (2) 리랭커: USB\bge-reranker-v2-m3 → C:\models\bge-reranker-v2-m3 로 복사

# (3) OCR: USB\paddlex → %USERPROFILE%\.paddlex 로 복사 (OCR 쓸 때만)
```
> A 에 이미 `qwen3_8b_ctx32998`/`qwen3:8b` 가 있으면 그대로 사용. `ollama list` 로 실제 태그 확인.

### 1-4. 서버 설정값 수정
`packaging\start_server.ps1` 상단을 A 환경에 맞게:
```powershell
$env:RAG_LLM      = "qwen3_8b_ctx32998"           # ollama list 의 실제 태그
$env:RAG_EMBED    = "bge-m3"
$env:RAG_RERANKER = "C:\models\bge-reranker-v2-m3" # 1-3(2) 경로
# OCR 안 쓰면 한 줄 추가:  $env:RAG_OCR = "0"
```

### 1-5. 사내 문서 인덱싱
```powershell
# 실제 문서(xlsx/docx/pptx/pdf/txt/이미지)를 C:\rag\data\ 에 넣는다.
# Ollama 가 켜져 있어야 함(Windows 는 보통 자동 서비스). 확인:
Invoke-RestMethod http://localhost:11434/api/version

# 인덱싱(둘 중 하나):
#  (a) 아래 1-6 으로 서버를 켠 뒤, 브라우저에서 [관리 탭] → [전체 재인덱싱]
#  (b) CLI:
$env:RAG_EMBED="bge-m3"
.\.venv\Scripts\python -c "from rag.index.indexer import Indexer; print(Indexer().reindex(full=True))"
```

### 1-6. 서버 켜기
```powershell
.\packaging\start_server.ps1
# 출력되는 접속 주소 확인 예: http://192.168.0.10:8501
```
- 방화벽 인바운드 8501 허용(스크립트가 시도; 실패 시 관리자 PowerShell에서:
  `netsh advfirewall firewall add rule name="RAG 8501" dir=in action=allow protocol=TCP localport=8501`)
- 로컬 확인: A 브라우저에서 `http://localhost:8501` → 질문 1건 테스트.

### 1-7. 부팅 시 자동 구동 (작업 스케줄러)
1. `작업 스케줄러` → `작업 만들기`
2. 일반: "가장 높은 권한으로 실행" 체크
3. 트리거: "로그온할 때" (또는 "시스템 시작 시")
4. 동작: 프로그램 `powershell.exe`,
   인수 `-ExecutionPolicy Bypass -File C:\rag\packaging\start_server.ps1`
5. 저장. (Ollama 는 설치 시 자동 상주하므로 별도 조치 불필요.)
> 서비스로 더 견고하게 하려면 NSSM: `nssm install RAG-Server powershell -ExecutionPolicy Bypass -File C:\rag\packaging\start_server.ps1`

---

## 2단계 — 개발 PC B-1/B-2/… (설치 없음, 독립 앱)

브라우저가 아니라 **독립 실행 앱(`rag-client.exe`)** 으로 띄운다(주소창·탭 없는 자체 창).

### 2-A. 클라이언트 exe 빌드 (온라인 Windows PC, 1회 — 0단계에서 함께)
```powershell
.\packaging\client\build_client.ps1     # → packaging\client\dist\rag-client.exe
```
- 결과 `rag-client.exe` 자체는 오프라인 동작. Win11 은 WebView2 내장(구형 Windows면 런타임 반입).

### 2-B. 각 개발 PC 배포
1. `rag-client.exe` + `server.txt` 를 B PC 같은 폴더에 복사.
2. `server.txt` 를 A 서버 주소로 수정(한 줄): `http://192.168.0.10:8501` (1-6 출력 주소).
3. **`rag-client.exe` 더블클릭 → 독립 창으로 앱 실행.** 바탕화면 바로가기+아이콘 지정 시 완전한 앱 형태.
4. 서버 IP가 바뀌면 **server.txt 만 수정**(재빌드 불필요). 연결 실패 창이 뜨면 서버 실행/방화벽/주소 확인.

> 무빌드 대안: `packaging\open_client.bat`(Edge 앱모드 `--app`)도 주소창 없는 창을 띄운다.
> 자세한 내용은 `packaging/client/README.md`.

---

## 3단계 — 운영 · 문제 해결

### 문서 추가/변경
- 새 문서를 A의 `data\` 에 넣고 → 브라우저 [관리 탭] → **증분 인덱싱**(변경분만 처리).

### 개선기록 회수 (폐쇄망 밖 개선용)
- [개선 기록 탭] → **Markdown 내보내기** → `C:\rag\data\feedback\feedback_export.md` 생성.
- **이 파일만** 반출(실제 값은 자동 비식별화, 표는 형태만). 이 파일을 개발자에게 전달.

### 서버 재시작
- 실행 창 닫기(Ctrl+C) 후 `start_server.ps1` 재실행. (스케줄러 등록 시 재로그온/재부팅으로도)

### 자주 나는 오류
| 증상 | 원인/조치 |
|---|---|
| `import 실패` (설치 시) | 파이썬 버전 ≠ wheelhouse 태그 → 맞는 wheelhouse 반입 |
| `임베딩 차원 불일치 768` | bge-m3 가 nomic 오라벨 → 정품 bge-m3 재반입, `ollama show bge-m3`=1024 |
| `Ollama 연결 실패` | `ollama serve`/Ollama 서비스 미실행 → 시작. `:11434` 응답 확인 |
| B에서 접속 불가 | A 서버 미실행 / 방화벽 8501 / 다른 서브넷 |
| LLM 태그 오류 | `start_server.ps1` 의 `RAG_LLM` 을 `ollama list` 실제 태그로 |
| OCR 추론 실패(oneDNN) | 코드가 `enable_mkldnn=False` 로 이미 회피. paddle 재확인 |
| 질의가 느림/대기 | GPU 1장 직렬 처리 — 동시 질의 수 조절(2~3 권장) |

### 참고 문서
- 오프라인 패키징: `packaging/README.md` · 모델 이전: `docs/model_transfer.md`
- 설계: `docs/design.md` · 서버/클라이언트 스크립트: `packaging/start_server.ps1`, `packaging/open_client.bat`
