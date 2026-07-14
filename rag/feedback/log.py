"""개선기록 저장/조회/내보내기 — 저장 시점에 이미 비식별화된 레코드만 기록.

- 저장: JSONL(`feedback_dir/feedback.jsonl`). **비식별화된 레코드만** 들어가므로 파일 자체가 안전.
- 내보내기: 사람이 읽는 Markdown(`feedback_export.md`) — 이 파일을 USB로 반출.
- 원본(실데이터)은 이 계층에 절대 들어오지 않는다(app이 sanitize_record 후 호출).
"""
from __future__ import annotations

import json
import os

from ..config import CONFIG
from .sanitize import sanitize_record


class FeedbackLog:
    def __init__(self, path: str = None):
        self.dir = path or CONFIG.feedback_dir
        self.jsonl = os.path.join(self.dir, "feedback.jsonl")

    def add(self, record: dict, already_sanitized: bool = False,
            image_bytes: bytes = None, image_ext: str = "png") -> dict:
        """레코드 추가. 기본은 방어적으로 재-비식별화(app이 안 했더라도 안전 보장).

        image_bytes 있으면 images/ 에 저장하고 레코드에 상대경로(image)를 남긴다.
        """
        safe = record if already_sanitized else sanitize_record(record)
        os.makedirs(self.dir, exist_ok=True)
        if image_bytes:
            n = self.count() + 1
            slug = str(safe.get("ts", "img")).replace(":", "").replace(" ", "_").replace("-", "")
            rel = os.path.join("images", f"{slug}_{n}.{image_ext}")
            os.makedirs(os.path.join(self.dir, "images"), exist_ok=True)
            with open(os.path.join(self.dir, rel), "wb") as f:
                f.write(image_bytes)
            safe["image"] = rel.replace("\\", "/")
        with open(self.jsonl, "a", encoding="utf-8") as f:
            f.write(json.dumps(safe, ensure_ascii=False) + "\n")
        return safe

    def load_all(self) -> list:
        if not os.path.exists(self.jsonl):
            return []
        out = []
        with open(self.jsonl, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out

    def count(self) -> int:
        return len(self.load_all())

    def export_markdown(self, out_path: str = None) -> str:
        """비식별화 레코드를 Markdown으로 내보내고 경로 반환(USB 반출용)."""
        records = self.load_all()
        out_path = out_path or os.path.join(self.dir, "feedback_export.md")
        lines = ["# 개선 기록 (비식별화 · 반출용)", "",
                 f"총 {len(records)}건. 실제 프로토콜 값·명칭은 가명(어휘N/IDN/치환숫자·HEX)으로 "
                 "치환됨. 표는 형태(행×열)만 보존.", ""]
        for i, r in enumerate(records, 1):
            lines.append(f"## {i}. [{r.get('kind')}] {r.get('category','')} "
                         f"(심각도: {r.get('severity','')})  · {r.get('ts','')}")
            if r.get("question"):
                lines.append(f"- **질문**: {r['question']}")
            if r.get("answer"):
                lines.append(f"- **답변**: {r['answer']}")
            if r.get("note"):
                lines.append(f"- **메모**: {r['note']}")
            if r.get("image"):
                lines.append(f"- **첨부 이미지**: ![]({r['image']})  (`{r['image']}`)")
            cs = r.get("context_summary")
            if cs:
                lines.append(f"- **검색 근거 요약**: 총 {cs.get('n',0)}개 "
                             f"(표 {cs.get('table',0)} / 텍스트 {cs.get('text',0)})")
            for j, c in enumerate(r.get("contexts", []), 1):
                m = c.get("metadata", {})
                shape = c.get("table_shape")
                tag = f"표 {shape['rows']}행×{shape['cols']}열" if shape and shape.get("is_table") \
                    else m.get("kind", "text")
                loc = m.get("page_no") or m.get("slide_no") or m.get("sheet_name") \
                    or m.get("section") or ""
                lines.append(f"  - 근거{j} [{tag}] {m.get('doc_title','')} {loc}")
            lines.append("")
        os.makedirs(self.dir, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return out_path
