# 사내 지식 공유 RAG 플랫폼 — 상세 설계서

> 버전: v0.2 (사용자 답변 반영) · 대상 배포 환경: 오프라인(폐쇄망) Windows 11 PC
> 변경: PDF 파서 추가, 리랭커 MVP 포함, LLM/HEX 사양 확정, 메모리 예산 재산정.
> 미확정: bge-m3 임베딩 태그 검증(`docs/open_questions.md` Q1-b).

---

## 0. 전제와 최우선 원칙

1. **오프라인 배포가 최상위 제약이다.** 설치 시 인터넷이 필요한 방식은 전부 실패로 간주한다.
   모든 라이브러리는 "Windows + Python 3.10~3.12 + 순수 `pip` wheel 오프라인 설치 가능"을
   1순위로 검증한다(§10 검증표).
2. **12GB RAM / 8GB VRAM에서 확실히 도는 구성이 이론상 우수한 구성보다 우선한다.**
3. **실제 사내 자료는 개발 PC에 존재하지 않는다.** 더미 샘플로만 개발/테스트하며,
   샘플은 **검토 게이트**(§12) 통과 후에만 파이프라인 확정에 사용한다.
4. **HEX 로그는 지식 문서가 아니다.** 질의 시 업로드되는 분석 입력물이다(§7).

### 확정된 스택 (사용자 결정·답변 반영)

| 구성요소 | 선택 | 근거 |
|---|---|---|
| 웹 UI | **Streamlit** | 단일 호스트 다중 사용자(2~3명), 순수 wheel, 업로드/확인단계 UI 용이 |
| LLM | **qwen3_8b_ctx32998** (주) / `qwen3.5:2b`(폴백) | 8B·32k 컨텍스트 5.2GB → HEX 로그·다청크 RAG에 유리 |
| 임베딩 | **bge-m3 (1024d) via Ollama** | 한/영 다국어 검색 강함. **정품 재반입 확정**(기존 `bge-m3-FP16.gguf` 태그는 nomic 오라벨 → §10-이전절차) |
| 리랭커 | **bge-reranker-v2-m3 (CPU)** | 사용자 요청으로 **MVP 포함**. torch CPU로 질의 VRAM 무경합 |
| 벡터 DB | **ChromaDB** | 순수 파이썬, 메타데이터 필터 편의. BM25 미내장 → 별도 결합(§5) |
| LLM 런타임 | **Ollama** (기설치) | 모델 스와핑/keep_alive로 VRAM 관리 |
| 한국어 형태소 | **kiwipiepy** | Windows wheel, BM25 토큰화 |
| 파서 | openpyxl/python-docx/python-pptx/**pdfplumber**/charset-normalizer | 표+텍스트 중심, 순수 wheel |

---

## 1. 전체 아키텍처

```
[인제스천 파이프라인]
  문서(xlsx/docx/pptx/pdf/txt/이미지)
    └─ 포맷별 파서 ──▶ 정규화 텍스트 + 구조 메타(표/시트/슬라이드/페이지)
        └─ (이미지) OCR ──▶ 텍스트
    └─ 청킹(표 보존, 메타 부착; doc_type=protocol_spec|general)
        └─ 임베딩(bge-m3) ──▶ ChromaDB(dense)  +  kiwipiepy 토큰화 ──▶ BM25 인덱스
        └─ 파일 해시/mtime ──▶ 증분 인덱싱 매니페스트

[질의 파이프라인 — 일반 문서 QA]
  질문 ─▶ 하이브리드 검색(dense+BM25 → RRF) ─▶ 리랭커(bge-reranker, CPU)
       ─▶ 컨텍스트 조립(출처 메타) ─▶ LLM(Ollama) ─▶ 한국어 답변 + 출처

[질의 파이프라인 — HEX 분석 모드] (§7)
  HEX 업로드 + 질문 ─▶ 프로토콜 명세 후보 검색 ─▶ [UI 확인 단계 필수]
       ─▶ 확정 명세 컨텍스트 + HEX 파싱/구간추출 ─▶ LLM ─▶ 분석 답변

[UI] Streamlit(0.0.0.0:8501): 문서 QA 탭 / HEX 분석 탭 / 관리(인덱싱) 탭
```

모듈 구조(예정): `ingest/ index/ retrieve/ generate/ hex/ app/ packaging/`.

---

## 2. 메모리 예산 (VRAM 8GB / RAM 12GB) — 리랭커 포함 재산정

질의 시 **동시에 상주해야 하는** 자원 기준.

