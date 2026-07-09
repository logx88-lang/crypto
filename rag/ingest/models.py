"""인제스천 데이터 모델 — Element(추출 단위) / ParsedDoc / Chunk(인덱싱 단위)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Element:
    """문서에서 등장 순서대로 추출한 단위.

    kind: 'text' | 'table' | 'image'
    text: 정규화 텍스트 (표는 마크다운 직렬화 문자열)
    location: 위치 메타 (page_no / sheet_name / slide_no / section 등)
    """
    kind: str
    text: str
    location: dict = field(default_factory=dict)


@dataclass
class ParsedDoc:
    source_file: str          # 원본 파일 경로/이름
    doc_title: str
    doc_type: str             # 'protocol_spec' | 'general'
    ext: str                  # 확장자 (소문자, 점 제외)
    elements: list = field(default_factory=list)   # list[Element]


@dataclass
class Chunk:
    text: str
    metadata: dict = field(default_factory=dict)

    @property
    def chunk_id(self) -> str:
        return self.metadata.get("chunk_id", "")


def content_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def make_chunk(text: str, *, source_file: str, doc_title: str, doc_type: str,
               kind: str, location: dict, index: int) -> Chunk:
    """일관된 메타데이터로 Chunk 생성."""
    ch = content_hash(text)
    loc_tag = "-".join(f"{k}{v}" for k, v in sorted(location.items()) if v not in (None, ""))
    meta = {
        "source_file": source_file,
        "doc_title": doc_title,
        "doc_type": doc_type,
        "kind": kind,                 # 'text' | 'table'
        "chunk_id": f"{source_file}::{loc_tag}::{index}::{ch}",
        "content_hash": ch,
    }
    # 위치 메타 병합 (page_no/sheet_name/slide_no/section)
    for k, v in location.items():
        if v not in (None, ""):
            meta[k] = v
    return Chunk(text=text, metadata=meta)
