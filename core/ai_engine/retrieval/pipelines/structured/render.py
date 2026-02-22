from __future__ import annotations

import re
from typing import Any, Dict, List

def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


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


def render_transcript_answer(rows: List[Dict[str, Any]], query: str, profile: Dict[str, Any] | None = None) -> str:
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
        lines = [
            "## Ringkasan Nilai Rendah",
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
        lines.append(f"| {idx} | {mk} | {row.get('sks')} | {nilai} |")
    return "\n".join(lines).strip()


def render_schedule_answer(rows: List[Dict[str, Any]], day_filter: str) -> str:
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


def render_sources(rows: List[Dict[str, Any]], max_sources: int = 8) -> List[Dict[str, Any]]:
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


def extract_transcript_profile(text_chunks: List[str]) -> Dict[str, Any]:
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
