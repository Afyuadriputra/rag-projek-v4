import unittest

from core.ai_engine import ingest as ingest_mod


class TestParserChunkingProfile(unittest.TestCase):
    def test_chunk_kind_tagging_row_parent_text(self):
        rows = [
            {
                "hari": "SENIN",
                "sesi": "I",
                "jam": "07:00-07:50",
                "kode": "IF101",
                "mata_kuliah": "Algoritma",
                "sks": "3",
                "kelas": "A",
                "ruang": "1.10",
                "dosen": "Dosen A",
                "semester": "3",
                "page": 1,
            },
            {
                "hari": "SENIN",
                "sesi": "II",
                "jam": "08:00-08:50",
                "kode": "IF102",
                "mata_kuliah": "Struktur Data",
                "sks": "3",
                "kelas": "A",
                "ruang": "1.11",
                "dosen": "Dosen B",
                "semester": "3",
                "page": 1,
            },
        ]
        row_chunks = ingest_mod._schedule_rows_to_row_chunks(rows)
        payloads = ingest_mod._build_chunk_payloads(
            doc_type="schedule",
            text_content="Dokumen jadwal semester 3.",
            row_chunks=row_chunks,
            schedule_rows=rows,
        )
        kinds = [str(p.get("chunk_kind")) for p in payloads]
        self.assertIn("row", kinds)
        self.assertIn("parent", kinds)
        self.assertIn("text", kinds)

    def test_parent_chunk_contains_page_and_day_section(self):
        rows = [
            {
                "hari": "SELASA",
                "sesi": "III",
                "jam": "10:00-10:50",
                "mata_kuliah": "Basis Data",
                "kode": "IF201",
                "kelas": "B",
                "ruang": "2.01",
                "dosen": "Dosen C",
                "semester": "5",
                "page": 2,
            }
        ]
        parents = ingest_mod._schedule_rows_to_parent_chunks(rows, target_chars=500)
        self.assertGreaterEqual(len(parents), 1)
        first = parents[0]
        self.assertEqual(first.get("chunk_kind"), "parent")
        self.assertEqual(first.get("page"), 2)
        self.assertIn("hari:", str(first.get("section", "")))

    def test_ocr_like_row_still_normalized_time(self):
        s = ingest_mod._normalize_time_range("0 5 :7 0-0 0 :7 0")
        self.assertEqual(s, "07:00-07:50")
