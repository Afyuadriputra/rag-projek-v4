from unittest import TestCase

from core.ai_engine.ingest_pipeline.chunking.chunk_builder import build_chunk_payloads


class IngestPipelineChunkBuilderTests(TestCase):
    def test_build_chunk_payloads_delegates_to_legacy_callable(self):
        def _legacy(**kwargs):
            self.assertEqual(kwargs["doc_type"], "transcript")
            return [{"text": "x", "chunk_kind": "row"}]

        out = build_chunk_payloads(
            doc_type="transcript",
            text_content="body",
            row_chunks=["r1"],
            schedule_rows=None,
            deps={"_build_chunk_payloads": _legacy},
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["chunk_kind"], "row")

