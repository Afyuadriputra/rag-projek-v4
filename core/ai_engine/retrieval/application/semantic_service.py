from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List

from ...config import get_vectorstore
from ..config.settings import get_retrieval_settings
from ..domain.models import QueryContext
from ..domain.policies import is_personal_document_query, should_abstain_no_grounding
from ..infrastructure.metrics import emit_rag_metric
from ..pipelines.semantic.answer import build_sources, run_answer
from ..pipelines.semantic.run import run_retrieval
from ..rules import infer_doc_type


def _use_optimized_for_request(*, user_id: int, request_id: str, query: str, traffic_pct: int) -> bool:
    pct = max(min(int(traffic_pct), 100), 0)
    if pct <= 0:
        return False
    if pct >= 100:
        return True

    seed = f"{int(user_id)}|{str(request_id or '-')}|{str(query or '')}".encode("utf-8")
    bucket = int(hashlib.md5(seed).hexdigest()[:8], 16) % 100
    return bucket < pct


def run_semantic(
    *,
    user_id: int,
    query: str,
    request_id: str,
    intent_route: str,
    has_docs_hint: bool,
    resolved_doc_ids: List[int],
    resolved_titles: List[str],
    unresolved_mentions: List[str],
    ambiguous_mentions: List[str],
) -> Dict[str, Any]:
    """
    Transitional semantic executor.

    Default tetap legacy path (risk-low). Path modular diaktifkan via flag.
    """
    settings = get_retrieval_settings()
    use_optimized = bool(settings.semantic_optimized_retrieval_enabled) and _use_optimized_for_request(
        user_id=int(user_id),
        request_id=str(request_id or "-"),
        query=str(query or ""),
        traffic_pct=int(settings.semantic_optimized_traffic_pct),
    )
    if use_optimized:
        optimized = _run_semantic_optimized(
            user_id=user_id,
            query=query,
            request_id=request_id,
            intent_route=intent_route,
            has_docs_hint=has_docs_hint,
            resolved_doc_ids=resolved_doc_ids,
            resolved_titles=resolved_titles,
            unresolved_mentions=unresolved_mentions,
            ambiguous_mentions=ambiguous_mentions,
        )
        if optimized is not None:
            opt_validation = str((optimized.get("meta") or {}).get("validation") or "")
            if bool(settings.semantic_optimized_legacy_fallback_enabled) and opt_validation == "failed_fallback":
                return _run_semantic_legacy(
                    user_id=user_id,
                    query=query,
                    request_id=request_id,
                    intent_route=intent_route,
                    resolved_titles=resolved_titles,
                    unresolved_mentions=unresolved_mentions,
                    ambiguous_mentions=ambiguous_mentions,
                )
            return optimized
        if not bool(settings.semantic_optimized_legacy_fallback_enabled):
            return {
                "answer": "Maaf, sistem sedang sibuk memproses jawaban. Silakan coba lagi sebentar.",
                "sources": [],
                "meta": {
                    "mode": "semantic_policy" if intent_route == "semantic_policy" else "doc_background",
                    "pipeline": "rag_semantic",
                    "intent_route": str(intent_route or "default_rag"),
                    "validation": "failed_fallback",
                    "answer_mode": "factual",
                    "retrieval_docs_count": 0,
                    "structured_returned": 0,
                    "top_score": 0.0,
                    "stage_timings_ms": {"retrieval_ms": 0, "llm_ms": 0},
                },
            }

    return _run_semantic_legacy(
        user_id=user_id,
        query=query,
        request_id=request_id,
        intent_route=intent_route,
        resolved_titles=resolved_titles,
        unresolved_mentions=unresolved_mentions,
        ambiguous_mentions=ambiguous_mentions,
    )


def _run_semantic_legacy(
    *,
    user_id: int,
    query: str,
    request_id: str,
    intent_route: str,
    resolved_titles: List[str],
    unresolved_mentions: List[str],
    ambiguous_mentions: List[str],
) -> Dict[str, Any]:
    t0 = time.time()
    from .. import main as legacy_main

    out = legacy_main._ask_bot_legacy(user_id=user_id, query=query, request_id=request_id)
    answer = str(out.get("answer") or "")
    sources = list(out.get("sources") or [])
    meta = dict(out.get("meta") or {})

    meta.setdefault("pipeline", "rag_semantic")
    meta.setdefault("intent_route", str(intent_route or "default_rag"))
    meta.setdefault("validation", "not_applicable")
    meta.setdefault("answer_mode", "factual")
    meta.setdefault("referenced_documents", resolved_titles)
    meta.setdefault("unresolved_mentions", unresolved_mentions)
    meta.setdefault("ambiguous_mentions", ambiguous_mentions)

    docs_count = int(meta.get("retrieval_docs_count") or len(sources))
    if should_abstain_no_grounding(
        docs_count=docs_count,
        doc_type=infer_doc_type(query) or "general",
        is_personal_query=is_personal_document_query(query),
    ):
        meta["validation"] = "no_grounding_evidence"

    meta["retrieval_docs_count"] = docs_count
    if "top_score" not in meta:
        meta["top_score"] = 0.0
    if "structured_returned" not in meta:
        meta["structured_returned"] = int((meta.get("analytics_stats") or {}).get("returned") or 0)

    timings = dict(meta.get("stage_timings_ms") or {})
    timings.setdefault("retrieval_ms", int(meta.get("retrieval_ms") or max((time.time() - t0) * 1000, 0)))
    timings.setdefault("llm_ms", int(meta.get("llm_time_ms") or meta.get("llm_ms") or 0))
    meta["stage_timings_ms"] = timings

    return {"answer": answer, "sources": sources, "meta": meta}


