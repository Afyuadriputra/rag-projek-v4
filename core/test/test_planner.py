import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import AcademicDocument
from core.academic import planner as planner_engine


class PlannerEngineTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="planner_u", password="pass123")

    def test_detect_data_level_level3(self):
        AcademicDocument.objects.create(
            user=self.user,
            title="Transkrip Nilai Semester 1.pdf",
            file=SimpleUploadedFile("t.pdf", b"x"),
            is_embedded=True,
        )
        AcademicDocument.objects.create(
            user=self.user,
            title="Jadwal KRS Semester 5.pdf",
            file=SimpleUploadedFile("j.pdf", b"x"),
            is_embedded=True,
        )

        level = planner_engine.detect_data_level(self.user)
        self.assertEqual(level["level"], 3)
        self.assertTrue(level["has_transcript"])
        self.assertTrue(level["has_schedule"])

    def test_initial_state_skips_to_goals_when_level3(self):
        state = planner_engine.build_initial_state(
            {
                "level": 3,
                "has_transcript": True,
                "has_schedule": True,
                "has_curriculum": False,
                "documents": [],
            }
        )
        self.assertEqual(state["current_step"], "goals")

    def test_process_answer_transitions(self):
        state = planner_engine.build_initial_state(
            {
                "level": 0,
                "has_transcript": False,
                "has_schedule": False,
                "has_curriculum": False,
                "documents": [],
            }
        )
        state = planner_engine.process_answer(state, message="2")
        self.assertEqual(state["current_step"], "profile_jurusan")
        state = planner_engine.process_answer(state, message="Teknik Informatika")
        self.assertEqual(state["current_step"], "profile_semester")


class PlannerApiTests(TestCase):
    def setUp(self):
        self.client = self.client_class()
        self.user = User.objects.create_user(username="planner_api", password="pass123")
        self.client.force_login(self.user)

    def test_planner_mode_start(self):
        resp = self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": ""}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content.decode())
        self.assertIn("type", body)
        self.assertIn(body["type"], {"planner_step", "planner_generate", "planner_output"})
        self.assertIn("options", body)
        self.assertIn("allow_custom", body)
        self.assertIn("planner_step", body)
        self.assertIn("session_state", body)
        self.assertIsInstance(body["session_state"], dict)

    def test_planner_mode_continue(self):
        self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": ""}),
            content_type="application/json",
        )
        resp = self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": "1", "option_id": 1}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content.decode())
        self.assertIn("type", body)
        self.assertIn("planner_step", body)
        self.assertIn("session_state", body)

    def test_planner_mode_start_level0_begins_from_data_step(self):
        resp = self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": ""}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content.decode())
        self.assertEqual(body.get("planner_step"), "data")
        self.assertEqual(body.get("session_state", {}).get("data_level", {}).get("level"), 0)

    def test_planner_mode_start_level2_keeps_data_step_with_partial_flags(self):
        AcademicDocument.objects.create(
            user=self.user,
            title="Transkrip Nilai Semester 3.pdf",
            file=SimpleUploadedFile("transkrip.pdf", b"x"),
            is_embedded=True,
        )

        resp = self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": ""}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content.decode())
        self.assertEqual(body.get("planner_step"), "data")
        data_level = body.get("session_state", {}).get("data_level", {})
        self.assertEqual(data_level.get("level"), 2)
        self.assertTrue(data_level.get("has_transcript"))
        self.assertFalse(data_level.get("has_schedule"))

    def test_planner_mode_start_level3_skips_to_goals_step(self):
        AcademicDocument.objects.create(
            user=self.user,
            title="Transkrip Nilai Semester 3.pdf",
            file=SimpleUploadedFile("transkrip.pdf", b"x"),
            is_embedded=True,
        )
        AcademicDocument.objects.create(
            user=self.user,
            title="Jadwal KRS Semester 5.pdf",
            file=SimpleUploadedFile("jadwal.pdf", b"x"),
            is_embedded=True,
        )

        resp = self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": ""}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content.decode())
        self.assertEqual(body.get("planner_step"), "goals")
        self.assertEqual(body.get("session_state", {}).get("data_level", {}).get("level"), 3)

    def test_chat_invalid_mode(self):
        resp = self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "unknown", "message": "halo"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_chat_invalid_option_id_type(self):
        resp = self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": "1", "option_id": "abc"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    @patch("core.views.service.chat_and_save", return_value={"answer": "ok", "sources": [], "session_id": 1})
    def test_chat_mode_still_works(self, _chat_mock):
        resp = self.client.post(
            "/api/chat/",
            data=json.dumps({"message": "halo", "mode": "chat"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content.decode())
        self.assertEqual(body.get("answer"), "ok")
