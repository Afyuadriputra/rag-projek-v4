import unittest

from core.ai_engine import ingest as ingest_mod


class TranscriptChunkingUnitTests(unittest.TestCase):
    def test_transcript_rows_to_row_chunks_format(self):
        rows = [
            {"semester": 1, "mata_kuliah": "Kalkulus", "sks": 3, "nilai_huruf": "A"},
            {"semester": 1, "mata_kuliah": "Fisika", "sks": 2, "nilai_huruf": "B"},
        ]
        chunks = ingest_mod._transcript_rows_to_row_chunks(rows)
        self.assertEqual(len(chunks), 2)
        self.assertIn("TRANSCRIPT_ROW 1", chunks[0])
        self.assertIn("mata_kuliah=Kalkulus", chunks[0])
        self.assertIn("nilai_huruf=A", chunks[0])

    def test_transcript_chunk_kind_row_and_doc_type_transcript(self):
        rows = [{"semester": 1, "mata_kuliah": "Basis Data", "sks": 3, "nilai_huruf": "AB"}]
        payloads = ingest_mod._build_chunk_payloads(
            doc_type="transcript",
            text_content="transkrip akademik semester 1",
            row_chunks=ingest_mod._transcript_rows_to_row_chunks(rows),
            schedule_rows=None,
        )
        kinds = [p.get("chunk_kind") for p in payloads]
        self.assertIn("row", kinds)
        self.assertIn("text", kinds)
        self.assertNotIn("parent", kinds)

    def test_transcript_dedup_rows(self):
        rows = [
            {"semester": 2, "mata_kuliah": "Algoritma", "sks": 3, "nilai_huruf": "A"},
            {"semester": 2, "mata_kuliah": "Algoritma", "sks": 3, "nilai_huruf": "A"},
        ]
        out = ingest_mod._normalize_transcript_rows(rows, fallback_semester=None)
        self.assertEqual(len(out), 1)
