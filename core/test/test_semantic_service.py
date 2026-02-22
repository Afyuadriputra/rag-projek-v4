from django.test import SimpleTestCase
from unittest.mock import patch
from langchain_core.documents import Document

from core.ai_engine.retrieval.application.semantic_service import run_semantic
from core.ai_engine.retrieval.config.settings import RetrievalSettings


class SemanticServiceTests(SimpleTestCase):
    @patch("core.ai_engine.retrieval.application.semantic_service.is_personal_document_query")
    @patch("core.ai_engine.retrieval.application.semantic_service.infer_doc_type")
    @patch("core.ai_engine.retrieval.main._ask_bot_legacy")
    def test_no_grounding_validation(self, ask_mock, infer_mock, personal_mock):
        ask_mock.return_value = {"answer": "x", "sources": [], "meta": {"pipeline": "rag_semantic"}}
        infer_mock.return_value = "transcript"
        personal_mock.return_value = True

        out = run_semantic(
            user_id=1,
            query="nilai saya bagaimana",
            request_id="rid",
            intent_route="default_rag",
            has_docs_hint=True,
            resolved_doc_ids=[],
            resolved_titles=[],
            unresolved_mentions=[],
            ambiguous_mentions=[],
        )
        self.assertEqual(out.get("meta", {}).get("validation"), "no_grounding_evidence")

    @patch("core.ai_engine.retrieval.application.semantic_service.is_personal_document_query")
    @patch("core.ai_engine.retrieval.application.semantic_service.infer_doc_type")
    @patch("core.ai_engine.retrieval.main._ask_bot_legacy")
    def test_preserve_existing_meta(self, ask_mock, infer_mock, personal_mock):
        ask_mock.return_value = {
            "answer": "ok",
            "sources": [{"source": "khs.pdf"}],
            "meta": {"pipeline": "rag_semantic", "intent_route": "default_rag", "validation": "not_applicable"},
        }
        infer_mock.return_value = "general"
        personal_mock.return_value = False

        out = run_semantic(
            user_id=1,
            query="apa itu sks",
            request_id="rid2",
            intent_route="default_rag",
            has_docs_hint=True,
            resolved_doc_ids=[],
            resolved_titles=["KHS"],
            unresolved_mentions=[],
            ambiguous_mentions=[],
        )
        self.assertEqual(out.get("meta", {}).get("pipeline"), "rag_semantic")
        self.assertEqual(out.get("meta", {}).get("retrieval_docs_count"), 1)

    @patch("core.ai_engine.retrieval.application.semantic_service.emit_rag_metric")
    @patch("core.ai_engine.retrieval.application.semantic_service.run_answer")
    @patch("core.ai_engine.retrieval.application.semantic_service.run_retrieval")
    @patch("core.ai_engine.retrieval.application.semantic_service.get_vectorstore")
    @patch("core.ai_engine.retrieval.application.semantic_service.is_personal_document_query", return_value=False)
    @patch("core.ai_engine.retrieval.application.semantic_service.infer_doc_type", return_value="general")
    @patch("core.ai_engine.retrieval.application.semantic_service.get_retrieval_settings")
    def test_semantic_optimized_success(
        self,
        settings_mock,
        _infer_mock,
        _personal_mock,
        _vector_mock,
        retrieve_mock,
        llm_mock,
        metric_mock,
    ):
        settings_mock.return_value = RetrievalSettings(semantic_optimized_retrieval_enabled=True, rag_dense_k=5)
        retrieve_mock.return_value = {
            "mode": "doc_background",
            "docs": [Document(page_content="SKS adalah satuan kredit semester.", metadata={"source": "pedoman.pdf"})],
            "dense_hits": 1,
            "top_score": 0.88,
            "retrieval_ms": 10,
        }
        llm_mock.return_value = {"ok": True, "text": "SKS adalah satuan kredit semester.", "model": "m", "llm_ms": 12}

        out = run_semantic(
            user_id=1,
            query="apa itu sks",
            request_id="rid3",
            intent_route="default_rag",
            has_docs_hint=True,
            resolved_doc_ids=[],
            resolved_titles=[],
            unresolved_mentions=[],
            ambiguous_mentions=[],
        )
        self.assertEqual(out.get("meta", {}).get("pipeline"), "rag_semantic")
        self.assertEqual(out.get("meta", {}).get("retrieval_docs_count"), 1)
        self.assertEqual(out.get("meta", {}).get("validation"), "not_applicable")
        payload = metric_mock.call_args[0][0]
        self.assertEqual(payload.get("mode"), "doc_background")
        self.assertEqual(payload.get("status_code"), 200)

    @patch("core.ai_engine.retrieval.application.semantic_service.emit_rag_metric")
    @patch("core.ai_engine.retrieval.application.semantic_service.run_answer")
    @patch(
        "core.ai_engine.retrieval.application.semantic_service.run_retrieval",
        return_value={"mode": "doc_background", "docs": [], "dense_hits": 0, "top_score": 0.0, "retrieval_ms": 9},
    )
    @patch("core.ai_engine.retrieval.application.semantic_service.get_vectorstore")
    @patch("core.ai_engine.retrieval.application.semantic_service.is_personal_document_query", return_value=True)
    @patch("core.ai_engine.retrieval.application.semantic_service.infer_doc_type", return_value="transcript")
    @patch("core.ai_engine.retrieval.application.semantic_service.get_retrieval_settings")
    def test_semantic_optimized_no_grounding_personal(
        self,
        settings_mock,
        _infer_mock,
        _personal_mock,
        _vector_mock,
        _retrieve_mock,
        llm_mock,
        metric_mock,
    ):
        settings_mock.return_value = RetrievalSettings(semantic_optimized_retrieval_enabled=True, rag_dense_k=5)
        llm_mock.return_value = {"ok": True, "text": "unused", "model": "m", "llm_ms": 12}

        out = run_semantic(
            user_id=1,
            query="nilai saya berapa",
            request_id="rid4",
            intent_route="default_rag",
            has_docs_hint=True,
            resolved_doc_ids=[],
            resolved_titles=[],
            unresolved_mentions=[],
            ambiguous_mentions=[],
        )
        self.assertEqual(out.get("meta", {}).get("validation"), "no_grounding_evidence")
        self.assertEqual(out.get("meta", {}).get("retrieval_docs_count"), 0)
        llm_mock.assert_not_called()
        payload = metric_mock.call_args[0][0]
        self.assertEqual(payload.get("status_code"), 200)

    @patch("core.ai_engine.retrieval.application.semantic_service.emit_rag_metric")
    @patch("core.ai_engine.retrieval.application.semantic_service.run_answer")
    @patch(
        "core.ai_engine.retrieval.application.semantic_service.run_retrieval",
        return_value={"mode": "doc_background", "docs": [], "dense_hits": 0, "top_score": 0.0, "retrieval_ms": 11},
    )
    @patch("core.ai_engine.retrieval.application.semantic_service.get_vectorstore")
    @patch("core.ai_engine.retrieval.application.semantic_service.is_personal_document_query", return_value=False)
    @patch("core.ai_engine.retrieval.application.semantic_service.infer_doc_type", return_value="general")
    @patch("core.ai_engine.retrieval.application.semantic_service.get_retrieval_settings")
    def test_semantic_optimized_metric_mode_semantic_policy(
        self,
        settings_mock,
        _infer_mock,
        _personal_mock,
        _vector_mock,
        _retrieve_mock,
        llm_mock,
        metric_mock,
    ):
        settings_mock.return_value = RetrievalSettings(semantic_optimized_retrieval_enabled=True, rag_dense_k=5)
        llm_mock.return_value = {"ok": True, "text": "ok", "model": "m", "llm_ms": 1}

        run_semantic(
            user_id=1,
            query="apa syarat lulus skripsi",
            request_id="rid-policy",
            intent_route="semantic_policy",
            has_docs_hint=True,
            resolved_doc_ids=[],
            resolved_titles=[],
            unresolved_mentions=[],
            ambiguous_mentions=[],
        )
        payload = metric_mock.call_args[0][0]
        self.assertEqual(payload.get("mode"), "semantic_policy")

    @patch("core.ai_engine.retrieval.application.semantic_service.run_answer")
    @patch(
        "core.ai_engine.retrieval.application.semantic_service.run_retrieval",
        return_value={"mode": "doc_background", "docs": [], "dense_hits": 0, "top_score": 0.0, "retrieval_ms": 12},
    )
    @patch("core.ai_engine.retrieval.application.semantic_service.get_vectorstore")
    @patch("core.ai_engine.retrieval.application.semantic_service.is_personal_document_query", return_value=False)
    @patch("core.ai_engine.retrieval.application.semantic_service.infer_doc_type", return_value="general")
    @patch("core.ai_engine.retrieval.application.semantic_service.get_retrieval_settings")
    def test_semantic_optimized_fallback_to_legacy_when_llm_fail(
        self,
        settings_mock,
        _infer_mock,
        _personal_mock,
        _vector_mock,
        _retrieve_mock,
        llm_mock,
    ):
        settings_mock.return_value = RetrievalSettings(semantic_optimized_retrieval_enabled=True, rag_dense_k=5)
        llm_mock.return_value = {"ok": False, "error": "timeout"}

        out = run_semantic(
            user_id=1,
            query="apa itu sks",
            request_id="rid5",
            intent_route="default_rag",
            has_docs_hint=True,
            resolved_doc_ids=[],
            resolved_titles=[],
            unresolved_mentions=[],
            ambiguous_mentions=[],
        )
        self.assertEqual(out.get("meta", {}).get("validation"), "failed_fallback")
        self.assertEqual(out.get("meta", {}).get("pipeline"), "rag_semantic")

    @patch("core.ai_engine.retrieval.main._ask_bot_legacy")
    @patch("core.ai_engine.retrieval.application.semantic_service.run_answer")
    @patch(
        "core.ai_engine.retrieval.application.semantic_service.run_retrieval",
        return_value={"mode": "doc_background", "docs": [], "dense_hits": 0, "top_score": 0.0, "retrieval_ms": 12},
    )
    @patch("core.ai_engine.retrieval.application.semantic_service.get_vectorstore")
    @patch("core.ai_engine.retrieval.application.semantic_service.is_personal_document_query", return_value=False)
    @patch("core.ai_engine.retrieval.application.semantic_service.infer_doc_type", return_value="general")
    @patch("core.ai_engine.retrieval.application.semantic_service.get_retrieval_settings")
    def test_semantic_optimized_can_use_legacy_fallback_when_enabled(
        self,
        settings_mock,
        _infer_mock,
        _personal_mock,
        _vector_mock,
        _retrieve_mock,
        llm_mock,
        legacy_mock,
    ):
        settings_mock.return_value = RetrievalSettings(
            semantic_optimized_retrieval_enabled=True,
            semantic_optimized_legacy_fallback_enabled=True,
            rag_dense_k=5,
        )
        llm_mock.return_value = {"ok": False, "error": "timeout"}
        legacy_mock.return_value = {"answer": "legacy", "sources": [], "meta": {"pipeline": "rag_semantic"}}

        out = run_semantic(
            user_id=1,
            query="apa itu sks",
            request_id="rid6",
            intent_route="default_rag",
            has_docs_hint=True,
            resolved_doc_ids=[],
            resolved_titles=[],
            unresolved_mentions=[],
            ambiguous_mentions=[],
        )
        self.assertEqual(out.get("answer"), "legacy")
