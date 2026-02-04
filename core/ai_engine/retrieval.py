# core/ai_engine/retrieval.py

import os
import re
import time
import logging
import json
from typing import Any, Dict, List, Optional, Tuple

from langchain_openai import ChatOpenAI
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate

from .config import get_vectorstore

logger = logging.getLogger(__name__)

# =========================
# Models (sanitized)
# =========================
PRIMARY_MODEL = os.environ.get(
    "OPENROUTER_MODEL",
    "qwen/qwen3-next-80b-a3b-instruct:free"
)

BACKUP_MODELS_RAW = [
    PRIMARY_MODEL,
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "arcee-ai/trinity-large-preview:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "arcee-ai/trinity-large-preview:free",
    "meta-llama/llama-3.3-70b-instruct:free",
]
BACKUP_MODELS = [m.strip() for m in BACKUP_MODELS_RAW if isinstance(m, str) and m.strip()]

REQUEST_TIMEOUT_SEC = int(os.environ.get("OPENROUTER_TIMEOUT", "45"))
MAX_RETRIES = int(os.environ.get("OPENROUTER_MAX_RETRIES", "1"))
TEMPERATURE = float(os.environ.get("OPENROUTER_TEMPERATURE", "0.2"))
RAG_MAX_DISTANCE = float(os.environ.get("RAG_MAX_DISTANCE", "0.45"))  # lower is better (Chroma distance)

# =========================
# Small-talk / intent gate
# =========================
_SMALLTALK_EXACT = {
    "hi", "halo", "hai", "hello", "hey", "p",
    "assalamualaikum", "waalaikumsalam",
    "selamat pagi", "selamat siang", "selamat sore", "selamat malam",
    "makasih", "terima kasih", "thanks", "thx",
    "ok", "oke", "sip", "mantap",
}
_SMALLTALK_CONTAINS = [
    "apa kabar", "how are you", "lagi apa", "siapa kamu", "kamu siapa",
]
_SEMESTER_RE = re.compile(r"\bsemester\s*(\d+)\b", re.IGNORECASE)
_TOPIC_KEYWORDS = {
    "ai": ["ai", "artificial intelligence", "kecerdasan buatan", "machine learning", "deep learning", "pembelajaran mendalam", "computer vision", "pengolahan citra", "nlp", "pemrosesan bahasa alami", "data mining"],
    "web": ["web", "pemrograman web", "fullstack", "frontend", "backend"],
    "mobile": ["mobile", "android", "ios", "pemrograman mobile"],
    "data": ["data", "sains data", "data science", "basis data", "database", "big data"],
    "jaringan": ["jaringan", "network", "komunikasi data", "sistem operasi"],
}


def _is_smalltalk(q: str) -> bool:
    ql = (q or "").strip().lower()
    if not ql:
        return True
    if ql in _SMALLTALK_EXACT:
        return True
    if any(p in ql for p in _SMALLTALK_CONTAINS):
        return True
    if len(ql.split()) <= 2 and any(w in ql for w in ["hi", "halo", "hai", "hello", "hey"]):
        return True
    return False


def _smalltalk_reply() -> str:
    return (
        "Halo! \n\n"
        "Aku bisa bantu baca dokumen akademik kamu (KRS/jadwal/transkrip).\n"
        "Contoh pertanyaan:\n"
        "- *jam berapa saja saya kuliah dalam 1 minggu?*\n"
        "- *rekap jadwal per hari*\n"
        "- *hitung total SKS*\n"
        "- *nilai terendah saya apa?* (kalau data nilai ada)\n"
    )


