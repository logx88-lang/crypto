# 프로젝트 이어가기 (Handoff) — VPN 서버(Ollama 설치 가능)에서 재개

> 이 문서 하나로 다른 머신에서 프로젝트를 이어서 진행할 수 있도록 정리했다.
> 정본 문서: 설계 `docs/design.md` · 진행로그 `progress.md` · 규약 `CLAUDE.md` ·
> 모델이전 `docs/model_transfer.md` · 샘플요약 `samples/MANIFEST.md` · 남은질문 `docs/open_questions.md`.

---

## 0. 30초 요약 (지금 어디까지 왔나)

- **설계 확정**: 오프라인 한/영 RAG + 통신 로그 분석 플랫폼. 스택·메모리예산·패키징 전략 문서화 완료.
- **더미 샘플 세트 완료**: 프로토콜 명세(PDF/Word) + HEX/자연어 로그(여러 포맷) + 일반문서 + 이미지.
- **MVP 1차(결정적 코어) 완료 + 테스트 12/12 통과** — 파서·표보존 청킹·통신로그 분석(Ollama 불필요).
- **남은 일 = 2차 증분(Ollama 필요)**: 임베딩·ChromaDB·BM25·RRF·리랭커·LLM 답변·Streamlit UI.
- VPN 서버는 인터넷/LLM 설치가 가능하므로 **여기서 2차 증분을 실제로 E2E 검증**할 수 있다.

---

## 1. 저장소 가져오기

```bash
git clone <REPO_URL> crypto && cd crypto
git checkout claude/claude-md-docs-xtu1qe     # 개발 브랜치 (모든 작업이 여기 있음)
python3 tests/test_core.py                    # (의존성 설치 후) 12/12 통과 확인
```
- 기본 브랜치 `main`, 개발 브랜치 `claude/claude-md-docs-xtu1qe`.
- Claude Code로 열면 `.claude/` 훅이 대화를 `conversation_log.md`에 계속 자동 기록한다.

---

## 2. 환경 세팅 (VPN 서버)

### 2-1. 파이썬 + 결정적 코어 의존성 (지금 코드 실행/테스트용)
```bash
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install openpyxl python-docx python-pptx pdfplumber charset-normalizer
python3 tests/test_core.py         # 파서·청킹·로그 코어 검증
python3 samples/generate_samples.py  # (선택) 샘플 재생성 — 추가로 reportlab Pillow 필요
```

### 2-2. 2차 증분 의존성 (Ollama 연동)
```bash
pip install chromadb kiwipiepy bm25s ollama sentence-transformers transformers torch
```
> 주의: 여기서는 개발 편의로 그냥 설치한다. **오프라인 배포용 wheelhouse는 별도**로
> `requirements.in` 기준 `pip download --platform win_amd64 --only-binary=:all:` 로 만든다(§design 10).

### 2-3. Ollama + 모델 준비
```bash
# Ollama 설치 후 (https://ollama.com), 서버 기동: ollama serve
ollama pull bge-m3        # 임베딩 1024d (정품). ollama show bge-m3 → embedding length 1024 확인
ollama pull qwen3:8b      # LLM (기본). 배포 PC의 qwen3_8b_ctx32998 는 커스텀 32k Modelfile 태그
```
- **LLM 태그 다를 때**: 코드는 `rag/config.py` 기본값 `qwen3_8b_ctx32998` 를 쓴다. 새 서버에서
  `qwen3:8b` 를 쓰려면 환경변수로 덮어쓴다:
  ```bash
  export RAG_LLM=qwen3:8b        # Windows: set RAG_LLM=qwen3:8b
  export RAG_EMBED=bge-m3
  ```
- **리랭커**: `bge-reranker-v2-m3` 는 sentence-transformers가 온라인에서 받아온다(최초 1회). CPU 실행 기본.
- 32k 컨텍스트가 필요하면 배포 PC와 동일하게 Modelfile로 재생성(`docs/model_transfer.md` 참고).

### 2-4. 첫 스모크 체크(권장)
```bash
python3 -c "import ollama; print(len(ollama.embeddings(model='bge-m3', prompt='테스트')['embedding']))"
# → 1024 가 나와야 정상 (768이면 nomic — bge-m3 재확인)
```

---

## 3. 지금까지 만들어진 것 (코드 지도)

```
rag/
  config.py            # 모델태그·청킹/검색 파라미터 (환경변수 override)
  ingest/
    models.py          # Element / ParsedDoc / Chunk / make_chunk
    tables.py          # 표 → 마크다운 직렬화
    parsers.py         # parse_file(): xlsx/docx/pptx/pdf/txt (순서보존·표추출·인코딩판별·doc_type)
    chunker.py         # chunk_document(): 표 보존 청킹 + 텍스트 오버랩 윈도우
  logs/
    profiles.py        # ParsingProfile + 내장 프로파일(xm200/tg15/generic)
    detect.py          # detect_log_type(hex/자연어), detect_profile(토큰/타임스탬프/방향/프레이밍 추정)
    parser.py          # reconstruct_bytes / verify_frame(XOR·CRC16) / analyze_text_log / analyze_binary_log
  index/ retrieve/ generate/ app/   # ← 아직 없음(2차 증분에서 생성)
samples/
  generate_samples.py  # 더미 샘플 생성기(재현 가능)
  dummy_set/           # protocol/ hex/ docs/ images/
  MANIFEST.md          # 검토 요약
tests/test_core.py     # dummy_set 대조 12/12
```

