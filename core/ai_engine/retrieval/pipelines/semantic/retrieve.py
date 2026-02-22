from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ...infrastructure.vector_repo import dense_search, sparse_search, rrf_fuse


def retrieve_dense_docs(vectorstore: Any, query: str, k: int, filter_where: Dict[str, Any] | None = None) -> List[Tuple[Any, float]]:
    return dense_search(vectorstore=vectorstore, query=query, k=k, filter_where=filter_where)


def retrieve_hybrid_docs(query: str, dense_scored: List[Tuple[Any, float]], docs_pool: List[Any], bm25_k: int) -> List[Tuple[Any, float]]:
    sparse_scored = sparse_search(query=query, docs_pool=docs_pool, k=bm25_k)
    return rrf_fuse(dense_docs=dense_scored, sparse_docs=sparse_scored, k=bm25_k)
