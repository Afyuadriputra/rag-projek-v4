import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from core.models import AcademicDocument


class ServiceFacadeCompatTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="svc_facade_u", password="pass12345")
        self.client.force_login(self.user)

    @patch("core.service.assess_documents_relevance")
    def test_patch_assess_documents_relevance_affects_start_v3(self, relevance_mock):
        relevance_mock.return_value = {
            "is_relevant": False,
            "relevance_score": 0.1,
            "relevance_reasons": ["irrelevant"],
            "blocked_reason": "blocked",
        }
        AcademicDocument.objects.create(
            user=self.user,
            title="Catatan random.pdf",
            file=SimpleUploadedFile("x.pdf", b"x"),
            is_embedded=True,
        )
        res = self.client.post("/api/planner/start/", data=json.dumps({"reuse_doc_ids": []}), content_type="application/json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json().get("error_code"), "IRRELEVANT_DOCUMENTS")

    @patch("core.service._generate_next_step_llm")
    def test_patch_generate_next_step_llm_affects_next_step_v3(self, next_mock):
        next_mock.return_value = {
            "ready_to_generate": False,
            "step": {
                "step_key": "followup_1",
                "title": "Pendalaman",
                "question": "Lanjut?",
                "options": [{"id": 1, "label": "A", "value": "a"}, {"id": 2, "label": "B", "value": "b"}],
                "allow_manual": True,
                "required": True,
                "source_hint": "mixed",
                "reason": "x",
            },
        }
        AcademicDocument.objects.create(
            user=self.user,
            title="KHS.pdf",
            file=SimpleUploadedFile("khs.pdf", b"x"),
            is_embedded=True,
        )
        start = self.client.post("/api/planner/start/", data=json.dumps({"reuse_doc_ids": []}), content_type="application/json").json()
        run_id = start["planner_run_id"]
        res = self.client.post(
            "/api/planner/next-step/",
            data=json.dumps(
                {
                    "planner_run_id": run_id,
                    "step_key": "intent",
                    "answer_value": "ipk",
                    "answer_mode": "manual",
                    "client_step_seq": 1,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload.get("status"), "success")
        self.assertEqual((payload.get("step") or {}).get("step_key"), "followup_1")

