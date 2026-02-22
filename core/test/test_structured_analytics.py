from django.test import SimpleTestCase
from unittest.mock import patch

from core.ai_engine.retrieval.structured_analytics import run_structured_analytics


class _FakeCollection:
    def __init__(self, transcript_docs=None, schedule_docs=None):
        self.transcript_docs = transcript_docs or []
        self.schedule_docs = schedule_docs or []

    def get(self, where=None, include=None):
        where = where or {}
        doc_type = ""
        for part in where.get("$and", []):
            if isinstance(part, dict) and "doc_type" in part:
                doc_type = part.get("doc_type")
        pool = self.transcript_docs if doc_type == "transcript" else self.schedule_docs
        documents = [x[0] for x in pool]
        metadatas = [x[1] for x in pool]
        return {"documents": documents, "metadatas": metadatas, "ids": [str(i) for i in range(len(documents))]}


class _FakeCollectionNoAnd:
    def __init__(self, docs_with_meta=None):
        self.docs_with_meta = docs_with_meta or []

    def get(self, where=None, include=None):
        where = where or {}
        if "$and" in where:
            raise ValueError("Expected where value to be primitive, got $and")
        user_id = str(where.get("user_id") or "")
        pool = []
        for text, meta in self.docs_with_meta:
            if str((meta or {}).get("user_id") or "") == user_id:
                pool.append((text, meta))
        return {
            "documents": [x[0] for x in pool],
            "metadatas": [x[1] for x in pool],
            "ids": [str(i) for i in range(len(pool))],
        }


class _FakeVectorStore:
    def __init__(self, collection):
        self._collection = collection


