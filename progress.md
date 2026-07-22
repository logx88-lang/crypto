# progress.md — 진행 로그 / 지식·의사결정 기록

> 규칙: **변경마다** (1) 새로 알게 된 사실·제약, (2) 의사결정 갈림길과 선택·근거,
> (3) 다음 액션을 아래에 append 하고 git push 한다. 최신 항목이 위로 오도록 역순 기록.

---

## 2026-07-13 (6) — 개선기록 기능(폐쇄망 반출용 비식별화) ✅

### 목적
업무 PC(폐쇄망)에서 실사용하며 개선사항을 기록하되, **실제 프로토콜 데이터는 반출 불가** →
양식(구조)은 유지하고 실제 값은 **자동 비식별화(가명화)**해 외부에서 개선 작업 가능하게.

### 구현
- **`rag/feedback/sanitize.py`** — 구조 보존 결정적 가명화. 한글 어휘→`어휘N`, 영문 식별자→`IDN`,
  숫자→같은자릿수 다른숫자, HEX→같은형태 다른값. 표 파이프·구분선·행/열 배치·문장 골격 보존.
  `table_shape()`(값 없이 행×열만), `sanitize_record()`(레코드당 매핑1개, 안전메타[page/kind/
  doc_type] 유지·민감메타[doc_title/sheet] 가명화). 매핑은 저장 안 함(레코드 간 상관 불가).
- **`rag/feedback/log.py`** — JSONL 저장(비식별 레코드만) + Markdown 반출. `add()`는 방어적 재-비식별.
- **Streamlit**: QA/로그 결과 아래 `🚩 개선 기록` 캡처 폼(유형·심각도·메모 + **저장 전 비식별 미리보기**),
  신규 `개선 기록` 탭(목록·건수·Markdown 반출·다운로드). `data/feedback/`(gitignore).
- **테스트** `tests/test_feedback.py` 7/7: 실데이터(한글/식별자) 완전 제거·구조 보존·결정성·
  table_shape·레코드 안전메타·로그 왕복·반출물 안전.

### UI E2E 검증(Playwright)
- 4탭 렌더, 로그탭 캡처폼+저장, 개선기록 탭·반출. **핵심**: 입력 `"XM-200 코인 투입 0x12 명령 해석"`
  → 디스크 저장 `"ID1 어휘1 어휘2 0x29 어휘3 어휘4"` (구조 유지·실데이터 0). 5/5 PASS.
- 버그 2건 수정: **Streamlit expander 중첩 금지**(미리보기를 체크박스 토글로) + 개선기록 탭 라벨과
  캡처폼 expander 라벨 충돌(고유 문자열로 셀렉트).

### 운영 메모
- 반출 흐름: 개선기록 탭 → `data/feedback/feedback_export.md` 생성 → **이 파일만 USB 반출**(실데이터 없음).
- 전체 단위 **37/37**(core12+retrieval12+ocr6+feedback7).

### 다음(사용자)
- 업무 PC 실사용 중 개선 케이스를 이 기능으로 기록 → 반출물 회신 → 그 근거로 표 청킹/추출 개선 착수.

---

## 2026-07-13 (5) — 하이브리드 검색 평가 하네스 + 파라미터 튜닝 ✅

### 한 일
- **`eval/` 평가 하네스**: `eval_set.py`(더미 근거 질문 16개, must_contain 판정) +
  `run_eval.py`(질문별 임베딩·dense·bm25·리랭커점수 1회 캐시 → 파라미터 조합 인메모리 스윕).
  `Reranker.scores()`(정렬없는 점수) 추가. LLM 미호출로 가벼움.
- 스윕: 앙상블 가중치(dense:bm25) 7종 × rerank on/off × rrf_k(10/60/100), rerank_top_n(5~27).

### 결과 (더미 27청크, n=16) — Recall@k / MRR
- **리랭커 ON = 최대 지렛대**: MRR 0.874→**0.944**(R@3도 상승). rerank-on 구성은 가중치·rrf_k·
  rerank_top_n 무관하게 R@5=0.94/MRR≈0.944로 포화(소코퍼스라 리랭커가 흡수).
- **하이브리드 > 단일 리트리버**(rerank 전): hybrid 1:1 MRR 0.874 vs dense-only 0.770 / bm25-only
  0.790 → 두 리트리버 병용 가치 입증.
- **유일 실패(1/16) = 표 희석**: "TG-15 ADDR 필드 의미" 정답이 필드 여럿 섞인 큰 표 청크 →
  융합 7위→리랭커 9위로 저평가. 파라미터가 아닌 **청킹(행/필드 단위) 개선** 사안.

