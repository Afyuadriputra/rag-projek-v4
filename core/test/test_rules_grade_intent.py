from django.test import SimpleTestCase

from core.ai_engine.retrieval.rules import extract_grade_calc_input, is_grade_rescue_query


class GradeIntentRuleTests(SimpleTestCase):
    def test_is_grade_rescue_query_true(self):
        self.assertTrue(is_grade_rescue_query("tolong hitung nilai uas saya"))
        self.assertTrue(is_grade_rescue_query("target nilai akhir B gimana?"))
        self.assertTrue(is_grade_rescue_query("UTS 60 bobot 40 target B"))

    def test_is_grade_rescue_query_false(self):
        self.assertFalse(is_grade_rescue_query("tolong buat jadwal kuliah"))

    def test_extract_grade_calc_input_with_letter_target(self):
        parsed = extract_grade_calc_input("UTS 55 bobot 40 target B")
        self.assertIsNotNone(parsed)
        self.assertAlmostEqual(parsed["current_score"], 55.0, places=2)
        self.assertAlmostEqual(parsed["current_weight"], 40.0, places=2)
        self.assertAlmostEqual(parsed["target_score"], 70.0, places=2)
        self.assertAlmostEqual(parsed["remaining_weight"], 60.0, places=2)

    def test_extract_grade_calc_input_with_numeric_target(self):
        parsed = extract_grade_calc_input("nilai sekarang 62 bobot 30 target 78")
        self.assertIsNotNone(parsed)
        self.assertAlmostEqual(parsed["target_score"], 78.0, places=2)

    def test_extract_grade_calc_input_target_a(self):
        parsed = extract_grade_calc_input("UTS 70 bobot 50 target A")
        self.assertIsNotNone(parsed)
        self.assertAlmostEqual(parsed["target_score"], 80.0, places=2)

    def test_extract_grade_calc_input_weight_over_100_is_clamped(self):
        parsed = extract_grade_calc_input("UTS 70 bobot 140 target B")
        self.assertIsNotNone(parsed)
        self.assertAlmostEqual(parsed["current_weight"], 100.0, places=2)
        self.assertAlmostEqual(parsed["remaining_weight"], 0.0, places=2)

    def test_extract_grade_calc_input_ambiguous_returns_none(self):
        parsed = extract_grade_calc_input("tolong bantu saya")
        self.assertIsNone(parsed)