| 모델 | 구성 | 배치 | VRAM |
|---|---|---|---|
| LLM `qwen3_8b_ctx32998` | 8B Q4, 32k ctx 지원 | **GPU** | ~5.2GB (+ KV) |
| KV 캐시 | `num_ctx=4096` 기본 | GPU | ~0.5GB (8192면 ~1GB) |
| 임베딩 bge-m3 | 1024d, F16 ~1.2GB | **GPU**(질의 단건은 CPU도 가능) | ~1.2GB |
| 리랭커 bge-reranker-v2-m3 | CrossEncoder | **CPU (torch CPU)** | 0 (GPU) |
| OCR | PaddleOCR | **인제스천 시점만** | 질의 무경합 |

**질의 시 GPU 합계 ≈ LLM 5.2 + KV 0.5 + 임베딩 0.5~1.2 ≈ 6.2–6.9GB → 8GB 내 여유 확보.**

**전략 (확실히 도는 구성)**
1. **리랭커는 CPU 실행**(torch CPU wheel). 2~3명·top-k 재정렬은 CPU에서 수백 ms → 수용 가능.
   질의 시 GPU를 LLM+임베딩 전용으로 유지.
2. 임베딩은 인제스천 배치는 GPU, 질의 단건은 필요 시 CPU로 돌려 GPU를 LLM에 양보 가능.
3. **하드웨어 상향 시**(사용자 언급) 리랭커를 GPU(torch CUDA)로 이동해 지연 단축.
4. OCR은 인제스천 시점에만 동작하므로 질의 LLM과 경합하지 않음(배치 처리).
5. `num_ctx` 기본 4096, HEX 장문 분석 시 선택적 상향(32k 모델이므로 가능하나 KV VRAM 주의).

> ✅ **bge-m3 태그 검증 완료(해결)**: 기존 `bge-m3-FP16.gguf` 태그는 실제로 **nomic-bert 136.73M,
> 768d, ctx 2048**(=nomic-embed-text 오라벨)로 확인됨. **정품 bge-m3(1024d) 재반입 확정**(§10-이전절차).
> 위 예산은 정품 bge-m3(F16 ~1.2GB) 기준으로 반영됨.

---

## 3. 포맷별 파싱 전략

공통: **표준 양식 없음 → 템플릿 비의존.** 텍스트·표 중심 정규화 + 출처 메타 부착.
프로토콜 명세가 주로 **표+텍스트(Word/PDF)** 이므로 **표 직렬화 정확도가 최우선**.

### xlsx — `openpyxl` (순수 wheel ✓)
시트별 분리(시트명 메타), 표→마크다운 직렬화, 병합셀 fill-forward, 다중 헤더 `상위 > 하위` 병합.

### docx — `python-docx` (순수 wheel ✓)
문단/표/이미지 추출, 본문 XML 순회로 인라인 순서 보존, 비표준 스타일 무시(텍스트 우선), 표 직렬화.

### pptx — `python-pptx` (순수 wheel ✓)
슬라이드 단위 텍스트+표+이미지, 슬라이드 번호 메타, 표 직렬화, (선택)발표자 노트.

### pdf — `pdfplumber` (순수 파이썬 ✓) **[신규]**
- 프로토콜 명세의 핵심 포맷. **페이지 단위** 텍스트 + `extract_tables()`로 **표 구조 추출** → 마크다운 직렬화.
- 페이지 번호 메타 부착. 다단(멀티컬럼) 레이아웃은 좌→우 정렬 보정.
- **스캔 PDF(이미지)** 페이지는 텍스트가 비면 OCR(§8)로 라우팅.
- 대안: PyMuPDF(빠름, 바이너리 wheel)이나 AGPL 라이선스 → 기본은 pdfplumber(MIT) 채택.

### txt — `charset-normalizer` (순수 wheel ✓)
EUC-KR/CP949/UTF-8(+BOM) 자동 판별, 실패 시 CP949→UTF-8 폴백.

### 이미지 — OCR (§8, Phase 3) · hex — 인덱싱 제외(§7)

---

## 4. 청킹 전략

- **~400–800 토큰, 10–15% 오버랩**(bge-m3 토크나이저 기준, 한국어 토큰 밀도 반영).
- **표는 청크 경계에서 분할 금지.** 큰 표는 독립 청크로 분리하고 헤더를 각 조각에 반복 부착.
- **문서당 표·페이지가 많음(사용자 확인)**: 프로토콜 명세는 표가 다수·다중 페이지 → **표 단위 청크**를
  기본으로 하고 각 표에 `표제목/페이지/문서` 메타 부착. 검색 시 표 청크가 파편화되지 않게 유지하고,
  후보가 많아지므로 **리랭커의 역할이 커진다**(§5). 페이지 번호 메타로 출처 정확도 확보.
