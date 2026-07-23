#!/usr/bin/env python3
"""Claude Code Stop 훅 — 대화 내역을 원본 그대로 실시간으로 conversation_log.md에 누적한다.

동작:
  - Stop 훅은 종료 시 stdin으로 {"transcript_path": ..., "session_id": ..., "cwd": ...} 등을 받는다.
  - 세션 트랜스크립트(JSONL)를 읽어 아직 기록하지 않은 user/assistant 메시지를
    conversation_log.md 에 [타임스탬프] 역할 헤더 + 본문 형태로 append 한다.
  - 이미 기록한 메시지는 uuid 로 추적(.claude/hooks/.log_state.json)하여 중복을 막는다.
  - 어떤 오류가 나도 Claude 진행을 막지 않도록 항상 exit 0.

설계 메모:
  - "원본 그대로" 원칙: 사용자 입력 텍스트와 어시스턴트 텍스트는 가공 없이 그대로 기록.
  - 도구 호출/결과는 대화 흐름 파악용으로 한 줄 마커(툴 이름)만 남기고 큰 페이로드는 생략한다.
  - 이 훅은 온라인 개발 PC(현재 환경)에서만 동작한다. 오프라인 배포물과는 무관.
"""
import sys
import os
import json
import datetime


def _load_state(state_path):
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("written_uuids", []))
    except Exception:
        return set()


def _save_state(state_path, written):
    try:
        # uuid 집합이 무한정 커지지 않도록 최근 5000개만 유지(트랜스크립트는 append-only)
        trimmed = list(written)[-5000:]
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump({"written_uuids": trimmed}, f, ensure_ascii=False)
    except Exception:
        pass


def _blocks_to_text(content):
    """content(문자열 또는 블록 리스트)를 (본문텍스트, 툴마커리스트)로 변환."""
    if isinstance(content, str):
        return content, []
    texts, markers = [], []
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                texts.append(block.get("text", ""))
            elif btype == "thinking":
                # 내부 사고는 대화 원본에 포함하지 않는다.
                continue
            elif btype == "tool_use":
                markers.append(f"[도구 호출: {block.get('name', '?')}]")
            elif btype == "tool_result":
                markers.append("[도구 결과]")
    return "\n".join(t for t in texts if t).strip(), markers


def _fmt_ts(raw):
    if not raw:
        return datetime.datetime.now().isoformat(timespec="seconds")
    return raw


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    transcript_path = payload.get("transcript_path")
    if not transcript_path or not os.path.exists(transcript_path):
        return 0

    hooks_dir = os.path.dirname(os.path.abspath(__file__))
    state_path = os.path.join(hooks_dir, ".log_state.json")
    # 로그는 항상 이 스크립트가 속한 저장소 루트(crypto)에 기록한다.
    # (기존 cwd 기준은 상위 폴더에서 세션이 돌면 엉뚱한 위치에 파일이 생기는 버그)
    repo_root = os.path.dirname(os.path.dirname(hooks_dir))          # .claude/hooks → repo
    log_path = os.path.join(repo_root, "conversation_log.md")

    # 가드: 훅이 상위 프로젝트에도 등록될 수 있으므로, 이 저장소(crypto)를 실제로 다룬
    # 세션만 기록한다(트랜스크립트에 저장소 경로 언급 여부). 무관한 대화가 GitHub에
    # push되는 이 저장소의 로그에 섞이는 것을 방지.
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            if repo_root not in f.read():
                return 0
    except Exception:
        return 0

    written = _load_state(state_path)
    new_lines = []

    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            records = [json.loads(line) for line in f if line.strip()]
    except Exception:
        return 0

    for rec in records:
        rtype = rec.get("type")
        if rtype not in ("user", "assistant"):
            continue
        if rec.get("isMeta") or rec.get("isSidechain"):
            continue
        uuid = rec.get("uuid")
        if not uuid or uuid in written:
            continue

        message = rec.get("message") or {}
        role = message.get("role", rtype)
        body, markers = _blocks_to_text(message.get("content", ""))

        # 도구 결과만 있는 user 레코드(툴 아웃풋)는 대화 본문이 아니므로 마커만 있고 본문 없음 → 건너뜀
        if not body and not markers:
            written.add(uuid)
            continue
        if role == "user" and not body and markers == ["[도구 결과]"]:
            written.add(uuid)
            continue

        ts = _fmt_ts(rec.get("timestamp"))
        label = "사용자" if role == "user" else "어시스턴트"
        chunk = [f"\n### {label} · {ts}\n"]
        if body:
            chunk.append(body + "\n")
        if markers:
            chunk.append("\n".join(markers) + "\n")
        new_lines.append("\n".join(chunk))
        written.add(uuid)

    if new_lines:
        header_needed = not os.path.exists(log_path)
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                if header_needed:
                    f.write(
                        "# 대화 로그 (conversation_log.md)\n\n"
                        "> 이 파일은 `.claude/hooks/log_conversation.py` Stop 훅이 "
                        "매 응답 종료 시 자동으로 누적한다. 수동 편집하지 말 것.\n"
                    )
                f.write("".join(new_lines))
        except Exception:
            return 0

    _save_state(state_path, written)
    return 0


if __name__ == "__main__":
    sys.exit(main())
