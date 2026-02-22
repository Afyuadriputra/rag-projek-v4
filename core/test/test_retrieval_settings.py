import os

from django.test import SimpleTestCase

from core.ai_engine.retrieval.config.settings import get_retrieval_settings


class RetrievalSettingsTests(SimpleTestCase):
    def test_defaults(self):
        os.environ.pop("RAG_REFACTOR_CHAT_SERVICE_ENABLED", None)
        os.environ.pop("RAG_REFACTOR_STRUCTURED_PIPELINE_ENABLED", None)
        os.environ.pop("RAG_GROUNDING_POLICY_V2_ENABLED", None)
        os.environ.pop("RAG_METRIC_ENRICHMENT_ENABLED", None)
        os.environ.pop("RAG_SEMANTIC_OPTIMIZED_RETRIEVAL_ENABLED", None)
        os.environ.pop("RAG_SEMANTIC_OPTIMIZED_TRAFFIC_PCT", None)
        os.environ.pop("RAG_SEMANTIC_OPTIMIZED_LEGACY_FALLBACK_ENABLED", None)
        os.environ.pop("RAG_USER_DOCS_CACHE_TTL_S", None)
        s = get_retrieval_settings()
        self.assertFalse(s.refactor_chat_service_enabled)
        self.assertFalse(s.refactor_structured_pipeline_enabled)
        self.assertTrue(s.grounding_policy_v2_enabled)
        self.assertTrue(s.metric_enrichment_enabled)
        self.assertFalse(s.semantic_optimized_retrieval_enabled)
        self.assertEqual(s.semantic_optimized_traffic_pct, 100)
        self.assertFalse(s.semantic_optimized_legacy_fallback_enabled)
        self.assertEqual(s.rag_user_docs_cache_ttl_s, 60)

    def test_env_override(self):
        os.environ["RAG_REFACTOR_CHAT_SERVICE_ENABLED"] = "1"
        os.environ["RAG_REFACTOR_STRUCTURED_PIPELINE_ENABLED"] = "true"
        os.environ["RAG_GROUNDING_POLICY_V2_ENABLED"] = "0"
        os.environ["RAG_METRIC_ENRICHMENT_ENABLED"] = "0"
        os.environ["RAG_SEMANTIC_OPTIMIZED_RETRIEVAL_ENABLED"] = "1"
        os.environ["RAG_SEMANTIC_OPTIMIZED_TRAFFIC_PCT"] = "50"
        os.environ["RAG_SEMANTIC_OPTIMIZED_LEGACY_FALLBACK_ENABLED"] = "1"
        os.environ["RAG_USER_DOCS_CACHE_TTL_S"] = "90"
        s = get_retrieval_settings()
        self.assertTrue(s.refactor_chat_service_enabled)
        self.assertTrue(s.refactor_structured_pipeline_enabled)
        self.assertFalse(s.grounding_policy_v2_enabled)
        self.assertFalse(s.metric_enrichment_enabled)
        self.assertTrue(s.semantic_optimized_retrieval_enabled)
        self.assertEqual(s.semantic_optimized_traffic_pct, 50)
        self.assertTrue(s.semantic_optimized_legacy_fallback_enabled)
        self.assertEqual(s.rag_user_docs_cache_ttl_s, 90)
