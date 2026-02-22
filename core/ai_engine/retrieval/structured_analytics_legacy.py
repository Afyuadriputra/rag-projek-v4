from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterator, List

from ..config import get_vectorstore
from .domain.models import QueryContext
from .pipelines.structured import fetch as _fetch_module
from .pipelines.structured.polish import _invoke_polisher_llm as _default_invoke_polisher_llm
from .pipelines.structured.polish import polish as _polish_structured
from .pipelines.structured.run import run as _run_structured


# Exposed hook for compatibility/tests (can be patched from facade module).
def _invoke_polisher_llm(prompt: str) -> str:
    return _default_invoke_polisher_llm(prompt)


@contextmanager
def _patch_fetch_vectorstore() -> Iterator[None]:
    original_get_vectorstore = _fetch_module.get_vectorstore
    _fetch_module.get_vectorstore = get_vectorstore
    try:
        yield
    finally:
        _fetch_module.get_vectorstore = original_get_vectorstore


def _run_structured_analytics_legacy(user_id: int, query: str, doc_ids: List[int] | None = None) -> Dict[str, Any]:
    with _patch_fetch_vectorstore():
        out = _run_structured(QueryContext(user_id=int(user_id), query=str(query or ""), doc_ids=doc_ids))
    return {
        "ok": out.ok,
        "answer": out.answer,
        "sources": out.sources,
        "doc_type": out.doc_type,
        "facts": out.facts,
        "stats": out.stats,
        "reason": out.reason,
    }


def polish_structured_answer(
    *,
    query: str,
    deterministic_answer: str,
    facts: List[Dict[str, Any]],
    doc_type: str,
    style_hint: str = "factual",
) -> Dict[str, Any]:
    return _polish_structured(
        query=query,
        deterministic_answer=deterministic_answer,
        facts=facts,
        doc_type=doc_type,
        style_hint=style_hint,
        invoke_polisher_fn=_invoke_polisher_llm,
    )


def run_structured_analytics(user_id: int, query: str, doc_ids: List[int] | None = None) -> Dict[str, Any]:
    return _run_structured_analytics_legacy(user_id=user_id, query=query, doc_ids=doc_ids)
