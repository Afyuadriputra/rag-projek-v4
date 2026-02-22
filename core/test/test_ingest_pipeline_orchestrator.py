from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from core.ai_engine.ingest import process_document
from core.ai_engine import ingest


class IngestPipelineOrchestratorTests(TestCase):
    def _mk_doc(self, path: str, title: str = "doc.txt"):
        return SimpleNamespace(
            id=10,
            title=title,
            file=SimpleNamespace(path=path),
            user=SimpleNamespace(id=99),
        )

    def test_orchestrator_text_flow_writes_once(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "a.txt"
            p.write_text("hello world", encoding="utf-8")
            doc = self._mk_doc(str(p), "a.txt")

            fake_vs = MagicMock()
            with patch("core.ai_engine.ingest.get_vectorstore", return_value=fake_vs):
                ok = process_document(doc)
            self.assertTrue(ok)
            fake_vs.add_texts.assert_called_once()

    def test_orchestrator_returns_false_on_error(self):
        doc = self._mk_doc("D:/tmp/does-not-exist.txt", "missing.txt")
        self.assertFalse(process_document(doc))

    @patch("core.ai_engine.ingest.UniversalTranscriptParser.parse_pages")
    @patch("core.ai_engine.ingest._extract_pdf_tables")
    @patch("core.ai_engine.ingest._extract_pdf_page_raw_payload")
    @patch("core.ai_engine.ingest.pdfplumber.open")
    @patch("core.ai_engine.ingest.get_vectorstore")
    def test_compat_patch_transcript_parser_affects_facade_flow(
        self,
        mock_get_vectorstore,
        mock_pdf_open,
        mock_page_payload,
        mock_extract_tables,
        mock_parse_pages,
    ):
        doc = self._mk_doc("D:/tmp/khs.pdf", "khs.pdf")
        mock_get_vectorstore.return_value = MagicMock()
        fake_page = MagicMock()
        fake_page.extract_text.return_value = "KHS"
        mock_pdf_open.return_value.__enter__.return_value.pages = [fake_page]
        mock_extract_tables.return_value = ("", ["Grade", "Bobot"], [])
        mock_page_payload.return_value = [{"page": 1, "raw_text": "x", "rough_table_text": ""}]
        mock_parse_pages.return_value = {
            "ok": True,
            "data_rows": [{"semester": 1, "mata_kuliah": "Kalkulus", "sks": 3, "nilai_huruf": "A"}],
            "stats": {},
        }

        ok = process_document(doc)
        self.assertTrue(ok)
        mock_parse_pages.assert_called()

    @patch("core.ai_engine.ingest._norm", side_effect=lambda v: f"NORM::{str(v).strip()}")
    def test_compat_patch_norm_affects_pdf_page_payload(self, _mock_norm):
        fake_page = MagicMock()
        fake_page.extract_text.return_value = "  Hello  "
        fake_page.extract_tables.return_value = [[[" A ", " B "]]]
        fake_pdf = SimpleNamespace(pages=[fake_page])

        payload = ingest._extract_pdf_page_raw_payload(fake_pdf, file_path="")
        self.assertEqual(payload[0]["raw_text"], "NORM::Hello")
        self.assertIn("NORM::A | NORM::B", payload[0]["rough_table_text"])

    @patch("core.ai_engine.ingest._normalize_time_range", side_effect=lambda _v: "09:00-10:00")
    def test_compat_patch_normalize_time_range_affects_extract_pdf_tables(self, _mock_time):
        fake_page = MagicMock()
        fake_page.extract_tables.return_value = [
            [
                ["HARI", "JAM", "MATA KULIAH"],
                ["Senin", "7.00 - 8.40", "Algoritma"],
            ]
        ]
        fake_page.extract_text.return_value = ""
        fake_pdf = SimpleNamespace(pages=[fake_page])

        _table_text, _cols, rows = ingest._extract_pdf_tables(fake_pdf)
        self.assertTrue(rows)
        self.assertEqual(rows[0].get("jam"), "09:00-10:00")
