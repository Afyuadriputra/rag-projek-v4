from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, SimpleTestCase, TestCase

from core.ai_engine.retrieval.main import (
    _extract_doc_mentions,
    _normalize_doc_key,
    _resolve_user_doc_mentions,
)
from core import service


class DocMentionParserTests(SimpleTestCase):
    def test_extract_doc_mentions_returns_clean_query_and_mentions(self):
        clean, mentions = _extract_doc_mentions(
            "tolong cek @Jadwal Semester 3.pdf dan @Transkrip_aku.csv untuk saya"
        )
        self.assertEqual(
            mentions,
            ["Jadwal Semester 3.pdf", "Transkrip_aku.csv"],
        )
        self.assertNotIn("@", clean)
        self.assertIn("tolong cek", clean)

    def test_normalize_doc_key_handles_extension_and_symbols(self):
        out = _normalize_doc_key("  Jadwal-Mata Kuliah_Semester 3.PDF ")
        self.assertEqual(out, "jadwal mata kuliah semester 3")

    @patch("core.ai_engine.retrieval.main.AcademicDocument")
    def test_resolve_user_doc_mentions_unique_and_unresolved(self, doc_model_mock):
        doc_model_mock.objects.filter.return_value.values.return_value = [
            {"id": 11, "title": "Jadwal Semester 3.pdf"},
            {"id": 12, "title": "Transkrip Nilai 2025.csv"},
        ]
        out = _resolve_user_doc_mentions(user_id=1, mentions=["jadwal semester", "file ga ada"])
        self.assertEqual(out["resolved_doc_ids"], [11])
        self.assertEqual(out["resolved_titles"], ["Jadwal Semester 3.pdf"])
        self.assertEqual(out["unresolved_mentions"], ["file ga ada"])
        self.assertEqual(out["ambiguous_mentions"], [])

    @patch("core.ai_engine.retrieval.main.AcademicDocument")
    def test_resolve_user_doc_mentions_ambiguous(self, doc_model_mock):
        doc_model_mock.objects.filter.return_value.values.return_value = [
            {"id": 11, "title": "Jadwal Semester 3 A.pdf"},
            {"id": 12, "title": "Jadwal Semester 3 B.pdf"},
        ]
        out = _resolve_user_doc_mentions(user_id=1, mentions=["jadwal semester 3"])
        self.assertEqual(out["resolved_doc_ids"], [])
        self.assertEqual(out["ambiguous_mentions"], ["jadwal semester 3"])


class ServiceMetaPropagationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="u_meta",
            password="pass12345",
            email="u_meta@example.com",
        )

    @patch("core.service.ask_bot")
    def test_chat_and_save_returns_meta_from_ask_bot(self, ask_bot_mock):
        ask_bot_mock.return_value = {
            "answer": "Jawaban AI",
            "sources": [{"source": "x.pdf", "snippet": "x"}],
            "meta": {"mode": "doc_referenced", "referenced_documents": ["x.pdf"]},
        }
        out = service.chat_and_save(
            user=self.user,
            message="cek @x.pdf",
            request_id="rid-meta-1",
        )
        self.assertEqual(out["answer"], "Jawaban AI")
        self.assertEqual(out["meta"]["mode"], "doc_referenced")
        self.assertEqual(out["meta"]["referenced_documents"], ["x.pdf"])


class ChatApiMetaResponseTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="u_api",
            password="pass12345",
            email="u_api@example.com",
        )
        self.client.force_login(self.user)

    @patch("core.views.service.chat_and_save")
    def test_chat_api_returns_meta_field(self, chat_save_mock):
        chat_save_mock.return_value = {
            "answer": "Jawaban API",
            "sources": [],
            "meta": {"mode": "llm_only"},
            "session_id": 77,
        }
        res = self.client.post(
            "/api/chat/",
            data='{"message":"halo","mode":"chat"}',
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertIn("meta", payload)
        self.assertEqual(payload["meta"]["mode"], "llm_only")
