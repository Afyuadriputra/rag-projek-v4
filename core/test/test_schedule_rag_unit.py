import unittest

from core.ai_engine import ingest as ingest_mod
from core.ai_engine.retrieval import main as ret_main


class TestScheduleIntent(unittest.TestCase):
    def test_infer_doc_type_schedule(self):
        self.assertEqual(ret_main.infer_doc_type("jadwal kelas hari senin"), "schedule")

    def test_filter_builder_has_semester_and_doc_type(self):
        out = ret_main._build_chroma_filter(user_id=1, query="jadwal semester 3")
        self.assertIn("$and", out)
        filters = out["$and"]
        self.assertTrue(any(x.get("semester") == 3 for x in filters if isinstance(x, dict)))
        self.assertTrue(any(x.get("doc_type") == "schedule" for x in filters if isinstance(x, dict)))


class TestChunkProfile(unittest.TestCase):
    def test_parent_chunk_presence_for_schedule(self):
        rows = [
            {
                "hari": "SENIN",
                "sesi": "I",
                "jam": "07:00-07:50",
                "mata_kuliah": "Hukum",
                "kode": "HK101",
                "kelas": "A",
                "ruang": "1.10",
                "dosen": "Dosen A",
                "semester": 3,
                "page": 1,
            }
        ]
        payloads = ingest_mod._build_chunk_payloads(
            doc_type="schedule",
            text_content="jadwal kuliah",
            row_chunks=ingest_mod._schedule_rows_to_row_chunks(rows),
            schedule_rows=rows,
        )
        kinds = [p.get("chunk_kind") for p in payloads]
        self.assertIn("row", kinds)
        self.assertIn("parent", kinds)
        self.assertIn("text", kinds)
