from __future__ import annotations

import os
import time
from typing import Any, Callable, Dict, List, Tuple

from ...domain.models import AnswerEnvelope, QueryContext
from .rerank import rerank
from .retrieve import retrieve_dense_docs, retrieve_hybrid_docs


def run(query_ctx: QueryContext, runner: Callable[[int, str, str], Dict[str, Any]]) -> AnswerEnvelope:
    out = runner(int(query_ctx.user_id), query_ctx.query, query_ctx.request_id)
    return AnswerEnvelope(
        answer=str(out.get("answer") or ""),
        sources=list(out.get("sources") or []),
        meta=dict(out.get("meta") or {}),
    )


def _env_bool(name: str, default: bool = False) -> bool:
    val = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return val in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except Exception:
        return int(default)


def _is_optimized_path_enabled() -> bool:
    return _env_bool("RAG_SEMANTIC_OPTIMIZED_RETRIEVAL_ENABLED", default=False)


def _classify_query_intent(query: str) -> str:
    ql = str(query or "").lower()
    doc_markers = [
        "rekap nilai",
        "nilai saya",
        "ipk saya",
        "ips saya",
        "transkrip",
        "jadwal saya",
        "jadwal kelas",
        "mata kuliah",
        "khs",
        "krs",
        "sks",
        "ruang",
        "jam",
        "semester",
    ]
    return "doc_targeted" if any(x in ql for x in doc_markers) else "general_academic"


