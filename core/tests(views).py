import json
import logging
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase

from .models import AcademicDocument, ChatHistory


# =========================================================
# Logging Setup (rapi + tidak dobel handler)
# =========================================================
logger = logging.getLogger("TEST_LOGGER")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - [TEST] - %(message)s", datefmt="%H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def _banner(title: str) -> None:
    logger.info("-" * 62)
    logger.info(title)
    logger.info("-" * 62)


class AcademicRAGSystemTest(TestCase):
    """
    Test suite ringkas untuk memastikan:
    1) Model DB berjalan benar
    2) Upload API memproses file dan memanggil AI ingest (mock)
    3) Chat API menyimpan history dan mengembalikan jawaban (mock)
    4) Endpoint API dilindungi @login_required
    """

    def setUp(self):
        _banner("SETUP: Membuat User Dummy + Login Client")
        self.client = Client()
        self.user = User.objects.create_user(
            username="mahasiswa_test",
            password="password123",
            email="mhs@test.com",
        )
        ok = self.client.login(username="mahasiswa_test", password="password123")
        self.assertTrue(ok, "Login gagal pada setUp() — cek kredensial test")
        logger.info("✅ Login berhasil sebagai 'mahasiswa_test'")

    # =========================================================
    # TEST 1: DATABASE MODELS
    # =========================================================
    def test_model_creation(self):
        _banner("SCENARIO 1: Database Models")

        # Arrange & Act
        doc = AcademicDocument.objects.create(
            user=self.user,
            title="KRS_Semester_5.pdf",
            file="documents/dummy.pdf",
        )
        chat = ChatHistory.objects.create(
            user=self.user,
            question="Apa mata kuliah saya?",
            answer="Anda mengambil Algoritma.",
        )

        # Assert
        self.assertEqual(str(doc), "mahasiswa_test - KRS_Semester_5.pdf")
        self.assertEqual(chat.user.username, "mahasiswa_test")

        logger.info("✅ AcademicDocument tersimpan dan __str__ sesuai.")
        logger.info("✅ ChatHistory tersimpan dengan user yang benar.")

    # =========================================================
    # TEST 2: UPLOAD API (INGESTION)
    # =========================================================
    @patch("core.views.process_document")
    def test_upload_api_flow(self, mock_process_document):
        _banner("SCENARIO 2: Upload API (Batch Ingestion)")

        # Arrange: mock ingest sukses
        mock_process_document.return_value = True

        dummy_file = SimpleUploadedFile(
            "test_krs.pdf",
            b"Dummy PDF content for testing.",
            content_type="application/pdf",
        )

        logger.info("ACTION: POST /api/upload/ (1 file)")

        # Act (PENTING: key harus 'files', bukan 'file')
        response = self.client.post("/api/upload/", data={"files": dummy_file})

        # Assert response
        self.assertEqual(
            response.status_code, 200, f"Upload harusnya 200, tapi dapat {response.status_code}. Body={response.content!r}"
        )
        payload = response.json()
        self.assertEqual(payload.get("status"), "success")
        logger.info(f"RESPONSE: {payload}")

        # Assert DB: dokumen tersimpan dan embedded True
        self.assertTrue(
            AcademicDocument.objects.filter(user=self.user, title="test_krs.pdf").exists(),
            "AcademicDocument tidak ditemukan di DB setelah upload.",
        )
        doc = AcademicDocument.objects.get(user=self.user, title="test_krs.pdf")
        self.assertTrue(doc.is_embedded, "Dokumen harusnya is_embedded=True saat ingest sukses.")

        # Assert AI ingest dipanggil tepat 1x
        # (di backend kamu, 1 file => process_document 1x)
        self.assertEqual(
            mock_process_document.call_count, 1,
            f"process_document harus dipanggil 1x, tapi dipanggil {mock_process_document.call_count}x"
        )

        logger.info("✅ Upload sukses: dokumen tersimpan, embedded=True, ingest dipanggil 1x.")

    # =========================================================
    # TEST 3: CHAT API (RETRIEVAL)
    # =========================================================
    @patch("core.views.ask_bot")
    def test_chat_api_flow(self, mock_ask_bot):
        _banner("SCENARIO 3: Chat API (Retrieval Flow)")

        # Arrange
        mock_response_text = "Berdasarkan dokumen, IPK Anda adalah 3.90"
        mock_ask_bot.return_value = mock_response_text

        payload = {"message": "Berapa IPK saya?"}
        logger.info(f"ACTION: POST /api/chat/ message='{payload['message']}'")

        # Act
        response = self.client.post(
            "/api/chat/",
            data=json.dumps(payload),
            content_type="application/json",
        )

        # Assert response
        self.assertEqual(response.status_code, 200)
        response_data = response.json()

        self.assertEqual(response_data.get("answer"), mock_response_text)
        logger.info(f"AI ANSWER: {response_data['answer']}")

        # Assert history saved
        self.assertTrue(
            ChatHistory.objects.filter(
                user=self.user,
                question="Berapa IPK saya?",
                answer=mock_response_text,
            ).exists(),
            "ChatHistory tidak tersimpan di DB.",
        )

        # Assert ask_bot dipanggil dengan user.id
        args, _kwargs = mock_ask_bot.call_args
        self.assertEqual(args[0], self.user.id)

        logger.info("✅ Chat sukses: response benar, history tersimpan, ask_bot terpanggil.")

    # =========================================================
    # TEST 4: SECURITY CHECK (LOGIN REQUIRED)
    # =========================================================
    def test_unauthorized_access(self):
        _banner("SCENARIO 4: Security (Unauthorized Access)")

        self.client.logout()
        logger.info("ACTION: Logout lalu akses endpoint API")

        res_upload = self.client.post("/api/upload/")
        res_chat = self.client.post("/api/chat/", data={})
        res_docs = self.client.get("/api/documents/")

        # Default @login_required biasanya redirect 302 ke /login/
        self.assertIn(res_upload.status_code, (302, 403))
        self.assertIn(res_chat.status_code, (302, 403))
        self.assertIn(res_docs.status_code, (302, 403))

        logger.info("✅ Unauthorized access ditolak (302/403). Security OK.")
