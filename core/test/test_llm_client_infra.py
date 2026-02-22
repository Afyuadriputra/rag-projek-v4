from unittest.mock import patch

from django.test import SimpleTestCase

from core.ai_engine.retrieval.config.settings import RetrievalSettings
from core.ai_engine.retrieval.infrastructure import llm_client


class LlmClientInfraTests(SimpleTestCase):
    @patch(
        "core.ai_engine.retrieval.infrastructure.llm_client.get_retrieval_settings",
        return_value=RetrievalSettings(semantic_optimized_retrieval_enabled=False),
    )
    @patch("core.ai_engine.retrieval.infrastructure.llm_client.invoke", return_value="jawaban")
    @patch("core.ai_engine.retrieval.infrastructure.llm_client.build", return_value=object())
    @patch("core.ai_engine.retrieval.infrastructure.llm_client.backup_models", return_value=["model-a"])
    def test_invoke_with_model_fallback_primary_success(self, _settings, _bm, _build, _invoke):
        out = llm_client.invoke_with_model_fallback(prompt="halo", cfg={"model": "model-a"})
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("text"), "jawaban")
        self.assertEqual(out.get("model"), "model-a")
        self.assertFalse(out.get("fallback_used"))

    @patch(
        "core.ai_engine.retrieval.infrastructure.llm_client.get_retrieval_settings",
        return_value=RetrievalSettings(semantic_optimized_retrieval_enabled=False),
    )
    @patch("core.ai_engine.retrieval.infrastructure.llm_client.time.sleep")
    @patch("core.ai_engine.retrieval.infrastructure.llm_client.get_retry_sleep_seconds", return_value=0.01)
    @patch("core.ai_engine.retrieval.infrastructure.llm_client.invoke", return_value="ok-backup")
    @patch(
        "core.ai_engine.retrieval.infrastructure.llm_client.build",
        side_effect=[RuntimeError("primary down"), object()],
    )
    @patch("core.ai_engine.retrieval.infrastructure.llm_client.backup_models", return_value=["primary", "backup"])
    def test_invoke_with_model_fallback_uses_backup(
        self, _settings, _bm, _build, _invoke, _retry, sleep_mock
    ):
        out = llm_client.invoke_with_model_fallback(prompt="halo", cfg={"model": "primary"})
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("model"), "backup")
        self.assertTrue(out.get("fallback_used"))
        self.assertTrue(sleep_mock.called)

    @patch(
        "core.ai_engine.retrieval.infrastructure.llm_client.get_retrieval_settings",
        return_value=RetrievalSettings(semantic_optimized_retrieval_enabled=False),
    )
    @patch("core.ai_engine.retrieval.infrastructure.llm_client.build", side_effect=RuntimeError("all-down"))
    @patch("core.ai_engine.retrieval.infrastructure.llm_client.backup_models", return_value=["m1"])
    def test_invoke_with_model_fallback_all_failed(self, _settings, _bm, _build):
        out = llm_client.invoke_with_model_fallback(prompt="halo", cfg={"model": "m1"})
        self.assertFalse(out.get("ok"))
        self.assertIn("all-down", out.get("error", ""))

    @patch("core.ai_engine.retrieval.infrastructure.llm_client.get_retrieval_settings")
    def test_retry_sleep_seconds_from_settings(self, settings_mock):
        settings_mock.return_value = RetrievalSettings(rag_retry_sleep_ms=750)
        self.assertEqual(llm_client.get_retry_sleep_seconds(), 0.75)
