# core/tests.py
import json
import logging
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase

from .models import AcademicDocument, ChatHistory
from . import service


# =========================================================
# Logging Setup (rapi + tidak dobel handler)
# =========================================================
logger = logging.getLogger("TEST_LOGGER")
logger.setLevel(logging.INFO)
logger.propagate = False  # penting biar tidak dobel ke root logger

if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - [TEST] - %(message)s", datefmt="%H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def banner(title: str) -> None:
    logger.info("=" * 70)
    logger.info(title)
    logger.info("=" * 70)


class AcademicRAGSystemTests(TestCase):
    """
    FINAL TEST SUITE (post-refactor)

    Fokus:
    A) Unit test service.py (business logic) -> cepat & deterministik
    B) Smoke test endpoint -> memastikan wiring URL/views aman
    """

    def setUp(self):
        banner("SETUP: Create user + login client")
        self.client = Client()
        self.user = User.objects.create_user(
            username="mahasiswa_test",
            password="password123",
            email="mhs@test.com",
        )
        ok = self.client.login(username="mahasiswa_test", password="password123")
        self.assertTrue(ok, "Login gagal pada setUp() — cek kredensial test.")
        logger.info("✅ Logged in as mahasiswa_test")

    # =========================================================
    # SCENARIO 1: MODEL BASIC
    # =========================================================
    def test_models_create_and_str(self):
        banner("SCENARIO 1: Models - create + __str__")

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

        self.assertEqual(str(doc), "mahasiswa_test - KRS_Semester_5.pdf")
        self.assertIn("mahasiswa_test", str(chat))

        logger.info("✅ AcademicDocument __str__ OK")
        logger.info("✅ ChatHistory saved OK")

    # =========================================================
    # SCENARIO 2: SERVICE - Upload batch
    # =========================================================
    @patch("core.service.process_document")
    def test_service_upload_files_batch_success(self, mock_process_document):
        banner("SCENARIO 2: Service - upload_files_batch (success)")

        mock_process_document.return_value = True

        dummy_file = SimpleUploadedFile(
            "test_krs.pdf",
            b"Dummy PDF content for testing.",
            content_type="application/pdf",
        )

        logger.info("ACTION: service.upload_files_batch(user, [file])")
        payload = service.upload_files_batch(self.user, [dummy_file])

        logger.info(f"RESULT: {payload}")
        self.assertEqual(payload.get("status"), "success")

        # DB check
        self.assertTrue(
            AcademicDocument.objects.filter(user=self.user, title="test_krs.pdf").exists(),
            "AcademicDocument tidak tersimpan setelah upload_files_batch.",
        )
        doc = AcademicDocument.objects.get(user=self.user, title="test_krs.pdf")
        self.assertTrue(doc.is_embedded, "is_embedded harus True saat ingest sukses.")

        # ingest dipanggil 1x untuk 1 file
        self.assertEqual(mock_process_document.call_count, 1)

        logger.info("✅ Upload service sukses: doc saved, embedded=True, ingest called 1x")

    @patch("core.service.process_document")
    def test_service_upload_files_batch_fail_parsing(self, mock_process_document):
        banner("SCENARIO 3: Service - upload_files_batch (fail parsing => doc deleted)")

        mock_process_document.return_value = False

        dummy_file = SimpleUploadedFile(
            "fail.pdf",
            b"Dummy content",
            content_type="application/pdf",
        )

        payload = service.upload_files_batch(self.user, [dummy_file])
        logger.info(f"RESULT: {payload}")

        self.assertEqual(payload.get("status"), "error")
        self.assertFalse(
            AcademicDocument.objects.filter(user=self.user, title="fail.pdf").exists(),
            "Doc harusnya tidak ada (deleted) jika parsing gagal.",
        )
        self.assertEqual(mock_process_document.call_count, 1)

        logger.info("✅ Fail parsing: payload error + doc dibersihkan dari DB")

    # =========================================================
    # SCENARIO 4: SERVICE - Chat + save history
    # =========================================================
    @patch("core.service.ask_bot")
    def test_service_chat_and_save(self, mock_ask_bot):
        banner("SCENARIO 4: Service - chat_and_save (mock LLM + save history)")

        mock_ask_bot.return_value = "Jawaban mock AI"
        message = "Berapa IPK saya?"

        payload = service.chat_and_save(self.user, message, request_id="test-rid-123")
        logger.info(f"RESULT: {payload}")

        self.assertEqual(payload.get("answer"), "Jawaban mock AI")

        # history saved
        self.assertTrue(
            ChatHistory.objects.filter(user=self.user, question=message, answer="Jawaban mock AI").exists(),
            "ChatHistory tidak tersimpan oleh service.chat_and_save",
        )

        # ask_bot dipanggil dengan user.id + message
        args, kwargs = mock_ask_bot.call_args
        self.assertEqual(args[0], self.user.id)
        self.assertEqual(args[1], message)
        self.assertEqual(kwargs.get("request_id"), "test-rid-123")

        logger.info("✅ chat_and_save: answer OK, history saved, ask_bot called w/ request_id")

    # =========================================================
    # SCENARIO 5: ENDPOINT SECURITY (login required)
    # =========================================================
    def test_api_requires_login(self):
        banner("SCENARIO 5: Endpoint - login_required protection")

        self.client.logout()
        logger.info("ACTION: logout, then access API endpoints without auth")

        res_upload = self.client.post("/api/upload/")
        res_chat = self.client.post("/api/chat/", data={})
        res_docs = self.client.get("/api/documents/")

        self.assertIn(res_upload.status_code, (302, 403))
        self.assertIn(res_chat.status_code, (302, 403))
        self.assertIn(res_docs.status_code, (302, 403))

        logger.info("✅ Unauthorized blocked (302/403) for upload/chat/docs")

    # =========================================================
    # SCENARIO 6: ENDPOINT SMOKE (wiring)
    # =========================================================
@patch("core.service.get_documents_payload")
def test_documents_api_smoke(self, mock_get_docs):
    banner("SCENARIO 6: Endpoint - /api/documents/ smoke test (wiring)")

    mock_get_docs.return_value = {
        "documents": [],
        "storage": {
            "used_bytes": 0,
            "quota_bytes": 100 * 1024 * 1024,
            "used_pct": 0,
            "used_human": "0 B",
            "quota_human": "100.00 MB",
        },
    }

    logger.info("ACTION: GET /api/documents/ (mock service.get_documents_payload)")
    res = self.client.get("/api/documents/")

    logger.info(f"RESPONSE status={res.status_code} body={res.content[:200]!r}")
    self.assertEqual(res.status_code, 200)

    data = res.json()
    self.assertIn("documents", data)
    self.assertIn("storage", data)

    storage = data["storage"]
    for k in ("used_bytes", "quota_bytes", "used_pct", "used_human", "quota_human"):
        self.assertIn(k, storage, f"Key '{k}' harus ada di storage payload")

    logger.info("✅ documents_api OK: response shape valid (documents + storage lengkap)")
