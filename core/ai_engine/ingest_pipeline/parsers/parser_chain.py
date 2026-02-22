from typing import Any, Dict, List, Optional

from .schedule_llm_parser import parse_schedule_llm
from .schedule_rule_parser import parse_schedule_rules
from .transcript_llm_parser import parse_transcript_llm
from .transcript_rule_parser import parse_transcript_rules


def run_schedule_parser_chain(
    *,
    enabled: bool,
    candidate: bool,
    parser_cls: Any,
    page_payload: List[Dict[str, Any]],
    source: str,
    fallback_semester: Optional[int],
    table_schedule_rows: Optional[List[Dict[str, Any]]],
    deps: Dict[str, Any],
) -> Dict[str, Any]:
    schedule_rows: List[Dict[str, Any]] = []
    parser_used = False
    if enabled and candidate:
        schedule_rows = parse_schedule_llm(
            parser_cls=parser_cls,
            page_payload=page_payload,
            source=source,
            fallback_semester=fallback_semester,
            deps=deps,
        )
        parser_used = bool(schedule_rows)
    if not schedule_rows:
        schedule_rows = parse_schedule_rules(table_schedule_rows=table_schedule_rows, deps=deps)
    return {
        "schedule_rows": schedule_rows,
        "schedule_parser_used": parser_used,
    }


def run_transcript_parser_chain(
    *,
    enabled: bool,
    candidate: bool,
    parser_cls: Any,
    page_payload: List[Dict[str, Any]],
    source: str,
    fallback_semester: Optional[int],
    deps: Dict[str, Any],
) -> Dict[str, Any]:
    if not (enabled and candidate):
        return {"transcript_rows": [], "source": "disabled"}

    norm = deps.get("_norm")
    normalized_parts: List[str] = []
    for payload in page_payload or []:
        raw = str(payload.get("raw_text") or "")
        table = str(payload.get("rough_table_text") or "")
        raw_n = norm(raw) if callable(norm) else raw.strip()
        table_n = norm(table) if callable(norm) else table.strip()
        if raw_n and table_n:
            normalized_parts.append(raw_n + "\n" + table_n)
        elif raw_n:
            normalized_parts.append(raw_n)
        elif table_n:
            normalized_parts.append(table_n)

    det = parse_transcript_rules("\n".join(normalized_parts), fallback_semester, deps=deps)
    det_rows = list(det.get("data_rows") or [])
    if det_rows:
        return {"transcript_rows": det_rows, "source": "deterministic", "stats": det.get("stats") or {}}

    parsed = parse_transcript_llm(
        parser_cls=parser_cls,
        page_payload=page_payload,
        source=source,
        fallback_semester=fallback_semester,
    )
    if parsed.get("ok"):
        return {"transcript_rows": list(parsed.get("data_rows") or []), "source": "llm", "stats": parsed.get("stats") or {}}
    return {"transcript_rows": [], "source": "llm_fail", "error": parsed.get("error") or "unknown_error"}

