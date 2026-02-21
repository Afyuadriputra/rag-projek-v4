from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from core.models import ChatHistory, ChatSession
from core.services.chat import service as chat_service


class ChatServiceUnitTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="svc_chat_u", password="pass12345")

    @patch("core.services.chat.service.ask_bot")
    def test_chat_and_save_grade_rescue_path(self, ask_bot_mock):
        out = chat_service.chat_and_save(
            user=self.user,
            message="nilai sekarang 60 bobot 40 target B",
            request_id="rid-chat-unit",
        )
        ask_bot_mock.assert_not_called()
        self.assertIn("Grade Rescue", out["answer"])
        self.assertEqual(out["sources"], [])
        self.assertEqual(ChatHistory.objects.filter(user=self.user).count(), 1)

    def test_get_or_create_chat_session_existing(self):
        s = ChatSession.objects.create(user=self.user, title="x")
        out = chat_service.get_or_create_chat_session(user=self.user, session_id=s.id)
        self.assertEqual(out.id, s.id)

    @patch("core.services.chat.service.ask_bot")
    def test_chat_and_save_with_meta_sources(self, ask_bot_mock):
        ask_bot_mock.return_value = {"answer": "ok", "sources": [{"source": "a"}], "meta": {"mode": "x"}}
        out = chat_service.chat_and_save(user=self.user, message="halo", request_id="rid")
        self.assertEqual(out["answer"], "ok")
        self.assertEqual(out["sources"], [{"source": "a"}])
        self.assertEqual(out["meta"], {"mode": "x"})

