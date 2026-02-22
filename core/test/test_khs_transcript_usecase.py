from unittest.mock import patch

from django.test import SimpleTestCase

from core.ai_engine.retrieval.main import ask_bot
from core.ai_engine.retrieval.structured_analytics import run_structured_analytics


class _FakeCollection:
    def __init__(self, docs_with_meta=None):
        self.docs_with_meta = docs_with_meta or []

    def get(self, where=None, include=None):
        where = where or {}
        where_and = where.get("$and") if isinstance(where, dict) else None
        if not where_and:
            # fallback mode from implementation
            uid = str((where or {}).get("user_id") or "")
            pool = [(d, m) for d, m in self.docs_with_meta if str((m or {}).get("user_id") or "") == uid]
            return {
                "documents": [x[0] for x in pool],
                "metadatas": [x[1] for x in pool],
            }

        user_id = ""
        chunk_kind = ""
        doc_type = ""
        for part in where_and:
            if not isinstance(part, dict):
                continue
            if "user_id" in part:
                user_id = str(part.get("user_id") or "")
            if "chunk_kind" in part:
                chunk_kind = str(part.get("chunk_kind") or "")
            if "doc_type" in part:
                doc_type = str(part.get("doc_type") or "")

        pool = []
        for text, meta in self.docs_with_meta:
            m = meta or {}
            if user_id and str(m.get("user_id") or "") != user_id:
                continue
            if chunk_kind and str(m.get("chunk_kind") or "") != chunk_kind:
                continue
            if doc_type and str(m.get("doc_type") or "") != doc_type:
                continue
            pool.append((text, m))
        return {
            "documents": [x[0] for x in pool],
            "metadatas": [x[1] for x in pool],
        }


class _FakeVectorStore:
    def __init__(self, collection):
        self._collection = collection


