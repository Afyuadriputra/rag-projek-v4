import json
from unittest.mock import patch

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import AcademicDocument, ChatHistory


class AcademicRAGSystemTests(TestCase):
    """
    Test suite end-to-end untuk:
    - Auth (login required)
    - Inertia dashboard (/)
    - API Chat (/api/chat/)
    - API Upload batch (/api/upload/)
    - API Documents refresh (/api/documents/)
    """

    def setUp(self):
        # Client + user dummy
        self.client = Client()
        self.user = User.objects.create_user(
            username="mahasiswa_test",
            email="mhs@test.com",
            password="password123",
        )
        self.client.login(username="mahasiswa_test", password="password123")

    # =========================================================
    # 1) MODEL TESTS
    # =========================================================
    def test_models_create_and_str(self):
        doc = AcademicDocument.objects.create(
            user=self.user,
            title="KRS_Semester_5.pdf",
            file="documents/dummy.pdf"
        )
        self.assertEqual(str(doc), "mahasiswa_test - KRS_Semester_5.pdf")

        chat = ChatHistory.objects.create(
            user=self.user,
            question="Apa mata kuliah saya?",
            answer="Anda mengambil Algoritma."
        )
        self.assertTrue("mahasiswa_test" in str(chat))
        self.assertEqual(chat.user.username, "mahasiswa_test")

    # =========================================================
    # 2) SECURITY: LOGIN REQUIRED
    # =========================================================
    def test_api_requires_login(self):
        self.client.logout()

        # Chat API
        res_chat = self.client.post(
            "/api/chat/",
            data=json.dumps({"message": "halo"}),
            content_type="application/json",
        )
        # Default @login_required -> redirect 302 ke login
        self.assertIn(res_chat.status_code, (302, 403))

        # Upload API
        res_upload = self.client.post("/api/upload/")
        self.assertIn(res_upload.status_code, (302, 403))

        # Documents API
        res_docs = self.client.get("/api/documents/")
        self.assertIn(res_docs.status_code, (302, 403))

    # =========================================================
    # 3) INERTIA DASHBOARD (/)
    # =========================================================
    def test_dashboard_home_ok(self):
        """
        Cek endpoint "/" tidak error dan mengembalikan response OK.
        (Kita tidak membedah HTML Inertia di sini, cukup pastikan view jalan.)
        """
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)

    # =========================================================
    # 4) CHAT API
    # =========================================================
    @patch("core.views.ask_bot")
    def test_chat_api_success_saves_history(self, mock_ask_bot):
        mock_ask_bot.return_value = "Jawaban AI dummy"

        payload = {"message": "Berapa IPK saya?"}
        res = self.client.post(
            "/api/chat/",
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["answer"], "Jawaban AI dummy")

        # history tersimpan
        self.assertTrue(ChatHistory.objects.filter(
            user=self.user,
            question="Berapa IPK saya?",
            answer="Jawaban AI dummy"
        ).exists())

        # pastikan ask_bot dipanggil dengan user.id
        mock_ask_bot.assert_called_once()
        called_args = mock_ask_bot.call_args[0]
        self.assertEqual(called_args[0], self.user.id)

    def test_chat_api_invalid_json(self):
        res = self.client.post(
            "/api/chat/",
            data="{invalid_json}",
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"], "Invalid JSON")

    def test_chat_api_empty_message(self):
        res = self.client.post(
            "/api/chat/",
            data=json.dumps({"message": ""}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"], "Pesan kosong")

    def test_chat_api_method_not_allowed(self):
        res = self.client.get("/api/chat/")
        self.assertEqual(res.status_code, 405)

    # =========================================================
    # 5) UPLOAD API (BATCH)
    # =========================================================
    @patch("core.views.process_document")
    def test_upload_api_success_single_file(self, mock_process_document):
        """
        Penting: backend kamu membaca request.FILES.getlist("files")
        Jadi key-nya HARUS 'files', bukan 'file'.
        """
        mock_process_document.return_value = True

        f1 = SimpleUploadedFile(
            "test_krs.pdf",
            b"dummy pdf content",
            content_type="application/pdf"
        )

        res = self.client.post("/api/upload/", data={"files": [f1]})
        self.assertEqual(res.status_code, 200)

        data = res.json()
        self.assertEqual(data["status"], "success")

        # Dokumen tersimpan + embedded True
        doc = AcademicDocument.objects.get(user=self.user, title="test_krs.pdf")
        self.assertTrue(doc.is_embedded)

        mock_process_document.assert_called_once()

    @patch("core.views.process_document")
    def test_upload_api_batch_mixed_success_and_fail(self, mock_process_document):
        """
        Test batch upload 2 file:
        - file1 sukses embed
        - file2 gagal parsing -> record dihapus
        """
        # Return success untuk file pertama, fail untuk kedua
        mock_process_document.side_effect = [True, False]

        f1 = SimpleUploadedFile("ok.pdf", b"content", content_type="application/pdf")
        f2 = SimpleUploadedFile("fail.pdf", b"content", content_type="application/pdf")

        res = self.client.post("/api/upload/", data={"files": [f1, f2]})
        self.assertEqual(res.status_code, 200)

        # ok.pdf harus ada & embedded
        self.assertTrue(AcademicDocument.objects.filter(user=self.user, title="ok.pdf", is_embedded=True).exists())

        # fail.pdf harus TIDAK ada karena doc.delete() saat ingest fail
        self.assertFalse(AcademicDocument.objects.filter(user=self.user, title="fail.pdf").exists())

    def test_upload_api_no_files(self):
        res = self.client.post("/api/upload/", data={})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["status"], "error")

    def test_upload_api_method_not_allowed(self):
        res = self.client.get("/api/upload/")
        self.assertEqual(res.status_code, 405)

    # =========================================================
    # 6) DOCUMENTS API
    # =========================================================
    def test_documents_api_ok_shape(self):
        """
        Pastikan response punya keys:
        - documents (list)
        - storage (object)
        """
        # Buat dummy dokumen supaya list tidak kosong
        AcademicDocument.objects.create(
            user=self.user,
            title="KHS_1.pdf",
            file="documents/dummy.pdf",
            is_embedded=True
        )

        res = self.client.get("/api/documents/")
        self.assertEqual(res.status_code, 200)

        data = res.json()
        self.assertIn("documents", data)
        self.assertIn("storage", data)

        self.assertIsInstance(data["documents"], list)
        self.assertIsInstance(data["storage"], dict)

        # storage fields minimal yang kamu pakai di frontend
        storage = data["storage"]
        for key in ["used_bytes", "quota_bytes", "used_pct", "used_human", "quota_human"]:
            self.assertIn(key, storage)

    def test_documents_api_method_not_allowed(self):
        res = self.client.post("/api/documents/")
        self.assertEqual(res.status_code, 405)
