# 오프라인 배포 패키징 가이드 (design.md §10)

폐쇄망 Windows 11 PC(인터넷 차단, RAM 12GB, RTX 3060 Ti 8GB, Python 3.10~3.12)에 USB로만
반입해 설치한다. 이 폴더의 스크립트로 **온라인 PC에서 wheelhouse를 만들고**, 오프라인 PC에서
`install.ps1`/`install.bat`로 **인터넷 없이** 설치한다.

## 배포 토폴로지 (1 서버 · N 클라이언트)

Streamlit은 **웹 앱(서버 렌더링)** 이라 설치는 **서버 1대에만** 한다.

```
[업무 PC A = 서버]  ← 전체 설치(파이썬+wheelhouse+Ollama+모델+인덱스)
   Ollama(127.0.0.1:11434) + Streamlit(0.0.0.0:8501) + ChromaDB/BM25 인덱스
        ▲ 사내망 HTTP :8501
        │
   ┌────┼─────────────┬─────────────┐
[B-1]        [B-2]         [B-3] …   ← **설치 없음**. 브라우저로 http://A:8501 접속
 (개발 PC = 클라이언트: open_client.bat 더블클릭 = 브라우저 열기)
```

- **서버 A**: `install.ps1`로 설치 → 인덱싱(관리 탭) → `start_server.ps1`로 상시 구동
  (Ollama·LLM·리랭커·OCR·인덱스 전부 A에서 실행). GPU 1장이라 LLM 질의는 **직렬 처리**
  → 동시 사용자가 몰리면 "처리 중" 후 순차 응답(2~3명 원활, 그 이상은 대기 발생).
- **클라이언트 B-x**: 아무 설치 없이 **브라우저만**. `open_client.bat`(서버 주소만 수정)을
  각 PC 바탕화면에 복사해 더블클릭 = 웹 UI 열기. Ollama/모델/인덱스는 B에 필요 없음.
- 개선기록(`data/feedback/`)·인덱스는 **서버 A에 공유 저장** → 누가 접속하든 같은 데이터.

## 0. 배포 폴더 구조 (USB)

```
crypto-rag-dist/
  rag/  tests/  samples/  smoke_test.py  requirements.txt   # 소스 + 잠금 목록
  wheelhouse/win_amd64_py312/   # 순수 wheel (서버 A=Python 3.12.7 → py312. cp312 전 패키지 실측 확인)
  models/                       # (별도) Ollama blobs+manifests, 리랭커 가중치 — docs/model_transfer.md
  packaging/install.ps1 | install.bat | build_wheelhouse.sh | README.md
  docs/                         # model_transfer.md 등 가이드
```

## 1. 온라인 PC에서 wheelhouse 생성 — **반드시 Windows에서**

```powershell
.\packaging\build_wheelhouse.ps1          # 배포 PC가 3.10/3.12 면 해당 파이썬으로 각각 재실행
```

> ⚠️ **왜 리눅스가 아니라 Windows에서 빌드하나 (2026-07-13 실측)**: 리눅스에서
> `pip download --platform win_amd64` 는 환경마커(`sys_platform`)를 **호스트(리눅스) 기준**으로
> 평가한다. 그래서 `chromadb`→`uvicorn[standard]`→**`uvloop`(Unix 전용)** 가 포함돼야 한다고 보고
> win wheel을 못 찾아 해석이 깨진다(ResolutionImpossible). **Windows 네이티브 `pip download`** 는
> 마커를 올바로 평가해 uvloop를 자동 제외하고 win wheel을 받는다. → 빌드는 Windows에서.

핵심 주의 (구현 중 실측으로 확정된 함정):

- **`kiwipiepy_model` 은 sdist-only (wheel 없음, ~84MB 데이터)** → `--only-binary=:all:` 이 실패한다.
  해결: `pip wheel kiwipiepy_model` 로 **`py3-none-any` 유니버설 wheel을 미리 빌드**해 wheelhouse에 넣는다
  (순수 데이터라 컴파일러 불필요). `build_wheelhouse.ps1` 이 자동 처리.
  - 엔진 `kiwipiepy` 자체는 `cp39-abi3-win_amd64` wheel 제공 → 정상.