# =========================
# Intent & query detectors
# =========================
def _is_academic_question(q: str) -> bool:
    """
    Perluas agar pertanyaan jadwal/hari/jam tidak ditolak.
    """
    ql = (q or "").lower()
    keywords = [
        # nilai / transkrip
        "nilai", "grade", "bobot", "ipk", "ips", "transkrip", "khs",
        # krs / matkul
        "krs", "kartu rencana studi", "mata kuliah", "matakuliah", "mk", "sks",
        "semester", "rekap", "urut", "tertinggi", "terendah", "lulus",
        #  jadwal
        "jadwal", "jam", "hari", "waktu", "kuliah", "kelas", "ruang", "dosen",
        "senin", "selasa", "rabu", "kamis", "jumat", "jum'at", "sabtu", "minggu",
    ]
    return any(k in ql for k in keywords)


def _wants_grade(q: str) -> bool:
    ql = (q or "").lower()
    keys = ["nilai", "grade", "bobot", "mutu", "ipk", "ips", "nilai huruf", "nilai angka"]
    return any(k in ql for k in keys)


def _wants_schedule(q: str) -> bool:
    ql = (q or "").lower()
    keys = ["jadwal", "jam", "hari", "waktu", "kuliah", "kelas", "ruang", "dosen", "per hari", "minggu"]
    return any(k in ql for k in keys)


def _wants_semester(q: str) -> bool:
    ql = (q or "").lower()
    return "semester" in ql


def _wants_krs_reco(q: str) -> bool:
    ql = (q or "").lower()
    keys = ["rekomendasi", "sarankan", "pilih", "ambil", "krs"]
    # only treat as KRS recommendation if query is about KRS/jadwal/SKS
    krs_signals = ["krs", "jadwal", "sks", "mata kuliah", "matakuliah", "mk"]
    return any(k in ql for k in keys) and any(s in ql for s in krs_signals)


def _wants_thesis_title(q: str) -> bool:
    ql = (q or "").lower()
    return any(k in ql for k in ["skripsi", "judul skripsi", "judul", "topik penelitian"])


def _wants_thesis_followup(q: str) -> Optional[str]:
    ql = (q or "").lower()
    if "minat" in ql or ql.strip().startswith(("ai", "web", "mobile", "data", "jaringan")):
        for key, kws in _TOPIC_KEYWORDS.items():
            if any(k in ql for k in kws):
                return key
    return None


def _extract_course_titles(docs) -> List[str]:
    rows = _extract_schedule_rows_from_docs(docs)
    titles = []
    for r in rows:
        mk = str(r.get("mata_kuliah", "")).strip()
        if mk:
            titles.append(mk)
    return titles


def _suggest_thesis_titles(topic_key: str, course_titles: List[str]) -> List[str]:
    # heuristic: pick courses related to topic and build thesis ideas
    rel = []
    kws = _TOPIC_KEYWORDS.get(topic_key, [])
    for t in course_titles:
        tl = t.lower()
        if any(k in tl for k in kws):
            rel.append(t)
    rel = list(dict.fromkeys(rel))[:5]
    if topic_key == "ai":
        base = [
            "Klasifikasi teks akademik menggunakan Transformer",
            "Deteksi plagiarisme dokumen PDF berbasis embedding",
            "Rekomendasi KRS menggunakan model pembelajaran mesin",
            "Ekstraksi jadwal kuliah dari PDF dengan OCR dan NLP",
            "Chatbot akademik berbasis RAG untuk konsultasi KRS",
        ]
    elif topic_key == "web":
        base = [
            "Portal akademik berbasis web dengan analitik perilaku pengguna",
            "Dashboard rekomendasi KRS berbasis data historis",
            "Sistem manajemen dokumen akademik dengan pencarian semantik",
        ]
    elif topic_key == "mobile":
        base = [
            "Aplikasi mobile asisten akademik dengan notifikasi jadwal",
            "OCR dokumen akademik di perangkat mobile",
        ]
    elif topic_key == "data":
        base = [
            "Analisis pola pengambilan mata kuliah berbasis data historis",
            "Prediksi kelulusan mata kuliah menggunakan data akademik",
        ]
    elif topic_key == "general":
        base = [
            "Sistem rekomendasi KRS berbasis preferensi mahasiswa",
            "Analisis pola pengambilan mata kuliah dan dampaknya terhadap IPK",
            "Optimasi jadwal kuliah untuk meminimalkan konflik",
            "Pencarian semantik dokumen akademik berbasis embedding",
            "Analisis keterkaitan mata kuliah dan kompetensi lulusan",
        ]
    else:
        base = [
            "Optimasi jadwal kuliah untuk meminimalkan konflik",
            "Sistem rekomendasi KRS berbasis preferensi mahasiswa",
        ]
    # enrich with course names if any
    if rel:
        base = [f"{b} (terkait: {', '.join(rel[:2])})" for b in base[:4]] + base[4:]
    return base[:6]


