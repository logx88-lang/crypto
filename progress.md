# progress.md — 진행 로그 / 지식·의사결정 기록

> 규칙: **변경마다** (1) 새로 알게 된 사실·제약, (2) 의사결정 갈림길과 선택·근거,
> (3) 다음 액션을 아래에 append 하고 git push 한다. 최신 항목이 위로 오도록 역순 기록.

---

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
