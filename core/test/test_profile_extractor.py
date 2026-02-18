from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from core.academic.profile_extractor import extract_profile_hints
from core.models import AcademicDocument


class ProfileExtractorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="profile_u", password="pass123")

    @patch("core.academic.profile_extractor.get_vectorstore")
    def test_profile_extractor_detects_major_from_explicit_prodi(self, vs_mock):
        AcademicDocument.objects.create(
            user=self.user,
            title="Transkrip Teknik Informatika.pdf",
            file=SimpleUploadedFile("t.pdf", b"x"),
            is_embedded=True,
        )
        doc = MagicMock()
        doc.page_content = "Program Studi: Teknik Informatika"
        doc.metadata = {"source": "transkrip.pdf"}
        vs_mock.return_value.similarity_search.return_value = [doc]

        hints = extract_profile_hints(self.user)
        majors = hints.get("major_candidates", [])
        self.assertTrue(any(m.get("value") == "Teknik Informatika" for m in majors))
        self.assertIn(hints.get("confidence_summary"), {"medium", "high"})
        self.assertIn("question_candidates", hints)

    @patch("core.academic.profile_extractor.get_vectorstore")
    def test_profile_extractor_detects_career_from_keywords(self, vs_mock):
        AcademicDocument.objects.create(
            user=self.user,
            title="CV Karir.pdf",
            file=SimpleUploadedFile("cv.pdf", b"x"),
            is_embedded=True,
        )
        doc = MagicMock()
        doc.page_content = "Target karir: Software Engineer pada startup."
        doc.metadata = {"source": "cv.pdf"}
        vs_mock.return_value.similarity_search.return_value = [doc]

        hints = extract_profile_hints(self.user)
        careers = hints.get("career_candidates", [])
        self.assertTrue(any(c.get("value") == "Software Engineer" for c in careers))

    @patch("core.academic.profile_extractor.get_vectorstore")
    def test_profile_extractor_low_confidence_when_no_relevant_signal(self, vs_mock):
        AcademicDocument.objects.create(
            user=self.user,
            title="Catatan Umum.txt",
            file=SimpleUploadedFile("x.txt", b"x"),
            is_embedded=True,
        )
        doc = MagicMock()
        doc.page_content = "Ini dokumen umum tanpa informasi jurusan."
        doc.metadata = {"source": "catatan.txt"}
        vs_mock.return_value.similarity_search.return_value = [doc]

        hints = extract_profile_hints(self.user)
        self.assertEqual(hints.get("confidence_summary"), "low")
        self.assertIsNotNone(hints.get("warning"))

    @patch("core.academic.profile_extractor.get_vectorstore")
    def test_profile_extractor_conflict_candidates_sets_warning(self, vs_mock):
        AcademicDocument.objects.create(
            user=self.user,
            title="Dokumen Campuran.pdf",
            file=SimpleUploadedFile("mix.pdf", b"x"),
            is_embedded=True,
        )
        doc1 = MagicMock()
        doc1.page_content = "Program Studi: Teknik Informatika"
        doc1.metadata = {"source": "a.pdf"}
        doc2 = MagicMock()
        doc2.page_content = "Program Studi: Sistem Informasi"
        doc2.metadata = {"source": "b.pdf"}
        vs_mock.return_value.similarity_search.return_value = [doc1, doc2]

        hints = extract_profile_hints(self.user)
        majors = hints.get("major_candidates", [])
        self.assertGreaterEqual(len(majors), 2)
        self.assertIsNotNone(hints.get("warning"))

    @patch("core.academic.profile_extractor.get_vectorstore")
    def test_profile_extractor_detects_schedule_fields_from_tabular_text(self, vs_mock):
        AcademicDocument.objects.create(
            user=self.user,
            title="Jadwal KRS.pdf",
            file=SimpleUploadedFile("jadwal.pdf", b"x"),
            is_embedded=True,
        )
        doc = MagicMock()
        doc.page_content = "Hari\tJam\tRuang\tKelas\nSenin\t08:00-10:00\tLab 1\tA"
        doc.metadata = {"source": "jadwal.pdf"}
        vs_mock.return_value.similarity_search.return_value = [doc]

        hints = extract_profile_hints(self.user)
        fields = hints.get("detected_fields") or []
        self.assertIn("hari", fields)
        self.assertIn("jam", fields)
        self.assertTrue(any((q.get("step") == "preferences_time") for q in (hints.get("question_candidates") or [])))
