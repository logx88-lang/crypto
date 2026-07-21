"""사용자(간이 로그인)·대화 저장소 — 서버 파일시스템에 JSON으로 영속화.

폐쇄망 사내 LAN 전제의 '가벼운' 사용자 구분(엔터프라이즈 인증 아님):
- users.json 에 사용자별 salt+hash 저장. 처음 로그인하는 이름은 자동 등록(자가가입).
- 대화는 data/conversations/<user>/<id>.json 로 사용자별 분리 저장.
"""
from __future__ import annotations

import hashlib
import json
import os
import time

from ..config import CONFIG


# --- 경로 ------------------------------------------------------------------
def _users_path() -> str:
    return os.path.join(CONFIG.data_dir, "users.json")


def _conv_dir(user: str) -> str:
    safe = "".join(c for c in user if c.isalnum() or c in "-_.")[:40] or "user"
    d = os.path.join(CONFIG.data_dir, "conversations", safe)
    os.makedirs(d, exist_ok=True)
    return d


# --- 사용자(간이 로그인) ---------------------------------------------------
def _load_users() -> dict:
    p = _users_path()
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_users(users: dict) -> None:
    os.makedirs(CONFIG.data_dir, exist_ok=True)
    with open(_users_path(), "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def _hash(pw: str, salt: str) -> str:
    return hashlib.sha256((salt + "|" + pw).encode("utf-8")).hexdigest()


def login_or_register(username: str, password: str) -> tuple:
    """(성공?, 메시지). 미등록 이름은 자동 등록. 기존 이름은 비밀번호 검증."""
    username = (username or "").strip()
    if not username:
        return False, "사용자 이름을 입력하세요."
    if len(password or "") < 1:
        return False, "비밀번호를 입력하세요."
    users = _load_users()
    if username in users:
        u = users[username]
        if _hash(password, u["salt"]) != u["hash"]:
            return False, "비밀번호가 일치하지 않습니다."
        return True, "로그인"
    # 자가가입(폐쇄망 신뢰 전제)
    salt = hashlib.sha1(os.urandom(16)).hexdigest()[:16]
    users[username] = {"salt": salt, "hash": _hash(password, salt),
                       "created": time.strftime("%Y-%m-%d %H:%M")}
    _save_users(users)
    return True, "신규 등록 후 로그인"


# --- 대화 ------------------------------------------------------------------
def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def new_conversation(user: str, title: str = "새 대화") -> dict:
    cid = time.strftime("%Y%m%d_%H%M%S") + f"_{int(time.time() * 1000) % 1000:03d}"
    conv = {"id": cid, "title": title, "user": user, "created": _now(),
            "updated": _now(), "messages": [], "summary": "", "scope_files": []}
    save_conversation(conv)
    return conv


def save_conversation(conv: dict) -> None:
    conv["updated"] = _now()
    path = os.path.join(_conv_dir(conv["user"]), conv["id"] + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(conv, f, ensure_ascii=False, indent=2)


def load_conversation(user: str, cid: str) -> dict:
    path = os.path.join(_conv_dir(user), cid + ".json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_conversations(user: str) -> list:
    """[{id, title, updated}] 최신순."""
    d = _conv_dir(user)
    out = []
    for fn in os.listdir(d):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(d, fn), encoding="utf-8") as f:
                c = json.load(f)
            out.append({"id": c["id"], "title": c.get("title", "대화"),
                        "updated": c.get("updated", "")})
        except Exception:
            continue
    return sorted(out, key=lambda x: x["updated"], reverse=True)


def delete_conversation(user: str, cid: str) -> None:
    path = os.path.join(_conv_dir(user), cid + ".json")
    if os.path.exists(path):
        os.remove(path)
