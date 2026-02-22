from __future__ import annotations

from typing import Any, List

from ...rerank import rerank_documents


def rerank(query: str, docs: List[Any], model_name: str, top_n: int) -> List[Any]:
    return rerank_documents(query=query, docs=docs, model_name=model_name, top_n=top_n)
