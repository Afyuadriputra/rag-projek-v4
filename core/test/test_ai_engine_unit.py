import unittest
from types import SimpleNamespace

from core.ai_engine import ingest as ingest_mod
from core.ai_engine.retrieval import main as ret_main


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
    def test_build_filter_contains_user_and_doc_type(self):
        out = ret_main._build_chroma_filter(user_id=7, query="jadwal semester 3")
        self.assertIn("$and", out)
        filters = out["$and"]
        self.assertTrue(any(f.get("user_id") == "7" for f in filters if isinstance(f, dict)))
        self.assertTrue(any(f.get("doc_type") == "schedule" for f in filters if isinstance(f, dict)))

    def test_dedup_docs(self):
        docs = [
            SimpleNamespace(metadata={"doc_id": "1", "source": "a.pdf", "page": 1}, page_content="A"),
            SimpleNamespace(metadata={"doc_id": "1", "source": "a.pdf", "page": 1}, page_content="A"),
            SimpleNamespace(metadata={"doc_id": "2", "source": "b.pdf", "page": 1}, page_content="B"),
        ]
        out = ret_main._dedup_docs(docs)
        self.assertEqual(len(out), 2)

    def test_has_citation_helper(self):
        self.assertTrue(ret_main._has_citation("Data ada di [source: jadwal.pdf]"))
        self.assertFalse(ret_main._has_citation("Tanpa sitasi"))

    def test_query_rewrite(self):
        q = "jadwal kelas hari senin jam pagi"
        out = ret_main._rewrite_queries(q)
        self.assertGreaterEqual(len(out), 1)
        self.assertEqual(out[0], q)
