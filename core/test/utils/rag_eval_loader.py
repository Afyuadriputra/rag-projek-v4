from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import yaml


_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


class RagEvalAssertionError(AssertionError):
    pass


def _load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise RagEvalAssertionError(f"Invalid YAML root object at {path}")
    return data


def load_query_source_mapping() -> Dict[str, Any]:
    return _load_yaml(_DATA_DIR / "rag_query_source_mapping.yaml")


def load_accuracy_prompts() -> Dict[str, Any]:
    return _load_yaml(_DATA_DIR / "rag_accuracy_prompts_50.yaml")


def load_uploaded_docs_mapping() -> Dict[str, Any]:
    return _load_yaml(_DATA_DIR / "rag_uploaded_docs_mapping.yaml")


def load_uploaded_docs_prompts() -> Dict[str, Any]:
    return _load_yaml(_DATA_DIR / "rag_uploaded_docs_prompts_50.yaml")


def load_uploaded_docs_ground_truth() -> Dict[str, Any]:
    return _load_yaml(_DATA_DIR / "rag_uploaded_docs_ground_truth.yaml")


def load_uploaded_docs_complex_mapping() -> Dict[str, Any]:
    return _load_yaml(_DATA_DIR / "rag_uploaded_docs_complex_mapping.yaml")


def load_uploaded_docs_complex_prompts() -> Dict[str, Any]:
    return _load_yaml(_DATA_DIR / "rag_uploaded_docs_complex_prompts_80.yaml")


def load_uploaded_docs_complex_ground_truth() -> Dict[str, Any]:
    return _load_yaml(_DATA_DIR / "rag_uploaded_docs_complex_ground_truth.yaml")


def resolve_sources_from_group(source_groups: Dict[str, Sequence[str]], group_name: str) -> List[str]:
    vals = list(source_groups.get(group_name) or [])
    if not vals:
        raise RagEvalAssertionError(f"Unknown or empty allowed_sources_group: {group_name}")
    return vals


def _norm_text(text: Any) -> str:
    return str(text or "").strip().lower()


def _norm_source_name(source: Any) -> str:
    raw = str(source or "").strip()
    if not raw:
        return ""
    return Path(raw).name.strip().lower()


def _extract_sources(out_sources: Iterable[Any]) -> List[str]:
    names: List[str] = []
    for item in list(out_sources or []):
        if isinstance(item, dict):
            name = _norm_source_name(item.get("source") or item.get("title") or item.get("doc_title"))
        else:
            name = _norm_source_name(item)
        if name:
            names.append(name)
    return names


def assert_pipeline(out: Dict[str, Any], expected: Dict[str, Any]) -> None:
    meta = dict(out.get("meta") or {})
    got = _norm_text(meta.get("pipeline"))
    allowed = [_norm_text(x) for x in list(expected.get("pipeline_in") or []) if _norm_text(x)]
    exact = _norm_text(expected.get("expected_pipeline"))
    if allowed:
        if got not in allowed:
            raise RagEvalAssertionError(f"pipeline mismatch: got={got}, expected_in={allowed}")
    elif exact and got != exact:
        raise RagEvalAssertionError(f"pipeline mismatch: got={got}, expected={exact}")


def assert_intent_route(out: Dict[str, Any], expected: Dict[str, Any]) -> None:
    meta = dict(out.get("meta") or {})
    got = _norm_text(meta.get("intent_route"))
    allowed = [_norm_text(x) for x in list(expected.get("intent_route_in") or []) if _norm_text(x)]
    exact = _norm_text(expected.get("expected_intent_route"))
    if allowed:
        if got not in allowed:
            raise RagEvalAssertionError(f"intent_route mismatch: got={got}, expected_in={allowed}")
    elif exact and got != exact:
        raise RagEvalAssertionError(f"intent_route mismatch: got={got}, expected={exact}")


