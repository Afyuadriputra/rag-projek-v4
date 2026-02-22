from typing import Any, Dict, List, Optional


def parse_schedule_rules(
    *,
    table_schedule_rows: Optional[List[Dict[str, Any]]],
    deps: Dict[str, Any],
) -> List[Dict[str, Any]]:
    return list(table_schedule_rows or [])

