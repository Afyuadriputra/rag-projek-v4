import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import AcademicDocument, PlannerHistory, ChatHistory
from core.academic import planner as planner_engine


class _FakePdfPage:
    def __init__(self, tables):
        self._tables = tables

    def extract_tables(self):
        return self._tables


class _FakePdfDoc:
    def __init__(self, tables):
        self.pages = [_FakePdfPage(tables)]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


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

    def test_dynamic_question_uses_profile_hints_question_candidates(self):
        state = planner_engine.build_initial_state(
            {
                "level": 0,
                "has_transcript": False,
                "has_schedule": False,
                "has_curriculum": False,
                "documents": [],
            }
        )
        state["profile_hints"] = {
            "question_candidates": [
                {
                    "step": "profile_jurusan",
                    "question": "Kami mendeteksi jurusan kamu kemungkinan Teknik Informatika. Benar?",
                    "mode": "confirm",
                }
            ]
        }
        state["current_step"] = "profile_jurusan"
        payload = planner_engine.get_step_payload(state)
        self.assertIn("Kami mendeteksi jurusan", payload.get("answer", ""))

    def test_build_wizard_blueprint_v3_has_steps_and_docs(self):
        blueprint = planner_engine.build_wizard_blueprint_v3(
            data_level={"level": 2, "has_transcript": True, "has_schedule": False},
            profile_hints={"confidence_summary": "medium"},
            documents_summary=[{"id": 1, "title": "KHS.pdf"}],
        )
        self.assertEqual(blueprint.get("version"), "v3")
        steps = blueprint.get("steps") or []
        self.assertTrue(len(steps) >= 3)
        self.assertIn("documents_summary", blueprint)


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
        self.assertIn("planner_warning", body)
        self.assertIn("profile_hints", body)
        self.assertIn("Upload sumber", str(body.get("planner_warning") or ""))
        self.assertEqual((body.get("planner_meta") or {}).get("origin"), "start_auto")
        self.assertEqual((body.get("planner_meta") or {}).get("event_type"), "start_auto")

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
        self.assertEqual((body.get("planner_meta") or {}).get("origin"), "option_select")
        self.assertEqual((body.get("planner_meta") or {}).get("event_type"), "option_select")

    def test_planner_mode_continue_empty_answer_keeps_same_step(self):
        start = self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": ""}),
            content_type="application/json",
        )
        start_body = json.loads(start.content.decode())
        self.assertEqual(start_body.get("planner_step"), "data")

        resp = self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": ""}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content.decode())
        self.assertEqual(body.get("planner_step"), "data")
        self.assertIn("Kamu belum menjawab", body.get("answer", ""))

    def test_planner_mode_continue_invalid_text_keeps_same_step(self):
        start = self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": ""}),
            content_type="application/json",
        )
        start_body = json.loads(start.content.decode())
        self.assertEqual(start_body.get("planner_step"), "data")

        resp = self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": "bebas aja"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content.decode())
        self.assertEqual(body.get("planner_step"), "data")
        self.assertIn("Jawaban belum sesuai opsi", body.get("answer", ""))
        self.assertEqual((body.get("planner_meta") or {}).get("origin"), "user_input")
        self.assertEqual((body.get("planner_meta") or {}).get("event_type"), "user_input")

    def test_planner_data_option_upload_requires_document_first(self):
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
        self.assertEqual(body.get("planner_step"), "data")
        self.assertIn("Opsi 1 memerlukan dokumen akademik", body.get("answer", ""))

    def test_planner_data_option_upload_passes_when_embedded_doc_exists(self):
        AcademicDocument.objects.create(
            user=self.user,
            title="KRS Semester 5.pdf",
            file=SimpleUploadedFile("krs.pdf", b"x"),
            is_embedded=True,
        )
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
        self.assertEqual(body.get("planner_step"), "profile_jurusan")

    def test_planner_jurusan_options_dynamic_from_documents(self):
        AcademicDocument.objects.create(
            user=self.user,
            title="Program Studi Teknik Informatika.pdf",
            file=SimpleUploadedFile("ti.pdf", b"x"),
            is_embedded=True,
        )
        self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": ""}),
            content_type="application/json",
        )
        resp = self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": "2", "option_id": 2}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content.decode())
        self.assertEqual(body.get("planner_step"), "profile_jurusan")
        labels = [str(o.get("label")) for o in body.get("options", [])]
        self.assertIn("Teknik Informatika", labels)

    def test_planner_career_options_dynamic_from_documents(self):
        AcademicDocument.objects.create(
            user=self.user,
            title="Target Karir Software Engineer.pdf",
            file=SimpleUploadedFile("career.pdf", b"x"),
            is_embedded=True,
        )
        self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": ""}),
            content_type="application/json",
        )
        self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": "2", "option_id": 2}),
            content_type="application/json",
        )
        self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": "1", "option_id": 1}),
            content_type="application/json",
        )
        self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": "1", "option_id": 1}),
            content_type="application/json",
        )
        resp = self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": "4", "option_id": 4}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content.decode())
        self.assertEqual(body.get("planner_step"), "career")
        labels = [str(o.get("label")) for o in body.get("options", [])]
        self.assertIn("Software Engineer", labels)

    @patch("core.academic.profile_extractor.pdfplumber.open")
    @patch("core.academic.profile_extractor.get_vectorstore")
    def test_planner_flow_dynamic_question_for_campus_pdf_format_indonesia(self, vs_mock, pdf_open_mock):
        vs_mock.return_value.similarity_search.return_value = []
        pdf_open_mock.return_value = _FakePdfDoc(
            tables=[
                [["Hari", "Jam", "Ruang", "Kelas"], ["Senin", "08:00-09:40", "A1-201", "IF-A"]],
            ]
        )
        AcademicDocument.objects.create(
            user=self.user,
            title="Jadwal Perkuliahan Kampus A.pdf",
            file=SimpleUploadedFile("kampus-a.pdf", b"%PDF-1.4"),
            is_embedded=True,
        )

        self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": ""}),
            content_type="application/json",
        )
        self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": "1", "option_id": 1}),
            content_type="application/json",
        )
        self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": "1", "option_id": 1}),
            content_type="application/json",
        )
        self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": "1", "option_id": 1}),
            content_type="application/json",
        )
        resp = self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": "1", "option_id": 1}),
            content_type="application/json",
        )

        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content.decode())
        self.assertEqual(body.get("planner_step"), "preferences_time")
        self.assertIn("tabel jadwal", str(body.get("answer") or "").lower())
        fields = (body.get("profile_hints") or {}).get("detected_fields") or []
        self.assertIn("hari", fields)
        self.assertIn("jam", fields)

    @patch("core.academic.profile_extractor.pdfplumber.open")
    @patch("core.academic.profile_extractor.get_vectorstore")
    def test_planner_flow_dynamic_question_for_campus_pdf_format_english_headers(self, vs_mock, pdf_open_mock):
        vs_mock.return_value.similarity_search.return_value = []
        pdf_open_mock.return_value = _FakePdfDoc(
            tables=[
                [["Day", "Time", "Room", "Class"], ["Monday", "13:00-14:40", "B2-301", "SE-B"]],
            ]
        )
        AcademicDocument.objects.create(
            user=self.user,
            title="Campus B Schedule.pdf",
            file=SimpleUploadedFile("campus-b.pdf", b"%PDF-1.4"),
            is_embedded=True,
        )

        self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": ""}),
            content_type="application/json",
        )
        self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": "1", "option_id": 1}),
            content_type="application/json",
        )
        self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": "1", "option_id": 1}),
            content_type="application/json",
        )
        self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": "1", "option_id": 1}),
            content_type="application/json",
        )
        resp = self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": "1", "option_id": 1}),
            content_type="application/json",
        )

        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content.decode())
        self.assertEqual(body.get("planner_step"), "preferences_time")
        self.assertIn("tabel jadwal", str(body.get("answer") or "").lower())
        fields = (body.get("profile_hints") or {}).get("detected_fields") or []
        self.assertIn("hari", fields)
        self.assertIn("jam", fields)

    def test_planner_refreshes_hints_after_new_upload(self):
        self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": ""}),
            content_type="application/json",
        )
        # Belum ada dokumen, opsi 1 harus ditolak
        blocked = self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": "1", "option_id": 1}),
            content_type="application/json",
        )
        blocked_body = json.loads(blocked.content.decode())
        self.assertEqual(blocked_body.get("planner_step"), "data")

        AcademicDocument.objects.create(
            user=self.user,
            title="KRS Semester 5.pdf",
            file=SimpleUploadedFile("krs.pdf", b"x"),
            is_embedded=True,
        )
        # Request berikutnya harus membaca data terbaru dan meloloskan opsi 1.
        allowed = self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": "1", "option_id": 1}),
            content_type="application/json",
        )
        allowed_body = json.loads(allowed.content.decode())
        self.assertEqual(allowed_body.get("planner_step"), "profile_jurusan")

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

    def test_planner_history_created_on_start_auto(self):
        resp = self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": "", "session_id": 99999}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(PlannerHistory.objects.filter(user=self.user, event_type="start_auto").exists())

    def test_planner_history_created_on_option_select(self):
        self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": "", "session_id": 12345}),
            content_type="application/json",
        )
        self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": "2", "option_id": 2, "session_id": 12345}),
            content_type="application/json",
        )
        self.assertTrue(PlannerHistory.objects.filter(user=self.user, event_type="option_select").exists())

    def test_planner_history_created_on_generate_and_save(self):
        # Siapkan data agar bisa cepat ke iterate lalu save.
        AcademicDocument.objects.create(
            user=self.user,
            title="KRS Semester 5.pdf",
            file=SimpleUploadedFile("krs.pdf", b"x"),
            is_embedded=True,
        )
        session_id = 777
        self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": "", "session_id": session_id}),
            content_type="application/json",
        )
        # data -> jurusan -> semester -> goals -> pref_time -> pref_free_day -> pref_balance -> review
        for _ in range(7):
            self.client.post(
                "/api/chat/",
                data=json.dumps({"mode": "planner", "message": "1", "option_id": 1, "session_id": session_id}),
                content_type="application/json",
            )

        # review: pilih confirm agar masuk generate (event_type=generate)
        self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": "1", "option_id": 1, "session_id": session_id}),
            content_type="application/json",
        )

        # iterate: pilih save (event_type=save)
        self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": "4", "option_id": 4, "session_id": session_id}),
            content_type="application/json",
        )

        self.assertTrue(PlannerHistory.objects.filter(user=self.user, event_type="generate").exists())
        self.assertTrue(PlannerHistory.objects.filter(user=self.user, event_type="save").exists())

    def test_session_timeline_merges_chat_and_planner_sorted(self):
        chat_resp = self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "chat", "message": "halo", "session_id": 456}),
            content_type="application/json",
        )
        self.assertEqual(chat_resp.status_code, 200)
        self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": "", "session_id": 456}),
            content_type="application/json",
        )

        session_id = json.loads(chat_resp.content.decode()).get("session_id")
        res = self.client.get(f"/api/sessions/{session_id}/timeline/")
        self.assertEqual(res.status_code, 200)
        body = json.loads(res.content.decode())
        kinds = [x.get("kind") for x in body.get("timeline", [])]
        self.assertIn("chat_user", kinds)
        self.assertIn("chat_assistant", kinds)
        self.assertIn("planner_milestone", kinds)

    def test_session_timeline_access_control_other_user_forbidden(self):
        other = User.objects.create_user(username="other_planner", password="pass123")
        self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "planner", "message": "", "session_id": 654}),
            content_type="application/json",
        )
        # Ambil session milik user pertama
        session_id = PlannerHistory.objects.filter(user=self.user).first().session_id

        self.client.force_login(other)
        res = self.client.get(f"/api/sessions/{session_id}/timeline/")
        self.assertEqual(res.status_code, 404)

    def test_existing_session_detail_history_endpoint_backward_compatible(self):
        resp_chat = self.client.post(
            "/api/chat/",
            data=json.dumps({"mode": "chat", "message": "halo kompat", "session_id": 808}),
            content_type="application/json",
        )
        session_id = json.loads(resp_chat.content.decode()).get("session_id")
        self.assertTrue(ChatHistory.objects.filter(user=self.user, session_id=session_id).exists())
        history_res = self.client.get(f"/api/sessions/{session_id}/")
        self.assertEqual(history_res.status_code, 200)
        body = json.loads(history_res.content.decode())
        self.assertIn("history", body)
        self.assertTrue(isinstance(body.get("history"), list))

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