def _run_semantic_optimized(
    *,
    user_id: int,
    query: str,
    request_id: str,
    intent_route: str,
    has_docs_hint: bool,
    resolved_doc_ids: List[int],
    resolved_titles: List[str],
    unresolved_mentions: List[str],
    ambiguous_mentions: List[str],
) -> Dict[str, Any] | None:
    """
    Experimental modular semantic path.

    Return None agar caller fallback ke legacy jika terjadi kendala.
    """
    t0 = time.time()
    doc_type = infer_doc_type(query) or "general"
    is_personal = is_personal_document_query(query)

    filter_where: Dict[str, Any] = {"user_id": str(user_id)}
    if resolved_doc_ids:
        filter_where["doc_id"] = {"$in": [str(x) for x in resolved_doc_ids]}
    elif doc_type in {"schedule", "transcript"}:
        filter_where["doc_type"] = doc_type

    try:
        vectorstore = get_vectorstore()
        retrieval = run_retrieval(
            vectorstore=vectorstore,
            query_ctx=QueryContext(
                user_id=int(user_id),
                query=str(query or ""),
                request_id=str(request_id or "-"),
                doc_ids=list(resolved_doc_ids or []),
            ),
            filter_where=filter_where,
            has_docs_hint=bool(has_docs_hint),
        )
    except Exception:
        _emit_semantic_metric(
            request_id=request_id,
            user_id=user_id,
            mode="semantic_policy" if intent_route == "semantic_policy" else "doc_background",
            query_len=len(str(query or "").strip()),
            dense_hits=0,
            final_docs=0,
            retrieval_ms=int(max((time.time() - t0) * 1000, 0)),
            llm_model="",
            llm_time_ms=0,
            fallback_used=False,
            source_count=0,
            pipeline="rag_semantic",
            intent_route=str(intent_route or "default_rag"),
            validation="failed_fallback",
            answer_mode="factual",
            status_code=500,
        )
        return {
            "answer": "Maaf, sistem sedang sibuk memproses jawaban. Silakan coba lagi sebentar.",
            "sources": [],
            "meta": {
                "mode": "semantic_policy" if intent_route == "semantic_policy" else "doc_background",
                "pipeline": "rag_semantic",
                "intent_route": str(intent_route or "default_rag"),
                "validation": "failed_fallback",
                "answer_mode": "factual",
                "referenced_documents": resolved_titles,
                "unresolved_mentions": unresolved_mentions,
                "ambiguous_mentions": ambiguous_mentions,
                "retrieval_docs_count": 0,
                "structured_returned": 0,
                "top_score": 0.0,
                "stage_timings_ms": {"retrieval_ms": int(max((time.time() - t0) * 1000, 0)), "llm_ms": 0},
            },
        }

    docs = list(retrieval.get("docs") or [])
    sources = build_sources(docs)
    docs_count = len(sources)
    top_score = float(retrieval.get("top_score") or 0.0)
    retrieval_ms = int(retrieval.get("retrieval_ms") or max((time.time() - t0) * 1000, 0))
    dense_hits = int(retrieval.get("dense_hits") or 0)
    mode = str(retrieval.get("mode") or ("doc_referenced" if resolved_titles else "doc_background"))

    if should_abstain_no_grounding(
        docs_count=docs_count,
        doc_type=doc_type,
        is_personal_query=is_personal,
    ):
        _emit_semantic_metric(
            request_id=request_id,
            user_id=user_id,
            mode="semantic_policy" if intent_route == "semantic_policy" else mode,
            query_len=len(str(query or "").strip()),
            dense_hits=dense_hits,
            final_docs=0,
            retrieval_ms=retrieval_ms,
            llm_model="",
            llm_time_ms=0,
            fallback_used=False,
            source_count=0,
            pipeline="rag_semantic",
            intent_route=str(intent_route or "default_rag"),
            validation="no_grounding_evidence",
            answer_mode="factual",
            status_code=200,
        )
        return {
            "answer": "Maaf, data dokumen belum cukup untuk menjawab pertanyaan personal ini secara akurat.",
            "sources": [],
            "meta": {
                "mode": "doc_background",
                "pipeline": "rag_semantic",
                "intent_route": str(intent_route or "default_rag"),
                "validation": "no_grounding_evidence",
                "answer_mode": "factual",
                "referenced_documents": resolved_titles,
                "unresolved_mentions": unresolved_mentions,
                "ambiguous_mentions": ambiguous_mentions,
                "retrieval_docs_count": 0,
                "structured_returned": 0,
                "top_score": 0.0,
                "stage_timings_ms": {"retrieval_ms": retrieval_ms, "llm_ms": 0},
            },
        }

    llm = run_answer(
        query=query,
        docs=docs,
        mode=mode,
        resolved_titles=resolved_titles,
        unresolved_mentions=unresolved_mentions,
    )
    metric_mode = "semantic_policy" if intent_route == "semantic_policy" else mode
    if not llm.get("ok"):
        _emit_semantic_metric(
            request_id=request_id,
            user_id=user_id,
            mode=metric_mode,
            query_len=len(str(query or "").strip()),
            dense_hits=dense_hits,
            final_docs=docs_count,
            retrieval_ms=retrieval_ms,
            llm_model="",
            llm_time_ms=0,
            fallback_used=False,
            source_count=len(sources),
            pipeline="rag_semantic",
            intent_route=str(intent_route or "default_rag"),
            validation="failed_fallback",
            answer_mode="factual",
            status_code=500,
        )
        return {
            "answer": "Maaf, sistem sedang sibuk memproses jawaban. Silakan coba lagi sebentar.",
            "sources": [],
            "meta": {
                "mode": metric_mode,
                "pipeline": "rag_semantic",
                "intent_route": str(intent_route or "default_rag"),
                "validation": "failed_fallback",
                "answer_mode": "factual",
                "referenced_documents": resolved_titles,
                "unresolved_mentions": unresolved_mentions,
                "ambiguous_mentions": ambiguous_mentions,
                "retrieval_docs_count": docs_count,
                "structured_returned": 0,
                "top_score": top_score,
                "stage_timings_ms": {"retrieval_ms": retrieval_ms, "llm_ms": 0},
            },
        }

    answer = str(llm.get("text") or "").strip() or "Maaf, tidak ada jawaban."
    _emit_semantic_metric(
        request_id=request_id,
        user_id=user_id,
        mode=metric_mode,
        query_len=len(str(query or "").strip()),
        dense_hits=dense_hits,
        final_docs=docs_count,
        retrieval_ms=retrieval_ms,
        llm_model=str(llm.get("model") or ""),
        llm_time_ms=int(llm.get("llm_ms") or 0),
        fallback_used=bool(llm.get("fallback_used")),
        source_count=len(sources),
        pipeline="rag_semantic",
        intent_route=str(intent_route or "default_rag"),
        validation="not_applicable",
        answer_mode="factual",
        status_code=200,
    )
    return {
        "answer": answer,
        "sources": sources,
        "meta": {
            "mode": mode,
            "pipeline": "rag_semantic",
            "intent_route": str(intent_route or "default_rag"),
            "validation": "not_applicable",
            "answer_mode": "factual",
            "referenced_documents": resolved_titles,
            "unresolved_mentions": unresolved_mentions,
            "ambiguous_mentions": ambiguous_mentions,
            "retrieval_docs_count": docs_count,
            "structured_returned": 0,
            "top_score": top_score,
            "llm_model": str(llm.get("model") or ""),
            "fallback_used": bool(llm.get("fallback_used")),
            "stage_timings_ms": {
                "retrieval_ms": retrieval_ms,
                "llm_ms": int(llm.get("llm_ms") or 0),
            },
        },
    }


