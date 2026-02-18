from django.test import SimpleTestCase

from core.academic.grade_calculator import (
    calculate_required_score,
    get_grade_letter,
    analyze_transcript_risks,
)


class GradeCalculatorTests(SimpleTestCase):
    def test_calculate_required_score_basic(self):
        res = calculate_required_score(
            achieved_components=[{"name": "UTS", "weight": 40, "score": 60}],
            target_final_score=70,
            remaining_weight=60,
        )
        self.assertAlmostEqual(res["required"], 76.67, places=2)
        self.assertTrue(res["possible"])

    def test_calculate_required_score_no_remaining(self):
        res = calculate_required_score(
            achieved_components=[{"name": "UTS", "weight": 100, "score": 50}],
            target_final_score=70,
            remaining_weight=0,
        )
        self.assertIsNone(res["required"])
        self.assertFalse(res["possible"])

    def test_calculate_required_score_target_a(self):
        res = calculate_required_score(
            achieved_components=[{"name": "UTS", "weight": 40, "score": 75}],
            target_final_score=80,
            remaining_weight=60,
        )
        self.assertAlmostEqual(res["required"], 83.33, places=2)
        self.assertTrue(res["possible"])

    def test_get_grade_letter_default_scale(self):
        self.assertEqual(get_grade_letter(85), "A")
        self.assertEqual(get_grade_letter(74), "B")
        self.assertEqual(get_grade_letter(60), "C")
        self.assertEqual(get_grade_letter(50), "D")
        self.assertEqual(get_grade_letter(20), "E")

    def test_analyze_transcript_risks(self):
        rows = [
            {"mata_kuliah": "Kalkulus", "nilai_huruf": "D", "nilai_angka": 52},
            {"mata_kuliah": "Basis Data", "nilai_huruf": "B", "nilai_angka": 75},
        ]
        out = analyze_transcript_risks(rows)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["mata_kuliah"], "Kalkulus")
        self.assertIn("required_for_b", out[0])
