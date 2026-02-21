from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, TypedDict


class StoragePayload(TypedDict):
    used_bytes: int
    quota_bytes: int
    used_pct: int
    used_human: str
    quota_human: str


class SessionPayload(TypedDict):
    id: int
    title: str
    created_at: str
    updated_at: str


@dataclass(slots=True)
class ChatResult:
    answer: str
    sources: List[Dict[str, Any]]
    meta: Dict[str, Any]
    session_id: int

