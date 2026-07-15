"""인덱서 — 폴더 스캔 → parse → chunk → (embed+store) + BM25 재구축 (design.md §9).

증분 인덱싱: 매니페스트 `{source_file: {content_hash, mtime, chunk_ids[]}}` 유지.
- 파일 해시 변경분만 재처리, 삭제 파일 청크 제거.
- BM25는 Chroma 코퍼스 전체에서 재구축(증분 add 복잡도 회피, 규모 ~100문서라 저렴).
- embed/store/bm25 는 주입 가능 → 순수 로직(diff_manifest) 단독 테스트 가능.
"""
from __future__ import annotations

import hashlib
import json
import os

from ..config import CONFIG
from ..ingest import parse_file, chunk_document, SUPPORTED_EXTS


# ---------------------------------------------------------------------------
# 순수 로직 (Ollama 불필요, 단위 테스트 대상)
# ---------------------------------------------------------------------------
def diff_manifest(old_manifest: dict, current: dict) -> tuple:
    """(to_index, to_delete). current: {source_file: {content_hash, mtime}}.

    - to_index: 신규 또는 content_hash 변경 파일.
    - to_delete: old 에 있으나 current 에 없는(삭제된) 파일.
    """
    to_index, to_delete = [], []
    for sf, meta in current.items():
        old = old_manifest.get(sf)
        if old is None or old.get("content_hash") != meta["content_hash"]:
            to_index.append(sf)
    for sf in old_manifest:
        if sf not in current:
            to_delete.append(sf)
    return to_index, to_delete


def list_documents(data_dir: str = None) -> list:
    """인덱싱 대상 문서(상대경로) 목록 — 예약폴더(chroma/feedback) 제외."""
    from ..ingest import SUPPORTED_EXTS
    data_dir = data_dir or CONFIG.data_dir
    reserved = {os.path.basename(CONFIG.chroma_dir), os.path.basename(CONFIG.feedback_dir)}
    out = []
    if os.path.isdir(data_dir):
        for root, dirs, files in os.walk(data_dir):
            dirs[:] = [d for d in dirs if d not in reserved]
            for f in files:
                if "." in f and f.rsplit(".", 1)[-1].lower() in SUPPORTED_EXTS:
                    rel = os.path.relpath(os.path.join(root, f), data_dir)
                    out.append(rel.replace("\\", "/"))
    return sorted(out)


def top_folder(rel_path: str) -> str:
    """data_dir 기준 상대경로 → 최상위 폴더명(하위폴더 없으면 '미분류')."""
    parts = rel_path.replace("\\", "/").split("/")
    return parts[0] if len(parts) > 1 else "미분류"


def _file_fingerprint(path: str) -> dict:
    with open(path, "rb") as f:
        data = f.read()
    return {"content_hash": hashlib.sha1(data).hexdigest()[:16],
            "mtime": os.path.getmtime(path)}


# ---------------------------------------------------------------------------
# 오케스트레이션
# ---------------------------------------------------------------------------
class Indexer:
    def __init__(self, embed_client=None, store=None, bm25=None,
                 data_dir: str = None, manifest_path: str = None, batch: int = 32):
        self.embed = embed_client
        self.store = store
        self.bm25 = bm25
        self.data_dir = data_dir or CONFIG.data_dir
        self.manifest_path = manifest_path or CONFIG.manifest_path
        self.batch = batch

    # --- 지연 생성 (주입 안 됐을 때만) ---
    def _ensure_clients(self):
        if self.embed is None:
            from .embed import EmbeddingClient
            self.embed = EmbeddingClient()
        if self.store is None:
            from .store import VectorStore
            self.store = VectorStore()
        if self.bm25 is None:
            from .bm25 import BM25Index
            self.bm25 = BM25Index()

    def _load_manifest(self) -> dict:
        if os.path.exists(self.manifest_path):
            with open(self.manifest_path, encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_manifest(self, manifest: dict) -> None:
        os.makedirs(os.path.dirname(self.manifest_path) or ".", exist_ok=True)
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    def _scan(self) -> dict:
        reserved = {os.path.basename(CONFIG.chroma_dir), os.path.basename(CONFIG.feedback_dir)}
        current = {}
        for root, dirs, files in os.walk(self.data_dir):
            dirs[:] = [d for d in dirs if d not in reserved]   # 인덱스/피드백 산출물 제외
            for name in files:
                ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                if ext not in SUPPORTED_EXTS:
                    continue
                path = os.path.join(root, name)
                rel = os.path.relpath(path, self.data_dir)
                current[rel] = _file_fingerprint(path)
        return current

    def _embed_batched(self, texts) -> list:
        vecs = []
        for i in range(0, len(texts), self.batch):
            vecs.extend(self.embed.embed(texts[i:i + self.batch]))
        return vecs

    def reindex(self, full: bool = False) -> dict:
        """증분(기본) 또는 전체(full=True) 인덱싱. 통계 dict 반환."""
        self._ensure_clients()
        manifest = {} if full else self._load_manifest()
        if full:
            # 전체 재인덱싱: 기존 컬렉션 비우기
            ids, _ = self.store.all_documents()
            if ids:
                self.store.delete(ids=ids)
        current = self._scan()
        to_index, to_delete = diff_manifest(manifest, current)

        stats = {"indexed": 0, "deleted": 0, "chunks": 0, "skipped": 0}

        # 삭제 + 변경 파일의 옛 청크 제거
        for sf in to_delete + [s for s in to_index if s in manifest]:
            old_ids = manifest.get(sf, {}).get("chunk_ids", [])
            if old_ids:
                self.store.delete(ids=old_ids)
            if sf in to_delete:
                manifest.pop(sf, None)
                stats["deleted"] += 1

        # 신규/변경 파일 인덱싱
        for sf in to_index:
            path = os.path.join(self.data_dir, sf)
            doc = parse_file(path)
            chunks = chunk_document(doc)
            if not chunks:
                manifest[sf] = {**current[sf], "chunk_ids": []}
                stats["skipped"] += 1
                continue
            folder = top_folder(sf)                 # 최상위 폴더(간단 필터용)
            rel = sf.replace("\\", "/")             # 전체 상대경로(폴더 트리·파일 필터용)
            for c in chunks:
                c.metadata["folder"] = folder
                c.metadata["rel_path"] = rel
            texts = [c.text for c in chunks]
            ids = [c.metadata["chunk_id"] for c in chunks]
            vecs = self._embed_batched(texts)
            self.store.add(ids=ids, embeddings=vecs, documents=texts,
                           metadatas=[c.metadata for c in chunks])
            manifest[sf] = {**current[sf], "chunk_ids": ids}
            stats["indexed"] += 1
            stats["chunks"] += len(chunks)

        # BM25 전체 재구축 (코퍼스 = Chroma 전체)
        all_ids, all_docs = self.store.all_documents()
        self.bm25.build(all_ids, all_docs)
        self.bm25.save()

        self._save_manifest(manifest)
        stats["total_chunks"] = len(all_ids)
        return stats
