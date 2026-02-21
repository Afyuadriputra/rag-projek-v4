from django.test import SimpleTestCase

from core.services.planner import state_machine as sm


class PlannerStateMachineUnitTests(SimpleTestCase):
    def test_get_expected_step_default(self):
        self.assertEqual(sm.get_expected_step({}), "intent")

    def test_get_expected_step_from_tree(self):
        self.assertEqual(sm.get_expected_step({"expected_step_key": "focus"}), "focus")

    def test_get_next_seq_default(self):
        self.assertEqual(sm.get_next_seq({}), 1)

    def test_get_next_seq_from_tree(self):
        self.assertEqual(sm.get_next_seq({"next_seq": 3}), 3)

    def test_can_generate_now(self):
        self.assertTrue(sm.can_generate_now(True, False))
        self.assertTrue(sm.can_generate_now(False, True))
        self.assertFalse(sm.can_generate_now(False, False))

    def test_compute_ui_hints(self):
        self.assertEqual(sm.compute_ui_hints(1), {"show_major_header": True, "show_path_header": False})
        self.assertEqual(sm.compute_ui_hints(2), {"show_major_header": False, "show_path_header": True})

    def test_build_progress(self):
        out = sm.build_progress(depth=2, estimated_total=4, max_depth=4)
        self.assertEqual(out, {"current": 2, "estimated_total": 4, "max_depth": 4})

    def test_advance_tree_for_next_step(self):
        out = sm.advance_tree_for_next_step(
            {"expected_step_key": "intent", "next_seq": 1},
            next_seq=2,
            can_generate=True,
            path_label="IPK",
            next_step_key="followup_1",
            next_question="Lanjut?",
        )
        self.assertEqual(out["next_seq"], 2)
        self.assertTrue(out["can_generate_now"])
        self.assertEqual(out["current_path_label"], "IPK")
        self.assertEqual(out["expected_step_key"], "followup_1")
        self.assertEqual(out["current_step_question"], "Lanjut?")

