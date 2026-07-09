"""전역 설정 — 경로, 모델 태그, 청킹/검색 파라미터.

오프라인 배포 전제: 모델 태그는 배포 PC의 Ollama에 존재해야 한다(docs/model_transfer.md).
값은 환경변수로 덮어쓸 수 있다(배포 PC에서 조정 용이).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


@dataclass
class Config:
    # --- 모델 (Ollama 태그) ---
    llm_model: str = _env("RAG_LLM", "qwen3_8b_ctx32998")        # 주 LLM (8B·32k ctx)
    llm_fallback: str = _env("RAG_LLM_FALLBACK", "qwen3.5:2b")   # 경량 폴백
    embed_model: str = _env("RAG_EMBED", "bge-m3")               # 정품 bge-m3 (1024d) — 재반입 확정
    embed_dim: int = int(_env("RAG_EMBED_DIM", "1024"))
    reranker_path: str = _env("RAG_RERANKER", "bge-reranker-v2-m3")  # 로컬 경로/모델명 (CPU)
    ollama_host: str = _env("OLLAMA_HOST", "http://localhost:11434")
    num_ctx: int = int(_env("RAG_NUM_CTX", "4096"))

    # --- 청킹 (토큰 근사는 문자 기반; 실제 임베딩은 bge-m3 토크나이저) ---
    chunk_chars: int = int(_env("RAG_CHUNK_CHARS", "1200"))   # ~500-700 토큰 근사
    chunk_overlap: int = int(_env("RAG_CHUNK_OVERLAP", "180"))  # ~15%
    table_max_chars: int = int(_env("RAG_TABLE_MAX_CHARS", "2400"))  # 표 청크 상한(초과 시 행 분할)

    # --- 검색 ---
    top_k_dense: int = 20
    top_k_bm25: int = 20
    rrf_k: int = 60
    rerank_top_n: int = 20   # 리랭커 입력 후보 수
    final_k: int = 5         # 최종 컨텍스트 청크 수

    # --- 경로 ---
    data_dir: str = _env("RAG_DATA_DIR", "data")          # 인덱싱 대상 문서 폴더
    chroma_dir: str = _env("RAG_CHROMA_DIR", "data/chroma")
    bm25_path: str = _env("RAG_BM25_PATH", "data/bm25.pkl")
    manifest_path: str = _env("RAG_MANIFEST", "data/manifest.json")

    # --- 문서 유형 분류 힌트 ---
    protocol_keywords: tuple = (
        "프로토콜", "명세", "통신 규격", "패킷", "packet", "protocol", "command code",
        "명령 코드", "프레임", "frame",
    )


CONFIG = Config()