class StructuredAnalyticsUnitTests(SimpleTestCase):
    @patch("core.ai_engine.retrieval.structured_analytics.get_vectorstore")
    def test_rekap_transcript_and_dedup_latest_semester(self, get_vs_mock):
        transcript_rows = [
            (
                "TRANSCRIPT_ROW 1: semester=1 | mata_kuliah=Algoritma | sks=3 | nilai_huruf=C",
                {"source": "smt1.pdf", "page": 1},
            ),
            (
                "TRANSCRIPT_ROW 2: semester=3 | mata_kuliah=Algoritma | sks=3 | nilai_huruf=B",
                {"source": "smt3.pdf", "page": 2},
            ),
            (
                "TRANSCRIPT_ROW 3: semester=2 | mata_kuliah=Basis Data | sks=3 | nilai_huruf=A",
                {"source": "smt2.pdf", "page": 3},
            ),
        ]
        get_vs_mock.return_value = _FakeVectorStore(_FakeCollection(transcript_docs=transcript_rows))
        out = run_structured_analytics(user_id=1, query="rekap semua matakuliah saya")
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("doc_type"), "transcript")
        facts = out.get("facts") or []
        self.assertEqual(len(facts), 2)
        algo = [x for x in facts if x.get("mata_kuliah") == "Algoritma"][0]
        self.assertEqual(algo.get("semester"), 3)

    @patch("core.ai_engine.retrieval.structured_analytics.get_vectorstore")
    def test_filter_low_grade(self, get_vs_mock):
        transcript_rows = [
            (
                "TRANSCRIPT_ROW 1: semester=1 | mata_kuliah=Algoritma | sks=3 | nilai_huruf=C",
                {"source": "smt1.pdf", "page": 1},
            ),
            (
                "TRANSCRIPT_ROW 2: semester=2 | mata_kuliah=Basis Data | sks=3 | nilai_huruf=A",
                {"source": "smt2.pdf", "page": 3},
            ),
        ]
        get_vs_mock.return_value = _FakeVectorStore(_FakeCollection(transcript_docs=transcript_rows))
        out = run_structured_analytics(user_id=1, query="rekap nilai rendah saya")
        facts = out.get("facts") or []
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0].get("mata_kuliah"), "Algoritma")

    @patch("core.ai_engine.retrieval.structured_analytics.get_vectorstore")
    def test_schedule_by_day_and_today(self, get_vs_mock):
        schedule_rows = [
            (
                "CSV_ROW 1: hari=Senin | jam_mulai=07:00 | jam_selesai=08:40 | mata_kuliah=Algoritma | ruangan=A1",
                {"source": "krs.pdf", "page": 1},
            ),
            (
                "CSV_ROW 2: hari=Selasa | jam_mulai=09:00 | jam_selesai=10:40 | mata_kuliah=Basis Data | ruangan=B2",
                {"source": "krs.pdf", "page": 2},
            ),
        ]
        get_vs_mock.return_value = _FakeVectorStore(_FakeCollection(schedule_docs=schedule_rows))
        out = run_structured_analytics(user_id=1, query="jadwal hari senin")
        facts = out.get("facts") or []
        self.assertEqual(out.get("doc_type"), "schedule")
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0].get("hari"), "Senin")

    @patch("core.ai_engine.retrieval.structured_analytics.get_vectorstore")
    def test_course_recap_falls_back_to_schedule_when_transcript_missing(self, get_vs_mock):
        schedule_rows = [
            (
                "CSV_ROW 1: hari=Senin | jam_mulai=07:00 | jam_selesai=08:40 | mata_kuliah=Algoritma | ruangan=A1 | semester=3",
                {"source": "krs.pdf", "page": 1},
            ),
            (
                "CSV_ROW 2: hari=Selasa | jam_mulai=09:00 | jam_selesai=10:40 | mata_kuliah=Basis Data | ruangan=B2 | semester=3",
                {"source": "krs.pdf", "page": 2},
            ),
        ]
        get_vs_mock.return_value = _FakeVectorStore(_FakeCollection(transcript_docs=[], schedule_docs=schedule_rows))
        out = run_structured_analytics(user_id=1, query="coba rekap semua mata kuliah saya")
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("doc_type"), "schedule")
        facts = out.get("facts") or []
        self.assertEqual(len(facts), 2)

    @patch("core.ai_engine.retrieval.structured_analytics.get_vectorstore")
    def test_fetch_row_chunks_fallback_when_chroma_get_does_not_support_and(self, get_vs_mock):
        docs_with_meta = [
            (
                "TRANSCRIPT_ROW 1: semester=1 | mata_kuliah=Algoritma | sks=3 | nilai_huruf=A-",
                {"user_id": "1", "chunk_kind": "row", "doc_type": "transcript", "doc_id": "10", "source": "khs.pdf", "page": 1},
            ),
            (
                "TEXT chunk biasa",
                {"user_id": "1", "chunk_kind": "text", "doc_type": "transcript", "doc_id": "10", "source": "khs.pdf", "page": 1},
            ),
        ]
        get_vs_mock.return_value = _FakeVectorStore(_FakeCollectionNoAnd(docs_with_meta=docs_with_meta))
        out = run_structured_analytics(user_id=1, query="rekap hasil studi saya")
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("doc_type"), "transcript")
        facts = out.get("facts") or []
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0].get("mata_kuliah"), "Algoritma")

    @patch("core.ai_engine.retrieval.structured_analytics.get_vectorstore")
    def test_stats_query_returns_profile_summary_without_full_table(self, get_vs_mock):
        transcript_docs = [
            (
                "TRANSCRIPT_ROW 1: semester=1 | mata_kuliah=Algoritma | sks=3 | nilai_huruf=A-",
                {"source": "khs.pdf", "page": 1},
            ),
            (
                "TRANSCRIPT_ROW 2: semester=2 | mata_kuliah=Basis Data | sks=3 | nilai_huruf=B+",
                {"source": "khs.pdf", "page": 2},
            ),
            (
                "Nama : PUTRI SARTIKA Dosen PA Program NIM : 220401214 : Teknik Informatika Studi "
                "Jumlah SKS yang telah ditempuh : 138 SKS SKS yang harus ditempuh : 144 SKS IPK : 3.63",
                {"source": "khs.pdf", "page": 1},
            ),
        ]
        get_vs_mock.return_value = _FakeVectorStore(_FakeCollection(transcript_docs=transcript_docs))
        out = run_structured_analytics(user_id=1, query="berapa ipk dan total sks saya?")
        self.assertTrue(out.get("ok"))
        answer = out.get("answer") or ""
        self.assertIn("## Statistik Studi", answer)
        self.assertIn("3.63", answer)
        self.assertIn("138 SKS", answer)
        self.assertNotIn("## Daftar Mata Kuliah", answer)

    @patch("core.ai_engine.retrieval.structured_analytics.get_vectorstore")
    def test_specific_course_and_semester_filter(self, get_vs_mock):
        transcript_docs = [
            (
                "TRANSCRIPT_ROW 1: semester=1 | mata_kuliah=Algoritma dan Pemrograman | sks=3 | nilai_huruf=A-",
                {"source": "khs.pdf", "page": 1},
            ),
            (
                "TRANSCRIPT_ROW 2: semester=3 | mata_kuliah=Algoritma dan Pemrograman | sks=3 | nilai_huruf=B+",
                {"source": "khs.pdf", "page": 2},
            ),
            (
                "TRANSCRIPT_ROW 3: semester=3 | mata_kuliah=Basis Data | sks=3 | nilai_huruf=A",
                {"source": "khs.pdf", "page": 2},
            ),
        ]
        get_vs_mock.return_value = _FakeVectorStore(_FakeCollection(transcript_docs=transcript_docs))

        out_semester = run_structured_analytics(user_id=1, query="rekap nilai saya semester 3")
        facts_semester = out_semester.get("facts") or []
        self.assertEqual(len(facts_semester), 2)
        self.assertTrue(all(int(x.get("semester") or 0) == 3 for x in facts_semester))

        out_course = run_structured_analytics(user_id=1, query="nilai matakuliah algoritma dan pemrograman saya berapa?")
        facts_course = out_course.get("facts") or []
        self.assertEqual(len(facts_course), 1)
        self.assertEqual((facts_course[0] or {}).get("mata_kuliah"), "Algoritma dan Pemrograman")