### 의사결정
- **파라미터 변경 없음(정당화 안 됨)**: 현재 기본값(리랭커 ON, 가중 1:1, rrf_k=60, rerank_top_n=20,
  final_k=5)이 이미 최적임을 데이터로 확인. 근거 없는 수치 조정 지양.
- 자산으로 하네스 + 발견 보존. **실 코퍼스(~100문서) 확보 후 재튜닝** 시 가중치/rrf_k 민감도 재평가.

### 다음 액션(후보)
- 표 청킹 개선(행/필드 단위 → 표 희석 완화) 후 하네스 재측정.
- 실 코퍼스 반입 시 eval_set 확장 + 재스윕.

---

## 2026-07-13 (4) — UI 실사용 점검 + OCR(Phase 3) 구현·실검증 ✅

### UI 실사용 점검 (Streamlit, Playwright 헤드리스)
- `streamlit run rag/app/main.py` 기동 후 브라우저 자동화로 **7/7 PASS**: 타이틀·3탭(문서QA/로그분석/관리)
  렌더, **관리탭 증분 인덱싱 버튼 실동작**(완료 표시), **로그 업로드→hex 감지→15프레임 파싱→
  프로토콜 명세 확인(필수) 게이트** UX, JS 에러 0. 스크린샷 확인.
- QA 파이프라인은 smoke로 이미 E2E 검증됨 → 브라우저 내 느린 CPU LLM 재실행은 생략.
- 점검용 Playwright/chromium은 별도 임시 venv(배포 `.venv` 무오염).

### OCR (Phase 3) — 구현 + 실 PaddleOCR 검증
- **`rag/ingest/ocr.py`**: `OCRBackend` 추상화 + `PaddleOCRBackend`(지연 로드, 주입 가능).
  미설치/`RAG_OCR=0` 시 `available()=False` → 파서는 마커만 남기고 진행(결정적 코어 무영향).
- **파서 통합**: 이미지 확장자(png/jpg/jpeg/bmp/tiff) `SUPPORTED_EXTS`+dispatch에 추가, `parse_image`
  신설(OCR→text element, source=ocr). `parse_pdf` 스캔페이지(텍스트 없음)를 렌더→OCR 라우팅
  (지연 평가 — 정상 PDF는 paddle import 안 함, 실측 0.25s).
- **테스트** `tests/test_ocr.py` 6/6(가짜 백엔드, paddle 불필요). 전체 **30/30**(core12+retrieval12+ocr6).
- **실 PaddleOCR E2E**: `system_diagram.png` → 한/영 정확 인식(XM-200·코인 컨트롤러·RS-485·TG-15·
  센서게이트웨이) → 청킹. Windows wheel 전원 확인(paddlepaddle 3.3.1·paddleocr 3.7.0·opencv·shapely 등).

### OCR에서 실측으로 잡은 이슈
- **PaddleOCR 3.x API 변경**: 2.x `ocr(img,cls=True)` → 3.x `predict(img)`+`rec_texts`. 백엔드가
  3.x 우선·2.x 폴백 양쪽 지원(생성 인자도 `use_textline_orientation`/`use_angle_cls` 순차 폴백).
- **paddlepaddle 3.x oneDNN 런타임 버그**(일부 CPU): `ConvertPirAttribute2RuntimeAttribute not
  support` → 추론 실패. **`enable_mkldnn=False`** 로 표준 CPU 커널 우회(코드 기본값). GPU 무관.
- 오프라인 모델 이전: 최초 실행이 `~/.paddlex/official_models/` 채움 → USB 반입(`docs/model_transfer.md` §3).

### 다음 액션
- (사용자·Windows) wheelhouse 생성 시 OCR 스택 포함(`requirements.txt`에 반영됨) → USB 배포.
- (선택) 하이브리드 파라미터 튜닝, 스캔 PDF 샘플로 PDF-OCR 경로 추가 검증.

---

## 2026-07-13 (3) — 폐쇄망 오프라인 패키징: 순수 wheel 실측 + 설치 스크립트 ✅

### 한 일
- `requirements.txt`(고정 잠금, 검증버전) · `packaging/`(`build_wheelhouse.ps1`·`install.ps1`·
  `install.bat`·`README.md`) 작성. `.gitignore`에 wheelhouse/data/logs 반영.