def _infer_doc_type(q: str) -> Optional[str]:
    ql = (q or "").lower()
    if any(k in ql for k in ["jadwal", "jam", "hari", "ruang", "kelas"]):
        return "schedule"
    if any(k in ql for k in ["transkrip", "nilai", "grade", "bobot", "ipk", "ips"]):
        return "transcript"
    if "krs" in ql:
        return "schedule"
    return None


# =========================
# Helpers: sources & llm
# =========================
def _build_sources_from_docs(docs, max_sources: int = 8, snippet_len: int = 220):
    if not docs:
        return []
    seen = set()
    sources = []
    for d in docs:
        meta = getattr(d, "metadata", {}) or {}
        src = meta.get("source") or "unknown"
        if src in seen:
            continue
        seen.add(src)

        snippet = (getattr(d, "page_content", "") or "").strip().replace("\n", " ")
        if len(snippet) > snippet_len:
            snippet = snippet[:snippet_len] + "..."

        sources.append({"source": src, "snippet": snippet})
        if len(sources) >= max_sources:
            break
    return sources


def _invoke_text(llm: ChatOpenAI, prompt: str) -> str:
    out = llm.invoke(prompt)
    if hasattr(out, "content"):
        return out.content or ""
    return str(out)


# =========================
# Allowed columns (anti-halu) - UPDATED
# =========================
def _count_letter_grades(text: str) -> int:
    if not text:
        return 0
    pattern = re.compile(r"\b([A-E])([+-])?\b", re.IGNORECASE)
    return len(pattern.findall(text))


def _detect_allowed_columns(docs) -> List[str]:
    """
    Izinkan kolom adaptif berdasarkan bukti:
    - metadata["columns"] (CSV/Excel/PDF baru)
    - keyword di page_content
    """
    allowed = ["Kode", "Mata Kuliah"]

    blob = " ".join([(getattr(d, "page_content", "") or "") for d in (docs or [])]).lower()

    meta_cols: List[str] = []
    for d in docs or []:
        meta = getattr(d, "metadata", {}) or {}
        cols = meta.get("columns")
        if isinstance(cols, list):
            for c in cols:
                cs = str(c).strip()
                if cs:
                    meta_cols.append(cs)
        elif isinstance(cols, str):
            # columns disimpan sebagai JSON string dari ingest
            try:
                parsed = json.loads(cols)
                if isinstance(parsed, list):
                    for c in parsed:
                        cs = str(c).strip()
                        if cs:
                            meta_cols.append(cs)
            except Exception:
                pass

    meta_cols_l = [c.lower() for c in meta_cols]

    def has_col(name: str, keywords: List[str]) -> bool:
        nl = name.lower()
        if nl in meta_cols_l:
            return True
        return any(k in blob for k in keywords)

    # ---- Jadwal ----
    if has_col("Hari", ["hari", "day", "senin", "selasa", "rabu", "kamis", "jum", "sabtu"]):
        allowed.append("Hari")

    # jam/time: cari pola 07:30 atau kata jam/waktu
    if has_col("Jam", [" jam ", "waktu", "time"]) or re.search(r"\b\d{1,2}[:.]\d{2}\b", blob):
        allowed.append("Jam")

    if has_col("Dosen Pengampu", ["dosen", "pengampu", "lecturer"]):
        allowed.append("Dosen Pengampu")

    # kampus beda-beda: ada yang pakai Kelas/Ruang/Lab
    if has_col("Kelas", ["kelas", "class", "ruang", "room", "lab"]):
        allowed.append("Kelas")

    if has_col("Ruang", ["ruang", "room", "lab"]):
        allowed.append("Ruang")

    # ---- Nilai / Transkrip ----
    grade_count = _count_letter_grades(blob)
    grade_keywords_hit = any(k in blob for k in ["grade", "nilai", "nilai huruf", "mutu"])
    has_nilai_header_like = any(k in blob for k in ["\nnilai\n", " nilai ", "nilai:", "nilai\t", "nilai |"])

    if has_col("Grade", ["grade", "nilai huruf", "mutu"]) or (
        (grade_keywords_hit or has_nilai_header_like) and grade_count >= 3
    ):
        allowed.append("Grade")

    if has_col("Bobot", ["bobot", "nilai angka", "angka mutu", "mutu", "skor"]):
        allowed.append("Bobot")

    if has_col("SKS", ["sks", "credit"]):
        allowed.append("SKS")

    # cek dari metadata semester
    has_sem_meta = any(
        isinstance((getattr(d, "metadata", {}) or {}).get("semester"), (int, str))
        for d in (docs or [])
    )
    if has_col("Semester", ["semester", "smt", "sem."]) or has_sem_meta:
        allowed.append("Semester")

    # unik & urut
    out: List[str] = []
    seen = set()
    for a in allowed:
        al = a.lower()
        if al in seen:
            continue
        seen.add(al)
        out.append(a)

    return out


