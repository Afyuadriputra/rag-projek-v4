import tempfile
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from core.ai_engine.ingest import process_document
from core.models import AcademicDocument


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
class UniversalScheduleParserIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ingest_schedule_u", password="pass123")

    @patch("core.ai_engine.ingest.get_vectorstore")
    @patch("core.ai_engine.ingest._extract_pdf_page_raw_payload")
    @patch("core.ai_engine.ingest.UniversalScheduleParser.parse_pages")
    @patch("core.ai_engine.ingest._extract_pdf_tables")
    @patch("core.ai_engine.ingest.pdfplumber.open")
    def test_process_document_pdf_schedule_uses_llm_parser_when_enabled(
        self,
        pdf_open_mock,
        extract_tables_mock,
        parse_pages_mock,
        page_payload_mock,
        get_vs_mock,
    ):
        fake_vs = _FakeVectorStore()
        get_vs_mock.return_value = fake_vs
        pdf_open_mock.return_value = _FakePdf([_FakePage("jadwal kuliah semester 3")])
        extract_tables_mock.return_value = ("", ["Hari", "Jam", "Ruang"], [])
        page_payload_mock.return_value = [{"page": 1, "raw_text": "dummy", "rough_table_text": ""}]
        parse_pages_mock.return_value = {
            "ok": True,
            "error": None,
            "data_rows": [
                {
                    "hari": "Senin",
                    "jam_mulai": "07:00",
                    "jam_selesai": "08:40",
                    "mata_kuliah": "Algoritma",
                    "ruangan": "A1",
                    "semester": 3,
                }
            ],
            "stats": {"pages": 1, "rows": 1, "model": "google/gemini-2.5-flash-lite"},
        }

        doc = AcademicDocument.objects.create(user=self.user, file=SimpleUploadedFile("krs.pdf", b"%PDF-1.4"))
        ok = process_document(doc)
        self.assertTrue(ok)
        self.assertTrue(fake_vs.metadatas)
        self.assertTrue(any(m.get("doc_type") == "schedule" for m in fake_vs.metadatas))
        self.assertTrue(any(m.get("chunk_kind") == "row" for m in fake_vs.metadatas))

    @patch("core.ai_engine.ingest.get_vectorstore")
    @patch("core.ai_engine.ingest.UniversalScheduleParser.parse_pages")
    @patch("core.ai_engine.ingest._extract_pdf_tables")
    @patch("core.ai_engine.ingest.pdfplumber.open")
    def test_process_document_pdf_schedule_fallback_to_legacy_when_llm_fail(
        self,
        pdf_open_mock,
        extract_tables_mock,
        parse_pages_mock,
        get_vs_mock,
    ):
        fake_vs = _FakeVectorStore()
        get_vs_mock.return_value = fake_vs
        pdf_open_mock.return_value = _FakePdf([_FakePage("jadwal kuliah semester 3")])
        extract_tables_mock.return_value = (
            "jadwal table",
            ["Hari", "Jam", "Mata Kuliah"],
            [
                {
                    "hari": "Senin",
                    "jam": "07:00-08:40",
                    "mata_kuliah": "Algoritma",
                    "ruang": "A1",
                    "sesi": "I",
                    "page": 1,
                }
            ],
        )
        parse_pages_mock.return_value = {
            "ok": False,
            "error": "invalid_json",
            "data_rows": [],
            "stats": {"pages": 1, "rows": 0},
        }

        doc = AcademicDocument.objects.create(user=self.user, file=SimpleUploadedFile("jadwal.pdf", b"%PDF-1.4"))
        ok = process_document(doc)
        self.assertTrue(ok)
        self.assertTrue(fake_vs.metadatas)
        self.assertTrue(any(m.get("doc_type") == "schedule" for m in fake_vs.metadatas))
        self.assertTrue(any(m.get("chunk_kind") == "row" for m in fake_vs.metadatas))