### 실측으로 확정된 배포 사실 (구현 첫 검증항목 — design.md §10)
1. **핵심 컴파일 패키지 전원 Windows(win_amd64/cp311) wheel 제공** → 오프라인 배포 실현 가능.
   `chromadb 1.5.9(cp39-abi3)`·`chroma-hnswlib 0.7.6`·`onnxruntime 1.27.0`·`tokenizers 0.23.1`·
   `grpcio`·`pydantic-core`·`numpy`·`torch 2.13.0`·`kiwipiepy 0.23.2` 등 (개별 `--no-deps` 실측).
2. **함정 A — `kiwipiepy_model` 은 sdist-only**(wheel 없음, 84MB 순수데이터). `--only-binary` 설치가
   막힘 → `pip wheel` 로 **`py3-none-any` 유니버설 wheel 미리 빌드**해 wheelhouse에 포함(컴파일 불필요).
   빌드 스크립트가 자동 처리.
3. **함정 B — wheelhouse는 반드시 Windows에서 빌드**. 리눅스 `pip download --platform win_amd64` 는
   환경마커(`sys_platform`)를 호스트 기준 평가 → `chromadb`→`uvicorn[standard]`→**`uvloop`(Unix전용)**
   때문에 ResolutionImpossible. Windows 네이티브 pip은 마커 정상 평가(uvloop 자동 제외). 실측으로 확인.
4. **torch = CPU wheel**(`--index-url .../whl/cpu`). 리랭커 `BAAI/bge-reranker-v2-m3`(~2.2GB)는
   pip 대상 아님 → HF snapshot_download 후 USB 반입, 로컬경로 지정(`RAG_RERANKER`).

### 다음 액션
1. (사용자) 온라인 **Windows** PC에서 `build_wheelhouse.ps1` 실행 → USB로 배포 PC 반입 → `install.ps1`.
2. 배포 PC 파이썬 3.10/3.12 면 해당 버전으로 wheelhouse 각각 생성.
3. (선택) Streamlit 실사용 점검, 하이브리드 파라미터 튜닝, OCR(Phase 3).

---

## 2026-07-13 (2) — B단계 E2E 검증 완료 (실 Ollama, CPU 서버) ✅

### 환경 구축 (VPN 서버, root 없이)
- 2차 파이썬 의존성 설치: **torch 2.13.0+cpu**(CUDA 인덱스로 CPU wheel), chromadb 1.5.9,
  kiwipiepy 0.23.2(+model), bm25s 0.3.9, sentence-transformers 5.6.0, transformers 5.13.1, streamlit 1.59.1.
- **Ollama 0.31.2** — root 불필요, `ollama-linux-amd64.tar.zst`(zstd) → `~/.local` 추출, `serve` 상시 기동
  (127.0.0.1:11434, CPU-only, 11.6GB 가용). ⚠️ 다운로드 URL은 GitHub 릴리스 자산(`.tar.zst`)만 유효
  (구 `ollama.com/download/*.tgz` 404).
- 모델 pull: `bge-m3`(1.2GB) + `qwen3:8b`(5.2GB).

### 실측으로 확정된 사실
- **bge-m3 = 1024d 정품 확인** (`/api/embed` 실측) — 이 서버에서 Q1-b 재확인(오라벨 아님).
- **E2E 스모크 전 단계 통과**(`smoke_test.py`, exit 0): 임베딩차원→인덱싱(7문서/27청크)→하이브리드+
  리랭커+LLM 답변(*"0x12=COIN_IN … [1]"* 출처정확)→근거없음 거부(*"…근거를 찾지 못했습니다"*)→
  로그분석(명세후보→[명세1] 근거해석+체크섬불일치 이상징후 명시).
- store+bm25 래퍼는 실 chromadb/bm25s/kiwipiepy로 별도 검증 통과.

### 버그·이슈 수정 (E2E에서 적발)
- **리랭커 repo id**: sentence-transformers가 bare 이름에 `cross-encoder/` 접두 → 존재하지 않는
  repo로 401. `RAG_RERANKER` 기본값 **`BAAI/bge-reranker-v2-m3`**(정식 repo)로 수정.
- **CPU 추론 타임아웃**: 로그해석(큰 프롬프트) LLM 호출이 300s 초과 → `CONFIG.llm_timeout`
  (env `RAG_LLM_TIMEOUT`, 기본 600s) 신설 + LLM 요청에 `keep_alive:"10m"`(호출간 5.2GB 재적재 회피).
- **BM25 id 타입**: bm25s가 `np.str_` 반환 → 순수 `str` 캐스팅(ChromaDB get/JSON 안전).

### 운영 메모
- 이 서버는 트레이딩 봇과 공유 → qwen3:8b CPU 추론은 전코어 부하. E2E 검증은 1회성으로 완료.
  `ollama serve` 는 `logs/ollama_serve.log`로 상시 기동 중(불필요 시 프로세스 종료 가능).