- 자연 경계(문단/슬라이드/시트/페이지) 우선, 문장 중간 절단 회피.
- **메타(청크마다)**: `source_file, doc_title, sheet_name|slide_no|page_no, section,
  doc_type(protocol_spec|general), chunk_id, content_hash`.
  → `doc_type=protocol_spec`는 HEX 워크플로우 후보 필터에 사용(§7).

---

## 5. 임베딩·검색·리랭킹

### 임베딩
- **bge-m3(1024d) via Ollama**. 인제스천 배치=GPU, 질의 단건=GPU/CPU 선택.
- 기존 `bge-m3-FP16.gguf` 태그는 nomic 오라벨로 확인 → **정품 bge-m3 재반입 확정**(§10-이전절차).
  코드/설정은 재반입한 정품 태그(예: `bge-m3`)를 참조하고, 오라벨 태그는 사용하지 않는다.

### 하이브리드 검색 (dense + sparse)
- **Sparse(BM25)**: `kiwipiepy` 형태소 토큰화 → `bm25s`(순수 파이썬). 영어는 소문자/공백 정규화.
- **Dense**: ChromaDB 벡터 검색.
- **융합**: **RRF** `score = Σ 1/(k+rank)` (k≈60), 가중치 파라미터화.
- 근거: 장비명·코드·약어가 많아 정확매칭(BM25)+의미매칭(dense) 결합이 견고.

### 리랭커 (MVP 포함 — 사용자 요청)
- **bge-reranker-v2-m3**를 **sentence-transformers CrossEncoder**로 로드, **CPU 실행**.
- 하이브리드 top-N(예: 20)을 재정렬해 최종 top-k(예: 5) 선정 → 근거 품질↑.
- 오프라인: `sentence-transformers`/`transformers`(순수 wheel) + `torch`(Windows CPU wheel) +
  **모델 가중치는 USB 반입**. 상향 시 torch CUDA로 GPU 가속.

---

## 6. 답변 생성

- **시스템 프롬프트(공식체)**: 한국어 공식체 답변, 컨텍스트 **근거 있을 때만** 답하고 각 주장에
  **출처(문서명·시트/슬라이드/페이지)** 표기, 근거 없으면 **"제공된 문서에서 근거를 찾지 못했습니다"**.
- Qwen3 thinking 억제(`/no_think`)로 간결·근거중심 답변 유도.
- **출처 렌더**: 근거 청크 메타를 답변 하단 목록으로, UI에서 원문 펼침 제공.
- **컨텍스트 예산**: `num_ctx=4096` 기본, top-k×청크크기로 동적 트림, KV VRAM과 연동(§2).

---

## 7. 통신 로그 분석 워크플로우 (핵심)

> 사용자 피드백 반영: 로그 포맷은 **장비별로 조금씩 다르며**, HEX가 아니라 **자연어로 표기된 로그**도
> 존재한다. 따라서 "HEX 전용"이 아니라 **통신 로그 분석 모드**(hex + 자연어 모두 처리)로 일반화한다.

1. **후보 검색**: 업로드 로그 + 질문(장비 단서)로 `doc_type=protocol_spec` 중 관련 명세 후보 하이브리드 검색.
2. **확인 단계 (필수·자동 추측 금지)**: 후보를 UI에 제시, **"이 문서의 프로토콜이 맞습니까?"**
   사용자 확정 전 해석 금지.
3. **해석·분석**: 확정 명세의 **패킷 구조·필드·명령 코드**를 컨텍스트로 로그 해석·답변.

### 7-1. 로그 종류 자동 판별 (업로드 시)
- **HEX 로그**: 라인의 대부분이 hex 토큰(`[XX]`/`XX`/`0xXX`)이면 → HEX 파서(7-2).
- **자연어 로그**: hex 토큰 비율이 낮고 자연어 문장 위주면 → **NL 로그 경로**. 로그 텍스트를 그대로
  청킹/발췌하고, 확정 명세와 함께 컨텍스트로 넣어 LLM이 사건 흐름을 해석(별도 바이트 파싱 없음).
- 혼합 로그는 라인 단위로 분기.

