import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Tuple
from zoneinfo import ZoneInfo

from .llm import build_llm, get_backup_models, get_runtime_openrouter_config, invoke_text
from ..config import get_vectorstore


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


def _env_bool(name: str, default: bool = False) -> bool:
    val = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return val in {"1", "true", "yes", "on"}


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


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


def _to_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        val = str(value).strip()
        if not val:
            return None
        return int(float(val))
    except Exception:
        return None


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


def _fetch_row_chunks(user_id: int, doc_type: str, doc_ids: List[int] | None = None) -> List[Tuple[str, Dict[str, Any]]]:
    try:
        vs = get_vectorstore()
        col = getattr(vs, "_collection", None) or getattr(vs, "collection", None)
        if col is None:
            return []
        where_parts: List[Dict[str, Any]] = [
            {"user_id": str(user_id)},
            {"chunk_kind": "row"},
            {"doc_type": doc_type},
        ]
        if doc_ids:
            where_parts.append({"doc_id": {"$in": [str(x) for x in doc_ids]}})
        where = {"$and": where_parts}
        used_fallback_filter = False
        try:
            # Chroma v1.x tidak menerima "ids" pada include.
            got = col.get(where=where, include=["documents", "metadatas"])
        except Exception:
            # Beberapa versi Chroma (terutama collection.get) tidak menerima operator `$and`.
            # Fallback: ambil by user_id lalu filter metadata di sisi aplikasi.
            used_fallback_filter = True
            try:
                got = col.get(where={"user_id": str(user_id)}, include=["documents", "metadatas"])
            except Exception:
                got = col.get(where={"user_id": str(user_id)})
        docs = list(got.get("documents", []) or [])
        metas = list(got.get("metadatas", []) or [])
        out: List[Tuple[str, Dict[str, Any]]] = []
        doc_id_set = {str(x) for x in (doc_ids or [])}
        for i, text in enumerate(docs):
            chunk = _normalize_text(text)
            if not chunk:
                continue
            meta = metas[i] if i < len(metas) and isinstance(metas[i], dict) else {}
            if used_fallback_filter:
                if _normalize_text(meta.get("chunk_kind")).lower() != "row":
                    continue
                if _normalize_text(meta.get("doc_type")).lower() != _normalize_text(doc_type).lower():
                    continue
                if doc_id_set and str(meta.get("doc_id")) not in doc_id_set:
                    continue
            out.append((chunk, meta))
        return out
    except Exception:
        return []


def _fetch_transcript_text_chunks(user_id: int, doc_ids: List[int] | None = None) -> List[str]:
    try:
        vs = get_vectorstore()
        col = getattr(vs, "_collection", None) or getattr(vs, "collection", None)
        if col is None:
            return []
        where_parts: List[Dict[str, Any]] = [
            {"user_id": str(user_id)},
            {"doc_type": "transcript"},
            {"chunk_kind": "text"},
        ]
        if doc_ids:
            where_parts.append({"doc_id": {"$in": [str(x) for x in doc_ids]}})
        where = {"$and": where_parts}
        used_fallback_filter = False
        try:
            got = col.get(where=where, include=["documents", "metadatas"])
        except Exception:
            used_fallback_filter = True
            try:
                got = col.get(where={"user_id": str(user_id)}, include=["documents", "metadatas"])
            except Exception:
                got = col.get(where={"user_id": str(user_id)})

        docs = list(got.get("documents", []) or [])
        metas = list(got.get("metadatas", []) or [])
        out: List[str] = []
        doc_id_set = {str(x) for x in (doc_ids or [])}
        for i, text in enumerate(docs):
            chunk = _normalize_text(text)
            if not chunk:
                continue
            if used_fallback_filter:
                meta = metas[i] if i < len(metas) and isinstance(metas[i], dict) else {}
                if _normalize_text(meta.get("doc_type")).lower() != "transcript":
                    continue
                if _normalize_text(meta.get("chunk_kind")).lower() != "text":
                    continue
                if doc_id_set and str(meta.get("doc_id")) not in doc_id_set:
                    continue
            out.append(chunk)
        return out
    except Exception:
        return []