- 새 서버에서 실행: `RAG_LLM=qwen3:8b RAG_EMBED=bge-m3 RAG_RERANKER=BAAI/bge-reranker-v2-m3`
  (config 기본은 배포 PC 태그 `qwen3_8b_ctx32998`).

### 다음 액션
1. (사용자) `gh auth login` → 개발 브랜치 push.
2. 순수 wheel 오프라인 설치 실측(`pip download --platform win_amd64 --only-binary=:all:`) —
   특히 chromadb/onnxruntime/torch. 실패 시 백업안(sqlite-vec / GGUF 리랭커).
3. Streamlit 실사용 점검(`streamlit run rag/app/main.py`), 하이브리드 파라미터 튜닝, OCR(Phase 3), 패키징.

---

## 2026-07-13 — 2차 증분 구현: 인덱싱·하이브리드검색·리랭커·LLM·로그워크플로우·Streamlit (코드 완료, E2E 대기)

### 한 일 (VPN 서버에서 재개, HANDOFF §4 순서대로)
- **환경**: 새 venv + 결정적 코어 의존성 설치 → 베이스라인 `tests/test_core.py` **12/12 통과** 재확인.
- **`rag/index/`**: `embed.py`(Ollama `/api/embed` urllib 래퍼, 차원검증=nomic 오라벨 조기적발) ·
  `store.py`(ChromaDB 래퍼, upsert/query/get/delete/all_documents, 코사인, 메타 sanitize) ·
  `bm25.py`(kiwipiepy 형태소+bm25s, 정규식 폴백 토크나이저, save/load) ·
  `indexer.py`(**증분 매니페스트** diff + parse→chunk→embed→store, BM25는 Chroma 코퍼스 전체 재구축).
- **`rag/retrieve/`**: `hybrid.py`(**RRF 순수함수** + dense/BM25 융합, BM25전용 후보 store.get 보강,
  where 사후필터) · `rerank.py`(bge-reranker-v2-m3 CrossEncoder, **CPU**).
- **`rag/generate/`**: `prompt.py`(공식체 시스템프롬프트·출처표기·근거없으면 "모른다", 순수) ·
  `llm.py`(Ollama `/api/chat` urllib, 폴백 재시도, `<think>` 제거) · `answer.py`(RAGPipeline + build_pipeline).
- **`rag/logs/workflow.py`**: 통신로그 분석 — 종류판별→파싱→**명세 후보검색(doc_type=protocol_spec)**→
  UI 확인단계용 조각→확정명세 기반 LLM 해석. 컨텍스트 초과 대비 프레임 요약 상한(§7-3).
- **`rag/app/main.py`**: Streamlit 3탭(문서QA / 로그분석[업로드+**필수 확인단계**] / 관리[증분·전체 인덱싱]).
- **테스트**: `tests/test_retrieval.py` 신설 — RRF·증분매니페스트·하이브리드·인덱서(인메모리 페이크)·
  프롬프트·no-context 단락·로그워크플로우 **12/12 통과** (전부 Ollama/Chroma/torch 불필요).
- **`smoke_test.py`**: B단계 E2E(임베딩차원→인덱싱→검색→리랭킹→LLM답변→로그해석) 스크립트 준비.

### 의사결정 (근거)
- **Ollama 격리 = 지연 임포트 + 의존성 주입**: 순수 로직(RRF·매니페스트·프롬프트)을 무거운 의존성 없이
  지금 단위테스트. 임베딩/LLM/리랭커는 얇은 래퍼로 분리. → 코드 24/24 검증을 Ollama 없이 달성.
- **HTTP는 urllib(표준)**: ollama 파이썬 클라이언트 버전 편차/추가 의존성 회피, `ollama_host` 존중.
- **BM25 증분 = 전체 재구축**: 규모 ~100문서라 저렴, incremental add 복잡도·불일치 위험 회피.
  코퍼스 단일 진실원천 = Chroma(문서 저장) → 매 인덱싱마다 `all_documents()`로 재빌드.
- **BM25 where 미지원 → 사후 메타필터**: dense는 네이티브 where, sparse 전용 후보는 조립 후 필터.

### 환경 실측 / 제약
- 이 서버: **CPU 전용(GPU 없음)**, 4코어/15GB RAM, Ollama 미설치. E2E는 정합성 검증 목적(속도 아님).
- CPU에서 qwen3:8b 추론은 전코어 부하 → **같은 VPS의 트레이딩 봇과 자원 경합 우려**(B단계 판단 필요).

