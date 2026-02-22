from django.test import SimpleTestCase
from unittest.mock import patch

from core.ai_engine.retrieval.application.chat_service import ask_bot
from core.ai_engine.retrieval.config.settings import RetrievalSettings


class ChatServiceOrchestrationTests(SimpleTestCase):
    @patch("core.ai_engine.retrieval.application.chat_service.build_guard_response")
    @patch("core.ai_engine.retrieval.application.chat_service.classify_safety")
    @patch("core.ai_engine.retrieval.application.chat_service.get_retrieval_settings")
    def test_guard_route_short_circuit(self, settings_mock, safety_mock, guard_response_mock):
        settings_mock.return_value = RetrievalSettings(metric_enrichment_enabled=True)
        safety_mock.return_value = {"decision": "refuse_crime"}
        guard_response_mock.return_value = {"answer": "blocked", "sources": [], "meta": {}}

        out = ask_bot(user_id=1, query="judi online", request_id="rid-g")
        self.assertEqual(out.get("answer"), "blocked")
        self.assertEqual(out.get("meta", {}).get("pipeline"), "route_guard")

    @patch("core.ai_engine.retrieval.application.chat_service.run_semantic")
    @patch("core.ai_engine.retrieval.application.chat_service.run_structured")
    @patch("core.ai_engine.retrieval.application.chat_service.resolve_route")
    @patch("core.ai_engine.retrieval.application.chat_service.has_user_documents")
    @patch("core.ai_engine.retrieval.application.chat_service.resolve_mentions")
    @patch("core.ai_engine.retrieval.application.chat_service.extract_mentions")
    @patch("core.ai_engine.retrieval.application.chat_service.classify_safety")
    @patch("core.ai_engine.retrieval.application.chat_service.get_retrieval_settings")
    def test_structured_route_short_circuit(
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
        extract_mock.return_value = ("rekap nilai saya", [])
        resolve_mentions_mock.return_value = {
            "resolved_doc_ids": [],
            "resolved_titles": [],
            "unresolved_mentions": [],
            "ambiguous_mentions": [],
        }
        has_docs_mock.return_value = True
        resolve_route_mock.return_value = {"route": "analytical_tabular", "reason": "matched", "matched": ["rekap"]}
        run_structured_mock.return_value = {
            "answer": "structured",
            "sources": [{"source": "khs.pdf"}],
            "meta": {"pipeline": "structured_analytics", "validation": "passed"},
        }

        out = ask_bot(user_id=1, query="rekap nilai saya", request_id="rid-s")
        self.assertEqual(out.get("answer"), "structured")
        self.assertEqual(out.get("meta", {}).get("pipeline"), "structured_analytics")
        run_semantic_mock.assert_not_called()

    @patch("core.ai_engine.retrieval.application.chat_service.build_out_of_domain_response")
    @patch("core.ai_engine.retrieval.application.chat_service.resolve_route")
    @patch("core.ai_engine.retrieval.application.chat_service.has_user_documents")
    @patch("core.ai_engine.retrieval.application.chat_service.resolve_mentions")
    @patch("core.ai_engine.retrieval.application.chat_service.extract_mentions")
    @patch("core.ai_engine.retrieval.application.chat_service.classify_safety")
    @patch("core.ai_engine.retrieval.application.chat_service.get_retrieval_settings")
    def test_out_of_domain_route(
        self,
        settings_mock,
        safety_mock,
        extract_mock,
        resolve_mentions_mock,
        has_docs_mock,
        resolve_route_mock,
        out_domain_mock,
    ):
        settings_mock.return_value = RetrievalSettings(metric_enrichment_enabled=True)
        safety_mock.return_value = {"decision": "allow"}
        extract_mock.return_value = ("resep ayam", [])
        resolve_mentions_mock.return_value = {
            "resolved_doc_ids": [],
            "resolved_titles": [],
            "unresolved_mentions": [],
            "ambiguous_mentions": [],
        }
        has_docs_mock.return_value = False
        resolve_route_mock.return_value = {"route": "out_of_domain", "reason": "matched", "matched": ["resep"]}
        out_domain_mock.return_value = {"answer": "ood", "sources": [], "meta": {"pipeline": "route_guard"}}

        out = ask_bot(user_id=1, query="resep ayam", request_id="rid-o")
        self.assertEqual(out.get("answer"), "ood")
        self.assertEqual(out.get("meta", {}).get("pipeline"), "route_guard")
