from unittest import TestCase

from core.ai_engine.ingest_pipeline.parsers.parser_chain import (
    run_schedule_parser_chain,
    run_transcript_parser_chain,
)


class _FakeTranscriptParser:
    def parse_pages(self, page_payload, source, fallback_semester=None):
        return {"ok": True, "data_rows": [{"semester": 1, "mata_kuliah": "AI", "sks": 3, "nilai_huruf": "A"}]}


class _FakeScheduleParser:
    def parse_pages(self, page_payload, source, fallback_semester=None):
        return {"ok": True, "data_rows": [{"hari": "Senin", "jam_mulai": "07:00", "jam_selesai": "08:40", "mata_kuliah": "Algo", "ruangan": "A1"}]}


class IngestPipelineParserChainTests(TestCase):
    def test_transcript_rule_success(self):
        deps = {
            "_norm": lambda s: str(s).strip(),
            "_extract_transcript_rows_deterministic": lambda text_blob, fallback_semester=None: {
                "data_rows": [{"semester": 1, "mata_kuliah": "Basis Data", "sks": 3, "nilai_huruf": "A-"}],
                "stats": {"rows_detected": 1},
            },
        }
        out = run_transcript_parser_chain(
            enabled=True,
            candidate=True,
            parser_cls=_FakeTranscriptParser,
            page_payload=[{"raw_text": "x", "rough_table_text": ""}],
            source="khs.pdf",
            fallback_semester=1,
            deps=deps,
        )
        self.assertEqual(out["source"], "deterministic")
        self.assertEqual(len(out["transcript_rows"]), 1)

    def test_transcript_rule_empty_fallback_llm(self):
        deps = {
            "_norm": lambda s: str(s).strip(),
            "_extract_transcript_rows_deterministic": lambda text_blob, fallback_semester=None: {"data_rows": []},
        }
        out = run_transcript_parser_chain(
            enabled=True,
            candidate=True,
            parser_cls=_FakeTranscriptParser,
            page_payload=[{"raw_text": "x", "rough_table_text": ""}],
            source="khs.pdf",
            fallback_semester=1,
            deps=deps,
        )
        self.assertEqual(out["source"], "llm")
        self.assertEqual(len(out["transcript_rows"]), 1)

    def test_schedule_fallback_path(self):
        deps = {"_canonical_schedule_to_legacy_rows": lambda rows, fallback_semester=None: rows}
        out = run_schedule_parser_chain(
            enabled=False,
            candidate=True,
            parser_cls=_FakeScheduleParser,
            page_payload=[],
            source="krs.pdf",
            fallback_semester=3,
            table_schedule_rows=[{"hari": "Senin"}],
            deps=deps,
        )
        self.assertFalse(out["schedule_parser_used"])
        self.assertEqual(out["schedule_rows"], [{"hari": "Senin"}])