### 다음 액션
1. **(B단계, 사용자 승인 대기)** 2차 의존성 설치(chromadb/kiwipiepy/bm25s/ollama/sentence-transformers/
   torch-CPU) + Ollama 설치 + `ollama pull bge-m3 qwen3:8b` → `python3 smoke_test.py` E2E.
   ⚠️ 트레이딩 봇 자원경합 → 실행 시점·강도 사용자 확인 후 진행.
2. 순수 wheel 오프라인 설치 실측(`pip download --platform win_amd64 --only-binary=:all:`).
3. E2E 통과 후: 하이브리드 파라미터 튜닝, OCR(Phase 3), 오프라인 패키징(install.bat/wheelhouse).

---

## 2026-07-09 (7) — 다른 머신(VPN 서버) 이어가기용 인수인계 문서

### 한 일
- `docs/HANDOFF.md` 작성: 저장소 가져오기 → 환경세팅(파이썬/의존성/Ollama+모델 pull) → 코드지도
  → 남은 2차 증분 모듈 계약(index/retrieve/generate/app) → 재개 시 기억할 결정/제약 → 작업규약.
- CLAUDE.md 현재상태에 HANDOFF 포인터 추가.

### 재개 메모
- VPN 서버는 인터넷/LLM 설치 가능 → `ollama pull bge-m3`(1024d 정품)·`qwen3:8b`로 2차 증분 E2E 검증 가능.
- 새 서버 LLM 태그가 다르면 `RAG_LLM`/`RAG_EMBED` 환경변수로 override(config 기본은 qwen3_8b_ctx32998).
- 2차 증분 권장 시작점: RRF(순수 로직, 테스트 가능) → 임베딩/ChromaDB/BM25 인덱서 → 리랭커 → LLM → Streamlit.

---

## 2026-07-09 (6) — MVP 결정적 코어 구현 + 샘플 대조 테스트 통과

### 한 일
- `rag/` 패키지 착수. **결정적(Ollama 불필요) 코어** 구현:
  - `rag/ingest/`: 파서(xlsx 병합셀 fill-forward/다중헤더, docx 순서보존, pptx 슬라이드, **pdf 표추출**,
    txt 인코딩판별), 표 마크다운 직렬화, **표 보존 청킹**(표 단위+헤더 반복, 텍스트 오버랩 윈도우), 메타.
  - `rag/logs/`: **장비별 파싱 프로파일** + HEX/자연어 자동판별 + 바이트 복원 + 프레이밍/체크섬(XOR/CRC16).
- `tests/test_core.py`: dummy_set 대조 **12/12 통과**.
- CLAUDE.md 실행/테스트·코드구조 절 갱신.

### 알게 된 사실 / 결정
- **바이너리(.dat) STX/ETX 프레이밍은 ETX 검색이 아니라 LEN 필드 기반이어야 함**(LEN·DATA에 0x03이
  들어갈 수 있음 — 예: DISPENSE `02 03 14 01 f4 e2 03`). 길이기반 프레이밍으로 수정해 15/15 유효.
- 텍스트 로그는 '라인=1프레임' 가정이 샘플에 부합. 프레이밍/체크섬은 확정 명세에서 오며 감지는 후보 제시용.
- 파서 검증: XM-200 PDF → 요소 12(표 8)·청크 12, HEX 15/15 유효, 자연어 로그 정상 분기.

### 다음 액션 (2차 증분, Ollama 필요 — 사용자 PC E2E)
- 임베딩(bge-m3)+ChromaDB+BM25 하이브리드+RRF+리랭커 → LLM 출처답변 → Streamlit(문서QA/로그분석/관리 탭).
- 로그분석 탭에 **프로토콜 후보 검색 → 확인 단계 → 해석** 흐름 연결.

---

## 2026-07-09 (5) — 검토 피드백 반영(갈림길): 로그 포맷 다양성 + 자연어 로그

### 사용자 피드백에서 나온 갈림길 정보
- **HEX 포맷이 장비별로 조금씩 다름** → 단일 하드코딩 파서 불가. **장비별 파싱 프로파일
  (timestamp/direction/byte_token/separator/framing/checksum/endian) + 자동 감지 + 사용자 확인**으로 설계.
  확정 프로파일은 저장해 재사용.
- **자연어로 표기된 로그도 존재** → "HEX 전용"을 **통신 로그 분석 모드**로 일반화. 업로드 시
  로그 종류(HEX/자연어) 자동 판별 → 자연어 로그는 바이트 파싱 없이 텍스트+명세로 LLM 해석.
- **문서당 표·페이지가 훨씬 많음** → **표 단위 청크 + 페이지 메타** 기본화, 후보 증가로 **리랭커 중요도 상승**.

