from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ....config import get_vectorstore


def fetch_row_chunks(user_id: int, doc_type: str, doc_ids: List[int] | None = None) -> List[Tuple[str, Dict[str, Any]]]:
    try:
        vs = get_vectorstore()
        col = getattr(vs, "_collection", None) or getattr(vs, "collection", None)
        if col is None:
            return []

        where_parts: List[Dict[str, Any]] = [
            {"user_id": str(user_id)},
            {"chunk_kind": "row"},
            {"doc_type": str(doc_type)},
        ]
        if doc_ids:
            where_parts.append({"doc_id": {"$in": [str(x) for x in doc_ids]}})

        where = {"$and": where_parts}
        used_fallback_filter = False
        try:
            got = col.get(where=where, include=["documents", "metadatas"])
        except Exception:
            used_fallback_filter = True
            try:
                got = col.get(where={"user_id": str(user_id)}, include=["documents", "metadatas"])
            except Exception:
                got = col.get(where={"user_id": str(user_id)})

        docs = list(got.get("documents", []) or [])
        metas = list(got.get("metadatas", []) or [])
        out: List[Tuple[str, Dict[str, Any]]] = []
        doc_id_set = {str(x) for x in (doc_ids or [])}
        for i, text in enumerate(docs):
            chunk = str(text or "").strip()
            if not chunk:
                continue
            meta = metas[i] if i < len(metas) and isinstance(metas[i], dict) else {}
            if used_fallback_filter:
                if str(meta.get("chunk_kind") or "").strip().lower() != "row":
                    continue
                if str(meta.get("doc_type") or "").strip().lower() != str(doc_type or "").strip().lower():
                    continue
                if doc_id_set and str(meta.get("doc_id")) not in doc_id_set:
                    continue
            out.append((chunk, meta))
        return out
    except Exception:
        return []


def fetch_transcript_text_chunks(user_id: int, doc_ids: List[int] | None = None) -> List[str]:
    try:
        vs = get_vectorstore()
        col = getattr(vs, "_collection", None) or getattr(vs, "collection", None)
        if col is None:
            return []

        where_parts: List[Dict[str, Any]] = [
            {"user_id": str(user_id)},
            {"doc_type": "transcript"},
            {"chunk_kind": "text"},
        ]
        if doc_ids:
            where_parts.append({"doc_id": {"$in": [str(x) for x in doc_ids]}})

        where = {"$and": where_parts}
        used_fallback_filter = False
        try:
            got = col.get(where=where, include=["documents", "metadatas"])
        except Exception:
            used_fallback_filter = True
            try:
                got = col.get(where={"user_id": str(user_id)}, include=["documents", "metadatas"])
            except Exception:
                got = col.get(where={"user_id": str(user_id)})

        docs = list(got.get("documents", []) or [])
        metas = list(got.get("metadatas", []) or [])
        out: List[str] = []
        doc_id_set = {str(x) for x in (doc_ids or [])}
        for i, text in enumerate(docs):
            chunk = str(text or "").strip()
            if not chunk:
                continue
            if used_fallback_filter:
                meta = metas[i] if i < len(metas) and isinstance(metas[i], dict) else {}
                if str(meta.get("doc_type") or "").strip().lower() != "transcript":
                    continue
                if str(meta.get("chunk_kind") or "").strip().lower() != "text":
                    continue
                if doc_id_set and str(meta.get("doc_id")) not in doc_id_set:
                    continue
            out.append(chunk)
        return out
    except Exception:
        return []
