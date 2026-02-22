from typing import Any, Dict, List, Optional, Tuple


def schedule_rows_to_csv_text(rows: Optional[List[Dict[str, Any]]], deps: Dict[str, Any]) -> Tuple[str, int, int]:
    fn = deps.get("_schedule_rows_to_csv_text")
    if callable(fn):
        return fn(rows)
    return "", 0, 0


def transcript_rows_to_csv_text(rows: Optional[List[Dict[str, Any]]], deps: Dict[str, Any]) -> Tuple[str, int, int]:
    fn = deps.get("_transcript_rows_to_csv_text")
    if callable(fn):
        return fn(rows)
    return "", 0, 0


def csv_preview(csv_text: str, deps: Dict[str, Any], max_lines: int = 12) -> str:
    fn = deps.get("_csv_preview")
    if callable(fn):
        return str(fn(csv_text, max_lines=max(3, max_lines)))
    return csv_text

