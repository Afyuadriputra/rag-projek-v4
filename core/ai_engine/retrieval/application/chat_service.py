from __future__ import annotations

import os
import time
from typing import Any, Dict

from ..config.settings import get_retrieval_settings
from ..infrastructure.metrics import attach_stage_timings, enrich_response_meta
from .answer_service import normalize_response
from .guards_service import build_guard_response, build_out_of_domain_response, classify_safety
from .mention_service import build_ambiguous_response, extract_mentions, has_user_documents, resolve_mentions
from .route_service import resolve_route
from .semantic_service import run_semantic
from .structured_service import run as run_structured


def ask_bot_legacy_compat(user_id: int, query: str, request_id: str = "-") -> Dict[str, Any]:
    from .. import main_legacy as legacy_main
    from .. import main as main_facade

    strict_markers = ["transkrip", "khs", "tabel mentah", "data mentah"]
    runtime_cfg = legacy_main.get_runtime_openrouter_config()
    api_key = str((runtime_cfg or {}).get("api_key") or "").strip()
    if not api_key:
        return {
            "answer": "OpenRouter API key belum di-set. Atur di Django Admin (LLM Configuration) atau .env.",
            "sources": [],
        }

    q_raw = str(query or "").strip()
    safety = classify_safety(q_raw)
    decision = str(safety.get("decision") or "allow")
    if decision in {"refuse_crime", "refuse_political", "redirect_weird"}:
        return build_guard_response(decision=decision, query=q_raw, request_id=request_id)

    q, mentions = main_facade._extract_doc_mentions(q_raw)
    if not q:
        q = q_raw

    mention_resolution = main_facade._resolve_user_doc_mentions(int(user_id), mentions)
    resolved_doc_ids = list(mention_resolution.get("resolved_doc_ids") or [])
    unresolved_mentions = list(mention_resolution.get("unresolved_mentions") or [])
    ambiguous_mentions = list(mention_resolution.get("ambiguous_mentions") or [])
    resolved_titles = list(mention_resolution.get("resolved_titles") or [])
    if ambiguous_mentions:
        return build_ambiguous_response(ambiguous_mentions)

    has_docs_hint = bool(main_facade._has_user_documents(int(user_id)))
    route_info = resolve_route(q)
    intent_route = str(route_info.get("route") or "default_rag")
    if intent_route == "out_of_domain":
        out = build_out_of_domain_response(intent_route=intent_route)
        meta = dict(out.get("meta") or {})
        meta["referenced_documents"] = resolved_titles
        meta["unresolved_mentions"] = unresolved_mentions
        meta["ambiguous_mentions"] = ambiguous_mentions
        out["meta"] = meta
        return out

    if (
        intent_route == "analytical_tabular"
        and has_docs_hint
        and str(os.environ.get("RAG_STRUCTURED_ANALYTICS_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}
    ):
        structured = main_facade.run_structured_analytics(
            user_id=int(user_id),
            query=q,
            doc_ids=resolved_doc_ids if resolved_doc_ids else None,
        )
        if structured.get("ok"):
            structured_doc_type = str(structured.get("doc_type") or "")
            structured_mode = "structured_transcript" if structured_doc_type == "transcript" else "structured_schedule"
            deterministic_answer = str(structured.get("answer") or "").strip() or "Maaf, data tidak ditemukan di dokumen Anda."
            structured_facts = list(structured.get("facts") or [])
            transcript_answer_mode = (
                main_facade._classify_transcript_answer_mode(q) if structured_doc_type == "transcript" else "factual"
            )
            ql = str(q or "").lower()
            strict_transcript_mode = structured_doc_type == "transcript" and any(m in ql for m in strict_markers)
            if strict_transcript_mode:
                answer = deterministic_answer
                validation_status = "skipped_strict"
            else:
                polished = main_facade.polish_structured_answer(
                    query=q,
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
            return {
                "answer": answer,
                "sources": list(structured.get("sources") or []),
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
                    "ambiguous_mentions": ambiguous_mentions,
                    "retrieval_ms": int(stats.get("latency_ms") or 0),
                    "llm_time_ms": 0,
                    "stage_timings_ms": {"retrieval_ms": int(stats.get("latency_ms") or 0), "llm_ms": 0},
                },
            }
        structured_doc_type = str(structured.get("doc_type") or "")
        ql = str(q or "").lower()
        strict_transcript_mode = structured_doc_type == "transcript" and any(m in ql for m in strict_markers)
        if strict_transcript_mode:
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
                    "ambiguous_mentions": ambiguous_mentions,
                    "retrieval_ms": int((structured.get("stats") or {}).get("latency_ms") or 0),
                    "llm_time_ms": 0,
                    "stage_timings_ms": {"retrieval_ms": int((structured.get("stats") or {}).get("latency_ms") or 0), "llm_ms": 0},
                },
            }

    return legacy_main.run_semantic_legacy_only(
        user_id=int(user_id),
        query=str(q or ""),
        request_id=str(request_id or "-"),
        intent_route=intent_route,
        has_docs_hint=bool(has_docs_hint),
        resolved_doc_ids=list(resolved_doc_ids or []),
        resolved_titles=list(resolved_titles or []),
        unresolved_mentions=list(unresolved_mentions or []),
        ambiguous_mentions=list(ambiguous_mentions or []),
        runtime_cfg=dict(runtime_cfg or {}),
    )


