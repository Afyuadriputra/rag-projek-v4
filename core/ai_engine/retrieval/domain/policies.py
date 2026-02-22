from __future__ import annotations

from typing import Any, Dict, Iterable


def needs_doc_grounding(doc_type: str) -> bool:
    return str(doc_type or "").strip().lower() in {"schedule", "transcript"}


def should_abstain_no_grounding(*, docs_count: int, doc_type: str, is_personal_query: bool) -> bool:
    return docs_count <= 0 and is_personal_query and needs_doc_grounding(doc_type)


def is_personal_document_query(query: str) -> bool:
    ql = str(query or "").lower()
    personal_markers = [
        "saya",
        "aku",
        "punya saya",
        "milik saya",
        "ipk saya",
        "ips saya",
        "transkrip saya",
        "jadwal saya",
        "nilai saya",
    ]
    return any(m in ql for m in personal_markers)


def is_strict_transcript_mode(query: str, markers: Iterable[str]) -> bool:
    ql = str(query or "").lower()
    return any(str(m or "").lower() in ql for m in markers)


def structured_polish_validation_status(polished: Dict[str, Any] | None) -> str:
    if not isinstance(polished, dict):
        return "failed_fallback"
    return str(polished.get("validation") or "failed_fallback")
