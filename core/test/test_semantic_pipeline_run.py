import os
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from core.ai_engine.retrieval.domain.models import QueryContext
from core.ai_engine.retrieval.pipelines.semantic.run import run_retrieval


def _doc(text: str, doc_id: str) -> SimpleNamespace:
    return SimpleNamespace(page_content=text, metadata={"doc_id": doc_id, "source": "khs.pdf"})


class SemanticPipelineRunTests(SimpleTestCase):
    @patch("core.ai_engine.retrieval.pipelines.semantic.run.rerank")
    @patch("core.ai_engine.retrieval.pipelines.semantic.run.retrieve_hybrid_docs")
    @patch("core.ai_engine.retrieval.pipelines.semantic.run.retrieve_dense_docs")
    def test_run_retrieval_uses_hybrid_and_rerank_for_doc_targeted(
        self,
        dense_mock,
        hybrid_mock,
        rerank_mock,
    ):
        old = dict(os.environ)
        try:
            os.environ["RAG_SEMANTIC_OPTIMIZED_RETRIEVAL_ENABLED"] = "0"
            os.environ["RAG_GENERAL_HYBRID_RETRIEVAL"] = "0"
            os.environ["RAG_GENERAL_RERANK_ENABLED"] = "0"
            os.environ["RAG_DOC_TARGETED_HYBRID_RETRIEVAL"] = "1"
            os.environ["RAG_DOC_TARGETED_RERANK_ENABLED"] = "1"
            os.environ["RAG_DOC_TARGETED_DENSE_K"] = "5"
            os.environ["RAG_DOC_TARGETED_BM25_K"] = "5"
            os.environ["RAG_DOC_TARGETED_RERANK_TOP_N"] = "2"

            d1 = _doc("jadwal semester 3", "1")
            d2 = _doc("rekap nilai semester 3", "2")
            dense_mock.return_value = [(d1, 0.6), (d2, 0.5)]
            hybrid_mock.return_value = [(d2, 0.9), (d1, 0.8)]
            rerank_mock.return_value = [d2, d1]

            out = run_retrieval(
                vectorstore=object(),
                query_ctx=QueryContext(user_id=1, query="rekap nilai saya semester 3"),
                filter_where={"user_id": "1"},
                has_docs_hint=True,
            )
            self.assertEqual(out.get("mode"), "doc_background")
            self.assertTrue(out.get("plan", {}).get("use_hybrid"))
            self.assertTrue(out.get("plan", {}).get("use_rerank"))
            hybrid_mock.assert_called_once()
            rerank_mock.assert_called_once()
            self.assertEqual(len(out.get("docs") or []), 2)
        finally:
            os.environ.clear()
            os.environ.update(old)

    @patch("core.ai_engine.retrieval.pipelines.semantic.run.retrieve_dense_docs")
    def test_run_retrieval_llm_only_when_no_docs_hint(self, dense_mock):
        out = run_retrieval(
            vectorstore=object(),
            query_ctx=QueryContext(user_id=1, query="apa itu sks"),
            filter_where={"user_id": "1"},
            has_docs_hint=False,
        )
        self.assertEqual(out.get("mode"), "llm_only")
        self.assertEqual(out.get("docs"), [])
        dense_mock.assert_not_called()
