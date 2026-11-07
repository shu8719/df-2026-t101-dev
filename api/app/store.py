"""プロトタイプ用の保存（Firestore・Cloud Storage の代わりに、手元のJSONとファイル）。"""
from __future__ import annotations

import json
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / ".data"
CASES = DATA / "cases"
FILES = DATA / "files"
_lock = threading.Lock()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(4)}"


def load_case(case_id: str) -> dict | None:
    p = CASES / f"{case_id}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def save_case(case: dict) -> None:
    CASES.mkdir(parents=True, exist_ok=True)
    case["updated_at"] = now()
    with _lock:
        (CASES / f"{case['case_id']}.json").write_text(json.dumps(case, ensure_ascii=False, indent=1, default=float),
                                                         encoding="utf-8")


def list_cases(owner: str) -> list[dict]:
    if not CASES.exists():
        return []
    out = []
    for p in sorted(CASES.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        c = json.loads(p.read_text(encoding="utf-8"))
        if c.get("owner") == owner:
            out.append(c)
    return out


def design_dir(case_id: str, design_id: str) -> Path:
    d = FILES / "cases" / case_id / "designs" / design_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def rel(path: Path) -> str:
    return path.relative_to(FILES).as_posix()
