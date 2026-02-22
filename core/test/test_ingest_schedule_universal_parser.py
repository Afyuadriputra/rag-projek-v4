import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.ai_engine import ingest as ingest_mod


class _FakeLLM:
    def __init__(self, content: str):
        self._content = content

    def invoke(self, _messages):
        return SimpleNamespace(content=self._content)


class UniversalScheduleParserUnitTests(unittest.TestCase):
    def test_parse_valid_json_rows(self):
        parser = ingest_mod.UniversalScheduleParser()
        content = (
            '{"data_rows":[{"hari":"Senin","jam_mulai":"07:00","jam_selesai":"08:40","mata_kuliah":"Kalkulus","ruangan":"A1"},'
            '{"hari":"Selasa","jam_mulai":"09:00","jam_selesai":"10:40","mata_kuliah":"Fisika","ruangan":"B2"}]}'
        )
        with patch.object(ingest_mod.UniversalScheduleParser, "_build_llm", return_value=_FakeLLM(content)):
            out = parser.parse_pages(
                pages=[{"page": 1, "raw_text": "dummy", "rough_table_text": ""}],
                source="krs.pdf",
                fallback_semester=2,
            )
        self.assertTrue(out.get("ok"))
        self.assertEqual(len(out.get("data_rows") or []), 2)

    def test_parse_ignores_noise_rows(self):
        parser = ingest_mod.UniversalScheduleParser()
        content = (
            '{"data_rows":[{"hari":"", "jam_mulai":"07:00","jam_selesai":"08:40","mata_kuliah":"Header", "ruangan":"A1"},'
            '{"hari":"Senin", "jam_mulai":"07:00","jam_selesai":"08:40","mata_kuliah":"Basis Data", "ruangan":"A1"}]}'
        )
        with patch.object(ingest_mod.UniversalScheduleParser, "_build_llm", return_value=_FakeLLM(content)):
            out = parser.parse_pages(
                pages=[{"page": 1, "raw_text": "dummy", "rough_table_text": ""}],
                source="krs.pdf",
                fallback_semester=2,
            )
        rows = out.get("data_rows") or []
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].get("mata_kuliah"), "Basis Data")

    def test_parse_invalid_json_fail(self):
        parser = ingest_mod.UniversalScheduleParser()
        with patch.object(ingest_mod.UniversalScheduleParser, "_build_llm", return_value=_FakeLLM("bukan json")):
            out = parser.parse_pages(
                pages=[{"page": 1, "raw_text": "dummy", "rough_table_text": ""}],
                source="krs.pdf",
                fallback_semester=2,
            )
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "invalid_json")

    def test_parse_empty_result(self):
        parser = ingest_mod.UniversalScheduleParser()
        with patch.object(
            ingest_mod.UniversalScheduleParser,
            "_build_llm",
            return_value=_FakeLLM('{"data_rows": []}'),
        ):
            out = parser.parse_pages(
                pages=[{"page": 1, "raw_text": "dummy", "rough_table_text": ""}],
                source="krs.pdf",
                fallback_semester=2,
            )
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("data_rows"), [])
