from unittest import TestCase

from core.ai_engine.ingest_pipeline.schemas import (
    BuildChunksResult,
    ChunkPayload,
    ExtractPagePayload,
    ExtractResult,
    ParseResult,
    PipelineOps,
)


class IngestPipelineSchemaTests(TestCase):
    def test_schema_defaults_and_fields(self):
        page = ExtractPagePayload(page=1, raw_text="hello")
        self.assertEqual(page.page, 1)
        self.assertEqual(page.raw_text, "hello")

        extracted = ExtractResult(text_content="t")
        self.assertEqual(extracted.detected_columns, [])
        self.assertEqual(extracted.schedule_rows, [])

        parsed = ParseResult(doc_type="transcript")
        self.assertEqual(parsed.doc_type, "transcript")
        self.assertEqual(parsed.row_chunks, [])

        chunk = ChunkPayload(text="abc", chunk_kind="row", page=2)
        self.assertEqual(chunk.page, 2)

        built = BuildChunksResult(chunks=["a"], metadatas=[{"k": "v"}])
        self.assertEqual(len(built.chunks), 1)
        self.assertEqual(built.metadatas[0]["k"], "v")

    def test_pipeline_ops_from_mapping_roundtrip(self):
        deps = {
            "pdfplumber": object(),
            "get_vectorstore": lambda: None,
            "UniversalTranscriptParser": object,
            "UniversalScheduleParser": object,
            "_extract_semester_from_text": lambda _s: 1,
            "_extract_pdf_tables": lambda _p: ("", [], []),
            "_extract_pdf_page_raw_payload": lambda _p, file_path="": [],
            "_is_schedule_candidate": lambda **_k: False,
            "_is_transcript_candidate": lambda **_k: False,
            "_canonical_schedule_to_legacy_rows": lambda rows, fallback_semester=None: rows,
            "_repair_rows_with_llm": lambda rows, source: (rows, {}),
            "_schedule_rows_to_row_chunks": lambda rows: [],
            "_schedule_rows_to_csv_text": lambda rows: ("", 0, 0),
            "_transcript_rows_to_row_chunks": lambda rows: [],
            "_transcript_rows_to_csv_text": lambda rows: ("", 0, 0),
            "_csv_preview": lambda text, max_lines=12: text,
            "_norm": lambda v: str(v),
            "_extract_transcript_rows_deterministic": lambda text_blob, fallback_semester=None: {"rows": []},
            "_detect_doc_type": lambda cols, rows: "general",
            "_build_chunk_payloads": lambda **kwargs: [],
        }
        ops = PipelineOps.from_mapping(deps)
        legacy = ops.as_legacy_mapping()
        self.assertIn("_norm", legacy)
        self.assertIn("pdfplumber", legacy)
