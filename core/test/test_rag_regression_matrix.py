from unittest.mock import patch

from django.test import SimpleTestCase

from core.ai_engine.retrieval.main import ask_bot


class RagRegressionMatrixTests(SimpleTestCase):
    @patch("core.ai_engine.retrieval.main.get_runtime_openrouter_config")
    def test_out_of_domain_still_guarded(self, cfg_mock):
        cfg_mock.return_value = {"api_key": "k", "model": "m", "backup_models": ["m"]}
        out = ask_bot(user_id=1, query="resep ayam kecap pedas", request_id="rm-1")
        self.assertEqual(out.get("meta", {}).get("intent_route"), "out_of_domain")

    @patch("core.ai_engine.retrieval.main.get_runtime_openrouter_config")
    def test_weird_query_redirected(self, cfg_mock):
        cfg_mock.return_value = {"api_key": "k", "model": "m", "backup_models": ["m"]}
        out = ask_bot(user_id=1, query="cara jadi dukun", request_id="rm-2")
        self.assertEqual(out.get("meta", {}).get("mode"), "guard")

    @patch("core.ai_engine.retrieval.main.get_runtime_openrouter_config")
    @patch("core.ai_engine.retrieval.main._has_user_documents")
    @patch("core.ai_engine.retrieval.main.retrieve_dense")
    @patch("core.ai_engine.retrieval.main.get_vectorstore")
    @patch("core.ai_engine.retrieval.main.create_stuff_documents_chain")
    def test_personal_typo_query_without_docs_abstains(
        self,
        chain_mock,
        _vs_mock,
        dense_mock,
        has_docs_mock,
        cfg_mock,
    ):
        cfg_mock.return_value = {"api_key": "k", "model": "m", "backup_models": ["m"]}
        has_docs_mock.return_value = True
        dense_mock.return_value = []
        out = ask_bot(user_id=1, query="brp nilai saya?", request_id="rm-3")
        self.assertEqual(out.get("meta", {}).get("validation"), "no_grounding_evidence")
        chain_mock.assert_not_called()