class KhsTranscriptUseCaseTests(SimpleTestCase):
    @patch("core.ai_engine.retrieval.structured_analytics.get_vectorstore")
    def test_rekap_hasil_studi_rendered_with_profile_stats_and_full_table(self, get_vs_mock):
        docs_with_meta = [
            (
                "TRANSCRIPT_ROW 1: semester=1 | mata_kuliah=PRAKTIKUM PENGANTAR TEKNOLOGI INFORMASI | sks=1 | nilai_huruf=A-",
                {"user_id": "1", "chunk_kind": "row", "doc_type": "transcript", "doc_id": "10", "source": "Kartu Hasil Studi puput.pdf", "page": 1},
            ),
            (
                "TRANSCRIPT_ROW 2: semester=1 | mata_kuliah=PENGANTAR TEKNOLOGI INFORMASI | sks=3 | nilai_huruf=A-",
                {"user_id": "1", "chunk_kind": "row", "doc_type": "transcript", "doc_id": "10", "source": "Kartu Hasil Studi puput.pdf", "page": 1},
            ),
            (
                "TRANSCRIPT_ROW 3: semester=1 | mata_kuliah=Pembelajaran Mendalam | sks=3 | nilai_huruf=A-",
                {"user_id": "1", "chunk_kind": "row", "doc_type": "transcript", "doc_id": "10", "source": "Kartu Hasil Studi puput.pdf", "page": 1},
            ),
            (
                "TRANSCRIPT_ROW 4: semester=1 | mata_kuliah=Skripsi | sks=6 | nilai_huruf=A-",
                {"user_id": "1", "chunk_kind": "row", "doc_type": "transcript", "doc_id": "10", "source": "Kartu Hasil Studi puput.pdf", "page": 1},
            ),
            (
                "Nama : PUTRI SARTIKA Dosen PA M.Kom Program NIM : 220401214 : Teknik Informatika Studi "
                "Jumlah SKS yang telah ditempuh : 138 SKS SKS yang harus ditempuh : 144 SKS IPK : 3.63 "
                "Pembelajaran Mendalam Isi Kuisioner Terlebih Dahulu Skripsi Isi Kuisioner Terlebih Dahulu",
                {"user_id": "1", "chunk_kind": "text", "doc_type": "transcript", "doc_id": "10", "source": "Kartu Hasil Studi puput.pdf", "page": 1},
            ),
        ]
        get_vs_mock.return_value = _FakeVectorStore(_FakeCollection(docs_with_meta=docs_with_meta))
        out = run_structured_analytics(user_id=1, query="coba rekap hasil studi saya")
        self.assertTrue(out.get("ok"))
        answer = out.get("answer") or ""
        self.assertIn("Berdasarkan Kartu Hasil Studi", answer)
        self.assertIn("## Informasi Umum", answer)
        self.assertIn("PUTRI SARTIKA", answer)
        self.assertIn("220401214", answer)
        self.assertIn("Teknik Informatika", answer)
        self.assertIn("## Statistik Studi", answer)
        self.assertIn("138 SKS", answer)
        self.assertIn("144 SKS", answer)
        self.assertIn("3.63", answer)
        self.assertIn("Pembelajaran Mendalam", answer)
        self.assertIn("Skripsi", answer)
        self.assertIn("## Daftar Mata Kuliah", answer)
        table_lines = [ln for ln in answer.splitlines() if ln.strip().startswith("|")]
        self.assertEqual(max(0, len(table_lines) - 2), 4)

    @patch("core.ai_engine.retrieval.structured_analytics.get_vectorstore")
    def test_query_tidak_lulus_filters_to_low_grades(self, get_vs_mock):
        docs_with_meta = [
            (
                "TRANSCRIPT_ROW 1: semester=1 | mata_kuliah=Algoritma | sks=3 | nilai_huruf=C",
                {"user_id": "1", "chunk_kind": "row", "doc_type": "transcript", "doc_id": "10", "source": "khs.pdf", "page": 1},
            ),
            (
                "TRANSCRIPT_ROW 2: semester=1 | mata_kuliah=Basis Data | sks=3 | nilai_huruf=A",
                {"user_id": "1", "chunk_kind": "row", "doc_type": "transcript", "doc_id": "10", "source": "khs.pdf", "page": 1},
            ),
            (
                "Nama : PUTRI SARTIKA Dosen PA Program NIM : 220401214 : Teknik Informatika Studi",
                {"user_id": "1", "chunk_kind": "text", "doc_type": "transcript", "doc_id": "10", "source": "khs.pdf", "page": 1},
            ),
        ]
        get_vs_mock.return_value = _FakeVectorStore(_FakeCollection(docs_with_meta=docs_with_meta))
        out = run_structured_analytics(user_id=1, query="rekap matakuliah saya yang tidak lulus")
        self.assertTrue(out.get("ok"))
        facts = out.get("facts") or []
        self.assertEqual(len(facts), 1)
        self.assertEqual((facts[0] or {}).get("mata_kuliah"), "Algoritma")
        self.assertEqual((facts[0] or {}).get("nilai_huruf"), "C")

    @patch("core.ai_engine.retrieval.main.create_stuff_documents_chain")
    @patch("core.ai_engine.retrieval.main.retrieve_dense")
    @patch("core.ai_engine.retrieval.main._has_user_documents")
    @patch("core.ai_engine.retrieval.main.run_structured_analytics")
    @patch("core.ai_engine.retrieval.main.get_runtime_openrouter_config")
    def test_ask_bot_hasil_studi_uses_structured_pipeline_and_skips_dense(
        self,
        cfg_mock,
        structured_mock,
        has_docs_mock,
        dense_mock,
        chain_mock,
    ):
        cfg_mock.return_value = {"api_key": "key", "model": "m", "backup_models": ["m"]}
        has_docs_mock.return_value = True
        structured_mock.return_value = {
            "ok": True,
            "doc_type": "transcript",
            "answer": (
                "Berdasarkan Kartu Hasil Studi, berikut rekap hasil studi kamu.\n\n"
                "## Informasi Umum\n- Nama: **PUTRI SARTIKA**\n\n"
                "## Statistik Studi\n- Total mata kuliah terdata: **55**\n\n"
                "## Daftar Mata Kuliah\n| No | Mata Kuliah | SKS | Nilai |\n|---:|---|---:|---|\n| 1 | Algoritma | 3 | A- |"
            ),
            "sources": [{"source": "Kartu Hasil Studi puput.pdf", "snippet": "semester=1 | mata_kuliah=Algoritma"}],
            "facts": [{"semester": 1, "mata_kuliah": "Algoritma", "sks": 3, "nilai_huruf": "A-"}],
            "stats": {"raw": 55, "deduped": 55, "returned": 55, "latency_ms": 5},
        }
        out = ask_bot(user_id=1, query="bagaimana hasil studi saya ini?", request_id="khs-1")
        self.assertEqual(out.get("meta", {}).get("pipeline"), "structured_analytics")
        self.assertEqual(out.get("meta", {}).get("mode"), "structured_transcript")
        self.assertIn("Berdasarkan Kartu Hasil Studi", out.get("answer", ""))
        dense_mock.assert_not_called()
        chain_mock.assert_not_called()

