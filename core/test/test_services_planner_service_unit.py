from django.test import SimpleTestCase

from core.services.planner import service as planner_service


class PlannerServiceHelperUnitTests(SimpleTestCase):
    def test_extract_major_override_from_answer(self):
        self.assertEqual(
            planner_service._extract_major_override_from_answer("jurusan saya yang benar teknik informatika"),
            "Teknik Informatika",
        )
        self.assertEqual(
            planner_service._extract_major_override_from_answer("saya dari sistem informasi"),
            "Sistem Informasi",
        )
        self.assertEqual(planner_service._extract_major_override_from_answer("fokus saya ai"), "")

    def test_estimate_dynamic_total_clamped(self):
        self.assertEqual(
            planner_service._estimate_dynamic_total(docs_summary=[], relevance_score=0.9, depth=0),
            3,
        )
        self.assertEqual(
            planner_service._estimate_dynamic_total(docs_summary=[{}, {}, {}, {}, {}, {}], relevance_score=0.3, depth=0),
            4,
        )
        self.assertEqual(
            planner_service._estimate_dynamic_total(docs_summary=[], relevance_score=0.9, depth=4),
            4,
        )

    def test_build_step_path_label(self):
        self.assertEqual(planner_service._build_step_path_label({"title": "IPK Evaluasi"}, "abc"), "IPK Evaluasi")
        self.assertIn("Path:", planner_service._build_step_path_label({}, "jurusan teknik informatika"))
        self.assertEqual(planner_service._build_step_path_label({}, ""), "Path Analisis")

    def test_planner_path_summary(self):
        self.assertEqual(planner_service._planner_path_summary([]), "Belum ada jawaban.")
        out = planner_service._planner_path_summary(
            [
                {"step_key": "intent", "answer_value": "ipk"},
                {"step_key": "followup_1", "answer_value": "cumlaude"},
            ]
        )
        self.assertIn("intent: ipk", out)
        self.assertIn("followup_1: cumlaude", out)

    def test_assess_documents_relevance(self):
        out = planner_service.assess_documents_relevance(user=None, docs_summary=[{"title": "KHS semester 1.pdf"}])
        self.assertTrue(out["is_relevant"])
        self.assertGreaterEqual(out["relevance_score"], 0.55)
        out2 = planner_service.assess_documents_relevance(user=None, docs_summary=[{"title": "catatan belanja"}])
        self.assertIn("relevance_score", out2)

