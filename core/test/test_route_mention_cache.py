from django.core.cache import cache
from django.test import SimpleTestCase
from unittest.mock import patch

from core.ai_engine.retrieval.application.mention_service import resolve_mentions
from core.ai_engine.retrieval.application.route_service import resolve_route
from core.ai_engine.retrieval.config.settings import RetrievalSettings


class RouteMentionCacheTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch("core.ai_engine.retrieval.application.route_service.route_intent")
    @patch("core.ai_engine.retrieval.application.route_service.get_retrieval_settings")
    def test_route_resolution_uses_cache(self, settings_mock, route_mock):
        settings_mock.return_value = RetrievalSettings(rag_route_cache_ttl_s=60)
        route_mock.return_value = {"route": "default_rag", "reason": "x", "matched": []}

        out1 = resolve_route("rekap nilai")
        out2 = resolve_route("rekap nilai")

        self.assertEqual(out1, out2)
        route_mock.assert_called_once()

    @patch("core.ai_engine.retrieval.main._resolve_user_doc_mentions")
    @patch("core.ai_engine.retrieval.application.mention_service.get_retrieval_settings")
    def test_mention_resolution_uses_cache(self, settings_mock, resolve_mock):
        settings_mock.return_value = RetrievalSettings(rag_mention_cache_ttl_s=60)
        resolve_mock.return_value = {
            "resolved_doc_ids": [1],
            "resolved_titles": ["KHS"],
            "unresolved_mentions": [],
            "ambiguous_mentions": [],
        }

        out1 = resolve_mentions(1, ["khs.pdf"])
        out2 = resolve_mentions(1, ["khs.pdf"])

        self.assertEqual(out1, out2)
        resolve_mock.assert_called_once()
