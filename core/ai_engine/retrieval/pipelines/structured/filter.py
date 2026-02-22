from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

_DAY_CANON = {
    "senin": "Senin",
    "selasa": "Selasa",
    "rabu": "Rabu",
    "kamis": "Kamis",
    "jumat": "Jumat",
    "jum'at": "Jumat",
    "sabtu": "Sabtu",
    "minggu": "Minggu",
    "monday": "Senin",
    "tuesday": "Selasa",
    "wednesday": "Rabu",
    "thursday": "Kamis",
    "friday": "Jumat",
    "saturday": "Sabtu",
    "sunday": "Minggu",
}

_GRADE_PRIORITY = {
    "A": 100,
    "A-": 96,
    "AB": 94,
    "B+": 90,
    "B": 86,
    "B-": 82,
    "BC": 80,
    "C+": 76,
    "C": 72,
    "C-": 68,
    "CD": 66,
    "D+": 62,
    "D": 58,
    "D-": 54,
    "E": 0,
}


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def dedupe_transcript_latest(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    slot: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = _normalize_text(row.get("mata_kuliah")).lower()
        if not key:
            continue
        current = slot.get(key)
        if current is None:
            slot[key] = row
            continue
        sem_new = int(row.get("semester") or 0)
        sem_old = int(current.get("semester") or 0)
        if sem_new > sem_old:
            slot[key] = row
            continue
        if sem_new == sem_old:
            score_new = int(_GRADE_PRIORITY.get(_normalize_text(row.get("nilai_huruf")).upper(), -1))
            score_old = int(_GRADE_PRIORITY.get(_normalize_text(current.get("nilai_huruf")).upper(), -1))
            if score_new > score_old:
                slot[key] = row
    return list(slot.values())


def is_low_grade_query(query: str) -> bool:
    ql = str(query or "").lower()
    return (
        ("nilai rendah" in ql)
        or ("nilai jelek" in ql)
        or ("yang rendah" in ql)
        or ("tidak lulus" in ql)
        or ("ngulang" in ql)
        or ("ulang matkul" in ql)
    )


def extract_day_filter(query: str) -> str:
    ql = str(query or "").lower()
    for raw in _DAY_CANON.keys():
        if raw in ql:
            return _DAY_CANON[raw]
    if ("hari ini" in ql) or ("today" in ql):
        tz_name = str(os.environ.get("RAG_ANALYTICS_TIMEZONE", "Asia/Jakarta")).strip() or "Asia/Jakarta"
        try:
            now = datetime.now(ZoneInfo(tz_name))
            return ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"][now.weekday()]
        except Exception:
            return ""
    return ""


def is_course_recap_query(query: str) -> bool:
    ql = str(query or "").lower()
    has_course = ("mata kuliah" in ql) or ("matakuliah" in ql)
    has_recap = any(k in ql for k in ["rekap", "ringkas", "rangkum", "semua", "daftar"])
    return has_course or has_recap


def extract_semester_filter(query: str) -> int | None:
    ql = str(query or "").lower()
    m = re.search(r"\bsemester\s*(\d{1,2})\b", ql)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def extract_course_query_term(query: str) -> str:
    q = _normalize_text(query)
    if not q:
        return ""

    m = re.search(r"['\"]([^'\"]{3,120})['\"]", q)
    if m:
        return _normalize_text(m.group(1))

    ql = q.lower()
    patterns = [
        r"(?:nilai|matakuliah|mata kuliah|mk)\s+(?:untuk|dari|pada)?\s*([a-z0-9 .\-]{4,120})",
        r"(?:bagaimana|gimana|rekap)\s+(?:nilai|hasil)\s+([a-z0-9 .\-]{4,120})",
    ]
    stop_suffix = [
        " saya berapa",
        " berapa",
        " saya",
        " ku",
        " ini",
        " dong",
        " ya",
        " sekarang",
        " ?",
        ",",
    ]
    for p in patterns:
        m = re.search(p, ql, flags=re.IGNORECASE)
        if not m:
            continue
        term = _normalize_text(m.group(1))
        if not term:
            continue
        for suff in stop_suffix:
            if term.endswith(suff):
                term = term[: -len(suff)].strip()
        term = re.sub(r"^(mata\s+kuliah|matakuliah)\s+", "", term, flags=re.IGNORECASE).strip()
        if len(term) >= 4:
            return term
    return ""
