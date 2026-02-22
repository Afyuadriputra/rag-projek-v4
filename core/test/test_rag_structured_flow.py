from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from core.ai_engine.retrieval.main import ask_bot


def _doc(text: str, source: str = "pedoman.pdf", doc_id: str = "1", page: int = 1):
    return SimpleNamespace(page_content=text, metadata={"source": source, "doc_id": doc_id, "page": page})


class RagStructuredFlowTests(SimpleTestCase):
    @patch("core.ai_engine.retrieval.main.run_structured_analytics")
    @patch("core.ai_engine.retrieval.main._has_user_documents")
    @patch("core.ai_engine.retrieval.main.retrieve_dense")
    @patch("core.ai_engine.retrieval.main.create_stuff_documents_chain")
    @patch("core.ai_engine.retrieval.main.get_runtime_openrouter_config")
    def test_analytical_intent_bypasses_dense_retrieval(
        self,
        cfg_mock,
        chain_mock,
        dense_mock,
        has_docs_mock,
        structured_mock,
    ):
        has_docs_mock.return_value = True
        cfg_mock.return_value = {"api_key": "key", "model": "m", "backup_models": ["m"]}
        structured_mock.return_value = {
            "ok": True,
            "doc_type": "transcript",
            "answer": "deterministic",
            "sources": [{"source": "khs.pdf", "snippet": "x"}],
            "facts": [{"semester": 3, "mata_kuliah": "Algoritma", "sks": 3, "nilai_huruf": "B"}],
            "stats": {"raw": 2, "deduped": 1, "returned": 1, "latency_ms": 5},
        }

        out = ask_bot(user_id=1, query="rekap nilai rendah saya", request_id="sf-1")
        self.assertEqual(out.get("meta", {}).get("pipeline"), "structured_analytics")
        self.assertEqual(out.get("meta", {}).get("intent_route"), "analytical_tabular")
        dense_mock.assert_not_called()
        chain_mock.assert_not_called()

    @patch("core.ai_engine.retrieval.main._has_user_documents")
    @patch("core.ai_engine.retrieval.main.create_stuff_documents_chain")
    @patch("core.ai_engine.retrieval.main.build_llm")
    @patch("core.ai_engine.retrieval.main.get_backup_models")
    @patch("core.ai_engine.retrieval.main.retrieve_dense")
    @patch("core.ai_engine.retrieval.main.get_vectorstore")
    @patch("core.ai_engine.retrieval.main.get_runtime_openrouter_config")
    def test_semantic_policy_uses_policy_doc_filter(
        self,
        cfg_mock,
        _vs_mock,
        dense_mock,
        backup_mock,
        _build_llm_mock,
        chain_mock,
        has_docs_mock,
    ):
        has_docs_mock.return_value = True
        cfg_mock.return_value = {"api_key": "key", "model": "m", "backup_models": ["m"]}
        backup_mock.return_value = ["m"]
        dense_mock.return_value = [(_doc("syarat lulus", source="pedoman.pdf"), 0.9)]
        fake_chain = MagicMock()
        fake_chain.invoke.return_value = {"answer": "Syarat lulus ada [source: pedoman.pdf]"}
        chain_mock.return_value = fake_chain

        out = ask_bot(user_id=1, query="apa syarat lulus skripsi?", request_id="sf-2")
        where = dense_mock.call_args.kwargs.get("filter_where") or {}
        self.assertIn("guideline", str(where))
        self.assertEqual(out.get("meta", {}).get("intent_route"), "semantic_policy")

    @patch("core.ai_engine.retrieval.main.retrieve_dense")
    @patch("core.ai_engine.retrieval.main.create_stuff_documents_chain")
    @patch("core.ai_engine.retrieval.main.get_runtime_openrouter_config")
    def test_out_of_domain_returns_fast_guard_without_vector_lookup(self, cfg_mock, chain_mock, dense_mock):
        cfg_mock.return_value = {"api_key": "key", "model": "m", "backup_models": ["m"]}
        out = ask_bot(user_id=1, query="resep ayam kecap enak", request_id="sf-3")
        self.assertIn("asisten akademik", out.get("answer", "").lower())
        self.assertEqual(out.get("meta", {}).get("intent_route"), "out_of_domain")
        dense_mock.assert_not_called()
        chain_mock.assert_not_called()

    @patch("core.ai_engine.retrieval.main.run_structured_analytics")
    @patch("core.ai_engine.retrieval.main._has_user_documents")
    @patch("core.ai_engine.retrieval.main.retrieve_dense")
    @patch("core.ai_engine.retrieval.main.get_runtime_openrouter_config")
    def test_transcript_analytical_empty_does_not_fallback_to_dense(
        self,
        cfg_mock,
        dense_mock,
        has_docs_mock,
        structured_mock,
    ):
        has_docs_mock.return_value = True
        cfg_mock.return_value = {"api_key": "key", "model": "m", "backup_models": ["m"]}
        structured_mock.return_value = {
            "ok": False,
            "doc_type": "transcript",
            "answer": "## Ringkasan\nMaaf, data tidak ditemukan di dokumen Anda.",
            "sources": [],
            "facts": [],
            "stats": {"raw": 0, "deduped": 0, "returned": 0, "latency_ms": 5},
            "reason": "no_row_chunks",
        }

        out = ask_bot(user_id=1, query="rekap transkrip khs saya", request_id="sf-4")
        self.assertEqual(out.get("meta", {}).get("pipeline"), "structured_analytics")
        self.assertEqual(out.get("meta", {}).get("validation"), "strict_no_fallback")
        dense_mock.assert_not_called()

    @patch("core.ai_engine.retrieval.main.polish_structured_answer")
    @patch("core.ai_engine.retrieval.main.run_structured_analytics")
    @patch("core.ai_engine.retrieval.main._has_user_documents")
    @patch("core.ai_engine.retrieval.main.retrieve_dense")
    @patch("core.ai_engine.retrieval.main.get_runtime_openrouter_config")
    def test_hasil_studi_query_allows_llm_polish_with_validation(
        self,
        cfg_mock,
        dense_mock,
        has_docs_mock,
        structured_mock,
        polish_mock,
    ):
        has_docs_mock.return_value = True
        cfg_mock.return_value = {"api_key": "key", "model": "m", "backup_models": ["m"]}
        structured_mock.return_value = {
            "ok": True,
            "doc_type": "transcript",
            "answer": "deterministic answer",
            "sources": [{"source": "khs.pdf", "snippet": "x"}],
            "facts": [{"semester": 3, "mata_kuliah": "Algoritma", "sks": 3, "nilai_huruf": "B"}],
            "stats": {"raw": 2, "deduped": 1, "returned": 1, "latency_ms": 5},
        }
        polish_mock.return_value = {"answer": "jawaban rapi tervalidasi", "validation": "passed"}

        out = ask_bot(user_id=1, query="bagaimana hasil studi saya ini?", request_id="sf-5")
        self.assertEqual(out.get("meta", {}).get("pipeline"), "structured_analytics")
        self.assertEqual(out.get("meta", {}).get("validation"), "passed")
        self.assertEqual(out.get("answer"), "jawaban rapi tervalidasi")
        polish_mock.assert_called_once()
        dense_mock.assert_not_called()