- **`torch` 는 CPU wheel** 사용(질의 GPU는 LLM 전용). `--index-url https://download.pytorch.org/whl/cpu`
  로 CPU 빌드를 고정한다(PyPI 기본 torch도 Windows는 CPU지만 명시가 안전).
- 3.10/3.11/3.12 는 ABI가 달라 **파이썬 마이너 버전별로 wheelhouse를 따로** 만든다(배포 PC 버전에 맞춰).

### 순수/바이너리 wheel 가용성 검증 결과 (2026-07-13, win_amd64 개별 실측 `--no-deps`)

> **cp311·cp312 둘 다 전 패키지 wheel 존재 확인**(서버 A=Python 3.12.7 → cp312 사용).
> paddlepaddle 3.3.1·torch 2.13.0·onnxruntime·numpy·chroma-hnswlib 등 cp312-win_amd64 확보.

**핵심 컴파일 패키지 전원 Windows wheel 제공 확인 → 오프라인 배포 실현 가능**:
`chromadb 1.5.9(cp39-abi3)` · `chroma-hnswlib 0.7.6` · `onnxruntime 1.27.0` · `tokenizers 0.23.1(abi3)` ·
`grpcio 1.82.1` · `pydantic-core 2.47.0` · `numpy 2.4.6` · `torch 2.13.0` · `kiwipiepy 0.23.2(abi3)` ·
`charset-normalizer/pyyaml/orjson` (전부 cp311-win_amd64). 순수 wheel: `bm25s/pdfplumber/streamlit/
sentence-transformers/transformers/openpyxl/python-docx/python-pptx` (py3-none-any). 유일 예외=위 kiwipiepy_model.

## 2. 리랭커/모델 가중치 (pip 대상 아님 — USB)

- Ollama 모델(`bge-m3` 1024d, `qwen3` 계열): `docs/model_transfer.md` 절차로 blobs+manifests 병합.
- 리랭커 `BAAI/bge-reranker-v2-m3`(~2.2GB): 온라인에서 폴더째 받아 USB → 오프라인 로컬 경로.
  온라인 PC에서 받기:
  ```bash
  python -c "from huggingface_hub import snapshot_download; \
    snapshot_download('BAAI/bge-reranker-v2-m3', local_dir='models/bge-reranker-v2-m3')"
  ```
  오프라인에서 지정: `set RAG_RERANKER=C:\models\bge-reranker-v2-m3`
  (코드 기본값도 `BAAI/bge-reranker-v2-m3` — 로컬 경로를 주면 네트워크 접근 없음).

## 3. 오프라인 PC 설치

```powershell
.\packaging\install.ps1        # 또는 packaging\install.bat
# → .venv 생성 → wheelhouse에서만(--no-index) 설치 → import 스모크
.\.venv\Scripts\python smoke_test.py     # Ollama+모델 반입 후 E2E
.\.venv\Scripts\streamlit run rag\app\main.py --server.address 0.0.0.0 --server.port 8501
```

## 4. 환경변수 (배포 PC 태그에 맞춤)

| 변수 | 기본 | 배포 PC |
|---|---|---|
| `RAG_LLM` | `qwen3_8b_ctx32998` | 배포 PC의 실제 태그 |
| `RAG_EMBED` | `bge-m3` | (정품 1024d) |
| `RAG_RERANKER` | `BAAI/bge-reranker-v2-m3` | `C:\models\bge-reranker-v2-m3` (로컬) |
| `RAG_LLM_TIMEOUT` | `600` | GPU면 더 짧아도 됨 |

## 5. 백업안 (wheel 실패 시)

- 벡터 DB: chromadb 네이티브 wheel(onnxruntime) 문제 시 → `sqlite-vec`.
- 리랭커: torch 반입 곤란 시 → GGUF + `llama-cpp-python`.
- (design.md 부록 A 리스크표 참조)
