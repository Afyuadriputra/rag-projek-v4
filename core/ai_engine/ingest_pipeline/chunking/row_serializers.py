from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


def schedule_rows_to_csv_text(rows: Optional[List[Dict[str, Any]]], *, deps: Dict[str, Any]) -> Tuple[str, int, int]:
    if not rows:
        return "", 0, 0
    norm = deps["_norm"]
    normalize_day_text = deps["_normalize_day_text"]
    normalize_time_range = deps["_normalize_time_range"]

    normalized_rows: List[Dict[str, Any]] = []
    no_counter = 0
    for r in rows:
        if not isinstance(r, dict):
            continue
        hari = normalize_day_text(r.get("hari", ""))
        hari = hari.upper() if hari else ""
        sesi = norm(r.get("sesi", ""))
        jam = normalize_time_range(r.get("jam", ""))
        ruang = norm(r.get("ruang", ""))
        ruang = __import__("re").sub(r"(?<=\d),(?=\d)", ".", ruang)
        smt = norm(r.get("semester", ""))
        mk = norm(r.get("mata_kuliah", ""))
        sks = norm(r.get("sks", ""))
        kls = norm(r.get("kelas", ""))
        dosen = norm(r.get("dosen", ""))
        if not (mk or norm(r.get("kode", ""))):
            continue
        no_counter += 1
        normalized_rows.append(
            {
                "NO": no_counter,
                "HARI": hari,
                "SESI": sesi,
                "JAM": jam,
                "Ruang": ruang,
                "SMT": smt,
                "MATA_KULIAH": mk,
                "SKS": sks,
                "KLS": kls,
                "DOSEN_PENGAMPU_TEAM_TEACHING": dosen,
            }
        )
    if not normalized_rows:
        return "", 0, 0
    df = pd.DataFrame(normalized_rows).fillna("")
    ordered_cols = ["NO", "HARI", "SESI", "JAM", "Ruang", "SMT", "MATA_KULIAH", "SKS", "KLS", "DOSEN_PENGAMPU_TEAM_TEACHING"]
    df = df[[c for c in ordered_cols if c in df.columns]]
    return df.to_csv(index=False), int(len(df.index)), int(len(df.columns))


def schedule_rows_to_row_chunks(rows: Optional[List[Dict[str, Any]]], *, deps: Dict[str, Any], limit: int = 2000) -> List[str]:
    if not rows:
        return []
    norm = deps["_norm"]
    canon_order = deps["_SCHEDULE_CANON_ORDER"]
    out: List[str] = []
    for idx, r in enumerate(rows[:limit], start=1):
        if not isinstance(r, dict):
            continue
        cells: List[str] = []
        for key in canon_order:
            val = norm(r.get(key, ""))
            if val:
                cells.append(f"{key}={val}")
        for key, value in r.items():
            if key in canon_order:
                continue
            val = norm(value)
            if val:
                cells.append(f"{key}={val}")
        if len(cells) >= 2:
            out.append(f"CSV_ROW {idx}: " + " | ".join(cells))
    return out


def transcript_rows_to_row_chunks(rows: Optional[List[Dict[str, Any]]], *, deps: Dict[str, Any], limit: int = 2500) -> List[str]:
    if not rows:
        return []
    norm = deps["_norm"]
    safe_int = deps["_safe_int"]
    out: List[str] = []
    for idx, r in enumerate(rows[: max(1, int(limit))], start=1):
        if not isinstance(r, dict):
            continue
        semester = safe_int(r.get("semester"))
        mk = norm(r.get("mata_kuliah"))
        sks = safe_int(r.get("sks"))
        grade = norm(r.get("nilai_huruf")).upper()
        if not mk or semester is None or sks is None or not grade:
            continue
        cells = [f"semester={semester}", f"mata_kuliah={mk}", f"sks={sks}", f"nilai_huruf={grade}"]
        page = safe_int(r.get("page"))
        if page and page > 0:
            cells.append(f"page={page}")
        out.append(f"TRANSCRIPT_ROW {idx}: " + " | ".join(cells))
    return out


def transcript_rows_to_csv_text(rows: Optional[List[Dict[str, Any]]], *, deps: Dict[str, Any]) -> Tuple[str, int, int]:
    if not rows:
        return "", 0, 0
    norm = deps["_norm"]
    safe_int = deps["_safe_int"]
    normalized: List[Dict[str, Any]] = []
    for i, r in enumerate(rows, start=1):
        if not isinstance(r, dict):
            continue
        semester = safe_int(r.get("semester"))
        mk = norm(r.get("mata_kuliah"))
        sks = safe_int(r.get("sks"))
        grade = norm(r.get("nilai_huruf")).upper().replace(" ", "")
        if semester is None or not mk or sks is None or not grade:
            continue
        normalized.append({"NO": i, "SEMESTER": semester, "MATA_KULIAH": mk, "SKS": sks, "NILAI_HURUF": grade})
    if not normalized:
        return "", 0, 0
    df = pd.DataFrame(normalized).fillna("")
    return df.to_csv(index=False), int(len(df.index)), int(len(df.columns))