**핵심 인터페이스 (2차 증분에서 재사용)**
- `parse_file(path) -> ParsedDoc` → `chunk_document(doc) -> list[Chunk]`
  - `Chunk.text`, `Chunk.metadata`(source_file/doc_title/doc_type/kind/page_no|sheet_name|slide_no/section/chunk_id/content_hash)
- `analyze_text_log(text, profile=None) -> {log_type, profile, frames|lines, valid_count, total}`
- `analyze_binary_log(data, profile) -> {...}` (LEN 기반 프레이밍)

---

## 4. 남은 작업 — 2차 증분 (Ollama 필요, 여기서 E2E 검증)

권장 순서와 각 모듈의 계약(설계 §1·§5·§6·§7 근거):

### (1) `rag/index/` — 인덱싱
- `embed.py`: `EmbeddingClient.embed(texts)->list[vec]` (Ollama `/api/embeddings`, model=CONFIG.embed_model,
  배치, 차원=CONFIG.embed_dim 검증). 인제스천은 배치, 질의는 단건.
- `store.py`: ChromaDB `PersistentClient(CONFIG.chroma_dir)` 래퍼 — add/query/delete, `where={"doc_type":...}` 필터.
- `bm25.py`: `kiwipiepy` 형태소 토큰화 + `bm25s` 인덱스(저장/로드). 영어는 소문자 정규화 병행.
- `indexer.py`: 폴더 스캔 → parse → chunk → (embed+store) + bm25 색인. **증분**: `manifest.json`에
  `{source_file:{content_hash,mtime,chunk_ids}}` 유지, 변경/삭제 반영(§design 9).

### (2) `rag/retrieve/` — 하이브리드 검색
- `hybrid.py`: dense(top_k_dense) + bm25(top_k_bm25) → **RRF**(rrf_k=60) 융합 → 후보. (RRF는 순수 로직,
  Ollama 없이도 단위테스트 가능 → 먼저 테스트 작성 권장.)
- `rerank.py`: `sentence-transformers` CrossEncoder(`bge-reranker-v2-m3`, **CPU**)로 rerank_top_n→final_k 재정렬.

### (3) `rag/generate/` — 답변 생성
- `prompt.py`: 시스템 프롬프트(한국어 **공식체**, 컨텍스트 근거 있을 때만, **출처 표기**, 근거 없으면
  "제공된 문서에서 근거를 찾지 못했습니다", Qwen3 `/no_think`).
- `llm.py`: Ollama chat(model=CONFIG.llm_model, num_ctx=CONFIG.num_ctx). 폴백 llm_fallback.
- `answer.py`: retrieve→rerank→컨텍스트 조립(출처 메타)→LLM→답변+근거목록.

### (4) 통신 로그 분석 워크플로우 (§design 7)
- 업로드 로그 → `detect_log_type`.
  - hex: `detect_profile` → 후보 명세 검색(`doc_type=protocol_spec` 필터) → **UI 확인 단계** →
    확정 명세 프레이밍/명령표로 `analyze_*` 해석 → LLM 설명.
  - 자연어: 텍스트+확정 명세를 컨텍스트로 LLM 해석(바이트 파싱 없음).
- 컨텍스트 초과 시 프레임/구간 분할(§7-3).

### (5) `rag/app/` — Streamlit UI
- 3탭: **문서 QA** / **로그 분석**(업로드+확인단계) / **관리**(인덱싱·재인덱싱).
- `streamlit run rag/app/main.py --server.address 0.0.0.0 --server.port 8501` (사내 2~3명).

### (6) 오프라인 패키징 (§design 10)
- `requirements.in` 확정 → wheelhouse, `install.bat/ps1`, `smoke_test.py`, 모델 이전 가이드.

---

## 5. 재개 시 꼭 기억할 결정/제약 (재논의 불필요)

- **오프라인 배포가 최상위 제약**: 새 의존성은 순수 wheel 여부 먼저 확인, `requirements.in`에 근거 기록.
- **메모리 예산**: 질의 시 GPU ≈ LLM 5.2 + KV 0.5 + bge-m3 1.2 ≈ 6.9GB(<8GB). **리랭커는 CPU**.
- **확정 스택**: Streamlit / bge-m3(1024d) / ChromaDB(+BM25 별도) / Ollama(qwen3 8B) / kiwipiepy / pdfplumber.
- **HEX 자동 추측 금지**: 프로토콜은 **UI 확인 단계** 후에만 해석. 포맷은 **장비별 프로파일**(하드코딩 금지).
- **자연어 로그**도 처리(로그 분석 = hex + 자연어).
- **더미 샘플만 사용**, 실제 자료 없음. 문서당 표·페이지 많음 → 표 단위 청크·리랭커 중요.
- **bge-m3 태그 주의**: 배포 PC의 `bge-m3-FP16.gguf` 는 nomic(768d) 오라벨 → 정품 재반입 확정
  (VPN 서버에서는 `ollama pull bge-m3`로 1024d 정품 사용).

## 6. 남은 확인 항목
- 배포 PC 정품 bge-m3 재반입(사용자 별도 진행 중) — `docs/model_transfer.md`.
- HEX 실제 포맷은 장비별로 더 다양할 수 있음 → 새 포맷 발견 시 `rag/logs/profiles.py`에 프로파일 추가.

## 7. 작업 규약 (계속)
- 의미 있는 변경마다 `progress.md`에 (사실/결정/다음액션) append + git push.
- `conversation_log.md`는 훅이 자동 기록(수동 편집 금지).
- 개발·커밋·push는 `claude/claude-md-docs-xtu1qe` 브랜치. PR은 명시 요청 시에만.
```bash
git add -A && git commit -m "..." && git push -u origin claude/claude-md-docs-xtu1qe
```
