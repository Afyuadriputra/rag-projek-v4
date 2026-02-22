from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from core.ai_engine.retrieval.structured_analytics import polish_structured_answer


class StructuredGuardrailsUnitTests(SimpleTestCase):
    @patch("core.ai_engine.retrieval.structured_analytics._invoke_polisher_llm")
    def test_polish_valid_pass(self, invoke_mock):
        invoke_mock.return_value = (
            "## Ringkasan\n"
            "| Semester | Mata Kuliah | SKS | Nilai Huruf |\n"
            "|---|---|---:|---|\n"
            "| 3 | Algoritma | 3 | B |\n"
        )
        facts = [{"semester": 3, "mata_kuliah": "Algoritma", "sks": 3, "nilai_huruf": "B"}]
        out = polish_structured_answer(
            query="rekap semua matakuliah saya",
            deterministic_answer="deterministic",
            facts=facts,
            doc_type="transcript",
        )
        self.assertEqual(out.get("validation"), "passed")
        self.assertIn("Algoritma", out.get("answer", ""))

    @patch("core.ai_engine.retrieval.structured_analytics._invoke_polisher_llm")
    def test_polish_hallucination_fallback(self, invoke_mock):
        invoke_mock.return_value = (
            "## Ringkasan\n"
            "| Semester | Mata Kuliah | SKS | Nilai Huruf |\n"
            "|---|---|---:|---|\n"
            "| 3 | Algoritma | 3 | B |\n"
            "| 4 | Matkul Ngawur | 3 | A |\n"
        )
        deterministic = "jawaban deterministik"
        facts = [{"semester": 3, "mata_kuliah": "Algoritma", "sks": 3, "nilai_huruf": "B"}]
        out = polish_structured_answer(
            query="rekap semua matakuliah saya",
            deterministic_answer=deterministic,
            facts=facts,
            doc_type="transcript",
        )
        self.assertEqual(out.get("validation"), "failed_fallback")
        self.assertEqual(out.get("answer"), deterministic)
