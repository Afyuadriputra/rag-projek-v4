from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from core.models import ChatHistory
from core.service import chat_and_save


class _FakeCollection:
    def __init__(self, documents, metadatas):
        self._documents = documents
        self._metadatas = metadatas

    def get(self, where=None, include=None):
        return {
            "ids": [str(i) for i in range(len(self._documents))],
            "documents": self._documents,
            "metadatas": self._metadatas,
        }


class _FakeVectorStore:
    def __init__(self, collection):
        self._collection = collection


class ServiceTranscriptRecapTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="svc_recap_u", password="pass123")

    @patch("core.service.ask_bot")
    @patch("core.service.get_vectorstore")
    def test_chat_and_save_recap_uses_llm_first(self, get_vs_mock, ask_bot_mock):
        ask_bot_mock.return_value = {"answer": "jawaban llm", "sources": [{"source": "llm"}]}

        documents = [
            "CSV_ROW 1: semester=1 | mata_kuliah=ALGORITMA DAN PEMROGRAMAN | sks=3",
            "CSV_ROW 2: semester=2 | mata_kuliah=BASIS DATA | sks=3",
            "CSV_ROW 3: semester=2 | mata_kuliah=JARINGAN KOMPUTER | sks=3",
            # duplikat baris harus terhapus dari hasil akhir
            "CSV_ROW 3: semester=2 | mata_kuliah=JARINGAN KOMPUTER | sks=3",
        ]
        metadatas = [
            {"source": "semester 1.pdf", "chunk_kind": "row"},
            {"source": "semester 2.pdf", "chunk_kind": "row"},
            {"source": "semester 2.pdf", "chunk_kind": "row"},
            {"source": "semester 2.pdf", "chunk_kind": "row"},
        ]
        get_vs_mock.return_value = _FakeVectorStore(_FakeCollection(documents, metadatas))

        payload = chat_and_save(
            user=self.user,
            message="Tolong rekap semua mata kuliah dan total SKS saya per semester",
            request_id="rid-recap",
        )

        ask_bot_mock.assert_called_once()
        self.assertEqual(payload["answer"], "jawaban llm")
        self.assertIn("meta", payload)
        self.assertEqual(ChatHistory.objects.filter(user=self.user).count(), 1)

    @patch("core.service.ask_bot")
    @patch("core.service.get_vectorstore")
    def test_chat_and_save_recap_falls_back_to_llm_if_no_structured_rows(self, get_vs_mock, ask_bot_mock):
        ask_bot_mock.return_value = {"answer": "jawaban llm", "sources": [{"source": "fallback"}]}
        get_vs_mock.return_value = _FakeVectorStore(_FakeCollection(documents=["teks bebas"], metadatas=[{}]))

        payload = chat_and_save(
            user=self.user,
            message="rekap mata kuliah saya",
            request_id="rid-recap-fallback",
        )

        ask_bot_mock.assert_called_once()
        self.assertEqual(payload["answer"], "jawaban llm")
        self.assertEqual(ChatHistory.objects.filter(user=self.user).count(), 1)
