import json
import tempfile
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from core.models import AcademicDocument
from core.ai_engine.ingest import process_document


class _FakeVectorStore:
    def __init__(self):
        self.metadatas = []
        self.texts = []

    def add_texts(self, texts, metadatas):
        self.texts.extend(list(texts or []))
        self.metadatas.extend(list(metadatas or []))
        return []


class _FakePage:
    def __init__(self, text: str = ""):
        self._text = text

    def extract_text(self):
        return self._text

    def extract_tables(self):
        return []


class _FakePdf:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class UniversalTranscriptParserIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ingest_transcript_u", password="pass123")

    @patch("core.ai_engine.ingest.get_vectorstore")
    @patch("core.ai_engine.ingest.UniversalTranscriptParser.parse_pages")
    @patch("core.ai_engine.ingest._extract_pdf_tables")
    @patch("core.ai_engine.ingest.pdfplumber.open")
    def test_process_document_transcript_prefers_deterministic_rows_when_available(
        self,
        pdf_open_mock,
        extract_tables_mock,
        parse_pages_mock,
        get_vs_mock,
    ):
        fake_vs = _FakeVectorStore()
        get_vs_mock.return_value = fake_vs
        raw = (
            "No Kode Mata Kuliah Nama Mata Kuliah SKS Nilai Bobot Mutu\n"
            "1 0401101 PRAKTIKUM PENGANTAR TEKNOLOGI INFORMASI 1 A- 3.75 3.75\n"
            "2 40401605 Pembelajaran Mendalam 3 Isi Kuisioner Terlebih Dahulu\n"
        )
        pdf_open_mock.return_value = _FakePdf([_FakePage(raw)])
        extract_tables_mock.return_value = ("", ["Nilai", "Bobot"], [])
        parse_pages_mock.return_value = {
            "ok": True,
            "error": None,
            "data_rows": [{"semester": 1, "mata_kuliah": "X", "sks": 1, "nilai_huruf": "A"}],
            "stats": {"pages": 1, "rows": 1, "model": "google/gemini-2.5-flash-lite"},
        }

        doc = AcademicDocument.objects.create(user=self.user, file=SimpleUploadedFile("khs_det.pdf", b"%PDF-1.4"))
        ok = process_document(doc)
        self.assertTrue(ok)
        parse_pages_mock.assert_not_called()
        self.assertTrue(any(m.get("doc_type") == "transcript" for m in fake_vs.metadatas))
        self.assertTrue(any(m.get("chunk_kind") == "row" for m in fake_vs.metadatas))

    @patch("core.ai_engine.ingest.get_vectorstore")
    @patch("core.ai_engine.ingest._extract_pdf_page_raw_payload")
    @patch("core.ai_engine.ingest.UniversalTranscriptParser.parse_pages")
    @patch("core.ai_engine.ingest._extract_pdf_tables")
    @patch("core.ai_engine.ingest.pdfplumber.open")
    def test_process_document_pdf_transcript_uses_llm_parser_when_enabled(
        self,
        pdf_open_mock,
        extract_tables_mock,
        parse_pages_mock,
        page_payload_mock,
        get_vs_mock,
    ):
        fake_vs = _FakeVectorStore()
        get_vs_mock.return_value = fake_vs
        pdf_open_mock.return_value = _FakePdf([_FakePage("transkrip nilai semester 1")])
        extract_tables_mock.return_value = ("", ["Grade", "Kredit"], [])
        page_payload_mock.return_value = [{"page": 1, "raw_text": "dummy", "rough_table_text": ""}]
        parse_pages_mock.return_value = {
            "ok": True,
            "error": None,
            "data_rows": [{"semester": 1, "mata_kuliah": "Kalkulus", "sks": 3, "nilai_huruf": "A"}],
            "stats": {"pages": 1, "rows": 1, "model": "google/gemini-2.5-flash-lite"},
        }

        doc = AcademicDocument.objects.create(user=self.user, file=SimpleUploadedFile("khs.pdf", b"%PDF-1.4"))
        ok = process_document(doc)
        self.assertTrue(ok)
        self.assertTrue(fake_vs.metadatas)
        self.assertTrue(any(m.get("doc_type") == "transcript" for m in fake_vs.metadatas))
        self.assertTrue(any(m.get("chunk_kind") == "row" for m in fake_vs.metadatas))

    @patch("core.ai_engine.ingest.get_vectorstore")
    @patch("core.ai_engine.ingest.UniversalTranscriptParser.parse_pages")
    @patch("core.ai_engine.ingest._extract_pdf_tables")
    @patch("core.ai_engine.ingest.pdfplumber.open")
    def test_process_document_pdf_transcript_fallback_to_legacy_when_llm_fail(
        self,
        pdf_open_mock,
        extract_tables_mock,
        parse_pages_mock,
        get_vs_mock,
    ):
        fake_vs = _FakeVectorStore()
        get_vs_mock.return_value = fake_vs
        pdf_open_mock.return_value = _FakePdf([_FakePage("transkrip nilai semester 1")])
        extract_tables_mock.return_value = ("tabel transkrip", ["Grade", "Nilai"], [])
        parse_pages_mock.return_value = {
            "ok": False,
            "error": "invalid_json",
            "data_rows": [],
            "stats": {"pages": 1, "rows": 0},
        }

        doc = AcademicDocument.objects.create(user=self.user, file=SimpleUploadedFile("transkrip.pdf", b"%PDF-1.4"))
        ok = process_document(doc)
        self.assertTrue(ok)
        self.assertTrue(fake_vs.metadatas)
        self.assertTrue(any(m.get("doc_type") == "transcript" for m in fake_vs.metadatas))

    @patch("core.ai_engine.ingest.get_vectorstore")
    @patch("core.ai_engine.ingest._extract_pdf_page_raw_payload")
    @patch("core.ai_engine.ingest.UniversalTranscriptParser.parse_pages")
    @patch("core.ai_engine.ingest._extract_pdf_tables")
    @patch("core.ai_engine.ingest.pdfplumber.open")
    def test_metadata_contains_transcript_rows_and_doc_type(
        self,
        pdf_open_mock,
        extract_tables_mock,
        parse_pages_mock,
        page_payload_mock,
        get_vs_mock,
    ):
        fake_vs = _FakeVectorStore()
        get_vs_mock.return_value = fake_vs
        pdf_open_mock.return_value = _FakePdf([_FakePage("khs semester 2")])
        extract_tables_mock.return_value = ("", ["Huruf Mutu", "Bobot"], [])
        page_payload_mock.return_value = [{"page": 1, "raw_text": "dummy", "rough_table_text": ""}]
        rows = [{"semester": 2, "mata_kuliah": "Basis Data", "sks": 3, "nilai_huruf": "B"}]
        parse_pages_mock.return_value = {"ok": True, "error": None, "data_rows": rows, "stats": {"pages": 1, "rows": 1}}

        doc = AcademicDocument.objects.create(user=self.user, file=SimpleUploadedFile("khs2.pdf", b"%PDF-1.4"))
        ok = process_document(doc)
        self.assertTrue(ok)
        self.assertTrue(fake_vs.metadatas)
        meta = fake_vs.metadatas[0]
        self.assertEqual(meta.get("doc_type"), "transcript")
        self.assertIn("transcript_rows", meta)
        stored_rows = json.loads(meta["transcript_rows"])
        self.assertEqual(len(stored_rows), 1)
        self.assertEqual(stored_rows[0].get("mata_kuliah"), "Basis Data")
