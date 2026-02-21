from __future__ import annotations

from typing import Optional, Tuple

from core.ai_engine.config import get_vectorstore
from core.ai_engine.ingest import process_document
from core.ai_engine.vector_ops import delete_vectors_for_doc, delete_vectors_for_doc_strict

__all__ = [
    "process_document",
    "delete_vectors_for_doc",
    "delete_vectors_for_doc_strict",
    "get_vectorstore",
]


def strict_delete_for_doc(user_id: str, doc_id: Optional[str] = None, source: Optional[str] = None) -> Tuple[bool, int]:
    return delete_vectors_for_doc_strict(user_id=user_id, doc_id=doc_id, source=source)

