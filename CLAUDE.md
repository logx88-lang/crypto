# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

한국어+영어 혼용 사내 문서(xlsx/docx/pptx/txt, 표·이미지 포함)를 로컬 LLM(Ollama) 기반 RAG로
검색·질의응답하고, 추가로 **HEX 통신 로그를 업로드해 프로토콜 명세 기반으로 분석**하는
사내 지식 공유 플랫폼이다.

**개발/배포 환경이 분리되어 있다 — 모든 설계 결정의 최상위 제약:**
- **개발 PC (현재 환경)**: 설계·개발·테스트·오프라인 패키징 수행. **실제 사내 자료는 없다.**
- **배포 PC (폐쇄망)**: 인터넷 완전 차단. `pip install`/`ollama pull`/모델 다운로드 전부 불가.
  Windows 11, RAM 12GB, RTX 3060 Ti(VRAM 8GB), Python 3.10~3.12, Ollama 기설치(bge-m3-FP16 포함).
  산출물은 USB 등 물리 매체로만 이동한다.

> "설치 시 인터넷이 필요한" 방식은 전부 실패다. 라이브러리는 **Windows + Python 3.10~3.12 +
> 순수 pip wheel 오프라인 설치 가능**을 1순위로 검증한다. **12GB RAM / 8GB VRAM에서 확실히 도는
> 구성**을 이론상 우수한 구성보다 우선한다.

## 현재 상태

**MVP 1차(결정적 코어) 완료 · 2차 증분(Ollama 연동) 대기.** 주요 문서:
- `docs/HANDOFF.md` — **다른 머신에서 이어서 진행하기 위한 인수인계**(환경세팅·모델준비·남은작업). 재개 시 먼저 읽기.
- `docs/design.md` — 상세 설계서(스펙 11항목 대응). **작업 전 반드시 숙지.**
- `docs/open_questions.md` — 사용자 답변 대기 중인 확인 질문.
- `progress.md` — 진행/지식/의사결정 로그. **변경마다 갱신 + push.**
- `conversation_log.md` — 대화 원본 자동 누적(훅이 기록, 수동 편집 금지).
- `.claude/` — 대화 자동 로깅 훅.

**진행 게이트(반드시 준수):** 실제 코드 구현은 (a) `open_questions.md` 답변 반영 + (b) 더미 샘플
세트 **검토 게이트 승인** 이후에만 착수한다. 승인 전 파이프라인 세부 구현을 확정하지 말 것.

## 확정된 스택

| 구성요소 | 선택 |
|---|---|
| 웹 UI | Streamlit (단일 호스트 다중 사용자 2~3명, `0.0.0.0:8501`) |
| LLM | qwen3_8b_ctx32998 (주, 8B·32k ctx) / qwen3.5:2b (폴백) via Ollama |
| 임베딩 | bge-m3 (1024d) via Ollama — **정품 재반입 확정**(기존 태그는 nomic 오라벨, `docs/model_transfer.md`) |
| 리랭커 | bge-reranker-v2-m3 (sentence-transformers CrossEncoder, **CPU**) — MVP 포함 |
| 벡터 DB | ChromaDB (BM25 미내장 → kiwipiepy + bm25s 별도 인덱스 + RRF 융합) |
| 문서 파서 | openpyxl / python-docx / python-pptx / **pdfplumber** / charset-normalizer |
| 한국어 형태소 | kiwipiepy |

> 대상 포맷: **xlsx · docx · pptx · pdf · txt · hex**(+이미지 OCR). PDF는 프로토콜 명세 주 포맷.

## 아키텍처 (예정 모듈 구조)

인제스천(포맷별 파서 → 정규화+메타 → 청킹) → 인덱싱(bge-m3 임베딩 → ChromaDB + BM25) →
질의(하이브리드 검색 + RRF → (선택)리랭커 → 컨텍스트 조립 → LLM 출처 답변) → Streamlit UI.
HEX 모드는 별도 분기(후보 검색 → **UI 확인 단계 필수** → 확정 명세 기반 해석). 상세는 `docs/design.md`.

예정 디렉터리: `ingest/ index/ retrieve/ generate/ hex/ app/ packaging/`.

## 규약 / 컨벤션

- **오프라인 우선**: 새 의존성 추가 시 순수 wheel 여부를 먼저 확인하고 `requirements.in`에 근거를 남긴다.
  컴파일 필요 패키지는 배제하거나 대안을 제시한다.
- **메모리 예산 준수**: 질의 시 동시 상주 모델의 VRAM 합이 8GB를 넘지 않게 설계(§design.md 2).
- **출처 표기 필수**: 답변은 한국어로, 근거 문서·위치(시트/슬라이드/페이지)를 표기하고 근거 없으면 모른다고 답한다.
- **HEX 자동 추측 금지**: 프로토콜 명세는 사용자 확인 단계를 거친 뒤에만 해석에 사용한다.
- **더미 샘플만 사용**: 테스트 데이터는 직접 생성한 더미 샘플이며, 검토 게이트 승인 후 사용한다.

## 코드 구조 (진행 중)

- `rag/` — 애플리케이션 패키지.
  - `rag/ingest/` — 포맷별 파서(`parsers.py`)·표 직렬화(`tables.py`)·표 보존 청킹(`chunker.py`)·모델(`models.py`). **결정적, Ollama 불필요.**
  - `rag/logs/` — 통신 로그 분석: 장비별 파싱 프로파일(`profiles.py`)·HEX/자연어 감지(`detect.py`)·바이트 복원+체크섬(`parser.py`).
  - `rag/config.py` — 모델 태그·청킹/검색 파라미터(환경변수로 덮어쓰기).
  - `rag/index /retrieve /generate /app` — 2차 증분(Ollama 필요, 미구현).
- `samples/` — 더미 샘플 생성기(`generate_samples.py`)·산출물(`dummy_set/`)·검토요약(`MANIFEST.md`).
- `tests/test_core.py` — 결정적 코어를 `dummy_set` 샘플로 대조 검증.

## 실행 / 테스트

개발 환경 의존성(파서 실행용): `pip install openpyxl python-docx python-pptx pdfplumber charset-normalizer`
(오프라인 배포는 `requirements.in` → wheelhouse. §design 10)

- **결정적 코어 테스트**(Ollama 불필요): `python3 tests/test_core.py`
  - 단일 테스트: `python3 -c "import tests.test_core as t; t.test_xm200_bracket_all_valid()"`
- **더미 샘플 재생성**: `python3 samples/generate_samples.py`
- 인덱싱/질의/Streamlit 실행(`streamlit run ...`)·smoke test는 2차 증분(Ollama 연동) 착수 시 기록한다.

## Git 워크플로우

- 기본 브랜치: `main`. 개발 브랜치: `claude/claude-md-docs-xtu1qe` (여기서 개발·커밋·push).
- `git push -u origin <branch-name>`. PR은 명시 요청 시에만.
- `progress.md`와 `conversation_log.md`는 의미 있는 변경 시 함께 커밋·push 한다.
