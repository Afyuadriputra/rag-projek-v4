from django.test import SimpleTestCase
from unittest.mock import patch

from core.ai_engine.retrieval.domain.models import QueryContext
from core.ai_engine.retrieval.pipelines.structured.run import run


class StructuredPipelineRuntimeTests(SimpleTestCase):
    @patch("core.ai_engine.retrieval.pipelines.structured.run.fetch_row_chunks")
    def test_no_rows_returns_no_row_chunks(self, fetch_mock):
        fetch_mock.return_value = []
        out = run(QueryContext(user_id=1, query="rekap nilai"))
        self.assertFalse(out.ok)
        self.assertEqual(out.reason, "no_row_chunks")

    @patch("core.ai_engine.retrieval.pipelines.structured.run.render_sources")
    @patch("core.ai_engine.retrieval.pipelines.structured.run.render_transcript_answer")
    @patch("core.ai_engine.retrieval.pipelines.structured.run.extract_transcript_profile")
    @patch("core.ai_engine.retrieval.pipelines.structured.run.fetch_transcript_text_chunks")
    @patch("core.ai_engine.retrieval.pipelines.structured.run.dedupe_transcript_latest")
    @patch("core.ai_engine.retrieval.pipelines.structured.run.normalize_transcript_from_chunk")
    @patch("core.ai_engine.retrieval.pipelines.structured.run.fetch_row_chunks")
    def test_transcript_pipeline_happy_path(
        self,
        fetch_mock,
        normalize_mock,
        dedupe_mock,
        fetch_text_mock,
        profile_mock,
        render_answer_mock,
        render_sources_mock,
    ):
        fetch_mock.return_value = [("row1", {"source": "khs.pdf", "page": 1})]
        normalize_mock.return_value = {"semester": 1, "mata_kuliah": "Algoritma", "sks": 3, "nilai_huruf": "A"}
        dedupe_mock.return_value = [{"semester": 1, "mata_kuliah": "Algoritma", "sks": 3, "nilai_huruf": "A"}]
        fetch_text_mock.return_value = ["profile"]
        profile_mock.return_value = {"nama": "A"}
        render_answer_mock.return_value = "answer"
        render_sources_mock.return_value = [{"source": "khs.pdf", "snippet": "x"}]

        out = run(QueryContext(user_id=1, query="rekap hasil studi"))
        self.assertTrue(out.ok)
        self.assertEqual(out.doc_type, "transcript")
        self.assertEqual(out.reason, "structured_transcript")
        self.assertEqual(out.answer, "answer")