def _emit_semantic_metric(
    *,
    request_id: str,
    user_id: int,
    mode: str,
    query_len: int,
    dense_hits: int,
    final_docs: int,
    retrieval_ms: int,
    llm_model: str,
    llm_time_ms: int,
    fallback_used: bool,
    source_count: int,
    pipeline: str,
    intent_route: str,
    validation: str,
    answer_mode: str,
    status_code: int,
) -> None:
    emit_rag_metric(
        {
            "request_id": str(request_id or "-"),
            "user_id": int(user_id),
            "mode": str(mode or "doc_background"),
            "query_len": max(int(query_len), 0),
            "dense_hits": max(int(dense_hits), 0),
            "bm25_hits": 0,
            "final_docs": max(int(final_docs), 0),
            "retrieval_ms": max(int(retrieval_ms), 0),
            "rerank_ms": 0,
            "llm_model": str(llm_model or ""),
            "llm_time_ms": max(int(llm_time_ms), 0),
            "fallback_used": bool(fallback_used),
            "source_count": max(int(source_count), 0),
            "pipeline": str(pipeline or "rag_semantic"),
            "intent_route": str(intent_route or "default_rag"),
            "validation": str(validation or "not_applicable"),
            "answer_mode": str(answer_mode or "factual"),
            "status_code": int(status_code),
        }
    )
