from __future__ import annotations

from typing import Any, Dict, List, Tuple

DEFAULT_GRADE_SCALE: List[Tuple[str, int, int]] = [
    ("A", 80, 100),
    ("B", 70, 79),
    ("C", 56, 69),
    ("D", 45, 55),
    ("E", 0, 44),
]


def calculate_required_score(
    achieved_components: List[Dict[str, Any]],
    target_final_score: float,
    remaining_weight: float,
) -> Dict[str, Any]:
    achieved = 0.0
    for comp in achieved_components or []:
        try:
            score = float(comp.get("score", 0) or 0)
            weight = float(comp.get("weight", 0) or 0)
        except Exception:
            score = 0.0
            weight = 0.0
        achieved += score * (weight / 100.0)

    try:
        target = float(target_final_score)
    except Exception:
        target = 0.0

    try:
        remaining = float(remaining_weight)
    except Exception:
        remaining = 0.0

    needed = target - achieved
    if remaining <= 0:
        return {
            "required": None,
            "possible": False,
            "achieved_so_far": round(achieved, 2),
            "needed_points": round(needed, 2),
            "reason": "Tidak ada komponen tersisa",
        }

    required = needed / (remaining / 100.0)
    return {
        "required": round(required, 2),
        "possible": 0 <= required <= 100,
        "achieved_so_far": round(achieved, 2),
        "needed_points": round(needed, 2),
    }


def get_grade_letter(score: float, grade_scale: List[Tuple[str, int, int]] | None = None) -> str:
    scale = grade_scale or DEFAULT_GRADE_SCALE
    try:
        s = float(score)
    except Exception:
        return "E"

    for letter, low, high in scale:
        if low <= s <= high:
            return letter
    if s > 100:
        return scale[0][0]
    return scale[-1][0]


def analyze_transcript_risks(
    transcript_rows: List[Dict[str, Any]],
    target_score_for_b: float = 70,
) -> List[Dict[str, Any]]:
    risks: List[Dict[str, Any]] = []
    for row in transcript_rows or []:
        mk = str(row.get("mata_kuliah") or row.get("course") or "-")
        score_raw = row.get("nilai_angka")
        letter_raw = str(row.get("nilai_huruf") or "").strip().upper()

        score = None
        if score_raw is not None and str(score_raw).strip() != "":
            try:
                score = float(score_raw)
            except Exception:
                score = None

        letter = letter_raw or (get_grade_letter(score) if score is not None else "")

        at_risk = False
        if score is not None and score < 56:
            at_risk = True
        if letter in {"D", "E"}:
            at_risk = True

        if not at_risk:
            continue

        # Default skenario rescue sederhana: komponen baru 100% untuk perbaikan.
        calc = calculate_required_score(
            achieved_components=[{"name": "Nilai Saat Ini", "weight": 100, "score": float(score or 0)}],
            target_final_score=target_score_for_b,
            remaining_weight=100,
        )

        risks.append(
            {
                "mata_kuliah": mk,
                "nilai_huruf": letter or "-",
                "nilai_angka": score,
                "target": target_score_for_b,
                "required_for_b": calc.get("required"),
                "possible": bool(calc.get("possible")),
            }
        )

    return risks
