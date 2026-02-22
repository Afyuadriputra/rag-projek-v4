import json
import re
from typing import Any, Dict, List, Optional


def extract_transcript_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    raw = str(text).strip()
    candidates: List[str] = [raw]
    fenced = re.search(r"```json\s*(.*?)\s*```", raw, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        candidates.append(fenced.group(1).strip())
    obj_blob = re.search(r"(\{[\s\S]*\})", raw)
    if obj_blob:
        candidates.append(obj_blob.group(1).strip())
    for c in candidates:
        if not c:
            continue
        try:
            parsed = json.loads(c)
        except Exception:
            continue
        if isinstance(parsed, dict) and isinstance(parsed.get("data_rows"), list):
            return parsed
    return None


def extract_schedule_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    raw = str(text).strip()
    candidates: List[str] = [raw]
    fenced = re.search(r"```json\s*(.*?)\s*```", raw, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        candidates.append(fenced.group(1).strip())
    obj_blob = re.search(r"(\{[\s\S]*\})", raw)
    if obj_blob:
        candidates.append(obj_blob.group(1).strip())
    arr_blob = re.search(r"(\[[\s\S]*\])", raw)
    if arr_blob:
        candidates.append(arr_blob.group(1).strip())
    for c in candidates:
        if not c:
            continue
        try:
            parsed = json.loads(c)
        except Exception:
            continue
        if isinstance(parsed, dict) and isinstance(parsed.get("data_rows"), list):
            return parsed
        if isinstance(parsed, list):
            return {"data_rows": parsed}
    return None


def safe_int(v: Any, *, norm_fn) -> Optional[int]:
    try:
        if v is None or isinstance(v, bool):
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, float):
            return int(round(v))
        s = norm_fn(v).replace(",", ".")
        if not s:
            return None
        return int(round(float(s)))
    except Exception:
        return None


def normalize_transcript_rows(rows: List[Dict[str, Any]], fallback_semester: Optional[int], *, deps: Dict[str, Any]) -> List[Dict[str, Any]]:
    norm = deps["_norm"]
    safe_int_fn = deps["_safe_int"]
    grade_whitelist = deps["_TRANSCRIPT_GRADE_WHITELIST"]
    out: List[Dict[str, Any]] = []
    seen = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        semester = safe_int_fn(row.get("semester"))
        if semester is None:
            semester = fallback_semester if fallback_semester is not None else 0
        mata_kuliah = norm(row.get("mata_kuliah"))
        if not mata_kuliah:
            continue
        sks = safe_int_fn(row.get("sks"))
        if sks is None:
            continue
        sks = max(0, min(12, sks))
        nilai_huruf = norm(row.get("nilai_huruf")).upper().replace(" ", "")
        if nilai_huruf not in grade_whitelist:
            continue
        page = safe_int_fn(row.get("page"))
        item = {"semester": int(semester), "mata_kuliah": mata_kuliah, "sks": int(sks), "nilai_huruf": nilai_huruf}
        if page and page > 0:
            item["page"] = int(page)
        key = (int(item["semester"]), norm(item["mata_kuliah"]).lower(), int(item["sks"]), str(item["nilai_huruf"]))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def normalize_schedule_rows(rows: List[Dict[str, Any]], fallback_semester: Optional[int], *, deps: Dict[str, Any]) -> List[Dict[str, Any]]:
    normalize_day_text = deps["_normalize_day_text"]
    norm = deps["_norm"]
    safe_int_fn = deps["_safe_int"]
    normalize_hhmm = deps["_normalize_hhmm"]
    normalize_time_range = deps["_normalize_time_range"]
    time_range_re = deps["_TIME_RANGE_RE"]

    out: List[Dict[str, Any]] = []
    seen = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        hari = normalize_day_text(row.get("hari") or row.get("day") or row.get("hari_kuliah") or "")
        mata_kuliah = norm(row.get("mata_kuliah") or row.get("matakuliah") or row.get("course_name") or row.get("nama_mata_kuliah") or "")
        ruangan = norm(row.get("ruangan") or row.get("ruang") or row.get("room") or row.get("lokasi") or "")
        semester = safe_int_fn(row.get("semester"))
        if semester is None and fallback_semester is not None:
            semester = int(fallback_semester)
        page = safe_int_fn(row.get("page"))
        jam_mulai = normalize_hhmm(str(row.get("jam_mulai") or ""))
        jam_selesai = normalize_hhmm(str(row.get("jam_selesai") or ""))
        if not (jam_mulai and jam_selesai):
            jam_field = normalize_time_range(str(row.get("jam") or row.get("waktu") or ""))
            m = time_range_re.search(jam_field)
            if m:
                jam_mulai = normalize_hhmm(m.group(1))
                jam_selesai = normalize_hhmm(m.group(2))
        if not mata_kuliah or not hari or not (jam_mulai and jam_selesai):
            continue
        item: Dict[str, Any] = {"hari": hari, "jam_mulai": jam_mulai, "jam_selesai": jam_selesai, "mata_kuliah": mata_kuliah, "ruangan": ruangan}
        if semester is not None:
            item["semester"] = int(max(0, semester))
        if page and page > 0:
            item["page"] = int(page)
        key = (norm(item.get("hari")).lower(), str(item.get("jam_mulai")), str(item.get("jam_selesai")), norm(item.get("mata_kuliah")).lower(), norm(item.get("ruangan")).lower(), int(item.get("semester", 0) or 0))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def is_transcript_candidate(title: str, detected_columns: Optional[List[str]], *, deps: Dict[str, Any]) -> bool:
    norm = deps["_norm"]
    title_hints = deps["_TRANSCRIPT_TITLE_HINTS"]
    col_hints = deps["_TRANSCRIPT_COL_HINTS"]
    title_l = norm(title).lower()
    if any(h in title_l for h in title_hints):
        return True
    cols_l = " ".join([norm(c).lower() for c in (detected_columns or []) if norm(c)])
    return any(h in cols_l for h in col_hints)


def is_schedule_candidate(title: str, detected_columns: Optional[List[str]], *, deps: Dict[str, Any]) -> bool:
    norm = deps["_norm"]
    title_hints = deps["_SCHEDULE_TITLE_HINTS"]
    col_hints = deps["_SCHEDULE_COL_HINTS"]
    title_l = norm(title).lower()
    if any(h in title_l for h in title_hints):
        return True
    cols_l = " ".join([norm(c).lower() for c in (detected_columns or []) if norm(c)])
    return any(h in cols_l for h in col_hints)


def canonical_schedule_to_legacy_rows(rows: List[Dict[str, Any]], fallback_semester: Optional[int], *, deps: Dict[str, Any]) -> List[Dict[str, Any]]:
    norm = deps["_norm"]
    normalize_hhmm = deps["_normalize_hhmm"]
    normalize_day_text = deps["_normalize_day_text"]
    safe_int_fn = deps["_safe_int"]
    out: List[Dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        jam_mulai = normalize_hhmm(str(row.get("jam_mulai") or ""))
        jam_selesai = normalize_hhmm(str(row.get("jam_selesai") or ""))
        jam = f"{jam_mulai}-{jam_selesai}" if jam_mulai and jam_selesai else ""
        semester = safe_int_fn(row.get("semester"))
        if semester is None and fallback_semester is not None:
            semester = int(fallback_semester)
        item: Dict[str, Any] = {
            "hari": normalize_day_text(row.get("hari", "")),
            "sesi": norm(row.get("sesi", "")),
            "jam": jam,
            "jam_mulai": jam_mulai,
            "jam_selesai": jam_selesai,
            "kode": norm(row.get("kode", "")),
            "mata_kuliah": norm(row.get("mata_kuliah", "")),
            "sks": norm(row.get("sks", "")),
            "kelas": norm(row.get("kelas", "")),
            "ruang": norm(row.get("ruangan") or row.get("ruang") or ""),
            "ruangan": norm(row.get("ruangan") or row.get("ruang") or ""),
            "dosen": norm(row.get("dosen", "")),
        }
        if semester is not None:
            item["semester"] = str(int(semester))
        page = safe_int_fn(row.get("page"))
        if page and page > 0:
            item["page"] = int(page)
        out.append(item)
    return out


def extract_transcript_rows_deterministic(text_blob: str, fallback_semester: Optional[int], *, deps: Dict[str, Any]) -> Dict[str, Any]:
    norm = deps["_norm"]
    safe_int_fn = deps["_safe_int"]
    row_re = deps["_TRANSCRIPT_ROW_RE"]
    pending_re = deps["_TRANSCRIPT_PENDING_RE"]
    grade_prefix_re = deps["_TRANSCRIPT_GRADE_PREFIX_RE"]
    grade_whitelist = deps["_TRANSCRIPT_GRADE_WHITELIST"]

    raw_blob = str(text_blob or "")
    if "\n" not in raw_blob:
        raw_blob = re.sub(r"\s(?=\d{1,3}\s+[A-Z0-9]{5,12}\s)", "\n", raw_blob)
    lines = [str(x or "").strip() for x in raw_blob.splitlines()]
    rows: List[Dict[str, Any]] = []
    rows_detected = 0
    rows_pending = 0
    grade_dist: Dict[str, int] = {}
    for ln in lines:
        line = re.sub(r"\s{2,}", " ", ln).strip()
        if not line:
            continue
        m = row_re.match(line)
        if not m:
            continue
        rows_detected += 1
        no, kode, mata_kuliah, sks_txt, tail = m.groups()
        mata_kuliah = norm(mata_kuliah)
        sks = safe_int_fn(sks_txt)
        if not mata_kuliah or sks is None:
            continue
        if pending_re.search(tail or ""):
            rows_pending += 1
            rows.append({"semester": int(fallback_semester or 0), "mata_kuliah": mata_kuliah, "sks": int(sks), "nilai_huruf": "ISI KUISIONER TERLEBIH DAHULU", "row_no": int(safe_int_fn(no) or 0), "kode": norm(kode).upper()})
            continue
        gm = grade_prefix_re.match(norm(tail).upper())
        if not gm:
            continue
        grade = norm(gm.group(1)).upper()
        if grade not in grade_whitelist:
            continue
        grade_dist[grade] = int(grade_dist.get(grade, 0)) + 1
        rows.append({"semester": int(fallback_semester or 0), "mata_kuliah": mata_kuliah, "sks": int(sks), "nilai_huruf": grade, "row_no": int(safe_int_fn(no) or 0), "kode": norm(kode).upper()})
    sks_done = None
    sks_required = None
    total_quality_points = ""
    ipk = ""
    m_sks_done = re.search(r"Jumlah SKS yang telah ditempuh\s*:\s*(\d+)", text_blob, re.IGNORECASE)
    if m_sks_done:
        sks_done = safe_int(m_sks_done.group(1), norm_fn=norm)
    m_sks_req = re.search(r"SKS yang harus ditempuh\s*:\s*(\d+)", text_blob, re.IGNORECASE)
    if m_sks_req:
        sks_required = safe_int(m_sks_req.group(1), norm_fn=norm)
    m_quality = re.search(r"Jumlah Nilai Mutu\s*:\s*([0-9]+(?:\.[0-9]+)?)", text_blob, re.IGNORECASE)
    if m_quality:
        total_quality_points = norm(m_quality.group(1))
    m_ipk = re.search(r"IPK\s*:\s*([0-9]+(?:\.[0-9]+)?)", text_blob, re.IGNORECASE)
    if m_ipk:
        ipk = norm(m_ipk.group(1))
    return {
        "data_rows": rows,
        "stats": {
            "rows_detected": int(rows_detected),
            "rows_valid": int(len(rows)),
            "rows_pending": int(rows_pending),
            "grade_distribution": grade_dist,
            "sks_done": int(sks_done) if sks_done is not None else None,
            "sks_required": int(sks_required) if sks_required is not None else None,
            "total_quality_points": total_quality_points,
            "ipk": ipk,
        },
    }
