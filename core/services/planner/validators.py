"""Planner validators."""

from __future__ import annotations

from typing import Any, Dict, List


def validate_run_state_for_next_step(*, run: Any, now_ts: Any) -> Dict[str, Any] | None:
    if not run:
        return {
            "status": "error",
            "error_code": "RUN_NOT_FOUND",
            "error": "planner_run_id tidak ditemukan.",
            "hint": "Mulai ulang planner dari onboarding.",
        }
    invalid_status = {"cancelled", "expired", "completed"}
    if str(getattr(run, "status", "")).lower() in invalid_status:
        return {
            "status": "error",
            "error_code": "RUN_INVALID_STATUS",
            "error": f"Planner run sudah {run.status}.",
            "hint": "Mulai run planner baru.",
        }
    expires_at = getattr(run, "expires_at", None)
    if expires_at and now_ts and now_ts > expires_at:
        return {
            "status": "error",
            "error_code": "RUN_EXPIRED",
            "error": "Planner run sudah kedaluwarsa.",
            "hint": "Mulai ulang planner agar state valid.",
        }
    return None


def validate_step_sequence(
    *,
    client_step_seq: int,
    next_seq: int,
    submitted_step: str,
    expected_step: str,
    answered_keys: List[str],
) -> Dict[str, Any]:
    if int(client_step_seq or 0) != int(next_seq or 1):
        return {
            "ok": False,
            "error": {
                "status": "error",
                "error": "Urutan langkah tidak valid (client_step_seq).",
                "error_code": "INVALID_STEP_SEQUENCE",
                "expected_step_key": expected_step,
                "expected_seq": next_seq,
            },
            "submitted_step": submitted_step,
        }
    normalized_submitted = str(submitted_step or "").strip()
    normalized_expected = str(expected_step or "").strip()
    if normalized_submitted and normalized_submitted != normalized_expected:
        if normalized_submitted in set(answered_keys or []):
            normalized_submitted = normalized_expected
        else:
            return {
                "ok": False,
                "error": {
                    "status": "error",
                    "error": "step_key tidak sesuai urutan planner.",
                    "error_code": "STEP_KEY_MISMATCH",
                    "expected_step_key": normalized_expected,
                    "expected_seq": next_seq,
                },
                "submitted_step": normalized_submitted,
            }
    return {"ok": True, "submitted_step": normalized_submitted or normalized_expected}


def validate_answer_payload(*, answer_value: str, answer_mode: str) -> Dict[str, Any] | None:
    normalized_mode = str(answer_mode or "").strip().lower()
    if normalized_mode not in {"option", "manual"}:
        return {"status": "error", "error_code": "INVALID_ANSWER_MODE", "error": "answer_mode tidak valid."}
    if not str(answer_value or "").strip():
        return {"status": "error", "error_code": "EMPTY_ANSWER", "error": "answer_value wajib diisi."}
    return None


def validate_execute_answers(blueprint: Dict[str, Any], answers: Dict[str, Any]) -> str:
    steps = blueprint.get("steps") if isinstance(blueprint, dict) else None
    if not isinstance(steps, list) or not steps:
        return "Blueprint planner tidak valid."

    valid_step_keys = []
    seen = set()
    required_keys = set()
    for s in steps:
        if not isinstance(s, dict):
            continue
        key = str(s.get("step_key") or "").strip()
        if not key:
            return "Blueprint planner tidak memiliki step_key valid."
        if key in seen:
            return f"Blueprint planner duplikat step_key: {key}"
        seen.add(key)
        valid_step_keys.append(key)
        if bool(s.get("required", True)):
            required_keys.add(key)
        allow_manual = bool(s.get("allow_manual", True))
        options = s.get("options") if isinstance(s.get("options"), list) else []
        if (not allow_manual) and len(options) < 2:
            return f"Blueprint step '{key}' tidak valid: options kurang dari 2."

    unknown_keys = [k for k in answers.keys() if k not in set(valid_step_keys)]
    if unknown_keys:
        return f"Jawaban memuat step tidak dikenal: {', '.join(sorted(unknown_keys))}"

    missing_required = [k for k in sorted(required_keys) if str(answers.get(k) or "").strip() == ""]
    if missing_required:
        return f"Jawaban required belum lengkap: {', '.join(missing_required)}"

    for k, v in answers.items():
        if not isinstance(v, (str, int, float, bool, dict, list)):
            return f"Tipe jawaban untuk step '{k}' tidak valid."

    meta = blueprint.get("meta") if isinstance(blueprint.get("meta"), dict) else {}
    if bool(meta.get("requires_major_confirmation")):
        major_keys = [k for k in valid_step_keys if ("jurusan" in k.lower()) or ("major" in k.lower())]
        if not major_keys:
            return ""
        has_major_answer = any(str(answers.get(k) or "").strip() for k in major_keys)
        if not has_major_answer:
            return "Konfirmasi jurusan wajib diisi karena confidence jurusan belum tinggi."
    return ""
