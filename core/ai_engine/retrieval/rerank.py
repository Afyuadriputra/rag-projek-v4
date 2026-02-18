import logging
from typing import Any, List, Sequence

from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)

_RERANKER_CACHE: dict[str, Any] = {}


def _get_reranker(model_name: str) -> Any:
    key = str(model_name or "").strip()
    if not key:
        raise ValueError("reranker model_name kosong")
    if key in _RERANKER_CACHE:
        return _RERANKER_CACHE[key]
    model = CrossEncoder(key)
    _RERANKER_CACHE[key] = model
    return model


def rerank_documents(query: str, docs: Sequence[Any], model_name: str, top_n: int) -> List[Any]:
    """
    Return docs terurut relevansi tertinggi.
    Jika gagal, return input docs apa adanya.
    """
    if not docs:
        return []
    try:
        reranker = _get_reranker(model_name)
        pairs = [[str(query or ""), str(getattr(d, "page_content", "") or "")] for d in docs]
        scores = reranker.predict(pairs)
        ranked = sorted(zip(docs, scores), key=lambda x: float(x[1]), reverse=True)
        out = [doc for doc, _score in ranked[: max(1, int(top_n))]]
        return out
    except Exception as e:
        logger.warning("Rerank gagal model=%s err=%s; fallback tanpa rerank", model_name, e)
        return list(docs)[: max(1, int(top_n))]
