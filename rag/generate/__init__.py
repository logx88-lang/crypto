"""답변 생성 계층 — 프롬프트 조립 + LLM(Ollama) + RAG 파이프라인."""
from .prompt import (build_messages, build_context, source_label, sources_list,
                     SYSTEM_PROMPT, NO_CONTEXT_ANSWER)
from .llm import LLMClient, LLMError
from .answer import RAGPipeline, build_pipeline

__all__ = [
    "build_messages", "build_context", "source_label", "sources_list",
    "SYSTEM_PROMPT", "NO_CONTEXT_ANSWER", "LLMClient", "LLMError",
    "RAGPipeline", "build_pipeline",
]