def _dedup_docs(docs: List[Any]) -> List[Any]:
    seen = set()
    out: List[Any] = []
    for d in docs:
        meta = getattr(d, "metadata", {}) or {}
        key = (
            str(meta.get("doc_id") or ""),
            str(meta.get("chunk_id") or ""),
            str(meta.get("row_id") or ""),
            str(getattr(d, "page_content", "") or "")[:120],
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out


def _resolve_retrieval_plan(mode: str, query_intent: str) -> Dict[str, Any]:
    dense_k = _env_int("RAG_DENSE_K", 30)
    bm25_k = _env_int("RAG_BM25_K", 40)
    rerank_top_n = _env_int("RAG_RERANK_TOP_N", 8)
    use_hybrid = _env_bool("RAG_HYBRID_RETRIEVAL", default=False)
    use_rerank = _env_bool("RAG_RERANK_ENABLED", default=False)

    optimized = _is_optimized_path_enabled()
    if mode == "doc_background":
        dense_k = _env_int("RAG_GENERAL_DENSE_K", 6)
        bm25_k = _env_int("RAG_GENERAL_BM25_K", 8)
        rerank_top_n = _env_int("RAG_GENERAL_RERANK_TOP_N", 4)
        use_hybrid = _env_bool("RAG_GENERAL_HYBRID_RETRIEVAL", default=False)
        use_rerank = _env_bool("RAG_GENERAL_RERANK_ENABLED", default=False)
        if query_intent == "doc_targeted":
            dense_k = _env_int("RAG_DOC_TARGETED_DENSE_K", 18)
            bm25_k = _env_int("RAG_DOC_TARGETED_BM25_K", 28)
            rerank_top_n = _env_int("RAG_DOC_TARGETED_RERANK_TOP_N", 10)
            use_hybrid = _env_bool("RAG_DOC_TARGETED_HYBRID_RETRIEVAL", default=True)
            use_rerank = _env_bool("RAG_DOC_TARGETED_RERANK_ENABLED", default=True)
    elif mode == "doc_referenced":
        dense_k = _env_int("RAG_DOC_DENSE_K", 12)
        bm25_k = _env_int("RAG_DOC_BM25_K", 20)
        rerank_top_n = _env_int("RAG_DOC_RERANK_TOP_N", 4)
        use_hybrid = _env_bool("RAG_DOC_HYBRID_RETRIEVAL", default=False)
        use_rerank = _env_bool("RAG_DOC_RERANK_ENABLED", default=True)

    rerank_model = str(os.environ.get("RAG_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")).strip()
    # Optimized path defaults prioritize p95 latency and can be overridden via env.
    if optimized:
        if mode == "doc_background" and query_intent == "general_academic":
            dense_k = _env_int("RAG_OPT_GENERAL_DENSE_K", 4)
            bm25_k = _env_int("RAG_OPT_GENERAL_BM25_K", 4)
            rerank_top_n = _env_int("RAG_OPT_GENERAL_RERANK_TOP_N", 3)
            use_hybrid = _env_bool("RAG_OPT_GENERAL_HYBRID_RETRIEVAL", default=False)
            use_rerank = _env_bool("RAG_OPT_GENERAL_RERANK_ENABLED", default=False)
        elif mode == "doc_background" and query_intent == "doc_targeted":
            dense_k = _env_int("RAG_OPT_DOC_TARGETED_DENSE_K", 8)
            bm25_k = _env_int("RAG_OPT_DOC_TARGETED_BM25_K", 8)
            rerank_top_n = _env_int("RAG_OPT_DOC_TARGETED_RERANK_TOP_N", 4)
            use_hybrid = _env_bool("RAG_OPT_DOC_TARGETED_HYBRID_RETRIEVAL", default=False)
            use_rerank = _env_bool("RAG_OPT_DOC_TARGETED_RERANK_ENABLED", default=False)
        elif mode == "doc_referenced":
            dense_k = _env_int("RAG_OPT_DOC_DENSE_K", 6)
            bm25_k = _env_int("RAG_OPT_DOC_BM25_K", 6)
            rerank_top_n = _env_int("RAG_OPT_DOC_RERANK_TOP_N", 4)
            use_hybrid = _env_bool("RAG_OPT_DOC_HYBRID_RETRIEVAL", default=False)
            use_rerank = _env_bool("RAG_OPT_DOC_RERANK_ENABLED", default=False)

    return {
        "dense_k": dense_k,
        "bm25_k": bm25_k,
        "rerank_top_n": rerank_top_n,
        "use_hybrid": use_hybrid,
        "use_rerank": use_rerank,
        "rerank_model": rerank_model,
        "optimized": optimized,
    }


def run_retrieval(
    *,
    vectorstore: Any,
    query_ctx: QueryContext,
    filter_where: Dict[str, Any] | None,
    has_docs_hint: bool,
) -> Dict[str, Any]:
    query = str(query_ctx.query or "").strip()
    resolved_doc_ids = list(query_ctx.doc_ids or [])
    mode = "llm_only"
    if has_docs_hint and resolved_doc_ids:
        mode = "doc_referenced"
    elif has_docs_hint:
        mode = "doc_background"

    query_intent = _classify_query_intent(query)
    plan = _resolve_retrieval_plan(mode=mode, query_intent=query_intent)

    if mode == "llm_only":
        return {
            "mode": mode,
            "query_intent": query_intent,
            "docs": [],
            "dense_scored": [],
            "dense_hits": 0,
            "bm25_hits": 0,
            "top_score": 0.0,
            "retrieval_ms": 0,
            "rerank_ms": 0,
            "plan": plan,
        }

    t0 = time.time()
    dense_scored: List[Tuple[Any, float]] = retrieve_dense_docs(
        vectorstore=vectorstore,
        query=query,
        k=max(int(plan["dense_k"]), 1),
        filter_where=filter_where,
    )
    dense_docs = _dedup_docs([d for d, _ in dense_scored])

    # Fallback lightweight when strict filter has no hit.
    allow_filter_fallback = _env_bool(
        "RAG_OPT_FILTER_FALLBACK_ENABLED",
        default=not bool(plan.get("optimized")),
    )
    if allow_filter_fallback and not dense_docs and isinstance(filter_where, dict) and "$and" in filter_where:
        fallback_scored = retrieve_dense_docs(
            vectorstore=vectorstore,
            query=query,
            k=max(int(plan["dense_k"]), 1),
            filter_where={"user_id": str(query_ctx.user_id)},
        )
        dense_scored = fallback_scored
        dense_docs = _dedup_docs([d for d, _ in fallback_scored])

    final_docs = list(dense_docs)
    final_scored: List[Tuple[Any, float]] = list(dense_scored)
    bm25_hits = 0
    if bool(plan["use_hybrid"]) and dense_docs:
        fused = retrieve_hybrid_docs(
            query=query,
            dense_scored=dense_scored,
            docs_pool=dense_docs,
            bm25_k=max(int(plan["bm25_k"]), 1),
        )
        bm25_hits = len(fused)
        final_docs = [d for d, _ in fused]
        final_scored = list(fused)

    rerank_ms = 0
    if bool(plan["use_rerank"]) and final_docs:
        rerank_t0 = time.time()
        final_docs = rerank(
            query=query,
            docs=final_docs[: max(int(plan["dense_k"]), int(plan["bm25_k"]))],
            model_name=str(plan["rerank_model"]),
            top_n=max(int(plan["rerank_top_n"]), 1),
        )
        rerank_ms = int(max((time.time() - rerank_t0) * 1000, 0))

    final_limit = int(plan["rerank_top_n"]) if bool(plan["use_rerank"]) else int(plan["dense_k"])
    docs = final_docs[: max(final_limit, 1)]
    top_score = float(final_scored[0][1]) if final_scored else 0.0
    retrieval_ms = int(max((time.time() - t0) * 1000, 0))

    if mode == "doc_background" and query_intent == "general_academic":
        low_rel_threshold = float(os.environ.get("RAG_GENERAL_RELEVANCE_THRESHOLD", "0.18"))
        if top_score < low_rel_threshold:
            docs = []

    return {
        "mode": mode,
        "query_intent": query_intent,
        "docs": docs,
        "dense_scored": dense_scored,
        "dense_hits": len(dense_docs),
        "bm25_hits": int(bm25_hits),
        "top_score": top_score,
        "retrieval_ms": retrieval_ms,
        "rerank_ms": rerank_ms,
        "plan": plan,
    }
