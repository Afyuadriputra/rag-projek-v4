import json
import os
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from core.models import AcademicDocument, PlannerRun


class PlannerV3ApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="planner_v3_u", password="pass12345")
        self.client.force_login(self.user)
        self.relevance_patcher = patch(
            "core.service.assess_documents_relevance",
            return_value={
                "is_relevant": True,
                "relevance_score": 0.91,
                "relevance_reasons": ["Dokumen akademik terdeteksi."],
                "blocked_reason": "",
            },
        )
        self.profile_patcher = patch(
            "core.service.extract_profile_hints",
            return_value={
                "major_candidates": [
                    {
                        "value": "Teknik Informatika",
                        "label": "Teknik Informatika",
                        "confidence": 0.86,
                        "evidence": ["term_match"],
                    }
                ],
                "career_candidates": [
                    {
                        "value": "Software Engineer",
                        "label": "Software Engineer",
                        "confidence": 0.72,
                        "evidence": ["term_match"],
                    }
                ],
                "confidence_summary": "high",
            },
        )
        self.blueprint_patcher = patch(
            "core.service._generate_planner_blueprint_llm",
            return_value={
                "version": "v3_dynamic",
                "steps": [
                    {
                        "step_key": "focus",
                        "title": "Fokus Analisis",
                        "question": "Fokus analisis?",
                        "options": [
                            {"id": 1, "label": "IPK", "value": "ipk_trend"},
                            {"id": 2, "label": "SKS", "value": "sks_recommendation"},
                        ],
                        "allow_manual": True,
                        "required": True,
                        "source_hint": "mixed",
                    },
                    {
                        "step_key": "jurusan",
                        "title": "Konfirmasi Jurusan",
                        "question": "Jurusan kamu?",
                        "options": [
                            {"id": 1, "label": "Teknik Informatika", "value": "Teknik Informatika"},
                            {"id": 2, "label": "Sistem Informasi", "value": "Sistem Informasi"},
                        ],
                        "allow_manual": True,
                        "required": True,
                        "source_hint": "profile",
                    },
                ],
                "meta": {
                    "doc_type_detected": "academic_document",
                    "major_inferred": "Teknik Informatika",
                    "major_confidence": 0.86,
                    "generation_mode": "llm",
                    "requires_major_confirmation": False,
                },
            },
        )
        self.relevance_patcher.start()
        self.profile_patcher.start()
        self.blueprint_patcher.start()
        self.addCleanup(self.relevance_patcher.stop)
        self.addCleanup(self.profile_patcher.stop)
        self.addCleanup(self.blueprint_patcher.stop)

    @staticmethod
    def _build_required_answers(blueprint: dict) -> dict:
        answers = {}
        steps = (blueprint or {}).get("steps") or []
        for step in steps:
            if not isinstance(step, dict):
                continue
            key = str(step.get("step_key") or "").strip()
            if not key:
                continue
            if not bool(step.get("required", True)):
                continue
            options = step.get("options") or []
            first_value = None
            if isinstance(options, list) and options:
                first_opt = options[0] if isinstance(options[0], dict) else {}
                first_value = first_opt.get("value")
            answers[key] = first_value if first_value not in {None, ""} else "manual"
        return answers

    def test_start_with_reuse_docs_success(self):
        AcademicDocument.objects.create(
            user=self.user,
            title="KHS Semester 1.pdf",
            file=SimpleUploadedFile("khs.pdf", b"x"),
            is_embedded=True,
        )
        res = self.client.post(
            "/api/planner/start/",
            data=json.dumps({"reuse_doc_ids": []}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload.get("status"), "success")
        self.assertTrue(payload.get("planner_run_id"))
        self.assertTrue(payload.get("intent_candidates"))
        self.assertEqual(payload.get("next_action"), "choose_intent")
        self.assertTrue((payload.get("wizard_blueprint") or {}).get("steps"))

    def test_start_with_specific_reuse_doc_ids_success(self):
        d1 = AcademicDocument.objects.create(
            user=self.user,
            title="KHS Semester 1.pdf",
            file=SimpleUploadedFile("khs1.pdf", b"x"),
            is_embedded=True,
        )
        AcademicDocument.objects.create(
            user=self.user,
            title="Jadwal Semester 1.pdf",
            file=SimpleUploadedFile("jadwal1.pdf", b"x"),
            is_embedded=True,
        )
        res = self.client.post(
            "/api/planner/start/",
            data=json.dumps({"reuse_doc_ids": [d1.id]}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        docs = payload.get("documents_summary") or []
        self.assertEqual(len(docs), 1)
        self.assertEqual(int(docs[0].get("id")), d1.id)

    @patch("core.service.upload_files_batch")
    def test_start_with_upload_success(self, upload_batch_mock):
        upload_batch_mock.return_value = {"status": "success", "msg": "ok"}
        AcademicDocument.objects.create(
            user=self.user,
            title="KRS.pdf",
            file=SimpleUploadedFile("krs.pdf", b"x"),
            is_embedded=True,
        )
        res = self.client.post("/api/planner/start/", data={"files": SimpleUploadedFile("a.pdf", b"abc")})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get("status"), "success")

    def test_start_requires_docs(self):
        res = self.client.post(
            "/api/planner/start/",
            data=json.dumps({"reuse_doc_ids": []}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json().get("status"), "error")

    @patch("core.service.assess_documents_relevance")
    def test_start_blocks_irrelevant_documents(self, relevance_mock):
        relevance_mock.return_value = {
            "is_relevant": False,
            "relevance_score": 0.12,
            "relevance_reasons": ["Dokumen bukan konteks akademik."],
            "blocked_reason": "Dokumen belum relevan untuk planner akademik.",
        }
        AcademicDocument.objects.create(
            user=self.user,
            title="Catatan Belanja.pdf",
            file=SimpleUploadedFile("belanja.pdf", b"x"),
            is_embedded=True,
        )
        res = self.client.post(
            "/api/planner/start/",
            data=json.dumps({"reuse_doc_ids": []}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        payload = res.json()
        self.assertEqual(payload.get("status"), "error")
        self.assertEqual(payload.get("error_code"), "IRRELEVANT_DOCUMENTS")
        self.assertTrue(payload.get("required_upload"))

    def test_execute_rejects_answers_non_object(self):
        res = self.client.post(
            "/api/planner/execute/",
            data=json.dumps({"planner_run_id": "abc", "answers": ["bad"]}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("answers harus object", res.json().get("error", ""))

    @patch("core.service.ask_bot")
    def test_execute_rejects_unknown_step_key(self, ask_bot_mock):
        ask_bot_mock.return_value = {"answer": "ok", "sources": []}
        AcademicDocument.objects.create(
            user=self.user,
            title="KHS.pdf",
            file=SimpleUploadedFile("khs.pdf", b"x"),
            is_embedded=True,
        )
        start = self.client.post(
            "/api/planner/start/",
            data=json.dumps({"reuse_doc_ids": []}),
            content_type="application/json",
        ).json()
        run_id = start["planner_run_id"]
        res = self.client.post(
            "/api/planner/execute/",
            data=json.dumps({"planner_run_id": run_id, "answers": {"step_liar": "abc"}}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("tidak dikenal", res.json().get("error", ""))

    @patch("core.service.ask_bot")
    def test_execute_requires_major_confirmation_when_needed(self, ask_bot_mock):
        ask_bot_mock.return_value = {"answer": "ok", "sources": []}
        session_res = self.client.post("/api/sessions/", data=json.dumps({}), content_type="application/json")
        session_id = session_res.json()["session"]["id"]
        run = PlannerRun.objects.create(
            user=self.user,
            session_id=session_id,
            status=PlannerRun.STATUS_READY,
            wizard_blueprint={
                "version": "v3_dynamic",
                "steps": [
                    {
                        "step_key": "focus",
                        "title": "Fokus",
                        "question": "Pilih fokus",
                        "options": [{"id": 1, "label": "A", "value": "a"}, {"id": 2, "label": "B", "value": "b"}],
                        "allow_manual": False,
                        "required": True,
                        "source_hint": "mixed",
                    },
                    {
                        "step_key": "jurusan",
                        "title": "Jurusan",
                        "question": "Konfirmasi jurusan",
                        "options": [{"id": 1, "label": "TI", "value": "TI"}, {"id": 2, "label": "SI", "value": "SI"}],
                        "allow_manual": True,
                        "required": False,
                        "source_hint": "profile",
                    },
                ],
                "meta": {"requires_major_confirmation": True},
            },
            documents_snapshot=[{"id": 1, "title": "KHS.pdf"}],
            expires_at=timezone.now() + timedelta(hours=1),
        )
        res = self.client.post(
            "/api/planner/execute/",
            data=json.dumps({"planner_run_id": str(run.id), "answers": {"focus": "a"}}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("jurusan", res.json().get("error", "").lower())

    @patch("core.service.ask_bot")
    def test_execute_rejects_when_run_expired(self, ask_bot_mock):
        ask_bot_mock.return_value = {"answer": "ok", "sources": []}
        AcademicDocument.objects.create(
            user=self.user,
            title="KHS.pdf",
            file=SimpleUploadedFile("khs.pdf", b"x"),
            is_embedded=True,
        )
        start = self.client.post(
            "/api/planner/start/",
            data=json.dumps({"reuse_doc_ids": []}),
            content_type="application/json",
        ).json()
        run_id = start["planner_run_id"]
        run = PlannerRun.objects.get(id=run_id)
        run.expires_at = timezone.now() - timedelta(minutes=1)
        run.save(update_fields=["expires_at"])

        first_step = ((start.get("wizard_blueprint") or {}).get("steps") or [{}])[0].get("step_key") or "focus"
        res = self.client.post(
            "/api/planner/execute/",
            data=json.dumps({"planner_run_id": run_id, "answers": {first_step: "x"}}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("kedaluwarsa", res.json().get("error", ""))

    @patch("core.service.ask_bot")
    def test_cancel_blocks_execute(self, ask_bot_mock):
        ask_bot_mock.return_value = {"answer": "ok", "sources": []}
        AcademicDocument.objects.create(
            user=self.user,
            title="KHS.pdf",
            file=SimpleUploadedFile("khs.pdf", b"x"),
            is_embedded=True,
        )
        start = self.client.post(
            "/api/planner/start/",
            data=json.dumps({"reuse_doc_ids": []}),
            content_type="application/json",
        ).json()
        run_id = start["planner_run_id"]
        cancel = self.client.post(
            "/api/planner/cancel/",
            data=json.dumps({"planner_run_id": run_id}),
            content_type="application/json",
        )
        self.assertEqual(cancel.status_code, 200)
        self.assertEqual(cancel.json().get("status"), "success")

        any_step = ((start.get("wizard_blueprint") or {}).get("steps") or [{}])[0].get("step_key") or "focus"
        res = self.client.post(
            "/api/planner/execute/",
            data=json.dumps({"planner_run_id": run_id, "answers": {any_step: "x"}}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("cancelled", res.json().get("error", ""))

    def test_cancel_idempotent_for_completed_or_cancelled(self):
        AcademicDocument.objects.create(
            user=self.user,
            title="KHS.pdf",
            file=SimpleUploadedFile("khs.pdf", b"x"),
            is_embedded=True,
        )
        start = self.client.post(
            "/api/planner/start/",
            data=json.dumps({"reuse_doc_ids": []}),
            content_type="application/json",
        ).json()
        run_id = start["planner_run_id"]

        first = self.client.post(
            "/api/planner/cancel/",
            data=json.dumps({"planner_run_id": run_id}),
            content_type="application/json",
        )
        second = self.client.post(
            "/api/planner/cancel/",
            data=json.dumps({"planner_run_id": run_id}),
            content_type="application/json",
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json().get("status"), "success")

    @patch("core.service.ask_bot")
    def test_execute_success(self, ask_bot_mock):
        ask_bot_mock.return_value = {"answer": "hasil planner", "sources": []}
        AcademicDocument.objects.create(
            user=self.user,
            title="KHS.pdf",
            file=SimpleUploadedFile("khs.pdf", b"x"),
            is_embedded=True,
        )
        start = self.client.post(
            "/api/planner/start/",
            data=json.dumps({"reuse_doc_ids": []}),
            content_type="application/json",
        ).json()
        run_id = start["planner_run_id"]
        answers = self._build_required_answers(start.get("wizard_blueprint") or {})
        res = self.client.post(
            "/api/planner/execute/",
            data=json.dumps(
                {
                    "planner_run_id": run_id,
                    "answers": answers,
                    "client_summary": "Analisis KHS saya",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get("status"), "success")
        run = PlannerRun.objects.get(id=run_id)
        self.assertEqual(run.status, PlannerRun.STATUS_COMPLETED)

    def test_next_step_success(self):
        AcademicDocument.objects.create(
            user=self.user,
            title="KHS.pdf",
            file=SimpleUploadedFile("khs.pdf", b"x"),
            is_embedded=True,
        )
        start = self.client.post(
            "/api/planner/start/",
            data=json.dumps({"reuse_doc_ids": []}),
            content_type="application/json",
        ).json()
        run_id = start["planner_run_id"]
        intent = (start.get("intent_candidates") or [])[0]
        res = self.client.post(
            "/api/planner/next-step/",
            data=json.dumps(
                {
                    "planner_run_id": run_id,
                    "step_key": "intent",
                    "answer_value": intent.get("value") or "ipk_trend",
                    "answer_mode": "option",
                    "client_step_seq": 1,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload.get("status"), "success")
        self.assertTrue(payload.get("progress"))
        self.assertIn("can_generate_now", payload)
        run = PlannerRun.objects.get(id=run_id)
        self.assertEqual(run.current_depth, 1)
        self.assertTrue(run.path_taken)

    def test_next_step_rejects_wrong_sequence(self):
        AcademicDocument.objects.create(
            user=self.user,
            title="KHS.pdf",
            file=SimpleUploadedFile("khs.pdf", b"x"),
            is_embedded=True,
        )
        start = self.client.post(
            "/api/planner/start/",
            data=json.dumps({"reuse_doc_ids": []}),
            content_type="application/json",
        ).json()
        run_id = start["planner_run_id"]
        res = self.client.post(
            "/api/planner/next-step/",
            data=json.dumps(
                {
                    "planner_run_id": run_id,
                    "step_key": "intent",
                    "answer_value": "ipk_trend",
                    "answer_mode": "option",
                    "client_step_seq": 2,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("client_step_seq", res.json().get("error", ""))

    @patch("core.service.ask_bot")
    def test_execute_rejects_inconsistent_path(self, ask_bot_mock):
        ask_bot_mock.return_value = {"answer": "ok", "sources": []}
        AcademicDocument.objects.create(
            user=self.user,
            title="KHS.pdf",
            file=SimpleUploadedFile("khs.pdf", b"x"),
            is_embedded=True,
        )
        start = self.client.post(
            "/api/planner/start/",
            data=json.dumps({"reuse_doc_ids": []}),
            content_type="application/json",
        ).json()
        run_id = start["planner_run_id"]
        run = PlannerRun.objects.get(id=run_id)
        run.path_taken = [{"seq": 1, "step_key": "intent", "answer_value": "ipk_trend", "answer_mode": "option"}]
        run.answers_snapshot = {"intent": "ipk_trend"}
        run.current_depth = 1
        run.status = PlannerRun.STATUS_COLLECTING
        run.save(update_fields=["path_taken", "answers_snapshot", "current_depth", "status"])
        res = self.client.post(
            "/api/planner/execute/",
            data=json.dumps(
                {
                    "planner_run_id": run_id,
                    "answers": {"intent": "ipk_trend"},
                    "path_taken": [],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("path_taken", res.json().get("error", ""))

    @patch.dict(os.environ, {"PLANNER_V3_ENABLED": "0"})
    def test_planner_v3_endpoints_disabled_by_flag(self):
        res_start = self.client.post("/api/planner/start/", data=json.dumps({}), content_type="application/json")
        res_next = self.client.post("/api/planner/next-step/", data=json.dumps({}), content_type="application/json")
        res_execute = self.client.post("/api/planner/execute/", data=json.dumps({}), content_type="application/json")
        res_cancel = self.client.post("/api/planner/cancel/", data=json.dumps({}), content_type="application/json")
        self.assertEqual(res_start.status_code, 404)
        self.assertEqual(res_next.status_code, 404)
        self.assertEqual(res_execute.status_code, 404)
        self.assertEqual(res_cancel.status_code, 404)

    @patch("core.service._extract_major_state")
    def test_start_major_unknown_returns_warning_and_meta_source(self, major_state_mock):
        major_state_mock.return_value = {
            "major_label": "",
            "major_confidence_score": 0.31,
            "major_confidence_level": "low",
            "source": "unknown",
            "evidence": [],
        }
        AcademicDocument.objects.create(
            user=self.user,
            title="Dokumen Akademik Umum.pdf",
            file=SimpleUploadedFile("doc.pdf", b"x"),
            is_embedded=True,
        )
        res = self.client.post(
            "/api/planner/start/",
            data=json.dumps({"reuse_doc_ids": []}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload.get("status"), "success")
        self.assertIn("Jurusan belum dapat dipastikan", str(payload.get("warning") or ""))
        self.assertEqual((payload.get("planner_header") or {}).get("major_label"), "Belum terdeteksi")
        self.assertEqual((payload.get("planner_meta") or {}).get("major_source"), "unknown")

    @patch("core.service._generate_next_step_llm")
    def test_next_step_manual_major_override_updates_major_state(self, next_llm_mock):
        next_llm_mock.return_value = {
            "ready_to_generate": False,
            "step": {
                "step_key": "followup_1",
                "title": "Pendalaman",
                "question": "Fokus berikutnya?",
                "options": [{"id": 1, "label": "A", "value": "a"}, {"id": 2, "label": "B", "value": "b"}],
                "allow_manual": True,
                "required": True,
                "source_hint": "mixed",
                "reason": "test",
            },
        }
        AcademicDocument.objects.create(
            user=self.user,
            title="KHS.pdf",
            file=SimpleUploadedFile("khs.pdf", b"x"),
            is_embedded=True,
        )
        start = self.client.post(
            "/api/planner/start/",
            data=json.dumps({"reuse_doc_ids": []}),
            content_type="application/json",
        ).json()
        run_id = start["planner_run_id"]
        res = self.client.post(
            "/api/planner/next-step/",
            data=json.dumps(
                {
                    "planner_run_id": run_id,
                    "step_key": "intent",
                    "answer_value": "jurusan saya yang benar teknik informatika",
                    "answer_mode": "manual",
                    "client_step_seq": 1,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload.get("status"), "success")
        major_state = payload.get("major_state") or {}
        self.assertEqual(major_state.get("source"), "user_override")
        self.assertEqual(major_state.get("major_label"), "Teknik Informatika")
        run = PlannerRun.objects.get(id=run_id)
        self.assertEqual((run.major_state_snapshot or {}).get("source"), "user_override")
        self.assertEqual((run.major_state_snapshot or {}).get("major_label"), "Teknik Informatika")

    @patch("core.service._generate_next_step_llm")
    def test_next_step_injects_fallback_options_when_llm_returns_empty_options(self, next_llm_mock):
        next_llm_mock.return_value = {
            "ready_to_generate": False,
            "step": {
                "step_key": "followup_1",
                "title": "Pendalaman Analisis",
                "question": "Area spesifik mana yang ingin didalami?",
                "options": [],
                "allow_manual": True,
                "required": True,
                "source_hint": "mixed",
                "reason": "test",
            },
        }
        AcademicDocument.objects.create(
            user=self.user,
            title="KHS.pdf",
            file=SimpleUploadedFile("khs.pdf", b"x"),
            is_embedded=True,
        )
        start = self.client.post(
            "/api/planner/start/",
            data=json.dumps({"reuse_doc_ids": []}),
            content_type="application/json",
        ).json()
        run_id = start["planner_run_id"]
        res = self.client.post(
            "/api/planner/next-step/",
            data=json.dumps(
                {
                    "planner_run_id": run_id,
                    "step_key": "intent",
                    "answer_value": "saya ingin fokus skripsi",
                    "answer_mode": "manual",
                    "client_step_seq": 1,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload.get("status"), "success")
        step = payload.get("step") or {}
        options = step.get("options") or []
        self.assertGreaterEqual(len(options), 2)
        self.assertTrue(all(isinstance(x, dict) and x.get("label") for x in options))
