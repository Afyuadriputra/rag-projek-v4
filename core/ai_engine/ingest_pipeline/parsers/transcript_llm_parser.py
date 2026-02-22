from typing import Any, Dict, List, Optional


def parse_transcript_llm(
    *,
    parser_cls: Any,
    page_payload: List[Dict[str, Any]],
    source: str,
    fallback_semester: Optional[int],
) -> Dict[str, Any]:
    parser = parser_cls()
    return dict(
        parser.parse_pages(
            page_payload,
            source=source,
            fallback_semester=fallback_semester,
        )
        or {}
    )

