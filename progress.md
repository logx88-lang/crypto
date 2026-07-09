# progress.md — 진행 로그 / 지식·의사결정 기록

> 규칙: **변경마다** (1) 새로 알게 된 사실·제약, (2) 의사결정 갈림길과 선택·근거,
> (3) 다음 액션을 아래에 append 하고 git push 한다. 최신 항목이 위로 오도록 역순 기록.

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