### 7-2. HEX 파서 — **장비별 파싱 프로파일** (하드코딩 금지)
포맷이 장비마다 달라 단일 파서로는 부족하다. **프로파일(설정)** 로 표현하고 **자동 감지 + 사용자 확인**한다.
관측된 변형(샘플 반영):
```
07/08 00:45:05 [02]-[01]-[10]-[11]-[03]   # 타임스탬프 + [] + '-' 구분자
07/08 00:45:05 [02][01][10][11][03]       # 타임스탬프 + []
[02][01][10][11][03]                       # 타임스탬프 없음
07/08 00:45:05 0x02 0x01 0x10 0x11 0x03    # 공백 구분 + 0x 접두
07/08 01:10:00 [TX] 01 05 41 00 00 2D 85   # 방향표시([TX]/[RX]) + 공백 hex (타 장비/타 프레임)
02 01 10 11 03 …                            # 바이너리(.dat) 원시 덤프
```
프로파일 필드(예): `timestamp_regex`(옵션), `direction_marker`(옵션 `[TX]/[RX]`),
`byte_token`(정규식: `\[hh\]` | `0xhh` | `hh`), `separator`, `framing`(STX/ETX | SOH/LEN | 개행 등),
`checksum`(XOR | CRC16 | none), `endian`.
- **자동 감지**: 토큰 패턴·구분자·프레임 시작바이트를 스캔해 프로파일 후보 추정 → **UI에서 사용자 확인**.
- **바이트 스트림 복원**: 타임스탬프/방향표시/구분자 제거 후 hex 토큰만 추출.
- **프레이밍/커맨드 매칭**: 확정 명세의 프레임 규칙(시작바이트·길이·체크섬)과 명령 코드로 프레임 분할·해석.
- **바이너리 .dat 폴백**: hex 토큰 패턴이 없으면 원시 바이트를 직접 프레이밍.

### 7-3. 고려사항
- **컨텍스트 초과**: 프레임/구간 단위 분할·질문 관련 구간 추출·요약→상세 2단계. 명세 청크를 컨텍스트에 우선 고정.
- **명세 표 참조 정확도**: 파싱 시 패킷 정의 표를 구조 메타로 보존해 필드 오프셋/폭 정확 인용.
- **UI 모드 분리**: 로그 분석 탭 별도, 파일 업로드 시에만 활성화, 확인 단계 필수 개입.
- **프로파일 재사용**: 확정한 장비별 프로파일을 저장해 다음 업로드에서 재사용(감지 정확도↑).

---

## 8. OCR (Phase 3)

| 방안 | 오프라인 | 자원 | 한/영 | 비고 |
|---|---|---|---|---|
| **PaddleOCR (1순위)** | paddlepaddle Windows wheel + 모델 반입 | 인제스천 GPU/CPU | 표·문서 강함 | 질의 VRAM 무경합 |
| Tesseract | 엔진 실행파일+언어팩 번들, pytesseract | CPU | 인쇄체 무난 | 순수 pip 아님 |

- 이미지 비중 문서 혼재 → **정확도 우선 PaddleOCR**. 인제스천 시점 실행이라 질의와 무경합.
- 스캔 PDF 페이지도 이 파이프라인으로 라우팅(§3 pdf).

---

## 9. 문서 업데이트 (증분 인덱싱)

- 규모(~100개, 초기 잦은 갱신) → **증분 인덱싱을 초기부터 중시**.
- 매니페스트 `{source_file:{content_hash,mtime,chunk_ids[]}}`. 해시 변경 시 해당 청크만 재처리,
  삭제 파일 청크 제거, 관리 탭에서 전체 재인덱싱 제공.

---

## 10. 오프라인 패키징 (가장 중요)

### wheelhouse
```
pip download -r requirements.txt \
  --platform win_amd64 --python-version 3.11 --only-binary=:all: -d wheelhouse/
```
- 순수 wheel만 수집. sdist만 있는(컴파일 필요) 패키지는 후보에서 배제/대안. 3.10/3.11/3.12 병행 수집.
- **배포 용량 제약 없음**(Q7) → torch/OCR 등 대용량 허용.

### 순수 wheel 검증표 (후보)

| 패키지 | 용도 | Win 순수 wheel | 비고 |
|---|---|---|---|
| streamlit | UI | ✓ | 의존성 동반 |
| chromadb | 벡터 DB | ✓ | onnxruntime 등 동반 |
| openpyxl / python-docx / python-pptx | office 파서 | ✓ | Pillow 동반(pptx) |
| **pdfplumber** | pdf 파서 | ✓(순수 파이썬) | pdfminer.six 동반 |
| charset-normalizer | 인코딩 | ✓ | |
| kiwipiepy | 형태소 | ✓ | |
| bm25s | BM25 | ✓ | 순수 파이썬 |
| ollama | 클라이언트 | ✓ | 엔진 기설치 |
| **torch (CPU)** | 리랭커 백엔드 | ✓ | 대용량, Windows CPU wheel |
| **sentence-transformers / transformers** | 리랭커 | ✓ | 모델 가중치 별도 반입 |
| paddleocr / paddlepaddle | OCR(Phase3) | ✓(대용량) | 모델 반입 |

