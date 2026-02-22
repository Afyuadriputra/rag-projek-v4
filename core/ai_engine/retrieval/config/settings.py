from __future__ import annotations

from dataclasses import dataclass
import os


def _env_bool(name: str, default: bool = False) -> bool:
    val = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return val in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except Exception:
        return int(default)


@dataclass(frozen=True)
class RetrievalSettings:
    refactor_chat_service_enabled: bool = False
    refactor_structured_pipeline_enabled: bool = False
    grounding_policy_v2_enabled: bool = True
    metric_enrichment_enabled: bool = True
    semantic_optimized_retrieval_enabled: bool = False
    semantic_optimized_traffic_pct: int = 100
    semantic_optimized_legacy_fallback_enabled: bool = False

    rag_dense_k: int = 30
    rag_bm25_k: int = 40
    rag_rerank_top_n: int = 8
    rag_retry_sleep_ms: int = 300
    rag_route_cache_ttl_s: int = 30
    rag_mention_cache_ttl_s: int = 30
    rag_user_docs_cache_ttl_s: int = 60


def get_retrieval_settings() -> RetrievalSettings:
    return RetrievalSettings(
        refactor_chat_service_enabled=_env_bool("RAG_REFACTOR_CHAT_SERVICE_ENABLED", default=False),
        refactor_structured_pipeline_enabled=_env_bool("RAG_REFACTOR_STRUCTURED_PIPELINE_ENABLED", default=False),
        grounding_policy_v2_enabled=_env_bool("RAG_GROUNDING_POLICY_V2_ENABLED", default=True),
        metric_enrichment_enabled=_env_bool("RAG_METRIC_ENRICHMENT_ENABLED", default=True),
        semantic_optimized_retrieval_enabled=_env_bool("RAG_SEMANTIC_OPTIMIZED_RETRIEVAL_ENABLED", default=False),
        semantic_optimized_traffic_pct=max(min(_env_int("RAG_SEMANTIC_OPTIMIZED_TRAFFIC_PCT", 100), 100), 0),
        semantic_optimized_legacy_fallback_enabled=_env_bool(
            "RAG_SEMANTIC_OPTIMIZED_LEGACY_FALLBACK_ENABLED",
            default=False,
        ),
        rag_dense_k=_env_int("RAG_DENSE_K", 30),
        rag_bm25_k=_env_int("RAG_BM25_K", 40),
        rag_rerank_top_n=_env_int("RAG_RERANK_TOP_N", 8),
        rag_retry_sleep_ms=_env_int("RAG_RETRY_SLEEP_MS", 300),
        rag_route_cache_ttl_s=_env_int("RAG_ROUTE_CACHE_TTL_S", 30),
        rag_mention_cache_ttl_s=_env_int("RAG_MENTION_CACHE_TTL_S", 30),
        rag_user_docs_cache_ttl_s=_env_int("RAG_USER_DOCS_CACHE_TTL_S", 60),
    )
