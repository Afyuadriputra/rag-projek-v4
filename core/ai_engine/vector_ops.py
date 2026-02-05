# core/ai_engine/vector_ops.py
from __future__ import annotations

from typing import Optional
import logging

from .config import get_vectorstore

logger = logging.getLogger(__name__)


def _get_collection(vectorstore):
    """
    LangChain Chroma biasanya menyimpan collection di attribute _collection.
    Kita bungkus biar gampang fallback kalau implementasi beda.
    """
    col = getattr(vectorstore, "_collection", None)
    if col is None:
        # fallback: coba attribute lain jika ada
        col = getattr(vectorstore, "collection", None)
    return col


def delete_vectors_for_doc(user_id: str, doc_id: Optional[str] = None, source: Optional[str] = None) -> int:
    """
    Hapus embeddings lama untuk 1 dokumen.
    Prioritas: user_id + doc_id.
    Fallback: user_id + source (untuk data lama yang belum punya doc_id).

    Return jumlah vector terhapus (best effort; kadang Chroma tidak mengembalikan count).
    """
    vs = get_vectorstore()
    col = _get_collection(vs)
    if col is None:
        logger.warning("vector_ops: collection not found; skip delete")
        return 0

    if doc_id:
        where = {"$and": [{"user_id": str(user_id)}, {"doc_id": str(doc_id)}]}
    elif source:
        where = {"$and": [{"user_id": str(user_id)}, {"source": str(source)}]}
    else:
        # unsafe: jangan delete kalau tidak ada identitas dokumen
        return 0

    # best-effort count
    count = 0
    try:
        got = col.get(where=where)
        count = len(got.get("ids", []) or [])
    except Exception:
        pass

    try:
        col.delete(where=where)
        try:
            vs.persist()
        except Exception:
            pass
        return count
    except Exception as e:
        logger.warning("vector_ops: delete_vectors_for_doc failed err=%r where=%s", e, where)
        return 0


def purge_vectors_for_user(user_id: int) -> int:
    """
    Hapus SEMUA embeddings milik user tertentu.
    Return jumlah vector terhapus (best effort).
    """
    vs = get_vectorstore()
    col = _get_collection(vs)
    if col is None:
        logger.warning("vector_ops: collection not found; skip purge")
        return 0

    where = {"user_id": str(user_id)}

    # best-effort count
    count = 0
    try:
        got = col.get(where=where)
        count = len(got.get("ids", []) or [])
    except Exception:
        pass

    try:
        col.delete(where=where)
        try:
            vs.persist()
        except Exception:
            pass

        logger.warning(" PURGE vectors user_id=%s deleted≈%s", user_id, count)
        return count
    except Exception as e:
        logger.warning("vector_ops: purge_vectors_for_user failed err=%r where=%s", e, where)
        return 0
