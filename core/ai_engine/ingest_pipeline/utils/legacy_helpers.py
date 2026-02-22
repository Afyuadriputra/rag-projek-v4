import re
from typing import Any, Dict, List, Optional

from ..constants import (
    CANON_LABELS,
    DAY_CANON,
    DAY_WORDS,
    HEADER_MAP,
    SEMESTER_RE,
    TIME_RANGE_RE,
    TIME_SINGLE_RE,
)


def norm(s: Any) -> str:
    s = "" if s is None else str(s)
    s = s.replace("\u00a0", " ")
    s = s.replace("\t", " ")
    s = s.replace("\r", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def norm_header(s: Any) -> str:
    out = norm(s).lower()
    out = out.replace(".", " ")
    out = re.sub(r"[^a-z0-9 ]+", " ", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def normalize_time_range(value: str) -> str:
    out = "" if value is None else str(value)
    out = out.replace("\n", " ").replace("\r", " ")
    out = out.replace("–", "-").replace("—", "-")
    out = out.replace(".", ":")
    out = re.sub(r"(?<=\d)\s+(?=\d)", "", out)
    out = re.sub(r"(?<=\d)\s*:\s*(?=\d)", ":", out)
    out = re.sub(r"\s+", " ", out).strip()
    out = re.sub(r"\s*-\s*", "-", out)
    out = out.replace("- ", "-")
    m = TIME_RANGE_RE.search(out)
    if m:
        try:
            h1, m1 = [int(x) for x in m.group(1).replace(".", ":").split(":")]
            h2, m2 = [int(x) for x in m.group(2).replace(".", ":").split(":")]
            if 0 <= h1 <= 23 and 0 <= h2 <= 23 and 0 <= m1 <= 59 and 0 <= m2 <= 59:
                return f"{h1:02d}:{m1:02d}-{h2:02d}:{m2:02d}"
        except Exception:
            pass
    digits = re.sub(r"\D+", "", out)
    if len(digits) == 8:
        def _chunk_reverse_4(d: str) -> str:
            return d[:4][::-1] + d[4:][::-1]

        candidates = [digits, digits[::-1], _chunk_reverse_4(digits), digits[4:] + digits[:4]]
        for cand in candidates:
            h1, m1, h2, m2 = int(cand[:2]), int(cand[2:4]), int(cand[4:6]), int(cand[6:8])
            if 0 <= h1 <= 23 and 0 <= h2 <= 23 and 0 <= m1 <= 59 and 0 <= m2 <= 59:
                a = h1 * 60 + m1
                b = h2 * 60 + m2
                if b < a:
                    h1, m1, h2, m2 = h2, m2, h1, m1
                return f"{h1:02d}:{m1:02d}-{h2:02d}:{m2:02d}"
    return out.strip()


def normalize_hhmm(value: str) -> str:
    out = norm(value).replace(".", ":")
    if not out:
        return ""
    m = TIME_SINGLE_RE.search(out)
    if not m:
        return ""
    try:
        hh, mm = [int(x) for x in m.group(0).split(":")]
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return f"{hh:02d}:{mm:02d}"
    except Exception:
        return ""
    return ""


def is_valid_time_range(value: str) -> bool:
    m = TIME_RANGE_RE.search(normalize_time_range(value or ""))
    if not m:
        return False
    try:
        h1, m1 = [int(x) for x in m.group(1).replace(".", ":").split(":")]
        h2, m2 = [int(x) for x in m.group(2).replace(".", ":").split(":")]
        return 0 <= h1 <= 23 and 0 <= h2 <= 23 and 0 <= m1 <= 59 and 0 <= m2 <= 59
    except Exception:
        return False


def normalize_day_text(value: str) -> str:
    raw = norm(value)
    if not raw:
        return ""
    letters = re.sub(r"[^a-z]+", "", raw.lower())
    if not letters:
        return raw
    if letters in DAY_CANON:
        return DAY_CANON[letters]
    rev = letters[::-1]
    if rev in DAY_CANON:
        return DAY_CANON[rev]
    return raw


def is_noise_numbering_row(row: List[str]) -> bool:
    vals = []
    for c in row:
        v = norm(c).replace(".", "").replace(",", "")
        if v:
            vals.append(v)
    if len(vals) < 5:
        return False
    if not all(v.isdigit() for v in vals):
        return False
    nums = [int(v) for v in vals]
    return nums == list(range(1, len(nums) + 1))


def is_noise_header_repeat_row(row: List[str]) -> bool:
    joined = norm_header(" ".join([norm(x) for x in row if norm(x)]))
    if not joined:
        return False
    return ("no" in joined and "hari" in joined and "jam" in joined and "mata kuliah" in joined)


def looks_like_header_row(row: List[str]) -> bool:
    joined = " ".join([norm_header(x) for x in row if norm(x)])
    if not joined:
        return False
    keys = [
        "hari", "day", "jam", "waktu", "time", "kode", "kode mk", "mk", "matakuliah", "mata kuliah", "course",
        "sks", "credit", "dosen", "pengampu", "lecturer", "kelas", "class", "ruang", "room", "lab", "no",
    ]
    hits = sum(1 for k in keys if k in joined)
    return hits >= 2


def canonical_header(name: str) -> Optional[str]:
    key = norm_header(name)
    if key in HEADER_MAP:
        return HEADER_MAP[key]
    for k, v in HEADER_MAP.items():
        if k and k in key:
            return v
    return None


def canonical_columns_from_header(header: List[str]) -> Dict[int, str]:
    mapping: Dict[int, str] = {}
    for i, h in enumerate(header):
        canon = canonical_header(h)
        if canon:
            mapping[i] = canon
    return mapping


def display_columns_from_mapping(mapping: Dict[int, str]) -> List[str]:
    cols: List[str] = []
    seen = set()
    for _, canon in mapping.items():
        label = CANON_LABELS.get(canon, canon.title())
        if label.lower() in seen:
            continue
        seen.add(label.lower())
        cols.append(label)
    return cols


def find_idx(header_l: List[str], candidates: List[str]) -> Optional[int]:
    for cand in candidates:
        cand_n = norm_header(cand)
        for i, h in enumerate(header_l):
            if h == cand_n:
                return i
        for i, h in enumerate(header_l):
            if cand_n and cand_n in h:
                return i
    return None


def row_to_text(row: List[str]) -> str:
    return " | ".join([norm(c) for c in row if norm(c)]).strip()


def extract_semester_from_text(value: str) -> Optional[int]:
    if not value:
        return None
    m = SEMESTER_RE.search(str(value))
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def detect_doc_type(detected_columns: Optional[List[str]], schedule_rows: Optional[List[Dict[str, Any]]]) -> str:
    cols = [c.lower() for c in (detected_columns or [])]
    if any(c in cols for c in ["hari", "jam", "ruang", "kelas"]):
        return "schedule"
    if schedule_rows:
        return "schedule"
    if any(c in cols for c in ["grade", "bobot", "nilai", "ips", "ipk"]):
        return "transcript"
    return "general"


def csv_preview(csv_text: str, max_lines: int = 12, max_chars: int = 3500) -> str:
    lines = (csv_text or "").splitlines()
    if not lines:
        return "-"
    preview = "\n".join(lines[:max_lines])
    if len(lines) > max_lines:
        preview += f"\n... (+{len(lines) - max_lines} rows)"
    if len(preview) > max_chars:
        preview = preview[:max_chars] + "\n... (truncated)"
    return preview


def parser_deps() -> Dict[str, Any]:
    return {
        "_norm": norm,
        "_norm_header": norm_header,
        "_looks_like_header_row": looks_like_header_row,
        "_canonical_columns_from_header": canonical_columns_from_header,
        "_display_columns_from_mapping": display_columns_from_mapping,
        "_find_idx": find_idx,
        "_row_to_text": row_to_text,
        "_normalize_time_range": normalize_time_range,
        "_normalize_day_text": normalize_day_text,
        "_is_noise_numbering_row": is_noise_numbering_row,
        "_is_noise_header_repeat_row": is_noise_header_repeat_row,
        "_DAY_WORDS": DAY_WORDS,
        "_TIME_RANGE_RE": TIME_RANGE_RE,
    }
