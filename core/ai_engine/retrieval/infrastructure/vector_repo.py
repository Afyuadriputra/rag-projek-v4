from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ..hybrid import retrieve_dense, retrieve_sparse_bm25, fuse_rrf


def dense_search(*, vectorstore: Any, query: str, k: int, filter_where: Dict[str, Any] | None = None) -> List[Tuple[Any, float]]:
    return retrieve_dense(vectorstore=vectorstore, query=query, k=k, filter_where=filter_where)


def sparse_search(*, query: str, docs_pool: List[Any], k: int) -> List[Tuple[Any, float]]:
    return retrieve_sparse_bm25(query=query, docs_pool=docs_pool, k=k)


def rrf_fuse(*, dense_docs: List[Tuple[Any, float]], sparse_docs: List[Tuple[Any, float]], k: int) -> List[Tuple[Any, float]]:
    return fuse_rrf(dense_docs=dense_docs, sparse_docs=sparse_docs, k=k)
