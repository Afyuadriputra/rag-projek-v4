from django.test import SimpleTestCase
from unittest.mock import patch

from core.ai_engine.retrieval.application.chat_service import ask_bot
from core.ai_engine.retrieval.config.settings import RetrievalSettings


class ChatServiceModularTests(SimpleTestCase):
    @patch("core.ai_engine.retrieval.application.chat_service.run_semantic")
    @patch("core.ai_engine.retrieval.application.chat_service.run_structured")
    @patch("core.ai_engine.retrieval.application.chat_service.resolve_route")
    @patch("core.ai_engine.retrieval.application.chat_service.has_user_documents")
    @patch("core.ai_engine.retrieval.application.chat_service.resolve_mentions")
    @patch("core.ai_engine.retrieval.application.chat_service.extract_mentions")
    @patch("core.ai_engine.retrieval.application.chat_service.classify_safety")
    @patch("core.ai_engine.retrieval.application.chat_service.get_retrieval_settings")
    def test_enriches_semantic_meta_defaults(
        self,
        settings_mock,
        safety_mock,
        extract_mock,
        resolve_mentions_mock,
        has_docs_mock,
        resolve_route_mock,
        run_structured_mock,
        run_semantic_mock,
    ):
        settings_mock.return_value = RetrievalSettings(metric_enrichment_enabled=True)
        safety_mock.return_value = {"decision": "allow"}
        extract_mock.return_value = ("cek nilai saya", [])
        resolve_mentions_mock.return_value = {
            "resolved_doc_ids": [],
            "resolved_titles": [],
            "unresolved_mentions": [],
            "ambiguous_mentions": [],
        }
        has_docs_mock.return_value = False
        resolve_route_mock.return_value = {"route": "default_rag", "reason": "ok", "matched": []}
        run_structured_mock.return_value = None
        run_semantic_mock.return_value = {"answer": "ok", "sources": [{"source": "khs.pdf"}], "meta": {}}

        out = ask_bot(user_id=1, query="cek nilai saya", request_id="rid-1")
        meta = out.get("meta") or {}

        self.assertEqual(meta.get("pipeline"), "rag_semantic")
        self.assertEqual(meta.get("intent_route"), "default_rag")
        self.assertEqual(meta.get("validation"), "not_applicable")
        self.assertEqual(meta.get("answer_mode"), "factual")
        self.assertIn("stage_timings_ms", meta)

    @patch("core.ai_engine.retrieval.application.chat_service.run_semantic")
    @patch("core.ai_engine.retrieval.application.chat_service.run_structured")
    @patch("core.ai_engine.retrieval.application.chat_service.resolve_route")
    @patch("core.ai_engine.retrieval.application.chat_service.has_user_documents")
    @patch("core.ai_engine.retrieval.application.chat_service.resolve_mentions")
    @patch("core.ai_engine.retrieval.application.chat_service.extract_mentions")
    @patch("core.ai_engine.retrieval.application.chat_service.classify_safety")
    @patch("core.ai_engine.retrieval.application.chat_service.get_retrieval_settings")
    def test_can_disable_metric_enrichment(
        self,
        settings_mock,
        safety_mock,
        extract_mock,
        resolve_mentions_mock,
        has_docs_mock,
        resolve_route_mock,
        run_structured_mock,
        run_semantic_mock,
    ):
        settings_mock.return_value = RetrievalSettings(metric_enrichment_enabled=False)
        safety_mock.return_value = {"decision": "allow"}
        extract_mock.return_value = ("apa itu sks", [])
        resolve_mentions_mock.return_value = {
            "resolved_doc_ids": [],
            "resolved_titles": [],
            "unresolved_mentions": [],
            "ambiguous_mentions": [],
        }
        has_docs_mock.return_value = False
        resolve_route_mock.return_value = {"route": "default_rag", "reason": "ok", "matched": []}
        run_structured_mock.return_value = None
        run_semantic_mock.return_value = {"answer": "ok", "sources": [], "meta": {"pipeline": "rag_semantic"}}

        out = ask_bot(user_id=1, query="apa itu sks", request_id="rid-3")
        self.assertEqual(out.get("meta"), {"pipeline": "rag_semantic"})