def _normalize_transcript_from_chunk(chunk: str, meta: Dict[str, Any]) -> Dict[str, Any] | None:
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


def _normalize_schedule_from_chunk(chunk: str, meta: Dict[str, Any]) -> Dict[str, Any] | None:
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


def _dedupe_transcript_latest(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
    # Pertahankan urutan kemunculan dokumen agar output rekap mengikuti urutan tabel asli.
    return list(slot.values())


def _is_today_query(query: str) -> bool:
    ql = str(query or "").lower()
    return ("hari ini" in ql) or ("today" in ql)


def _extract_day_filter(query: str) -> str:
    ql = str(query or "").lower()
    for raw in _DAY_CANON.keys():
        if raw in ql:
            return _DAY_CANON[raw]
    if _is_today_query(ql):
        tz_name = str(os.environ.get("RAG_ANALYTICS_TIMEZONE", "Asia/Jakarta")).strip() or "Asia/Jakarta"
        try:
            now = datetime.now(ZoneInfo(tz_name))
            return [
                "Senin",
                "Selasa",
                "Rabu",
                "Kamis",
                "Jumat",
                "Sabtu",
                "Minggu",
            ][now.weekday()]
        except Exception:
            return ""
    return ""


def _is_low_grade_query(query: str) -> bool:
    ql = str(query or "").lower()
    return (
        ("nilai rendah" in ql)
        or ("nilai jelek" in ql)
        or ("yang rendah" in ql)
        or ("tidak lulus" in ql)
        or ("ngulang" in ql)
        or ("ulang matkul" in ql)
    )


def _is_course_recap_query(query: str) -> bool:
    ql = str(query or "").lower()
    has_course = ("mata kuliah" in ql) or ("matakuliah" in ql)
    has_recap = any(k in ql for k in ["rekap", "ringkas", "rangkum", "semua", "daftar"])
    return has_course or has_recap


def _is_ipk_or_stats_query(query: str) -> bool:
    ql = str(query or "").lower()
    return any(
        k in ql
        for k in [
            "ipk",
            "ips",
            "sks",
            "total sks",
            "hasil studi",
            "progress studi",
            "statistik studi",
            "belum dinilai",
        ]
    )


def _extract_semester_filter(query: str) -> int | None:
    ql = str(query or "").lower()
    m = re.search(r"\bsemester\s*(\d{1,2})\b", ql)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _extract_course_query_term(query: str) -> str:
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


def _render_sources(rows: List[Dict[str, Any]], max_sources: int = 8) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for row in rows:
        source = _normalize_text(row.get("source") or "unknown")
        page = _to_int(row.get("page"))
        label = f"{source} (p.{page})" if page else source
        if label in seen:
            continue
        seen.add(label)
        if "nilai_huruf" in row:
            snippet = (
                f"semester={row.get('semester')} | mata_kuliah={row.get('mata_kuliah')} | "
                f"sks={row.get('sks')} | nilai_huruf={row.get('nilai_huruf')}"
            )
        else:
            snippet = (
                f"hari={row.get('hari')} | jam={row.get('jam_mulai')}-{row.get('jam_selesai')} | "
                f"mata_kuliah={row.get('mata_kuliah')} | ruangan={row.get('ruangan')}"
            )
        out.append({"source": label, "snippet": snippet})
        if len(out) >= max_sources:
            break
    return out


def _extract_transcript_profile(text_chunks: List[str]) -> Dict[str, Any]:
    merged = " ".join([_normalize_text(x) for x in text_chunks if _normalize_text(x)])
    merged = re.sub(r"\s+", " ", merged).strip()
    if not merged:
        return {
            "nama": "-",
            "nim": "-",
            "program_studi": "-",
            "sks_ditempuh": None,
            "sks_wajib": None,
            "ipk": "",
            "pending_courses": [],
        }

    nama = "-"
    nim = "-"
    program_studi = "-"
    sks_ditempuh = None
    sks_wajib = None
    ipk = ""

    m = re.search(r"Nama\s*:\s*([A-Z ]+?)\s+Dosen\s+PA", merged, flags=re.IGNORECASE)
    if m:
        nama = _normalize_text(m.group(1))
    m = re.search(r"\bNIM\s*:?\s*(\d+)\b", merged, flags=re.IGNORECASE)
    if m:
        nim = _normalize_text(m.group(1))
    m = re.search(r"Program\s+NIM\s*:?\s*\d+\s*:?\s*([A-Za-z ]+?)\s+Studi", merged, flags=re.IGNORECASE)
    if m:
        program_studi = _normalize_text(m.group(1))
    if program_studi == "-":
        m = re.search(r"Program\s+Studi\s*:?\s*([A-Za-z ]+)", merged, flags=re.IGNORECASE)
        if m:
            program_studi = _normalize_text(m.group(1))
    m = re.search(r"Jumlah\s+SKS\s+yang\s+telah\s+ditempuh\s*:?\s*(\d+)", merged, flags=re.IGNORECASE)
    if m:
        sks_ditempuh = _to_int(m.group(1))
    m = re.search(r"SKS\s+yang\s+harus\s+ditempuh\s*:?\s*(\d+)", merged, flags=re.IGNORECASE)
    if m:
        sks_wajib = _to_int(m.group(1))
    m = re.search(r"\bIPK\s*:?\s*([0-9]+(?:\.[0-9]+)?)", merged, flags=re.IGNORECASE)
    if m:
        ipk = _normalize_text(m.group(1))

    pending_courses: List[str] = []
    if re.search(r"Isi\s+Kuisioner|Isi\s+Kuesioner", merged, flags=re.IGNORECASE):
        # KHS UMRI pada umumnya menandai 2 mata kuliah ini sebagai pending.
        for mk in ["Pembelajaran Mendalam", "Skripsi"]:
            if re.search(re.escape(mk), merged, flags=re.IGNORECASE):
                pending_courses.append(mk)
    return {
        "nama": nama,
        "nim": nim,
        "program_studi": program_studi,
        "sks_ditempuh": sks_ditempuh,
        "sks_wajib": sks_wajib,
        "ipk": ipk,
        "pending_courses": pending_courses,
    }


def _render_transcript_answer(rows: List[Dict[str, Any]], query: str, profile: Dict[str, Any] | None = None) -> str:
    if not rows:
        return (
            "## Ringkasan\n"
            "Maaf, data tidak ditemukan di dokumen Anda.\n\n"
            "## Opsi Lanjut\n"
            "- Pastikan dokumen KHS/Transkrip sudah terunggah.\n"
            "- Jika ingin, sebutkan semester spesifik yang ingin direkap."
        )

    low_grade = _is_low_grade_query(query)
    stats_only = _is_ipk_or_stats_query(query) and not _is_course_recap_query(query)
    if low_grade:
        title = "## Ringkasan Nilai Rendah"
        lines = [
            title,
            f"- Total mata kuliah: **{len(rows)}**",
            f"- Total SKS: **{sum(int(x.get('sks') or 0) for x in rows)}**",
            "",
            "## Tabel",
            "| Semester | Mata Kuliah | SKS | Nilai Huruf |",
            "|---|---|---:|---|",
        ]
        for row in rows:
            lines.append(
                f"| {row.get('semester')} | {row.get('mata_kuliah')} | {row.get('sks')} | {row.get('nilai_huruf')} |"
            )
        return "\n".join(lines).strip()

    profile = profile or {}
    total_sks = sum(int(x.get("sks") or 0) for x in rows)
    sks_ditempuh = _to_int(profile.get("sks_ditempuh"))
    sks_wajib = _to_int(profile.get("sks_wajib"))
    ipk = _normalize_text(profile.get("ipk"))
    pending_courses = [x for x in (profile.get("pending_courses") or []) if _normalize_text(x)]

    if sks_ditempuh is None:
        sks_ditempuh = total_sks

    rows_sorted = list(rows)
    pending_lc = {x.lower() for x in pending_courses}
    if stats_only:
        lines = [
            "Berdasarkan Kartu Hasil Studi, berikut ringkasan hasil studi kamu.",
            "",
            "## Informasi Umum",
            f"- Nama: **{_normalize_text(profile.get('nama')) or '-'}**",
            f"- NIM: **{_normalize_text(profile.get('nim')) or '-'}**",
            f"- Program Studi: **{_normalize_text(profile.get('program_studi')) or '-'}**",
            "",
            "## Statistik Studi",
            f"- Total mata kuliah terdata: **{len(rows_sorted)}**",
            f"- Total SKS ditempuh: **{sks_ditempuh} SKS**",
            f"- SKS wajib: **{sks_wajib if sks_wajib is not None else '-'} SKS**",
            f"- IPK: **{ipk or '-'}**",
            (
                f"- Mata kuliah belum dinilai: **{', '.join(pending_courses)}** (menunggu isi kuesioner)"
                if pending_courses
                else "- Mata kuliah belum dinilai: **-**"
            ),
        ]
        return "\n".join(lines).strip()

    lines = [
        "Berdasarkan Kartu Hasil Studi, berikut rekap hasil studi kamu.",
        "",
        "## Informasi Umum",
        f"- Nama: **{_normalize_text(profile.get('nama')) or '-'}**",
        f"- NIM: **{_normalize_text(profile.get('nim')) or '-'}**",
        f"- Program Studi: **{_normalize_text(profile.get('program_studi')) or '-'}**",
        "",
        "## Statistik Studi",
        f"- Total mata kuliah terdata: **{len(rows_sorted)}**",
        f"- Total SKS ditempuh: **{sks_ditempuh} SKS**",
        f"- SKS wajib: **{sks_wajib if sks_wajib is not None else '-'} SKS**",
        f"- IPK: **{ipk or '-'}**",
        (
            f"- Mata kuliah belum dinilai: **{', '.join(pending_courses)}** (menunggu isi kuesioner)"
            if pending_courses
            else "- Mata kuliah belum dinilai: **-**"
        ),
        "",
        "## Daftar Mata Kuliah",
        "| No | Mata Kuliah | SKS | Nilai |",
        "|---:|---|---:|---|",
    ]
    for idx, row in enumerate(rows_sorted, start=1):
        mk = _normalize_text(row.get("mata_kuliah"))
        nilai = _normalize_text(row.get("nilai_huruf")).upper()
        if pending_lc and mk.lower() in pending_lc:
            nilai = "(Isi Kuesioner Terlebih Dahulu)"
        lines.append(
            f"| {idx} | {mk} | {row.get('sks')} | {nilai} |"
        )
    return "\n".join(lines).strip()


def _render_schedule_answer(rows: List[Dict[str, Any]], day_filter: str) -> str:
    if not rows:
        suffix = f" untuk **{day_filter}**" if day_filter else ""
        return (
            "## Ringkasan\n"
            f"Maaf, data tidak ditemukan di dokumen Anda{suffix}.\n\n"
            "## Opsi Lanjut\n"
            "- Pastikan dokumen KRS/Jadwal sudah terunggah.\n"
            "- Coba sebutkan hari yang ingin dicek, contoh: `jadwal hari senin`."
        )

    title = f"## Ringkasan Jadwal {day_filter}" if day_filter else "## Ringkasan Jadwal"
    lines = [
        title,
        f"- Total kelas: **{len(rows)}**",
        "",
        "## Tabel",
        "| Hari | Jam | Mata Kuliah | Ruangan | Semester |",
        "|---|---|---|---|---:|",
    ]
    for row in rows:
        jam = f"{row.get('jam_mulai')}-{row.get('jam_selesai')}"
        semester = row.get("semester") if row.get("semester") is not None else "-"
        lines.append(
            f"| {row.get('hari')} | {jam} | {row.get('mata_kuliah')} | {row.get('ruangan') or '-'} | {semester} |"
        )
    return "\n".join(lines).strip()


def _invoke_polisher_llm(prompt: str) -> str:
    runtime_cfg = get_runtime_openrouter_config()
    api_key = _normalize_text(runtime_cfg.get("api_key"))
    if not api_key:
        return ""
    runtime_cfg = dict(runtime_cfg)
    runtime_cfg["temperature"] = float(os.environ.get("RAG_ANALYTICS_POLISH_TEMPERATURE", "0") or 0)
    runtime_cfg["model"] = _normalize_text(
        os.environ.get("RAG_ANALYTICS_POLISH_MODEL", "google/gemini-3-flash-preview")
    ) or _normalize_text(runtime_cfg.get("model"))
    backup_models = get_backup_models(
        _normalize_text(runtime_cfg.get("model")),
        runtime_cfg.get("backup_models"),
    )
    for model_name in backup_models:
        try:
            llm = build_llm(model_name, runtime_cfg)
            out = invoke_text(llm, prompt).strip()
            if out:
                return out
        except Exception:
            continue
    return ""


def _validate_polished_answer(polished: str, facts: List[Dict[str, Any]]) -> bool:
    text = _normalize_text(polished)
    if not facts:
        return "data tidak ditemukan di dokumen anda" in text.lower()

    course_names = list(dict.fromkeys([_normalize_text(x.get("mata_kuliah")) for x in facts if _normalize_text(x.get("mata_kuliah"))]))
    if not course_names:
        return False

    lowered = text.lower()
    for name in course_names:
        if name.lower() not in lowered:
            return False

    table_lines = [ln for ln in text.splitlines() if ln.strip().startswith("|")]
    if len(table_lines) >= 3:
        data_rows = max(0, len(table_lines) - 2)
        if data_rows != len(facts):
            return False
    return True


def polish_structured_answer(
    *,
    query: str,
    deterministic_answer: str,
    facts: List[Dict[str, Any]],
    doc_type: str,
) -> Dict[str, Any]:
    if not _env_bool("RAG_ANALYTICS_POLISH_ENABLED", default=True):
        return {"answer": deterministic_answer, "validation": "skipped"}

    facts_payload = str(facts[: min(len(facts), 500)])
    prompt = (
        "Anda adalah Asisten Akademik.\n"
        "Data JSON di bawah ini adalah FAKTA MUTLAK dari sistem database terstruktur.\n"
        "Tugas Anda HANYA menyusun data ini menjadi kalimat yang ramah untuk pengguna.\n"
        "DILARANG KERAS menambah, mengurangi, atau mengubah nama mata kuliah/nilai/jam.\n"
        "Jika data JSON kosong, katakan: 'Maaf, data tidak ditemukan di dokumen Anda'.\n"
        "Pertahankan format markdown dengan tabel.\n\n"
        f"Jenis data: {doc_type}\n"
        f"Pertanyaan user: {query}\n"
        f"Data JSON: {facts_payload}\n\n"
        f"Draf jawaban deterministik:\n{deterministic_answer}\n"
    )
    polished = _invoke_polisher_llm(prompt)
    if not polished:
        return {"answer": deterministic_answer, "validation": "failed_fallback"}
    if _env_bool("RAG_ANALYTICS_POST_VALIDATE_ENABLED", default=True):
        if not _validate_polished_answer(polished, facts):
            return {"answer": deterministic_answer, "validation": "failed_fallback"}
    return {"answer": polished, "validation": "passed"}


def run_structured_analytics(user_id: int, query: str, doc_ids: List[int] | None = None) -> Dict[str, Any]:
    started = time.time()
    ql = str(query or "").lower()
    is_schedule = any(k in ql for k in ["jadwal", "krs", "hari"])
    is_low_grade = _is_low_grade_query(query)
    is_course_recap = _is_course_recap_query(query)
    doc_type = "schedule" if is_schedule else "transcript"
    rows_raw = _fetch_row_chunks(user_id=user_id, doc_type=doc_type, doc_ids=doc_ids)
    fallback_schedule_rows_raw: List[Tuple[str, Dict[str, Any]]] = []
    # Query recap mata kuliah sering datang tanpa kata "jadwal", padahal user hanya upload KRS/Jadwal.
    # Agar tetap terjawab dari dokumen, lakukan fallback transcript -> schedule.
    if doc_type == "transcript" and (not rows_raw) and (not is_low_grade) and is_course_recap:
        fallback_schedule_rows_raw = _fetch_row_chunks(user_id=user_id, doc_type="schedule", doc_ids=doc_ids)
        if fallback_schedule_rows_raw:
            doc_type = "schedule"
            rows_raw = fallback_schedule_rows_raw

    if not rows_raw:
        empty_answer = (
            "## Ringkasan\n"
            "Maaf, data tidak ditemukan di dokumen Anda.\n\n"
            "## Opsi Lanjut\n"
            "- Pastikan dokumen akademik sudah terunggah.\n"
            "- Jika sudah upload, coba sebutkan detail semester/hari."
        )
        return {
            "ok": False,
            "answer": empty_answer,
            "sources": [],
            "doc_type": doc_type,
            "facts": [],
            "stats": {"raw": 0, "deduped": 0, "returned": 0, "latency_ms": int((time.time() - started) * 1000)},
            "reason": "no_row_chunks",
        }

    if doc_type == "transcript":
        normalized = [_normalize_transcript_from_chunk(chunk, meta) for chunk, meta in rows_raw]
        rows = [x for x in normalized if isinstance(x, dict)]
        deduped = _dedupe_transcript_latest(rows)
        filtered = list(deduped)
        ql_local = str(query or "").lower()
        full_recap_requested = any(k in ql_local for k in ["rekap", "ringkas", "rangkum", "semua", "daftar"])
        semester_filter = _extract_semester_filter(query)
        if semester_filter is not None:
            filtered = [x for x in filtered if int(x.get("semester") or 0) == int(semester_filter)]
        if _is_low_grade_query(query):
            low_grade_set = {
                _normalize_text(x).upper()
                for x in str(os.environ.get("RAG_ANALYTICS_LOW_GRADES", "C,D,E,CD,D+,D-")).split(",")
                if _normalize_text(x)
            }
            filtered = [x for x in filtered if _normalize_text(x.get("nilai_huruf")).upper() in low_grade_set]
        course_term = _extract_course_query_term(query)
        if course_term and not full_recap_requested:
            term_lc = course_term.lower()
            filtered_by_course = [
                x for x in filtered if term_lc in _normalize_text(x.get("mata_kuliah")).lower()
            ]
            if filtered_by_course:
                filtered = filtered_by_course
        profile = _extract_transcript_profile(_fetch_transcript_text_chunks(user_id=user_id, doc_ids=doc_ids))
        answer = _render_transcript_answer(filtered, query=query, profile=profile)
        facts = filtered
        sources = _render_sources(filtered if filtered else deduped)
        return {
            "ok": True,
            "answer": answer,
            "sources": sources,
            "doc_type": doc_type,
            "facts": facts,
            "stats": {
                "raw": len(rows),
                "deduped": len(deduped),
                "returned": len(filtered),
                "latency_ms": int((time.time() - started) * 1000),
            },
            "reason": "structured_transcript",
        }

    normalized_schedule = [_normalize_schedule_from_chunk(chunk, meta) for chunk, meta in rows_raw]
    schedule_rows = [x for x in normalized_schedule if isinstance(x, dict)]
    day_filter = _extract_day_filter(query)
    filtered_schedule = list(schedule_rows)
    if day_filter:
        filtered_schedule = [x for x in schedule_rows if _normalize_text(x.get("hari")).lower() == day_filter.lower()]
    filtered_schedule.sort(key=lambda x: (_normalize_text(x.get("hari")), _normalize_text(x.get("jam_mulai")), _normalize_text(x.get("mata_kuliah"))))
    answer = _render_schedule_answer(filtered_schedule, day_filter=day_filter)
    sources = _render_sources(filtered_schedule if filtered_schedule else schedule_rows)
    return {
        "ok": True,
        "answer": answer,
        "sources": sources,
        "doc_type": doc_type,
        "facts": filtered_schedule,
        "stats": {
            "raw": len(schedule_rows),
            "deduped": len(schedule_rows),
            "returned": len(filtered_schedule),
            "latency_ms": int((time.time() - started) * 1000),
        },
        "reason": "structured_schedule",
    }