### 반영
- 설계서 §7 전면 개정(로그 종류 자동판별 7-1 / 장비별 프로파일 파서 7-2 / 고려사항 7-3), §4 대문서 대응 추가.
- 샘플 보강: HEX 변형 3종 추가(`coin_log_space0x.txt` 공백+0x, `sensor_log_tg15.txt` TG-15 방향표시·CRC16,
  `event_log_natural.txt` 자연어) + XM-200 PDF를 **4페이지·표 8개**로 확장(레지스터맵/비트필드/타이밍/NAK/설정).
- 검증: TG-15 CRC16 유효, XM-200 XOR 유효, PDF 4p·표8 추출 확인.

### 다음 액션
- **사용자 최종 승인 대기**(보강 샘플 기준). 승인 시 MVP 파이프라인 착수(파서는 프로파일 기반으로 설계).

---

## 2026-07-09 (4) — 더미 샘플 세트 생성(검토 게이트 대기)

### 한 일
- `samples/generate_samples.py` 작성·실행 → `samples/dummy_set/`에 12개 파일 생성.
  - 프로토콜 명세 2종: XM-200(**PDF**, STX/ETX/XOR), TG-15(**Word**, SOH/CRC16) — 후보 구분/확인단계 테스트용.
  - HEX 로그 4종(.txt/.dat): 타임스탬프±, `[XX]`/`-`구분자/바이너리 — 사용자 제공 포맷 반영, XM-200 규격 준수.
  - 일반 문서: xlsx(병합셀·다중헤더), docx(문단+표+이미지), pptx(표+이미지), txt(UTF-8/CP949).
  - 이미지: 한/영 구성도 PNG(OCR용).
- 검증: HEX 프레임 XOR 체크섬 전부 유효, PDF 한글 텍스트/표 추출 OK(1372자·표3), CP949 자동판별 OK,
  PNG 한글 렌더 확인.
- `samples/MANIFEST.md`(검토 요약)·`samples/requirements-dev.txt`(생성 전용 의존성) 작성.

### 알게 된 사실 / 결정
- 개발 PC 샘플 생성용 라이브러리(openpyxl/python-docx/python-pptx/reportlab/Pillow)는 **개발 전용**,
  오프라인 배포물과 분리. reportlab 내장 한글 CID 폰트(HYSMyeongJo-Medium)로 외부 TTF 없이 PDF 한글 처리.
- HEX 자체 정합성 확보(체크섬 유효) → 추후 파서 E2E 테스트에서 정답 대조 가능.

### 다음 액션 (게이트)
- **사용자 검토 대기**: `samples/MANIFEST.md`의 5개 항목 피드백 → 반영 후 승인 시 MVP 파이프라인 착수.

---

## 2026-07-09 (3) — bge-m3 태그 검증 완료, 정품 재반입 확정

### 새로 알게 된 사실 (검증 결과)
- 오프라인 PC `ollama show bge-m3-FP16.gguf` = **architecture=nomic-bert, 136.73M params,
  embedding length 768, context 2048, F16**. → 기존 `bge-m3-FP16.gguf` 태그는 **nomic 오라벨**로
  확정. 실제 bge-m3(1024d, ~567M)가 아님.

### 의사결정
- **정품 bge-m3 재반입 확정**(사용자 승인). 온라인 PC `ollama pull bge-m3`(1024d, F16 ~1.2GB) →
  USB 이전 → `ollama show`로 1024d 검증. 절차서 `docs/model_transfer.md` 신설.
- 애플리케이션 설정/코드는 **정품 `bge-m3` 태그만 참조**, 오라벨 태그 미사용.
- 메모리 예산: 정품 bge-m3 F16 ~1.2GB 반영 → 질의 GPU ≈ 6.9GB(여전히 8GB 내).

### 다음 액션
1. (사용자) 정품 bge-m3 재반입 후 1024d 검증(형편 될 때). 샘플 단계와 병행 가능.
2. **더미 샘플 세트 생성 → 검토 게이트** 진행.

---

## 2026-07-09 (2) — open_questions 답변 반영, 설계 v0.2

### 새로 알게 된 사실 / 제약
- **PDF가 핵심 포맷으로 추가됨**: 프로토콜 명세가 주로 **Word/PDF(표+텍스트)**. 원 스펙
  (xlsx/docx/pptx/txt/hex)엔 없던 **PDF 파서 필요** → `pdfplumber`(순수 파이썬, MIT, 표 추출 강함) 채택.
