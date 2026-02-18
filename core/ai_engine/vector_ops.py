# core/ai_engine/vector_ops.py
from __future__ import annotations

from typing import Optional, Tuple
import logging
import time

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


def _build_where(user_id: str, doc_id: Optional[str] = None, source: Optional[str] = None):
    if doc_id:
        return {"$and": [{"user_id": str(user_id)}, {"doc_id": str(doc_id)}]}
    if source:
        return {"$and": [{"user_id": str(user_id)}, {"source": str(source)}]}
    return None


def _count_ids(col, where) -> int:
    got = col.get(where=where)
    return len(got.get("ids", []) or [])


def delete_vectors_for_doc_strict(
    user_id: str,
    doc_id: Optional[str] = None,
    source: Optional[str] = None,
    retries: int = 3,
    sleep_ms: int = 120,
) -> Tuple[bool, int]:
    """
    Strict delete untuk memastikan vector benar-benar hilang.
    Return: (ok, remaining_vectors)
    """
    vs = get_vectorstore()
    col = _get_collection(vs)
    if col is None:
        logger.error("vector_ops strict: collection not found")
        return False, -1

    where = _build_where(user_id=user_id, doc_id=doc_id, source=source)
    if where is None:
        logger.error("vector_ops strict: missing identity user_id=%s doc_id=%s source=%s", user_id, doc_id, source)
        return False, -1

    for attempt in range(1, max(1, retries) + 1):
        try:
            col.delete(where=where)
            try:
                vs.persist()
            except Exception:
                pass
        except Exception as e:
            logger.warning("vector_ops strict: delete failed attempt=%s where=%s err=%r", attempt, where, e)

        try:
            remaining = _count_ids(col, where)
        except Exception as e:
            logger.warning("vector_ops strict: verify failed attempt=%s where=%s err=%r", attempt, where, e)
            remaining = -1

        if remaining == 0:
            return True, 0

        if attempt < retries:
            time.sleep(max(0, sleep_ms) / 1000.0)

    # final verify (best effort)
    try:
        remaining = _count_ids(col, where)
    except Exception:
        remaining = -1

    logger.error(
        "vector_ops strict: vectors still present user_id=%s doc_id=%s source=%s remaining=%s",
        user_id,
        doc_id,
        source,
        remaining,
    )
    return False, remaining


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
