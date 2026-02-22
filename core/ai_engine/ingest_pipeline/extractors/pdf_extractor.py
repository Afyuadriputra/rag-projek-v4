from typing import Any, Dict, List, Tuple


def extract_pdf_tables(pdf: Any, deps: Dict[str, Any]) -> Tuple[str, List[str], List[Dict[str, Any]]]:
    fn = deps.get("_extract_pdf_tables")
    if callable(fn):
        return fn(pdf)
    return "", [], []


def extract_pdf_page_payload(pdf: Any, file_path: str, deps: Dict[str, Any]) -> List[Dict[str, Any]]:
    fn = deps.get("_extract_pdf_page_raw_payload")
    if callable(fn):
        return list(fn(pdf, file_path=file_path) or [])
    return []


def extract_pdf_page_raw_payload_legacy(pdf: Any, file_path: str, deps: Dict[str, Any]) -> List[Dict[str, Any]]:
    norm = deps["_norm"]
    fitz_mod = deps.get("fitz")
    payload: List[Dict[str, Any]] = []
    for page_idx, page in enumerate(pdf.pages, start=1):
        raw_text = ""
        rough_table_parts: List[str] = []
        try:
            raw_text = norm(page.extract_text() or "")
        except Exception:
            raw_text = ""
        try:
            tables = page.extract_tables() or []
        except Exception:
            tables = []
        for table in tables:
            if not table:
                continue
            for row in table:
                if not row:
                    continue
                row_txt = " | ".join([norm(c) for c in row if norm(c)]).strip()
                if row_txt:
                    rough_table_parts.append(row_txt)
        payload.append({"page": page_idx, "raw_text": raw_text, "rough_table_text": "\n".join(rough_table_parts).strip()})

    if fitz_mod is not None and file_path:
        sparse = sum(1 for p in payload if not (norm(p.get("raw_text")) or norm(p.get("rough_table_text"))))
        if sparse > 0:
            try:
                doc = fitz_mod.open(file_path)
                for idx in range(min(len(payload), doc.page_count)):
                    if norm(payload[idx].get("raw_text")):
                        continue
                    txt = norm(doc.load_page(idx).get_text("text") or "")
                    if txt:
                        payload[idx]["raw_text"] = txt
                doc.close()
            except Exception:
                pass
    return payload