- **오프라인 PC 실제 모델(`ollama list`)**: `qwen3_8b_ctx32998`(5.2GB, 32k ctx), `qwen3:8b`(5.2GB),
  `qwen3.5:9`(6.6GB), `qwen3.5:2b`(2.7GB), `deepseek-r1:7b`(4.7GB), `qwen3.5:27b-q4_K_M`(17GB, VRAM초과) 등.
- 🔴 **bge-m3 태그 의심(발견)**: `bge-m3-FP16.gguf:latest`와 `nomic-embed-text:latest`가
  **동일 digest `bddc9fde5061`·274MB**. FP16 bge-m3는 ~1.1GB↑여야 하므로 274MB는 실제 bge-m3가
  아닐 가능성(태그가 nomic을 가리킴). → 검증 필요(open_questions Q1-b).
- 코퍼스 ~100개(1~5MB, 총 ~100~500MB), 초기 잦은 갱신 → 증분 인덱싱 조기 중시.
- 사내망 인바운드 허용, **동시 2~3명**(직렬 처리로 충분).
- HEX 포맷 구체화: 선택적 타임스탬프 + `[XX]` 바이트 토큰(+`-` 구분자), .txt/.dat 등. 프로토콜 문서
  ~50개·문서당 커맨드 10~30개.
- 배포 용량 **제약 없음** → torch/OCR 등 대용량 반입 허용.

### 의사결정 (갈림길과 선택 근거)
- **LLM = qwen3_8b_ctx32998(주) / qwen3.5:2b(폴백)**: 32k 컨텍스트가 HEX 장문·다청크 RAG에 유리,
  5.2GB로 8GB에 적합. 27b(17GB)·coder(부적합)·deepseek-r1(장황) 제외.
- **리랭커 MVP 포함**(사용자 요청): `bge-reranker-v2-m3`를 sentence-transformers CrossEncoder로
  **CPU 실행**(torch CPU wheel) → 질의 시 GPU는 LLM+임베딩 전용 유지. 하드웨어 상향 시 GPU 이동.
- **메모리 예산 재산정**: 질의 GPU ≈ LLM 5.2 + KV 0.5 + 임베딩 0.5~1.2 ≈ **6.2~6.9GB**(여유 확보).
- **답변 톤 = 공식체**, Qwen3 `/no_think`로 간결화.
- **배포 바인딩**: Streamlit `0.0.0.0:8501`(포트 변경 가능).

### 미해결 / 확인 필요
- 🔴 **Q1-b bge-m3 태그 검증**(차원 1024 vs 768, `ollama show`). 실제 nomic이면 정품 bge-m3 재반입.
- chromadb/onnxruntime/torch 순수 wheel 오프라인 설치 실측(구현 첫 단계). 백업안: sqlite-vec, llama-cpp 리랭커.

### 다음 액션
1. (사용자) Q1-b bge-m3 태그 검증 결과 회신.
2. **더미 샘플 세트 생성**(Word/PDF 프로토콜 명세 표 중심 + HEX .txt/.dat) → **검토 게이트**.
3. 승인 시 MVP(파서·인덱싱·하이브리드+리랭커·Streamlit) 착수.

## 2026-07-09 — 설계 단계 착수 및 핵심 스택 확정

### 새로 알게 된 사실 / 제약
- 배포 대상은 **완전 폐쇄망 Windows 11**(RAM 12GB, RTX 3060 Ti VRAM 8GB). 인터넷 설치 불가 →
  모든 라이브러리는 "순수 pip wheel 오프라인 설치 가능"이 1순위 기준.
- 오프라인 PC에 **bge-m3-FP16.gguf 기설치** 확인됨(임베딩 모델로 확정).
- 대상 포맷: xlsx/docx/pptx/txt/hex. **HEX는 지식 인덱싱 대상이 아니라 질의 시 분석 입력물**.
- 실제 사내 자료는 개발 PC에 없음 → 더미 샘플 + **검토 게이트** 절차 필수.

### 의사결정 (갈림길과 선택 근거)
- **UI = Streamlit**: 단일 호스트 다중 사용자 + 순수 wheel + 업로드/확인단계 UI 구현 용이.
- **임베딩 = bge-m3 (FP16 GGUF)**: 오프라인 PC 기설치 + 한국어 검색 강함.
- **벡터 DB = ChromaDB**: 사용자 선택. 메타데이터 필터 편의. 단, **BM25 미내장** →
  하이브리드는 kiwipiepy 토큰화 + 별도 BM25(bm25s/rank_bm25) 인덱스 + RRF 융합으로 구현.
