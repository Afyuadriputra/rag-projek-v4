from __future__ import annotations

import os
from typing import Any, Dict, List

from ..structured_analytics import polish_structured_answer, run_structured_analytics


_STRICT_TRANSCRIPT_MARKERS = [
    "transkrip",
    "khs",
    "tabel mentah",
    "data mentah",
]


def classify_transcript_answer_mode(query: str) -> str:
    from .. import main as legacy_main

    return legacy_main._classify_transcript_answer_mode(query)


def is_strict_transcript_mode(query: str, doc_type: str) -> bool:
    if doc_type != "transcript":
        return False
    ql = str(query or "").lower()
    return any(m in ql for m in _STRICT_TRANSCRIPT_MARKERS)


def run(
    *,
    user_id: int,
    query: str,
    intent_route: str,
    has_docs_hint: bool,
    resolved_doc_ids: List[int],
    unresolved_mentions: List[str],
    resolved_titles: List[str],
) -> Dict[str, Any] | None:
    if not (intent_route == "analytical_tabular" and has_docs_hint):
        return None
    if str(os.environ.get("RAG_STRUCTURED_ANALYTICS_ENABLED", "1")).strip().lower() not in {"1", "true", "yes", "on"}:
        return None

    structured = run_structured_analytics(
        user_id=int(user_id),
        query=query,
        doc_ids=resolved_doc_ids if resolved_doc_ids else None,
    )

    if structured.get("ok"):
        structured_doc_type = str(structured.get("doc_type") or "")
        structured_mode = "structured_transcript" if structured_doc_type == "transcript" else "structured_schedule"
        deterministic_answer = str(structured.get("answer") or "").strip() or "Maaf, data tidak ditemukan di dokumen Anda."
        structured_facts = list(structured.get("facts") or [])
        transcript_answer_mode = classify_transcript_answer_mode(query) if structured_doc_type == "transcript" else "factual"

        if is_strict_transcript_mode(query, structured_doc_type):
            answer = deterministic_answer
            validation_status = "skipped_strict"
        else:
            polished = polish_structured_answer(
                query=query,
                deterministic_answer=deterministic_answer,
                facts=structured_facts,
                doc_type=structured_doc_type,
                style_hint=transcript_answer_mode,
            )
            answer = str(polished.get("answer") or deterministic_answer)
            validation_status = str(polished.get("validation") or "failed_fallback")

        if unresolved_mentions:
            answer = (
                f"{answer}\n\n"
                f"Catatan rujukan: ada file yang tidak ditemukan ({', '.join([f'@{m}' for m in unresolved_mentions])})."
            ).strip()

        stats = structured.get("stats") or {}
        sources = list(structured.get("sources") or [])

        return {
            "answer": answer,
            "sources": sources,
            "meta": {
                "mode": structured_mode,
                "pipeline": "structured_analytics",
                "intent_route": intent_route,
                "validation": validation_status,
                "answer_mode": transcript_answer_mode if structured_doc_type == "transcript" else "factual",
                "analytics_stats": {
                    "raw": int(stats.get("raw") or 0),
                    "deduped": int(stats.get("deduped") or 0),
                    "returned": int(stats.get("returned") or 0),
                },
                "referenced_documents": resolved_titles,
                "unresolved_mentions": unresolved_mentions,
                "ambiguous_mentions": [],
                "retrieval_docs_count": int(stats.get("returned") or 0),
                "structured_returned": int(stats.get("returned") or 0),
                "top_score": 0.0,
            },
        }

    if is_strict_transcript_mode(query, str(structured.get("doc_type") or "")):
        strict_answer = str(structured.get("answer") or "").strip() or (
            "## Ringkasan\n"
            "Maaf, data tidak ditemukan di dokumen Anda.\n\n"
            "## Opsi Lanjut\n"
            "- Pastikan dokumen KHS/Transkrip sudah terunggah.\n"
            "- Jika sudah, coba re-ingest dokumen lalu ulangi pertanyaan."
        )
        return {
            "answer": strict_answer,
            "sources": list(structured.get("sources") or []),
            "meta": {
                "mode": "structured_transcript",
                "pipeline": "structured_analytics",
                "intent_route": intent_route,
                "validation": "strict_no_fallback",
                "analytics_stats": structured.get("stats") or {},
                "referenced_documents": resolved_titles,
                "unresolved_mentions": unresolved_mentions,
                "ambiguous_mentions": [],
                "structured_returned": int((structured.get("stats") or {}).get("returned") or 0),
                "retrieval_docs_count": int((structured.get("stats") or {}).get("returned") or 0),
                "top_score": 0.0,
            },
        }

    return None
