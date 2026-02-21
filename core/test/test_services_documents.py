from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from core.models import AcademicDocument
from core.services.documents import service as doc_service


class DocumentsServiceUnitTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="svc_doc_u", password="pass12345")

    def test_build_storage_payload_clamps_quota(self):
        out = doc_service.build_storage_payload(total_bytes=100, quota_bytes=0)
        self.assertEqual(out["quota_bytes"], 1)
        self.assertEqual(out["used_pct"], 100)

    @patch("core.services.documents.service.process_document", return_value=True)
    def test_upload_files_batch_success(self, _proc_mock):
        f = SimpleUploadedFile("a.pdf", b"abc")
        out = doc_service.upload_files_batch(user=self.user, files=[f], quota_bytes=1024 * 1024)
        self.assertEqual(out["status"], "success")
        self.assertEqual(AcademicDocument.objects.filter(user=self.user).count(), 1)

    @patch("core.services.documents.service.process_document", return_value=False)
    def test_upload_files_batch_parse_fail(self, _proc_mock):
        f = SimpleUploadedFile("a.pdf", b"abc")
        out = doc_service.upload_files_batch(user=self.user, files=[f], quota_bytes=1024 * 1024)
        self.assertEqual(out["status"], "error")
        self.assertEqual(AcademicDocument.objects.filter(user=self.user).count(), 0)

    @patch("core.services.documents.service.delete_vectors_for_doc_strict", return_value=(False, 1))
    def test_delete_document_for_user_strict_fail(self, _del_mock):
        doc = AcademicDocument.objects.create(user=self.user, file=SimpleUploadedFile("a.pdf", b"abc"), title="a.pdf")
        out = doc_service.delete_document_for_user(user=self.user, doc_id=doc.id)
        self.assertFalse(out)

