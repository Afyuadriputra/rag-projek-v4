from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from core.models import ChatHistory
from core.service import chat_and_save, planner_continue


class ServiceGradeIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="svc_grade_u", password="pass123")

    @patch("core.service.ask_bot")
    def test_chat_and_save_uses_grade_calculator_path(self, ask_bot_mock):
        payload = chat_and_save(
            user=self.user,
            message="hitung nilai, nilai sekarang 60 bobot 40 target B",
            request_id="rid-test",
        )
        ask_bot_mock.assert_not_called()
        self.assertIn("Grade Rescue", payload["answer"])
        self.assertIn("76.67", payload["answer"])
        self.assertEqual(payload["sources"], [])
        self.assertEqual(ChatHistory.objects.filter(user=self.user).count(), 1)

    @patch("core.service._generate_planner_with_llm", return_value="")
    def test_planner_continue_includes_grade_calc_in_generated_output(self, _llm_mock):
        planner_state = {
            "current_step": "review",
            "collected_data": {
                "jurusan": "Teknik Informatika",
                "semester": 5,
                "goal": "max_gpa",
                "career": "Software Engineer",
                "time_pref": "morning",
                "free_day": "friday",
            },
            "data_level": {"level": 0},
        }

        payload, new_state = planner_continue(
            user=self.user,
            planner_state=planner_state,
            message="UTS 60 bobot 40 target B",
            option_id=1,  # confirm -> generate
            request_id="rid-plan",
        )

        self.assertEqual(payload["type"], "planner_output")
        self.assertIn("Grade Rescue", payload["answer"])
        self.assertIn("76.67", payload["answer"])
        self.assertIn("## 📅 Jadwal", payload["answer"])
        self.assertIn("## 🎯 Rekomendasi Mata Kuliah", payload["answer"])
        self.assertIn("## 💼 Keselarasan Karir", payload["answer"])
        self.assertIn("## ⚖️ Distribusi Beban", payload["answer"])
        self.assertIn("## Selanjutnya", payload["answer"])
        self.assertEqual(new_state.get("current_step"), "iterate")

    @patch("core.service._generate_planner_with_llm", return_value="## 📅 Jadwal\n- draft")
    def test_planner_generate_enforces_required_sections(self, _llm_mock):
        planner_state = {
            "current_step": "review",
            "collected_data": {
                "jurusan": "Teknik Informatika",
                "semester": 5,
            },
            "data_level": {"level": 0},
        }
        payload, _new_state = planner_continue(
            user=self.user,
            planner_state=planner_state,
            message="1",
            option_id=1,  # confirm -> generate
            request_id="rid-required-sections",
        )
        self.assertEqual(payload["type"], "planner_output")
        self.assertIn("## 📅 Jadwal", payload["answer"])
        self.assertIn("## 🎯 Rekomendasi Mata Kuliah", payload["answer"])
        self.assertIn("## 💼 Keselarasan Karir", payload["answer"])
        self.assertIn("## ⚖️ Distribusi Beban", payload["answer"])
        self.assertIn("## ⚠️ Grade Rescue", payload["answer"])
        self.assertIn("## Selanjutnya", payload["answer"])