# =========================
# Schedule rows (data-first answering)
# =========================
_TIME_RANGE_RE = re.compile(r"(\d{1,2}[:.]\d{2})\s*[-–]\s*(\d{1,2}[:.]\d{2})")


def _extract_schedule_rows_from_docs(docs) -> List[Dict[str, Any]]:
    """
    Ambil schedule_rows dari metadata docs (hasil ingest.py baru).
    Dedup + flatten.
    """
    rows: List[Dict[str, Any]] = []
    seen = set()

    for d in docs or []:
        meta = getattr(d, "metadata", {}) or {}
        sr = meta.get("schedule_rows")
        if isinstance(sr, str):
            try:
                sr = json.loads(sr)
            except Exception:
                sr = None
        if not isinstance(sr, list):
            continue

        for item in sr:
            if not isinstance(item, dict):
                continue
            key = (
                str(item.get("hari", "")),
                str(item.get("jam", "")),
                str(item.get("kode", "")),
                str(item.get("mata_kuliah", "")),
                str(item.get("kelas", "")),
                str(item.get("ruang", "")),
            )
            if key in seen:
                continue
            seen.add(key)
            rows.append(item)

    return rows


def _extract_semesters_from_docs(docs) -> List[str]:
    sems = set()
    for d in docs or []:
        meta = getattr(d, "metadata", {}) or {}
        sem = meta.get("semester")
        if isinstance(sem, (int, float, str)):
            s = str(sem).strip()
            if s:
                sems.add(s)
        src = meta.get("source") or ""
        m = _SEMESTER_RE.search(str(src))
        if m:
            sems.add(m.group(1))
    return sorted(sems, key=lambda x: int(x) if str(x).isdigit() else x)


def _parse_time_range(jam: str) -> Optional[Tuple[int, int]]:
    if not jam:
        return None
    m = _TIME_RANGE_RE.search(str(jam).replace("–", "-"))
    if not m:
        return None
    t1 = m.group(1).replace(".", ":")
    t2 = m.group(2).replace(".", ":")
    try:
        h1, m1 = [int(x) for x in t1.split(":")]
        h2, m2 = [int(x) for x in t2.split(":")]
        return (h1 * 60 + m1, h2 * 60 + m2)
    except Exception:
        return None


