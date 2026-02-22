from typing import Any, Dict, Optional


def parse_transcript_rules(
    text_blob: str,
    fallback_semester: Optional[int],
    deps: Dict[str, Any],
) -> Dict[str, Any]:
    fn = deps.get("_extract_transcript_rows_deterministic")
    if callable(fn):
        return dict(fn(text_blob, fallback_semester=fallback_semester) or {})
    return {"ok": False, "data_rows": [], "stats": {}}

