from __future__ import annotations

from typing import Any, Dict

from core.monitoring import record_rag_metric


def emit_rag_metric(payload: Dict[str, Any]) -> None:
    record_rag_metric(**payload)


def enrich_response_meta(meta: Dict[str, Any], *, default_pipeline: str = "rag_semantic") -> Dict[str, Any]:
    base = dict(meta or {})
    analytics = base.get("analytics_stats") if isinstance(base.get("analytics_stats"), dict) else {}

    base.setdefault("pipeline", default_pipeline)
    base.setdefault("intent_route", "default_rag")
    base.setdefault("validation", "not_applicable")
    base.setdefault("answer_mode", "factual")

    if "retrieval_docs_count" not in base:
        base["retrieval_docs_count"] = int(base.get("final_docs") or 0)
    if "top_score" not in base:
        try:
            base["top_score"] = float(base.get("top_score") or 0.0)
        except Exception:
            base["top_score"] = 0.0
    if "structured_returned" not in base:
        base["structured_returned"] = int(analytics.get("returned") or 0)
    return base


def attach_stage_timings(
    meta: Dict[str, Any],
    *,
    route_ms: int | None = None,
    structured_ms: int | None = None,
    retrieval_ms: int | None = None,
    llm_ms: int | None = None,
) -> Dict[str, Any]:
    out = dict(meta or {})
    stage = dict(out.get("stage_timings_ms") or {})
    if route_ms is not None:
        stage["route_ms"] = int(max(route_ms, 0))
    if structured_ms is not None:
        stage["structured_ms"] = int(max(structured_ms, 0))
    if retrieval_ms is not None:
        stage["retrieval_ms"] = int(max(retrieval_ms, 0))
    if llm_ms is not None:
        stage["llm_ms"] = int(max(llm_ms, 0))
    out["stage_timings_ms"] = stage
    return out
