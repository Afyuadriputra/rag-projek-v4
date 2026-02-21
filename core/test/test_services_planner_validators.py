from datetime import timedelta
from types import SimpleNamespace

from django.test import SimpleTestCase
from django.utils import timezone

from core.services.planner import validators as vz


class PlannerValidatorsUnitTests(SimpleTestCase):
    def test_validate_run_state_not_found(self):
        out = vz.validate_run_state_for_next_step(run=None, now_ts=timezone.now())
        self.assertEqual(out["error_code"], "RUN_NOT_FOUND")

    def test_validate_run_state_invalid_status(self):
        run = SimpleNamespace(status="completed", expires_at=timezone.now() + timedelta(hours=1))
        out = vz.validate_run_state_for_next_step(run=run, now_ts=timezone.now())
        self.assertEqual(out["error_code"], "RUN_INVALID_STATUS")

    def test_validate_run_state_expired(self):
        run = SimpleNamespace(status="collecting", expires_at=timezone.now() - timedelta(seconds=1))
        out = vz.validate_run_state_for_next_step(run=run, now_ts=timezone.now())
        self.assertEqual(out["error_code"], "RUN_EXPIRED")

    def test_validate_step_sequence_invalid_seq(self):
        out = vz.validate_step_sequence(
            client_step_seq=2,
            next_seq=1,
            submitted_step="intent",
            expected_step="intent",
            answered_keys=[],
        )
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"]["error_code"], "INVALID_STEP_SEQUENCE")

    def test_validate_step_sequence_mismatch_recover(self):
        out = vz.validate_step_sequence(
            client_step_seq=1,
            next_seq=1,
            submitted_step="old_step",
            expected_step="intent",
            answered_keys=["old_step"],
        )
        self.assertTrue(out["ok"])
        self.assertEqual(out["submitted_step"], "intent")

    def test_validate_step_sequence_mismatch_reject(self):
        out = vz.validate_step_sequence(
            client_step_seq=1,
            next_seq=1,
            submitted_step="x",
            expected_step="intent",
            answered_keys=[],
        )
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"]["error_code"], "STEP_KEY_MISMATCH")

    def test_validate_answer_payload(self):
        self.assertEqual(vz.validate_answer_payload(answer_value="", answer_mode="manual")["error_code"], "EMPTY_ANSWER")
        self.assertEqual(vz.validate_answer_payload(answer_value="x", answer_mode="bad")["error_code"], "INVALID_ANSWER_MODE")
        self.assertIsNone(vz.validate_answer_payload(answer_value="ok", answer_mode="option"))

    def test_validate_execute_answers_unknown_and_required(self):
        blueprint = {
            "steps": [
                {"step_key": "intent", "required": True, "allow_manual": True, "options": []},
                {"step_key": "major", "required": False, "allow_manual": True, "options": []},
            ],
            "meta": {},
        }
        err = vz.validate_execute_answers(blueprint, {"other": "x"})
        self.assertIn("tidak dikenal", err)
        err = vz.validate_execute_answers(blueprint, {"intent": ""})
        self.assertIn("belum lengkap", err)

    def test_validate_execute_answers_major_confirmation(self):
        blueprint = {
            "steps": [
                {"step_key": "intent", "required": True, "allow_manual": True, "options": []},
                {"step_key": "major_confirm", "required": False, "allow_manual": True, "options": []},
            ],
            "meta": {"requires_major_confirmation": True},
        }
        err = vz.validate_execute_answers(blueprint, {"intent": "ipk"})
        self.assertIn("Konfirmasi jurusan wajib", err)

