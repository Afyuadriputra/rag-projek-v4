from __future__ import annotations

"""
Facade module for structured analytics orchestration.

This keeps `core.ai_engine.retrieval.structured_analytics.run_structured_analytics`
as the public API while moving heavy logic to `structured_analytics_legacy.py`
for maintainability and gradual modular migration.
"""

from typing import Any, Dict, List

from . import structured_analytics_legacy as _legacy_module

from .config.settings import get_retrieval_settings

get_vectorstore = _legacy_module.get_vectorstore
_invoke_polisher_llm = _legacy_module._invoke_polisher_llm


def _sync_legacy_dependencies() -> None:
    """Mirror facade symbols into legacy module so patching this module still works."""
    _legacy_module.get_vectorstore = get_vectorstore
    _legacy_module._invoke_polisher_llm = _invoke_polisher_llm


def polish_structured_answer(
    *,
    query: str,
    deterministic_answer: str,
    facts: List[Dict[str, Any]],
    doc_type: str,
    style_hint: str = "factual",
) -> Dict[str, Any]:
    _sync_legacy_dependencies()
    return _legacy_module.polish_structured_answer(
        query=query,
        deterministic_answer=deterministic_answer,
        facts=facts,
        doc_type=doc_type,
        style_hint=style_hint,
    )


def run_structured_analytics(user_id: int, query: str, doc_ids: List[int] | None = None) -> Dict[str, Any]:
    """Public compatibility facade with feature-flagged modular structured path."""
    settings = get_retrieval_settings()
    if settings.refactor_structured_pipeline_enabled:
        from .domain.models import QueryContext
        from .pipelines.structured.run import run as run_structured

        out = run_structured(QueryContext(user_id=int(user_id), query=query, doc_ids=doc_ids))
        return {
            "ok": out.ok,
            "answer": out.answer,
            "sources": out.sources,
            "doc_type": out.doc_type,
            "facts": out.facts,
            "stats": out.stats,
            "reason": out.reason,
        }
    _sync_legacy_dependencies()
    return _legacy_module.run_structured_analytics(user_id=user_id, query=query, doc_ids=doc_ids)
