from typing import Any, Dict, List, Optional


def parse_schedule_llm(
    *,
    parser_cls: Any,
    page_payload: List[Dict[str, Any]],
    source: str,
    fallback_semester: Optional[int],
    deps: Dict[str, Any],
) -> List[Dict[str, Any]]:
    parser = parser_cls()
    parsed = dict(
        parser.parse_pages(
            page_payload,
            source=source,
            fallback_semester=fallback_semester,
        )
        or {}
    )
    if not parsed.get("ok"):
        return []
    rows = list(parsed.get("data_rows") or [])
    if not rows:
        return []
    conv = deps.get("_canonical_schedule_to_legacy_rows")
    if callable(conv):
        return list(conv(rows, fallback_semester=fallback_semester) or [])
    return rows