def ask_bot(user_id: int, query: str, request_id: str = "-") -> Dict[str, Any]:
    t_start = time.time()
    q_raw = str(query or "").strip()

    safety = classify_safety(q_raw)
    decision = str(safety.get("decision") or "allow")
    if decision in {"refuse_crime", "refuse_political", "redirect_weird"}:
        q = q_raw
        out = build_guard_response(decision=decision, query=q, request_id=request_id)
        out = normalize_response(out)
        out["meta"] = attach_stage_timings(
            enrich_response_meta(out["meta"], default_pipeline="route_guard"),
            route_ms=int(max((time.time() - t_start) * 1000, 0)),
        )
        return out

    q, mentions = extract_mentions(q_raw)
    if not q:
        q = q_raw

    mention_resolution = resolve_mentions(int(user_id), mentions)
    resolved_doc_ids = list(mention_resolution.get("resolved_doc_ids") or [])
    unresolved_mentions = list(mention_resolution.get("unresolved_mentions") or [])
    ambiguous_mentions = list(mention_resolution.get("ambiguous_mentions") or [])
    resolved_titles = list(mention_resolution.get("resolved_titles") or [])

    if ambiguous_mentions:
        out = build_ambiguous_response(ambiguous_mentions)
        out = normalize_response(out)
        out["meta"] = attach_stage_timings(
            enrich_response_meta(out["meta"], default_pipeline="rag_semantic"),
            route_ms=int(max((time.time() - t_start) * 1000, 0)),
        )
        return out

    has_docs_hint = has_user_documents(int(user_id))
    route_t0 = time.time()
    route_info = resolve_route(q)
    intent_route = str(route_info.get("route") or "default_rag")
    route_ms = int(max((time.time() - route_t0) * 1000, 0))

    if intent_route == "out_of_domain":
        out = normalize_response(build_out_of_domain_response(intent_route=intent_route))
        out["meta"] = attach_stage_timings(
            enrich_response_meta(out["meta"], default_pipeline="route_guard"),
            route_ms=route_ms,
        )
        return out

    structured_t0 = time.time()
    structured_out = run_structured(
        user_id=int(user_id),
        query=q,
        intent_route=intent_route,
        has_docs_hint=has_docs_hint,
        resolved_doc_ids=resolved_doc_ids,
        unresolved_mentions=unresolved_mentions,
        resolved_titles=resolved_titles,
    )
    structured_ms = int(max((time.time() - structured_t0) * 1000, 0))
    if structured_out is not None:
        out = normalize_response(structured_out)
        meta = dict(out.get("meta") or {})
        meta["intent_route"] = intent_route
        out["meta"] = attach_stage_timings(
            enrich_response_meta(meta, default_pipeline=str(meta.get("pipeline") or "structured_analytics")),
            route_ms=route_ms,
            structured_ms=structured_ms,
        )
        return out

    semantic_out = run_semantic(
        user_id=int(user_id),
        query=q,
        request_id=str(request_id or "-"),
        intent_route=intent_route,
        has_docs_hint=bool(has_docs_hint),
        resolved_doc_ids=resolved_doc_ids,
        resolved_titles=resolved_titles,
        unresolved_mentions=unresolved_mentions,
        ambiguous_mentions=ambiguous_mentions,
    )
    out = normalize_response(semantic_out)
    settings = get_retrieval_settings()
    if settings.metric_enrichment_enabled:
        meta = dict(out.get("meta") or {})
        meta["intent_route"] = str(meta.get("intent_route") or intent_route)
        out["meta"] = attach_stage_timings(
            enrich_response_meta(meta, default_pipeline="rag_semantic"),
            route_ms=route_ms,
            structured_ms=structured_ms,
        )
    return out
