from __future__ import annotations

from typing import Any, Dict


def normalize_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "answer": str(payload.get("answer") or ""),
        "sources": list(payload.get("sources") or []),
        "meta": dict(payload.get("meta") or {}),
    }
