from __future__ import annotations

"""
Facade module for retrieval orchestration.

This keeps `core.ai_engine.retrieval.main.ask_bot` as the public API while
moving heavy logic to `main_legacy.py` for maintainability and gradual
modular migration.
"""

from typing import Any, Dict

from . import main_legacy as _legacy_module

from .config.settings import get_retrieval_settings

# Explicit compatibility aliases for patched private/helpers in tests.
_LEGACY_HAS_USER_DOCUMENTS_FN = _legacy_module._has_user_documents
_LEGACY_RESOLVE_USER_DOC_MENTIONS_FN = _legacy_module._resolve_user_doc_mentions
AcademicDocument = _legacy_module.AcademicDocument
build_llm = _legacy_module.build_llm
create_stuff_documents_chain = _legacy_module.create_stuff_documents_chain
fuse_rrf = _legacy_module.fuse_rrf
get_backup_models = _legacy_module.get_backup_models
get_runtime_openrouter_config = _legacy_module.get_runtime_openrouter_config
get_vectorstore = _legacy_module.get_vectorstore
invoke_text = _legacy_module.invoke_text
polish_structured_answer = _legacy_module.polish_structured_answer
rerank_documents = _legacy_module.rerank_documents
retrieve_dense = _legacy_module.retrieve_dense
retrieve_sparse_bm25 = _legacy_module.retrieve_sparse_bm25
run_structured_analytics = _legacy_module.run_structured_analytics
infer_doc_type = _legacy_module.infer_doc_type
_build_chroma_filter = _legacy_module._build_chroma_filter
_extract_doc_mentions = _legacy_module._extract_doc_mentions
_normalize_doc_key = _legacy_module._normalize_doc_key
_dedup_docs = _legacy_module._dedup_docs
_has_citation = _legacy_module._has_citation
_rewrite_queries = _legacy_module._rewrite_queries
_classify_transcript_answer_mode = _legacy_module._classify_transcript_answer_mode


def _has_user_documents(user_id: int) -> bool:
    _sync_legacy_dependencies()
    return bool(_LEGACY_HAS_USER_DOCUMENTS_FN(user_id))


def _resolve_user_doc_mentions(user_id: int, mentions):
    _sync_legacy_dependencies()
    return _LEGACY_RESOLVE_USER_DOC_MENTIONS_FN(user_id, mentions)


def _sync_legacy_dependencies() -> None:
    """Mirror facade symbols into legacy module so patching this module still works."""
    names = [
        "AcademicDocument",
        "_has_user_documents",
        "_resolve_user_doc_mentions",
        "build_llm",
        "create_stuff_documents_chain",
        "fuse_rrf",
        "get_backup_models",
        "get_runtime_openrouter_config",
        "get_vectorstore",
        "invoke_text",
        "polish_structured_answer",
        "rerank_documents",
        "retrieve_dense",
        "retrieve_sparse_bm25",
        "run_structured_analytics",
        "infer_doc_type",
        "_build_chroma_filter",
        "_extract_doc_mentions",
        "_normalize_doc_key",
        "_dedup_docs",
        "_has_citation",
        "_rewrite_queries",
        "_classify_transcript_answer_mode",
    ]
    for name in names:
        setattr(_legacy_module, name, globals()[name])


def _ask_bot_legacy(user_id, query, request_id: str = "-") -> Dict[str, Any]:
    _sync_legacy_dependencies()
    # Call legacy core directly to avoid recursive re-entry when chat-service flag is on.
    return _legacy_module._ask_bot_legacy(user_id=user_id, query=query, request_id=request_id)


def ask_bot(user_id, query, request_id: str = "-") -> Dict[str, Any]:
    """Public compatibility facade with feature-flagged modular path."""
    settings = get_retrieval_settings()
    if settings.refactor_chat_service_enabled:
        from .application.chat_service import ask_bot as modular_ask_bot

        return modular_ask_bot(user_id=user_id, query=query, request_id=request_id)
    return _ask_bot_legacy(user_id=user_id, query=query, request_id=request_id)