def assert_validation(out: Dict[str, Any], expected: Dict[str, Any]) -> None:
    meta = dict(out.get("meta") or {})
    got = _norm_text(meta.get("validation") or "not_applicable")
    allowed = [_norm_text(x) for x in list(expected.get("validation_in") or expected.get("expected_validation_in") or []) if _norm_text(x)]
    if allowed and got not in allowed:
        raise RagEvalAssertionError(f"validation mismatch: got={got}, expected_in={allowed}")


def assert_source_match(
    out_sources: Iterable[Any],
    allowed_sources: Sequence[str],
    mode: str = "any_of",
    required: bool = True,
) -> None:
    if not required:
        return

    normalized_allowed = [_norm_source_name(x) for x in list(allowed_sources or []) if _norm_source_name(x)]
    if not normalized_allowed:
        return

    got = _extract_sources(out_sources)
    if not got:
        raise RagEvalAssertionError("missing_source_evidence")

    if str(mode or "any_of").strip().lower() != "any_of":
        raise RagEvalAssertionError(f"unsupported source_match_mode: {mode}")

    if not any(g in set(normalized_allowed) for g in got):
        raise RagEvalAssertionError(
            f"source mismatch: got={sorted(set(got))}, allowed_any_of={sorted(set(normalized_allowed))}"
        )


def assert_text_constraints(answer: str, must_contain_any: Sequence[str], must_not_contain: Sequence[str]) -> None:
    low = _norm_text(answer)

    positive = [str(x).strip().lower() for x in list(must_contain_any or []) if str(x).strip()]
    if positive and not any(x in low for x in positive):
        raise RagEvalAssertionError(f"answer missing required phrase(s): any_of={positive}")

    negative = [str(x).strip().lower() for x in list(must_not_contain or []) if str(x).strip()]
    found = [x for x in negative if x in low]
    if found:
        raise RagEvalAssertionError(f"answer contains forbidden phrase(s): {found}")


_NUM_PATTERN = re.compile(r"\d+(?:[.,]\d+)?")


def _to_float(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value or "").strip().replace(",", ".")
    return float(raw)


def _extract_numbers_from_text(text: str) -> List[float]:
    vals: List[float] = []
    for tok in _NUM_PATTERN.findall(str(text or "")):
        try:
            vals.append(_to_float(tok))
        except Exception:
            continue
    return vals


def _resolve_expected_number(ref: Any, ground_truth: Dict[str, Any]) -> float:
    if isinstance(ref, (int, float)):
        return float(ref)

    raw = str(ref or "").strip()
    if not raw:
        raise RagEvalAssertionError("expected_numbers contains empty ref")

    if "." not in raw:
        return _to_float(raw)

    group, key = raw.split(".", 1)
    facts = dict(ground_truth.get("facts") or {})
    if group not in facts:
        raise RagEvalAssertionError(f"unknown ground truth group: {group}")

    item: Any = facts[group]
    for part in key.split("."):
        if not isinstance(item, dict) or part not in item:
            raise RagEvalAssertionError(f"unknown ground truth key: {raw}")
        item = item[part]

    return _to_float(item)


def assert_numeric_consistency(answer: str, expected_numbers: Sequence[Any], ground_truth: Dict[str, Any]) -> None:
    refs = list(expected_numbers or [])
    if not refs:
        return

    got = _extract_numbers_from_text(answer)
    if not got:
        raise RagEvalAssertionError("answer missing numeric evidence")

    missing: List[str] = []
    for ref in refs:
        want = _resolve_expected_number(ref, ground_truth)
        has_match = any(
            math.isclose(v, want, rel_tol=0.02, abs_tol=0.05)
            for v in got
        )
        if not has_match:
            missing.append(str(ref))

    if missing:
        raise RagEvalAssertionError(f"numeric mismatch: missing={missing}, got_numbers={got}")


