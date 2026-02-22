from unittest.mock import patch

from django.test import SimpleTestCase
from langchain_core.documents import Document

from core.ai_engine.retrieval.pipelines.semantic.answer import build_sources, run_answer


class SemanticAnswerPipelineTests(SimpleTestCase):
    def test_build_sources_maps_metadata(self):
        docs = [Document(page_content="x", metadata={"source": "khs.pdf", "page": 2})]
        out = build_sources(docs)
        self.assertEqual(out, [{"source": "khs.pdf", "page": 2}])

    @patch("core.ai_engine.retrieval.pipelines.semantic.answer.invoke_with_model_fallback")
    def test_run_answer_appends_unresolved_note(self, invoke_mock):
        invoke_mock.return_value = {"ok": True, "text": "Jawaban utama", "model": "m", "llm_ms": 10}
        out = run_answer(
            query="apa itu sks",
            docs=[],
            mode="doc_background",
            resolved_titles=[],
            unresolved_mentions=["missing.pdf"],
        )
        self.assertTrue(out.get("ok"))
        self.assertIn("Jawaban utama", out.get("text", ""))
        self.assertIn("@missing.pdf", out.get("text", ""))

    @patch("core.ai_engine.retrieval.pipelines.semantic.answer.invoke_with_model_fallback")
    def test_run_answer_tries_citation_enrichment_when_docs_exist(self, invoke_mock):
        invoke_mock.side_effect = [
            {"ok": True, "text": "Fakta tanpa sitasi", "model": "m", "llm_ms": 10},
            {"ok": True, "text": "Fakta [source: khs.pdf]", "model": "m", "llm_ms": 5},
        ]
        out = run_answer(
            query="nilai saya",
            docs=[Document(page_content="Nilai A", metadata={"source": "khs.pdf"})],
            mode="doc_referenced",
            resolved_titles=["khs.pdf"],
            unresolved_mentions=[],
        )
        self.assertTrue(out.get("ok"))
        self.assertIn("[source:", out.get("text", "").lower())