def extract_pdf_tables_legacy(pdf: Any, deps: Dict[str, Any]) -> Tuple[str, List[str], List[Dict[str, Any]]]:
    norm = deps["_norm"]
    norm_header = deps["_norm_header"]
    looks_like_header_row = deps["_looks_like_header_row"]
    canonical_columns_from_header = deps["_canonical_columns_from_header"]
    display_columns_from_mapping = deps["_display_columns_from_mapping"]
    find_idx = deps["_find_idx"]
    row_to_text = deps["_row_to_text"]
    normalize_time_range = deps["_normalize_time_range"]
    normalize_day_text = deps["_normalize_day_text"]
    is_noise_numbering_row = deps["_is_noise_numbering_row"]
    is_noise_header_repeat_row = deps["_is_noise_header_repeat_row"]
    day_words = deps["_DAY_WORDS"]
    max_schedule_rows = int(deps.get("_MAX_SCHEDULE_ROWS", 2500))
    time_range_re = deps["_TIME_RANGE_RE"]

    detected_columns: List[str] = []
    schedule_rows: List[Dict[str, Any]] = []
    text_parts: List[str] = []
    carry_day = ""
    carry_sesi = ""
    carry_jam = ""

    for page_idx, page in enumerate(pdf.pages, start=1):
        try:
            tables = page.extract_tables() or []
        except Exception:
            tables = []

        for table in tables:
            if not table:
                continue
            cleaned = [[norm(cell) for cell in row] for row in table if row]
            if not cleaned:
                continue

            for row in cleaned:
                text_parts.append(row_to_text(row))

            header = None
            canon_map: Dict[int, str] = {}
            if len(cleaned) >= 2 and looks_like_header_row(cleaned[0]):
                header = cleaned[0]
                canon_map = canonical_columns_from_header(header)
                for col in display_columns_from_mapping(canon_map):
                    if col not in detected_columns:
                        detected_columns.append(col)

            if header:
                header_l = [norm_header(h) for h in header]
                day_idx = find_idx(header_l, ["hari", "day"])
                sesi_idx = find_idx(header_l, ["sesi", "session"])
                time_idx = find_idx(header_l, ["jam", "waktu", "time"])
                code_idx = find_idx(header_l, ["kode mk", "kode", "course code", "kode matakuliah", "kode matkul"])
                name_idx = find_idx(header_l, ["nama matakuliah", "nama mata kuliah", "mata kuliah", "matakuliah", "course name", "nama"])
                sks_idx = find_idx(header_l, ["sks", "credit", "credits"])
                dosen_idx = find_idx(header_l, ["dosen pengampu", "dosen", "pengampu", "lecturer"])
                kelas_idx = find_idx(header_l, ["kelas", "kls", "class"])
                ruang_idx = find_idx(header_l, ["ruang", "room", "lab"])
                semester_idx = find_idx(header_l, ["semester", "smt", "smt.", "sm t", "s m t", "sm"])

                last_day = carry_day
                last_sesi = carry_sesi
                last_jam = carry_jam
                for row in cleaned[1:]:
                    if len(schedule_rows) >= max_schedule_rows:
                        break
                    if is_noise_numbering_row(row) or is_noise_header_repeat_row(row):
                        continue
                    day = row[day_idx] if day_idx is not None and day_idx < len(row) else ""
                    sesi = row[sesi_idx] if sesi_idx is not None and sesi_idx < len(row) else ""
                    jam = row[time_idx] if time_idx is not None and time_idx < len(row) else ""
                    semester_cell = row[semester_idx] if semester_idx is not None and semester_idx < len(row) else ""
                    joined_l = " ".join([norm_header(c) for c in row if norm(c)])
                    if not day:
                        for d in day_words:
                            if d in joined_l:
                                day = d.title() if d.isalpha() else d
                                break
                    if not jam:
                        m = time_range_re.search(normalize_time_range(" ".join(row)))
                        if m:
                            jam = f"{m.group(1).replace('.', ':')}-{m.group(2).replace('.', ':')}"
                    jam = normalize_time_range(jam)
                    day = normalize_day_text(day) or last_day
                    sesi = norm(sesi) or last_sesi
                    jam = normalize_time_range(jam) or last_jam
                    if day:
                        last_day = day
                    if sesi:
                        last_sesi = sesi
                    if jam:
                        last_jam = jam
                    if not day and not jam:
                        continue
                    item: Dict[str, Any] = {
                        "page": page_idx,
                        "hari": day,
                        "sesi": sesi,
                        "jam": jam,
                        "kode": row[code_idx] if code_idx is not None and code_idx < len(row) else "",
                        "mata_kuliah": row[name_idx] if name_idx is not None and name_idx < len(row) else "",
                        "sks": row[sks_idx] if sks_idx is not None and sks_idx < len(row) else "",
                        "dosen": row[dosen_idx] if dosen_idx is not None and dosen_idx < len(row) else "",
                        "kelas": row[kelas_idx] if kelas_idx is not None and kelas_idx < len(row) else "",
                        "ruang": row[ruang_idx] if ruang_idx is not None and ruang_idx < len(row) else "",
                        "semester": norm(semester_cell),
                    }
                    if not norm(item.get("dosen", "")):
                        for c in reversed(row):
                            c_norm = norm(c)
                            if not c_norm:
                                continue
                            if c_norm in {
                                norm(item.get("kode", "")),
                                norm(item.get("mata_kuliah", "")),
                                norm(item.get("sks", "")),
                                norm(item.get("kelas", "")),
                                norm(item.get("ruang", "")),
                                norm(item.get("semester", "")),
                            }:
                                continue
                            if "," in c_norm or "." in c_norm or len(c_norm.split()) >= 2:
                                item["dosen"] = c_norm
                                break
                    for idx, canon in canon_map.items():
                        if canon in item:
                            continue
                        if idx < len(row):
                            item[canon] = row[idx]
                    if item["hari"] or item["jam"]:
                        schedule_rows.append(item)
                carry_day = last_day
                carry_sesi = last_sesi
                carry_jam = last_jam
            else:
                for row in cleaned:
                    if len(schedule_rows) >= max_schedule_rows:
                        break
                    if is_noise_numbering_row(row) or is_noise_header_repeat_row(row):
                        continue
                    raw = row_to_text(row)
                    raw_n = normalize_time_range(raw)
                    low = raw_n.lower()
                    has_day = any(d in low for d in day_words)
                    has_time = bool(time_range_re.search(raw_n))
                    if has_day or has_time:
                        schedule_rows.append({"page": page_idx, "raw": raw_n})

        try:
            page_text = (page.extract_text() or "").strip()
        except Exception:
            page_text = ""
        if page_text:
            t = normalize_time_range(page_text)
            t_l = t.lower()
            time_ranges = list(time_range_re.finditer(t))
            if time_ranges:
                for m in time_ranges:
                    if len(schedule_rows) >= max_schedule_rows:
                        break
                    span_start = max(0, m.start() - 60)
                    span_end = min(len(t_l), m.end() + 60)
                    window = t_l[span_start:span_end]
                    day_found = ""
                    for d in day_words:
                        if d in window:
                            day_found = d
                            break
                    jam = normalize_time_range(f"{m.group(1).replace('.', ':')}-{m.group(2).replace('.', ':')}")
                    exists = False
                    for r in schedule_rows[-60:]:
                        if str(r.get("page")) == str(page_idx) and (r.get("hari") or "").lower() == day_found and (r.get("jam") or "") == jam:
                            exists = True
                            break
                    if not exists:
                        schedule_rows.append(
                            {
                                "page": page_idx,
                                "hari": day_found.title() if day_found else "",
                                "jam": jam,
                                "kode": "",
                                "mata_kuliah": "",
                                "sks": "",
                                "dosen": "",
                                "kelas": "",
                                "ruang": "",
                                "fallback": "page_text",
                            }
                        )

    out_rows: List[Dict[str, Any]] = []
    seen = set()
    for r in schedule_rows:
        if not isinstance(r, dict):
            continue
        hari = normalize_day_text(norm(r.get("hari", "")))
        jam = normalize_time_range(r.get("jam", ""))
        kode = norm(r.get("kode", ""))
        mk = norm(r.get("mata_kuliah", ""))
        kelas = norm(r.get("kelas", ""))
        ruang = norm(r.get("ruang", ""))
        try:
            page = int(r.get("page", 0) or 0)
        except Exception:
            page = 0
        hari_l = hari.lower()
        if hari_l in day_words:
            hari = hari_l.replace("jum'at", "Jum'at").title()
        key = (page, hari_l, jam, kode, mk, kelas, ruang)
        if key in seen:
            continue
        seen.add(key)
        r2 = dict(r)
        r2["page"] = page
        if hari:
            r2["hari"] = hari
        if jam:
            r2["jam"] = jam
        out_rows.append(r2)
    return "\n".join(text_parts).strip(), detected_columns, out_rows
