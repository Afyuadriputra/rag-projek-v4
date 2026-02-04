import json
import unittest
from types import SimpleNamespace

from core.ai_engine import ingest as ingest_mod
from core.ai_engine import retrieval as ret_mod


class TestAIEngineIngestUnit(unittest.TestCase):
    def test_extract_semester_from_text(self):
        self.assertEqual(ingest_mod._extract_semester_from_text("KRS Semester 7"), 7)
        self.assertEqual(ingest_mod._extract_semester_from_text("semester 10 ganjil"), 10)
        self.assertIsNone(ingest_mod._extract_semester_from_text("tidak ada angka"))

    def test_header_normalization_mapping(self):
        header = [
            "Kode MK",
            "Nama Matakuliah",
            "SKS",
            "Hari",
            "Jam",
            "Dosen Pengampu",
            "Kelas",
            "Ruang",
        ]
        mapping = ingest_mod._canonical_columns_from_header(header)
        labels = ingest_mod._display_columns_from_mapping(mapping)
        # minimal expected labels
        for col in ["Kode", "Mata Kuliah", "SKS", "Hari", "Jam", "Dosen Pengampu", "Kelas", "Ruang"]:
            self.assertIn(col, labels)

    def test_detect_doc_type(self):
        self.assertEqual(ingest_mod._detect_doc_type(["Hari", "Jam"], None), "schedule")
        self.assertEqual(ingest_mod._detect_doc_type(["Grade", "Bobot"], None), "transcript")
        self.assertEqual(ingest_mod._detect_doc_type(None, [{"hari": "Senin"}]), "schedule")
        self.assertEqual(ingest_mod._detect_doc_type([], None), "general")


class TestAIEngineRetrievalUnit(unittest.TestCase):
    def test_extract_semesters_from_docs(self):
        docs = [
            SimpleNamespace(metadata={"semester": 3, "source": "semester 3.pdf"}, page_content=""),
            SimpleNamespace(metadata={"source": "semester 7.pdf"}, page_content=""),
            SimpleNamespace(metadata={"semester": "5"}, page_content=""),
        ]
        sems = ret_mod._extract_semesters_from_docs(docs)
        self.assertEqual(sems, ["3", "5", "7"])

    def test_extract_schedule_rows_from_json_metadata(self):
        rows = [{"hari": "Senin", "jam": "07:30-09:00"}]
        docs = [SimpleNamespace(metadata={"schedule_rows": json.dumps(rows)}, page_content="")]
        out = ret_mod._extract_schedule_rows_from_docs(docs)
        self.assertEqual(out, rows)

    def test_sum_sks(self):
        rows = [{"sks": "3"}, {"sks": "2"}, {"sks": "4"}]
        self.assertEqual(ret_mod._sum_sks(rows), 9)

    def test_conflict_detection(self):
        rows = [
            {"hari": "Senin", "jam": "08:00-09:30", "mata_kuliah": "A"},
            {"hari": "Senin", "jam": "09:00-10:00", "mata_kuliah": "B"},
            {"hari": "Selasa", "jam": "08:00-09:00", "mata_kuliah": "C"},
        ]
        conflicts = ret_mod._detect_conflicts(rows)
        self.assertTrue(any(c["hari"] == "Senin" for c in conflicts))

