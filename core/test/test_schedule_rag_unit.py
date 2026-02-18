import unittest

from core.ai_engine.parsers.chunking import build_schedule_chunks
from core.ai_engine.retrieval import main as ret_main


class TestScheduleIntent(unittest.TestCase):
    def test_schedule_intent_detector(self):
        q = "Kapan kelas SMT 3 hari Senin jam 07.00?"
        self.assertTrue(ret_main._detect_schedule_intent(q))

    def test_filter_builder(self):
        q = "Kapan kelas SMT 3 kelas A hari Senin?"
        filters = ret_main._build_schedule_filters(q, {"user_id": "1"})
        first = filters[0]
        self.assertEqual(first.get("hari"), "SENIN")
        self.assertEqual(first.get("semester"), 3)
        self.assertIn("doc_type", first)


class TestChunkHeader(unittest.TestCase):
    def test_chunk_header_presence(self):
        rows = [
            {
                "hari": "SENIN",
                "sesi": "I",
                "jam_mulai": "07:00",
                "jam_selesai": "07:50",
                "mata_kuliah": "Hukum",
                "kode_mk": "HK101",
                "kelas": "A",
                "ruang_lokasi": "1.10",
                "dosen": ["Dosen A"],
                "semester": 3,
                "page": 1,
            }
        ]
        chunks = build_schedule_chunks(rows, "jadwal_fakultas")
        text = chunks[0][0]
        self.assertIn("SENIN, Sesi I", text)
        self.assertIn("07:00–07:50", text)