def assert_semester_coverage(answer: str, expected_semesters: Sequence[Any]) -> None:
    sems = []
    for x in list(expected_semesters or []):
        try:
            sems.append(int(str(x)))
        except Exception:
            continue
    if not sems:
        return

    low = _norm_text(answer)
    missing = [s for s in sems if f"semester {s}" not in low]
    if missing:
        raise RagEvalAssertionError(f"semester coverage mismatch: missing={missing}")


def assert_tabular_consistency(
    answer: str,
    expected_numbers: Sequence[Any],
    ground_truth: Dict[str, Any],
    tolerance_policy: Dict[str, float] | None = None,
) -> None:
    policy = dict(tolerance_policy or {})
    rel_tol = float(policy.get("rel_tol", 0.02))
    abs_tol = float(policy.get("abs_tol", 0.05))

    refs = list(expected_numbers or [])
    if not refs:
        return

    got = _extract_numbers_from_text(answer)
    if not got:
        raise RagEvalAssertionError("answer missing numeric evidence")

    missing: List[str] = []
    for ref in refs:
        want = _resolve_expected_number(ref, ground_truth)
        raw_ref = str(ref or "")
        integer_like_ref = any(k in raw_ref.lower() for k in ["count", "total_sks", ".sks", "semester_", ".matkul"])
        if integer_like_ref:
            has_match = any(int(round(v)) == int(round(want)) for v in got)
        else:
            has_match = any(math.isclose(v, want, rel_tol=rel_tol, abs_tol=abs_tol) for v in got)
        if not has_match:
            missing.append(str(ref))

    if missing:
        raise RagEvalAssertionError(f"tabular numeric mismatch: missing={missing}, got_numbers={got}")


def evaluate_rag_output(
    out: Dict[str, Any],
    expected: Dict[str, Any],
    *,
    source_groups: Dict[str, Sequence[str]] | None = None,
) -> None:
    assert_pipeline(out, expected)
    assert_intent_route(out, expected)
    assert_validation(out, expected)

    require_source_match = bool(expected.get("require_source_match", True))
    allowed_sources = list(expected.get("allowed_sources") or [])
    group = str(expected.get("allowed_sources_group") or "").strip()
    if (not allowed_sources) and group:
        allowed_sources = resolve_sources_from_group(source_groups or {}, group)

    assert_source_match(
        out_sources=list(out.get("sources") or []),
        allowed_sources=allowed_sources,
        mode=str(expected.get("source_match_mode") or "any_of"),
        required=require_source_match,
    )

    assert_text_constraints(
        answer=str(out.get("answer") or ""),
        must_contain_any=list(expected.get("must_contain_any") or []),
        must_not_contain=list(expected.get("must_not_contain") or []),
    )


def evaluate_uploaded_docs_output(
    out: Dict[str, Any],
    expected: Dict[str, Any],
    *,
    source_groups: Dict[str, Sequence[str]] | None = None,
    ground_truth: Dict[str, Any] | None = None,
) -> None:
    evaluate_rag_output(out, expected, source_groups=source_groups)
    assert_numeric_consistency(
        answer=str(out.get("answer") or ""),
        expected_numbers=list(expected.get("expected_numbers") or []),
        ground_truth=ground_truth or {},
    )


def evaluate_uploaded_docs_complex_output(
    out: Dict[str, Any],
    expected: Dict[str, Any],
    *,
    source_groups: Dict[str, Sequence[str]] | None = None,
    ground_truth: Dict[str, Any] | None = None,
) -> None:
    evaluate_rag_output(out, expected, source_groups=source_groups)
    assert_tabular_consistency(
        answer=str(out.get("answer") or ""),
        expected_numbers=list(expected.get("expected_numbers") or []),
        ground_truth=ground_truth or {},
        tolerance_policy={"rel_tol": 0.02, "abs_tol": 0.05},
    )
    assert_semester_coverage(
        answer=str(out.get("answer") or ""),
        expected_semesters=list(expected.get("expected_semesters") or []),
    )
