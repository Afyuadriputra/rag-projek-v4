from __future__ import annotations

import re
from typing import Any, Dict

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


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _to_int(value: Any) -> int | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        val = str(value).strip()
        if not val:
            return None
        return int(float(val))
    except Exception:
        return None


def _normalize_day(value: str) -> str:
    raw = _normalize_text(value).lower()
    raw_letters = re.sub(r"[^a-z]+", "", raw)
    if not raw_letters:
        return _normalize_text(value)
    if raw_letters in _DAY_CANON:
        return _DAY_CANON[raw_letters]
    rev = raw_letters[::-1]
    if rev in _DAY_CANON:
        return _DAY_CANON[rev]
    return _normalize_text(value)


def _normalize_hhmm(value: str) -> str:
    txt = _normalize_text(value).replace(".", ":")
    m = re.search(r"\b(\d{1,2}):(\d{2})\b", txt)
    if not m:
        return ""
    try:
        hh, mm = int(m.group(1)), int(m.group(2))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return f"{hh:02d}:{mm:02d}"
    except Exception:
        return ""
    return ""


def _parse_key_value_chunk(text: str) -> Dict[str, str]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    body = raw.split(":", 1)[1] if ":" in raw else raw
    out: Dict[str, str] = {}
    for part in body.split("|"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        key = _normalize_text(k).lower()
        val = _normalize_text(v)
        if key:
            out[key] = val
    return out


def normalize_transcript_from_chunk(chunk: str, meta: Dict[str, Any]) -> Dict[str, Any] | None:
    kv = _parse_key_value_chunk(chunk)
    semester = _to_int(kv.get("semester"))
    mata_kuliah = _normalize_text(kv.get("mata_kuliah") or kv.get("matakuliah"))
    sks = _to_int(kv.get("sks"))
    nilai_huruf = _normalize_text(kv.get("nilai_huruf")).upper()
    if not mata_kuliah or semester is None or sks is None or not nilai_huruf:
        return None
    return {
        "semester": int(semester),
        "mata_kuliah": mata_kuliah,
        "sks": int(sks),
        "nilai_huruf": nilai_huruf,
        "source": _normalize_text(meta.get("source") or "unknown"),
        "page": _to_int(meta.get("page")),
    }


def normalize_schedule_from_chunk(chunk: str, meta: Dict[str, Any]) -> Dict[str, Any] | None:
    kv = _parse_key_value_chunk(chunk)
    hari = _normalize_day(kv.get("hari") or kv.get("day") or "")
    mata_kuliah = _normalize_text(kv.get("mata_kuliah") or kv.get("matakuliah"))
    ruangan = _normalize_text(kv.get("ruangan") or kv.get("ruang") or kv.get("room"))
    semester = _to_int(kv.get("semester"))
    jam_mulai = _normalize_hhmm(kv.get("jam_mulai", ""))
    jam_selesai = _normalize_hhmm(kv.get("jam_selesai", ""))

    if not (jam_mulai and jam_selesai):
        jam = _normalize_text(kv.get("jam"))
        m = re.search(r"(\d{1,2}[:.]\d{2})\s*-\s*(\d{1,2}[:.]\d{2})", jam)
        if m:
            jam_mulai = _normalize_hhmm(m.group(1))
            jam_selesai = _normalize_hhmm(m.group(2))

    if not mata_kuliah or not hari or not (jam_mulai and jam_selesai):
        return None
    return {
        "hari": hari,
        "jam_mulai": jam_mulai,
        "jam_selesai": jam_selesai,
        "mata_kuliah": mata_kuliah,
        "ruangan": ruangan,
        "semester": semester,
        "source": _normalize_text(meta.get("source") or "unknown"),
        "page": _to_int(meta.get("page")),
    }
