import logging
from typing import Any, Dict, List, Sequence, Tuple

from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)


DocScore = Tuple[Any, float]


def _doc_key(doc: Any) -> str:
    meta = getattr(doc, "metadata", {}) or {}
    source = str(meta.get("source") or "")
    doc_id = str(meta.get("doc_id") or "")
    page = str(meta.get("page") or "")
    content = str(getattr(doc, "page_content", "") or "")[:120]
    return f"{doc_id}|{source}|{page}|{content}"


def _tokenize(text: str) -> List[str]:
    return [x for x in str(text or "").lower().strip().split() if x]


def retrieve_dense(vectorstore: Any, query: str, k: int, filter_where: Dict[str, Any] | None = None) -> List[DocScore]:
    try:
        return vectorstore.similarity_search_with_score(query, k=max(1, int(k)), filter=filter_where or {})
    except Exception:
        return []


def retrieve_sparse_bm25(query: str, docs_pool: Sequence[Any], k: int) -> List[DocScore]:
    if not docs_pool:
        return []
    tokenized_corpus = [_tokenize(getattr(d, "page_content", "")) for d in docs_pool]
    if not any(tokenized_corpus):
        return []
    bm25 = BM25Okapi(tokenized_corpus)
    scores = bm25.get_scores(_tokenize(query))
    ranked = sorted(zip(docs_pool, scores), key=lambda x: x[1], reverse=True)
    out: List[DocScore] = []
    for doc, score in ranked[: max(1, int(k))]:
        out.append((doc, float(score)))
    return out


def fuse_rrf(dense_docs: Sequence[DocScore], sparse_docs: Sequence[DocScore], k: int, rrf_k: int = 60) -> List[DocScore]:
    """
    Reciprocal Rank Fusion:
    score(d) = Σ 1 / (rrf_k + rank_i(d))
    """
    acc: Dict[str, Dict[str, Any]] = {}
    for rank, (doc, _score) in enumerate(dense_docs, start=1):
        key = _doc_key(doc)
        slot = acc.setdefault(key, {"doc": doc, "score": 0.0})
        slot["score"] += 1.0 / (rrf_k + rank)
    for rank, (doc, _score) in enumerate(sparse_docs, start=1):
        key = _doc_key(doc)
        slot = acc.setdefault(key, {"doc": doc, "score": 0.0})
        slot["score"] += 1.0 / (rrf_k + rank)

    ranked = sorted(acc.values(), key=lambda x: x["score"], reverse=True)
    out: List[DocScore] = [(x["doc"], float(x["score"])) for x in ranked[: max(1, int(k))]]
    logger.debug(
        "RRF fused dense=%s sparse=%s final=%s",
        len(dense_docs),
        len(sparse_docs),
        len(out),
    )
    return out