- **대화 로깅 = 자동 Stop 훅 → Markdown**: `.claude/hooks/log_conversation.py`가 트랜스크립트
  JSONL을 읽어 `conversation_log.md`에 원본 append(중복은 uuid로 방지). 훅 동작 검증 완료.
- **메모리 예산 결론**: LLM(7~8B Q4 ~5GB) + bge-m3(~2GB) ≈ 7GB로 8GB 내 동시 상주 가능.
  리랭커는 동시 상주 불가 → MVP 미포함. num_ctx 기본 4096. 필요 시 임베딩 CPU 실행으로 VRAM 회피.

### 미해결 / 확인 필요 (→ docs/open_questions.md)
- **LLM 모델 태그 불확실**("qwen 3.5 9b" 실재 불명) → 7~8B Q4_K_M 확정 권장, `ollama list` 확인 필요.
- 사내망 접속(방화벽/포트), 코퍼스 규모, OCR 방안, 리랭커 시점, HEX 특성, 배포 용량 → 질문 목록 참조.
- chromadb/onnxruntime 등 네이티브 wheel의 실제 오프라인 설치 가능 여부는 구현 첫 단계에서
  `pip download`로 실측 필요. 실패 시 백업안 = sqlite-vec.

### 다음 액션
1. 사용자에게 `docs/open_questions.md` 답변 요청.
2. 답변 반영 후 **더미 샘플 세트 생성 → 검토 게이트**(사용자 승인).
3. 승인 시 MVP(텍스트+표 QA) 구현 착수.

## 2026-07-22 — 웹 UI(Starlette+HTMX) 신설: Streamlit 대체 착수

### 배경 / 결정
- 사용자 피드백: Streamlit UI가 "별로 안이뻐" → 깔끔한 대안 요청. 목업 비교 후 **Starlette+HTMX+Tailwind**
  채택. 사용자 결정: **신규 UI로 전환**(나머지 기능 이식 후 Streamlit 폐기 예정, 그전까지 폴백 유지).
- 같은 백엔드(rag.chat/engine·logchat, rag.index, rag.feedback)를 **그대로 재사용**. 화면 계층만 신규.
  포트 8502(Streamlit 8501과 병행). 정적자산(htmx.min.js·tailwind.js) 저장소 동봉 → CDN/인터넷 불필요(폐쇄망 OK).
- 복사=execCommand 폴백, 이미지 붙여넣기=paste 이벤트 → **HTTPS 불필요, HTTP에서 동작** 확인.

### 산출물 (rag/webui/)
- `app.py` — Starlette 라우트: 로그인/대화전환, `/chat`(멀티턴 RAG, 스코프 반영), `/scope/*`(문서범위 트리),
  `/log/*`(로그 첨부·파싱·분리), `/feedback/*`(개선기록 폼·저장·목록·MD반출·이미지), `/admin/*`(업로드·재인덱싱), `/preview`.
- `scopetree.py` — 폴더/파일 체크박스 트리(HTMX). 선택의 진짜 상태=파일집합, 폴더체크는 렌더시 재계산(하위전체 동기화).
- `htmlpreview.py` — 근거 원본 미리보기 HTML(xlsx 시트탭/pdf 페이지이미지/docx·pptx/txt).
- `templates/`(base·_sidebar·chat·login·_user_msg·_assistant_msg·_logpanel·_fbform·feedback·admin·_admin_main·_modal),
  `static/`(htmx.min.js 50KB·tailwind.js 451KB·logo.png·app.js).
- `packaging/start_webui.ps1` — 서버A 실행 스크립트(8502, Streamlit과 병행). requirements(.in/.txt)에 순수 wheel 4종 추가.

### 검증 (Playwright + TestClient)
- 로그인→사이드바(로고·3메뉴·대화목록)→ChatGPT풍 말풍선, 인라인 `[N]` 인용 클릭→미리보기 모달(PDF 페이지 이미지).
- 스코프 트리 폴더 동기화: 폴더체크→하위 4개 선택(체크 5), 파일1 해제→폴더 해제·"선택 3개". 정상.
- 개선기록 모달 저장→개선기록 페이지 반영, 관리 업로드폼/폴더선택/문서목록/재인덱싱 라우트 정상.
- 실 LLM 답변 경로는 Streamlit과 동일 engine.answer 재사용(가짜 파이프라인으로 배선 확정; CPU라 느릴 뿐).

### 다음 액션
- 서버 A(배포)에서 8502 실측 후 Streamlit(rag/app) 최종 폐기 여부 확정. 그 전까지 두 UI 병행.
- 오프라인 wheelhouse 빌드 시 starlette/uvicorn/python-multipart win_amd64 wheel 포함 확인(전부 순수 파이썬).