def _detect_conflicts(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    conflicts = []
    by_day: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        day = (r.get("hari") or "Unknown").strip()
        by_day.setdefault(day, []).append(r)
    for day, items in by_day.items():
        items = [i for i in items if _parse_time_range(str(i.get("jam", "")))]
        items.sort(key=lambda x: _parse_time_range(str(x.get("jam", "")))[0])  # type: ignore
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a = items[i]
                b = items[j]
                ta = _parse_time_range(str(a.get("jam", "")))
                tb = _parse_time_range(str(b.get("jam", "")))
                if not ta or not tb:
                    continue
                # overlap
                if ta[1] > tb[0] and tb[1] > ta[0]:
                    conflicts.append({
                        "hari": day,
                        "a": a,
                        "b": b,
                    })
    return conflicts


def _sum_sks(rows: List[Dict[str, Any]]) -> int:
    total = 0
    for r in rows:
        v = str(r.get("sks", "")).strip()
        if not v:
            continue
        try:
            total += int(float(v))
        except Exception:
            continue
    return total


def _group_schedule(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group by hari. Sort by time_start if possible.
    """
    by_day: Dict[str, List[Dict[str, Any]]] = {}

    def time_key(jam: str) -> Tuple[int, int]:
        jam = (jam or "").replace("–", "-")
        m = _TIME_RANGE_RE.search(jam)
        if not m:
            return (99, 99)
        t = m.group(1).replace(".", ":")
        hh, mm = t.split(":")
        return (int(hh), int(mm))

    for r in rows:
        day = (r.get("hari") or "").strip() or "Unknown"
        by_day.setdefault(day, []).append(r)

    for day, items in by_day.items():
        items.sort(key=lambda x: time_key(str(x.get("jam", ""))))

    return by_day


def _render_schedule_table(rows: List[Dict[str, Any]], allowed_cols: List[str]) -> str:
    """
    Render tabel Markdown berdasarkan allowed_cols, tapi khusus jadwal
    kita prefer kolom yang relevan.
    """
    # prioritas kolom jadwal
    preferred = ["Hari", "Jam", "Kode", "Mata Kuliah", "SKS", "Dosen Pengampu", "Kelas", "Ruang"]
    chosen = [c for c in preferred if c in allowed_cols or c in ["Hari", "Jam", "Kode", "Mata Kuliah"]]

    # minimal
    if "Hari" not in chosen:
        chosen.insert(0, "Hari")
    if "Jam" not in chosen:
        chosen.insert(1, "Jam")
    if "Kode" not in chosen:
        chosen.append("Kode")
    if "Mata Kuliah" not in chosen:
        chosen.append("Mata Kuliah")

    header = "| " + " | ".join(chosen) + " |"
    sep = "| " + " | ".join(["---"] * len(chosen)) + " |"

    def get_cell(r: Dict[str, Any], col: str) -> str:
        col_l = col.lower()
        if col_l == "hari":
            return str(r.get("hari", "") or "")
        if col_l == "jam":
            return str(r.get("jam", "") or "")
        if col_l == "kode":
            return str(r.get("kode", "") or "")
        if col_l == "mata kuliah":
            return str(r.get("mata_kuliah", "") or "")
        if col_l == "sks":
            return str(r.get("sks", "") or "")
        if col_l == "dosen pengampu":
            return str(r.get("dosen", "") or "")
        if col_l == "kelas":
            return str(r.get("kelas", "") or "")
        if col_l == "ruang":
            return str(r.get("ruang", "") or "")
        return ""

    lines = [header, sep]
    for r in rows:
        lines.append("| " + " | ".join([get_cell(r, c).replace("\n", " ").strip() for c in chosen]) + " |")

    return "\n".join(lines)


def _schedule_answer_data_first(q: str, rows: List[Dict[str, Any]], sources: List[Dict[str, Any]], allowed_cols: List[str]) -> Dict[str, Any]:
    """
    Jawab pertanyaan jadwal berbasis rows terstruktur (lebih akurat).
    Tidak perlu LLM untuk menghasilkan data.
    """
    by_day = _group_schedule(rows)

    # Ringkasan jam per hari
    lines = []
    for day, items in by_day.items():
        jams = [str(it.get("jam", "")).strip() for it in items if str(it.get("jam", "")).strip()]
        # dedup jam
        seen = set()
        jams_u = []
        for j in jams:
            if j in seen:
                continue
            seen.add(j)
            jams_u.append(j)
        if jams_u:
            lines.append(f"- **{day}**: " + ", ".join(jams_u))

    table_md = _render_schedule_table(rows, allowed_cols)

    answer = (
        "## Ringkasan\n"
        "Berikut rekap jadwal kuliah kamu dari dokumen yang terunggah.\n\n"
        "## Tabel\n"
        f"{table_md}\n\n"
        "## Insight Singkat\n"
        + ("\n".join(lines) if lines else "- Jadwal berhasil diambil dari tabel dokumen.\n")
        + "\n\n"
        "## Pertanyaan Lanjutan\n"
        "Kamu mau aku rekap berdasarkan apa?\n"
        "- per hari (lebih ringkas)\n"
        "- mata kuliah paling pagi / paling sore\n"
        "- total jam kuliah per minggu\n\n"
        "## Opsi Cepat\n"
        "- [Rekap jadwal per hari]\n"
        "- [Hitung total jam kuliah per minggu]\n"
    )

    return {"answer": answer, "sources": sources}


# =========================
# Output contract validators
# =========================
_REQUIRED_HEADINGS = [
    "## Ringkasan",
    "## Tabel",
    "## Insight Singkat",
    "## Pertanyaan Lanjutan",
    "## Opsi Cepat",
]


def _missing_headings(md: str) -> List[str]:
    md = md or ""
    return [h for h in _REQUIRED_HEADINGS if h not in md]


def _extract_table_headers(md: str) -> List[List[str]]:
    if not md:
        return []
    lines = [l.strip() for l in md.splitlines()]
    headers = []
    for i in range(len(lines) - 1):
        if lines[i].startswith("|") and ("|" in lines[i]) and set(lines[i + 1].replace("|", "").strip()) <= set("-: "):
            cols = [c.strip() for c in lines[i].strip("|").split("|")]
            cols = [c for c in cols if c]
            if cols:
                headers.append(cols)
    return headers


def _find_illegal_columns(md: str, allowed_cols: List[str]) -> List[str]:
    allowed_l = {str(c).strip().lower() for c in (allowed_cols or []) if str(c).strip()}
    illegal = set()
    for header in _extract_table_headers(md):
        for c in header:
            if c.strip().lower() not in allowed_l:
                illegal.add(c.strip())
    return sorted(illegal)


def _grade_intent_addressed(md: str, allowed_cols: List[str]) -> bool:
    a = (md or "").lower()
    if ("data nilai" in a) and ("tidak" in a or "belum" in a or "tidak ada" in a):
        return True
    allowed_l = {c.lower() for c in (allowed_cols or [])}
    if "grade" in allowed_l and "| grade |" in a:
        return True
    if "bobot" in allowed_l and "| bobot |" in a:
        return True
    if re.search(r"\|\s*(grade|bobot)\s*\|", a):
        return True
    return False


def _repair_answer(llm: ChatOpenAI, answer: str, allowed_cols_str: str, issues: List[str]) -> str:
    repair_prompt = f"""
Perbaiki jawaban agar mengikuti KONTRAK OUTPUT MARKDOWN dan SKEMA.

ALLOWED_COLUMNS: {allowed_cols_str}

Masalah yang harus diperbaiki:
{chr(10).join(['- ' + x for x in issues])}

Aturan:
- Jangan menambah data baru.
- Jangan mengarang kolom di luar ALLOWED_COLUMNS.
- Pastikan heading wajib ada (persis):
  ## Ringkasan
  ## Tabel
  ## Insight Singkat
  ## Pertanyaan Lanjutan
  ## Opsi Cepat
- Jika pertanyaan user meminta nilai tapi Grade/Bobot tidak ada di ALLOWED_COLUMNS:
  tulis jelas "data nilai tidak ditemukan" dan jangan buat tabel seolah rekap nilai.

Jawaban lama:
{answer}

Tulis ulang jawaban (Markdown) yang sudah diperbaiki:
"""
    fixed = _invoke_text(llm, repair_prompt).strip()
    return fixed or answer


def _has_interactive_sections(answer: str) -> bool:
    a = (answer or "").lower()
    return ("insight singkat" in a) and (("pertanyaan lanjutan" in a) or ("opsi cepat" in a))


def _looks_like_markdown_table(answer: str) -> bool:
    a = (answer or "")
    return ("|" in a) and ("---" in a)


def _llm_general_answer(q: str, request_id: str = "-") -> Dict[str, Any]:
    # Deprecated in LLM-first mode; kept for compatibility.
    return {"answer": q, "sources": []}


# =========================
# Main
# =========================
def ask_bot(user_id, query, request_id: str = "-") -> Dict[str, Any]:
    if not os.environ.get("OPENROUTER_API_KEY"):
        return {
            "answer": "OPENROUTER_API_KEY belum di-set. Cek file .env / environment variables.",
            "sources": [],
        }

    q = (query or "").strip()

    # LLM-first: no smalltalk or hardcoded routing; always go to LLM with context if any.

    t0 = time.time()
    k = 20
    query_preview = q if len(q) <= 140 else q[:140] + "..."

    logger.info(
        " RAG start user_id=%s k=%s q='%s'",
        user_id, k, query_preview,
        extra={"request_id": request_id},
    )

    vectorstore = get_vectorstore()
    base_filter = {"user_id": str(user_id)}
    sem_match = _SEMESTER_RE.search(q)
    if sem_match:
        try:
            base_filter["semester"] = int(sem_match.group(1))
        except Exception:
            pass
    doc_type = _infer_doc_type(q)
    if doc_type:
        base_filter["doc_type"] = doc_type

    # Chroma expects a single operator in where; use $and when multiple filters
    chroma_where = base_filter
    if len(base_filter) > 1:
        chroma_where = {"$and": [{"user_id": str(user_id)}] + [
            {k: v} for k, v in base_filter.items() if k != "user_id"
        ]}

    # Use similarity_search_with_score to enable quality threshold
    docs_with_scores = vectorstore.similarity_search_with_score(q, k=k, filter=chroma_where)
    docs = [d for d, _ in docs_with_scores] if docs_with_scores else []
    scores = [s for _, s in docs_with_scores] if docs_with_scores else []

    # fallback: jika terlalu ketat, retry tanpa filter tambahan
    if not docs and (len(base_filter) > 1):
        docs_with_scores = vectorstore.similarity_search_with_score(q, k=k, filter={"user_id": str(user_id)})
        docs = [d for d, _ in docs_with_scores] if docs_with_scores else []
        scores = [s for _, s in docs_with_scores] if docs_with_scores else []

    # allow LLM even when docs are empty / low-quality; context may be empty

    sources = _build_sources_from_docs(docs)
    allowed_cols = _detect_allowed_columns(docs)
    allowed_cols_str = ", ".join(allowed_cols)

    # LLM-first: skip all data-first routes and guards

    # =========================
    # LLM RAG (default)
    # =========================
    template = """
Anda adalah asisten akademik yang menjawab pertanyaan pengguna dengan bantuan konteks dokumen jika tersedia.

Aturan:
- Selalu jawab pertanyaan user.
- Jika KONTEKS kosong, gunakan pengetahuan umum dan jelaskan bahwa dokumen pengguna tidak menyediakan data spesifik.
- Jika KONTEKS tersedia, gunakan itu sebagai rujukan utama.
- Format wajib:
  ## Ringkasan
  ## Tabel
  ## Insight Singkat
  ## Pertanyaan Lanjutan
  ## Opsi Cepat
- Jika tabel tidak diperlukan, isi dengan _Tidak ada data khusus dari dokumen pengguna._

KONTEKS:
{context}

PERTANYAAN:
{input}

JAWABAN (Markdown):
"""
    PROMPT = ChatPromptTemplate.from_template(template)

    last_error = ""
    for idx, model_name in enumerate(BACKUP_MODELS):
        model_t0 = time.time()
        try:
            logger.info(
                " LLM try idx=%s model=%s timeout=%ss max_retries=%s",
                idx, model_name, REQUEST_TIMEOUT_SEC, MAX_RETRIES,
                extra={"request_id": request_id},
            )

            llm = ChatOpenAI(
                openai_api_key=os.environ.get("OPENROUTER_API_KEY"),
                openai_api_base="https://openrouter.ai/api/v1",
                model_name=model_name,
                temperature=TEMPERATURE,
                request_timeout=REQUEST_TIMEOUT_SEC,
                max_retries=MAX_RETRIES,
                default_headers={
                    "HTTP-Referer": "http://localhost:8000",
                    "X-Title": "AcademicChatbot",
                },
            )

            qa_chain = create_stuff_documents_chain(llm, PROMPT)
            result = qa_chain.invoke({"input": q, "context": docs})

            if isinstance(result, dict):
                answer = result.get("answer") or result.get("output_text") or ""
            else:
                answer = str(result)
            answer = (answer or "").strip() or "Maaf, tidak ada jawaban."

            # Pastikan ada lapisan interaktif
            if _looks_like_markdown_table(answer) and (not _has_interactive_sections(answer)):
                enrich_prompt = f"""
Tambahkan lapisan interaktif TANPA mengubah isi tabel & tanpa menambah data baru.

Aturan:
- Pertahankan tabel apa adanya.
- Pastikan ada heading wajib (persis):
  ## Ringkasan
  ## Tabel
  ## Insight Singkat
  ## Pertanyaan Lanjutan
  ## Opsi Cepat
- Tambahkan Insight Singkat (2-4 bullet)
- Tambahkan Pertanyaan Lanjutan
- Tambahkan Opsi Cepat (2 opsi)

JAWABAN:
{answer}
"""
                enriched = _invoke_text(llm, enrich_prompt).strip()
                if enriched:
                    answer = enriched

            model_dur = round(time.time() - model_t0, 2)
            total_dur = round(time.time() - t0, 2)

            logger.info(
                " LLM ok idx=%s model=%s model_time=%ss total_time=%ss answer_len=%s sources=%s allowed_cols=%s",
                idx, model_name, model_dur, total_dur, len(answer), len(sources), len(allowed_cols),
                extra={"request_id": request_id},
            )

            if idx > 0:
                logger.warning(
                    " Fallback used idx=%s model=%s",
                    idx, model_name,
                    extra={"request_id": request_id},
                )

            return {"answer": answer, "sources": sources}

        except Exception as e:
            model_dur = round(time.time() - model_t0, 2)
            last_error = str(e)
            err_preview = last_error if len(last_error) <= 200 else last_error[:200] + "..."

            logger.warning(
                " LLM fail idx=%s model=%s dur=%ss err=%s",
                idx, model_name, model_dur, err_preview,
                extra={"request_id": request_id},
            )

            if idx < len(BACKUP_MODELS) - 1:
                time.sleep(0.8)
                continue

            logger.error(
                " All models failed last_err=%s",
                err_preview,
                extra={"request_id": request_id},
                exc_info=True,
            )

    total_dur = round(time.time() - t0, 2)
    return {"answer": f"Maaf, semua server AI sedang sibuk. (dur={total_dur}s, Error: {last_error})", "sources": []}
