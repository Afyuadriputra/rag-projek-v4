"""Planner state-machine primitives."""

from __future__ import annotations

from typing import Any, Dict


def get_expected_step(tree: Dict[str, Any], default: str = "intent") -> str:
    return str((tree or {}).get("expected_step_key") or default)


def get_next_seq(tree: Dict[str, Any]) -> int:
    return int((tree or {}).get("next_seq") or 1)


def can_generate_now(ready_to_generate: bool, reached_max: bool) -> bool:
    return bool(ready_to_generate or reached_max)


def compute_ui_hints(depth: int) -> Dict[str, bool]:
    d = int(depth or 0)
    return {"show_major_header": d <= 1, "show_path_header": d > 1}


def build_progress(depth: int, estimated_total: int, max_depth: int) -> Dict[str, int]:
    return {
        "current": int(depth or 0),
        "estimated_total": int(estimated_total or 0),
        "max_depth": int(max_depth or 0),
    }


def advance_tree_for_next_step(
    tree: Dict[str, Any],
    *,
    next_seq: int,
    can_generate: bool,
    path_label: str,
    next_step_key: str,
    next_question: str,
) -> Dict[str, Any]:
    out = dict(tree or {})
    out["next_seq"] = int(next_seq)
    out["can_generate_now"] = bool(can_generate)
    out["current_path_label"] = str(path_label or "")
    out["expected_step_key"] = str(next_step_key or "")
    out["current_step_question"] = str(next_question or "")
    return out
