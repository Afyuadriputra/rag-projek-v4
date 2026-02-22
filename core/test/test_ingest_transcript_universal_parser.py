import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.ai_engine import ingest as ingest_mod


class _FakeLLM:
    def __init__(self, content: str):
        self._content = content

    def invoke(self, _messages):
        return SimpleNamespace(content=self._content)


class UniversalTranscriptParserUnitTests(unittest.TestCase):
    def test_parse_valid_json_rows(self):
        parser = ingest_mod.UniversalTranscriptParser()
        content = (
            '{"data_rows":[{"semester":1,"mata_kuliah":"Kalkulus","sks":3,"nilai_huruf":"A"},'
            '{"semester":1,"mata_kuliah":"Fisika","sks":2,"nilai_huruf":"B+"}]}'
        )
        with patch.object(ingest_mod.UniversalTranscriptParser, "_build_llm", return_value=_FakeLLM(content)):
            out = parser.parse_pages(
                pages=[{"page": 1, "raw_text": "dummy", "rough_table_text": ""}],
                source="khs.pdf",
                fallback_semester=1,
            )
        self.assertTrue(out.get("ok"))
        self.assertEqual(len(out.get("data_rows") or []), 2)

    def test_parse_ignores_noise_rows(self):
        parser = ingest_mod.UniversalTranscriptParser()
        content = (
            '{"data_rows":[{"semester":1,"mata_kuliah":"","sks":3,"nilai_huruf":"A"},'
            '{"semester":1,"mata_kuliah":"Header Rektor","sks":"x","nilai_huruf":"A"},'
            '{"semester":1,"mata_kuliah":"Basis Data","sks":3,"nilai_huruf":"B"}]}'
        )
        with patch.object(ingest_mod.UniversalTranscriptParser, "_build_llm", return_value=_FakeLLM(content)):
            out = parser.parse_pages(
                pages=[{"page": 1, "raw_text": "dummy", "rough_table_text": ""}],
                source="khs.pdf",
                fallback_semester=1,
            )
        rows = out.get("data_rows") or []
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].get("mata_kuliah"), "Basis Data")

    def test_parse_maps_credit_to_sks_and_grade_to_nilai_huruf(self):
        parser = ingest_mod.UniversalTranscriptParser()
        # Simulasi hasil LLM yang sudah mengikuti aturan mapping prompt.
        content = '{"data_rows":[{"semester":2,"mata_kuliah":"Algoritma","sks":4,"nilai_huruf":"AB"}]}'
        with patch.object(ingest_mod.UniversalTranscriptParser, "_build_llm", return_value=_FakeLLM(content)):
            out = parser.parse_pages(
                pages=[{"page": 2, "raw_text": "Kredit 4 Grade AB", "rough_table_text": ""}],
                source="transkrip.pdf",
                fallback_semester=2,
            )
        rows = out.get("data_rows") or []
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].get("sks"), 4)
        self.assertEqual(rows[0].get("nilai_huruf"), "AB")

    def test_parse_invalid_json_fallback(self):
        parser = ingest_mod.UniversalTranscriptParser()
        with patch.object(ingest_mod.UniversalTranscriptParser, "_build_llm", return_value=_FakeLLM("bukan json")):
            out = parser.parse_pages(
                pages=[{"page": 1, "raw_text": "dummy", "rough_table_text": ""}],
                source="khs.pdf",
                fallback_semester=1,
            )
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "invalid_json")

    def test_parse_empty_result(self):
        parser = ingest_mod.UniversalTranscriptParser()
        with patch.object(
            ingest_mod.UniversalTranscriptParser,
            "_build_llm",
            return_value=_FakeLLM('{"data_rows": []}'),
        ):
            out = parser.parse_pages(
                pages=[{"page": 1, "raw_text": "dummy", "rough_table_text": ""}],
                source="khs.pdf",
                fallback_semester=1,
            )
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("data_rows"), [])

    def test_extract_transcript_rows_deterministic_parses_valid_and_pending(self):
        blob = (
            "1 0401101 PRAKTIKUM PENGANTAR TEKNOLOGI INFORMASI 1 A- 3.75 3.75\n"
            "2 40401605 Pembelajaran Mendalam 3 Isi Kuisioner Terlebih Dahulu\n"
            "Jumlah SKS yang telah ditempuh : 138 SKS\n"
            "SKS yang harus ditempuh : 144 SKS\n"
            "IPK : 3.63\n"
        )
        out = ingest_mod._extract_transcript_rows_deterministic(blob, fallback_semester=1)
        rows = out.get("data_rows") or []
        stats = out.get("stats") or {}
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].get("mata_kuliah"), "PRAKTIKUM PENGANTAR TEKNOLOGI INFORMASI")
        self.assertEqual(rows[0].get("nilai_huruf"), "A-")
        self.assertEqual(rows[1].get("mata_kuliah"), "Pembelajaran Mendalam")
        self.assertEqual(rows[1].get("nilai_huruf"), "ISI KUISIONER TERLEBIH DAHULU")
        self.assertEqual(int(stats.get("rows_detected") or 0), 2)
        self.assertEqual(int(stats.get("rows_pending") or 0), 1)
        self.assertEqual(str(stats.get("ipk") or ""), "3.63")