> 검증표는 후보이며 **실제 `pip download`로 순수 wheel 여부 확정**이 구현 첫 검증 항목.
> 실패 시 백업안: 벡터 DB→sqlite-vec, 리랭커→GGUF+llama-cpp-python.

### 설치·진단·모델 이전
- `install.bat`/`install.ps1`: venv → `pip install --no-index --find-links wheelhouse -r requirements.txt`.
- `smoke_test.py`: import + Ollama 연결/모델 존재 + 임베딩 1건(차원 확인) + 인덱싱→검색→리랭킹 왕복.
- Ollama 모델: blobs+manifests USB 이전 또는 GGUF+Modelfile `ollama create`. 리랭커/OCR 가중치도 USB.

### 모델 이전 절차 (요약 — 상세는 `docs/model_transfer.md`)
- **정품 bge-m3 재반입(필수)**: 온라인 PC `ollama pull bge-m3` → `~/.ollama/models`의 blobs+manifests를
  USB로 오프라인 PC 동일 경로(Windows `C:\Users\<user>\.ollama\models`)에 병합 → `ollama show bge-m3`로
  **1024차원** 확인. 코드는 정품 `bge-m3` 태그를 참조(오라벨 `bge-m3-FP16.gguf` 미사용).
- 리랭커 `bge-reranker-v2-m3`, OCR 모델 가중치: 온라인에서 받아 USB로 이전.

### 배포 폴더
```
crypto-rag-dist/  src/  wheelhouse/  models/  install.bat|ps1  smoke_test.py  docs/(이전가이드+매뉴얼)
```

---

## 11. 로드맵

### MVP — 텍스트+표 검색 QA (리랭커 포함)
- xlsx/docx/pptx/**pdf**/txt 파싱 → 청킹 → ChromaDB(bge-m3)+BM25 → RRF → **리랭커** → LLM 출처 답변
  → Streamlit(QA 탭 + 인덱싱 탭, 0.0.0.0 바인딩).
- **완료 기준**: 승인 샘플로 파싱→인덱싱→질의 E2E, 정확한 출처, 근거 없을 때 "모른다", 리랭킹 동작.

### Phase 2 — HEX 로그 분석
- HEX 업로드 → 명세 후보 검색 → **UI 확인 단계** → 확정 명세 기반 해석(바이트 토큰화·커맨드 매칭·구간분할).
- **완료 기준**: 가상 명세+HEX 샘플로 확인 흐름 거쳐 필드/명령 해석, 컨텍스트 초과 분할 동작.

### Phase 3 — 고도화
- 이미지/스캔PDF OCR, 리랭커 GPU 이동(상향 시), 하이브리드 파라미터 튜닝.

---

## 12. 개발 진행 절차 (샘플 검토 게이트)

1. **샘플 생성**: 한/영 혼용 xlsx·docx·pptx·**pdf**·txt(표·이미지, 양식 제각각) +
   가상 장비 프로토콜 명세(Word/PDF, 표 중심, 커맨드 10~30개) + 그 명세를 따르는 HEX 로그(.txt/.dat).
2. **검토 게이트(필수)**: 샘플 목록·구조·내용 요약을 사용자에게 제시 → 실제 자료와 대조 피드백 반영.
3. **승인 후에만** E2E 테스트. 승인 전 파이프라인 세부 확정 금지.

---

## 부록 A. 리스크와 대응

| 리스크 | 영향 | 대응 |
|---|---|---|
| ~~bge-m3 태그가 실제로 nomic~~ **[해결]** | 임베딩 차원/품질 상이 | 검증 완료(nomic 768d 오라벨 확인) → **정품 bge-m3 재반입 확정**(§10-이전절차) |
| chromadb/onnxruntime/torch 네이티브 wheel 누락 | 오프라인 설치 실패 | 구현 첫 단계 `pip download` 실측, 백업안(sqlite-vec/llama-cpp 리랭커) |
| 리랭커 CPU 지연 | 응답 지연 | top-N 축소, 상향 시 GPU 이동 |
| HEX 로그 컨텍스트 초과 | 분석 실패 | 패킷 분할·관련 구간 추출(§7) |
| 스캔 PDF 텍스트 미추출 | 검색 누락 | 텍스트 빈 페이지 OCR 라우팅(§3) |
