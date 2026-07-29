"""사내 지식 공유 RAG 플랫폼 (오프라인 배포 대상).

모듈 구조:
  rag.ingest   — 포맷별 파서 + 표 보존 청킹 (결정적, Ollama 불필요)
  rag.logs     — 통신 로그 분석(HEX/자연어 판별, 장비별 프로파일 파서)
  rag.index    — 임베딩·ChromaDB·BM25 (Ollama 필요, 2차 증분)
  rag.retrieve — 하이브리드 검색·RRF·리랭커 (2차 증분)
  rag.generate — 프롬프트·LLM 답변 (2차 증분)
  rag.app      — Streamlit UI (2차 증분)

상세 설계: docs/design.md
"""
__version__ = "0.1.0-dev"
