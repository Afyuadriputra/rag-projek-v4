# core/ai_engine/ingest.py

import re
import pdfplumber
import pandas as pd
import logging
import json
from typing import Any, Dict, List, Optional, Tuple

from langchain_text_splitters import RecursiveCharacterTextSplitter
from .config import get_vectorstore

logger = logging.getLogger(__name__)

# =========================
# Constants / Regex
# =========================
_DAY_WORDS = {
    "senin", "selasa", "rabu", "kamis", "jumat", "jum'at", "sabtu", "minggu",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
}

# jam range: 07:30-10:00 (menerima . juga)
_TIME_RANGE_RE = re.compile(r"(\d{1,2}[:.]\d{2})\s*[-–]\s*(\d{1,2}[:.]\d{2})")
# single time: 07:30
_TIME_SINGLE_RE = re.compile(r"\b\d{1,2}[:.]\d{2}\b")
_SEMESTER_RE = re.compile(r"\bsemester\s*(\d+)\b", re.IGNORECASE)

# header mapping (normalized -> canonical)
_HEADER_MAP = {
    "kode": "kode",
    "kode mk": "kode",
    "kode matakuliah": "kode",
    "kode matkul": "kode",
    "course code": "kode",
    "mk": "kode",
    "mata kuliah": "mata_kuliah",
    "matakuliah": "mata_kuliah",
    "nama mata kuliah": "mata_kuliah",
    "nama matakuliah": "mata_kuliah",
    "course name": "mata_kuliah",
    "nama": "mata_kuliah",
    "hari": "hari",
    "day": "hari",
    "jam": "jam",
    "waktu": "jam",
    "time": "jam",
    "sks": "sks",
    "credit": "sks",
    "credits": "sks",
    "dosen": "dosen",
    "pengampu": "dosen",
    "dosen pengampu": "dosen",
    "lecturer": "dosen",
    "kelas": "kelas",
    "class": "kelas",
    "ruang": "ruang",
    "room": "ruang",
    "lab": "ruang",
    "semester": "semester",
}

_CANON_LABELS = {
    "kode": "Kode",
    "mata_kuliah": "Mata Kuliah",
    "hari": "Hari",
    "jam": "Jam",
    "sks": "SKS",
    "dosen": "Dosen Pengampu",
    "kelas": "Kelas",
    "ruang": "Ruang",
    "semester": "Semester",
}


# =========================
# Small helpers
# =========================
def _norm(s: Any) -> str:
    """Normalize whitespace & stringify."""
    s = "" if s is None else str(s)
    s = s.replace("\u00a0", " ")  # non-breaking space
    s = s.replace("\t", " ")
    s = s.replace("\r", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _norm_header(s: Any) -> str:
    """Aggressive normalize for header matching."""
    s = _norm(s).lower()
    s = s.replace(".", " ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _normalize_time_range(s: str) -> str:
    """
    Normalize jam:
    - join newline
    - replace en-dash
    - remove weird spaces around '-'
    - convert '.' to ':'
    Return best-effort jam string.
    """
    s = "" if s is None else str(s)
    s = s.replace("\n", " ").replace("\r", " ")
    s = s.replace("–", "-").replace("—", "-")
    s = s.replace(".", ":")
    s = re.sub(r"\s+", " ", s).strip()
    # normalize spaces around dash
    s = re.sub(r"\s*-\s*", "-", s)
    # handle "07:30- 10:00" -> "07:30-10:00"
    s = s.replace("- ", "-")
    return s.strip()


def _looks_like_header_row(row: List[str]) -> bool:
    """
    Heuristik header KRS/jadwal:
    butuh >=2 sinyal seperti hari/jam/kode/nama/sks/dosen/kelas/ruang
    """
    joined = " ".join([_norm_header(x) for x in row if _norm(x)])
    if not joined:
        return False

    keys = [
        "hari", "day",
        "jam", "waktu", "time",
        "kode", "kode mk", "mk", "matakuliah", "mata kuliah", "course",
        "sks", "credit",
        "dosen", "pengampu", "lecturer",
        "kelas", "class",
        "ruang", "room", "lab",
        "no"
    ]
    hits = sum(1 for k in keys if k in joined)
    return hits >= 2


def _canonical_header(name: str) -> Optional[str]:
    key = _norm_header(name)
    if key in _HEADER_MAP:
        return _HEADER_MAP[key]
    # contains fallback
    for k, v in _HEADER_MAP.items():
        if k and k in key:
            return v
    return None


def _canonical_columns_from_header(header: List[str]) -> Dict[int, str]:
    mapping: Dict[int, str] = {}
    for i, h in enumerate(header):
        canon = _canonical_header(h)
        if canon:
            mapping[i] = canon
    return mapping


def _display_columns_from_mapping(mapping: Dict[int, str]) -> List[str]:
    cols = []
    seen = set()
    for _, canon in mapping.items():
        label = _CANON_LABELS.get(canon, canon.title())
        if label.lower() in seen:
            continue
        seen.add(label.lower())
        cols.append(label)
    return cols


def _find_idx(header_l: List[str], candidates: List[str]) -> Optional[int]:
    """
    Find first matching candidate in normalized header list.
    Candidate can be exact or contained.
    """
    for cand in candidates:
        cand_n = _norm_header(cand)
        for i, h in enumerate(header_l):
            if h == cand_n:
                return i
        # fallback contains
        for i, h in enumerate(header_l):
            if cand_n and cand_n in h:
                return i
    return None


def _row_to_text(row: List[str]) -> str:
    return " | ".join([_norm(c) for c in row if _norm(c)]).strip()


def _extract_semester_from_text(s: str) -> Optional[int]:
    if not s:
        return None
    m = _SEMESTER_RE.search(str(s))
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _detect_doc_type(detected_columns: Optional[List[str]], schedule_rows: Optional[List[Dict[str, Any]]]) -> str:
    cols = [c.lower() for c in (detected_columns or [])]
    if any(c in cols for c in ["hari", "jam", "ruang", "kelas"]):
        return "schedule"
    if schedule_rows:
        return "schedule"
    if any(c in cols for c in ["grade", "bobot", "nilai", "ips", "ipk"]):
        return "transcript"
    return "general"


# =========================
# PDF extraction
# =========================
def _extract_pdf_tables(pdf: pdfplumber.PDF) -> Tuple[str, List[str], List[Dict[str, Any]]]:
    """
    Return:
    - text_from_tables: string gabungan tabel untuk RAG
    - detected_columns: list kolom hasil deteksi header tabel (unik)
    - schedule_rows: list row ringkas jadwal (best-effort)
    """
    detected_columns: List[str] = []
    schedule_rows: List[Dict[str, Any]] = []
    text_parts: List[str] = []

    for page_idx, page in enumerate(pdf.pages, start=1):
        # --- 1) extract tables ---
        try:
            tables = page.extract_tables() or []
        except Exception:
            tables = []

        for table in tables:
            if not table:
                continue

            cleaned = [[_norm(cell) for cell in row] for row in table if row]
            if not cleaned:
                continue

            # text for rag
            for row in cleaned:
                text_parts.append(_row_to_text(row))

            # detect header
            header: Optional[List[str]] = None
            canon_map: Dict[int, str] = {}
            if len(cleaned) >= 2 and _looks_like_header_row(cleaned[0]):
                header = cleaned[0]
                canon_map = _canonical_columns_from_header(header)
                # store display columns
                for col in _display_columns_from_mapping(canon_map):
                    if col not in detected_columns:
                        detected_columns.append(col)

            # --- 2) schedule extraction from table ---
            if header:
                header_l = [_norm_header(h) for h in header]

                day_idx = _find_idx(header_l, ["hari", "day"])
                time_idx = _find_idx(header_l, ["jam", "waktu", "time"])
                code_idx = _find_idx(header_l, ["kode mk", "kode", "course code", "kode matakuliah", "kode matkul"])
                name_idx = _find_idx(header_l, ["nama matakuliah", "nama mata kuliah", "mata kuliah", "matakuliah", "course name", "nama"])
                sks_idx = _find_idx(header_l, ["sks", "credit", "credits"])
                dosen_idx = _find_idx(header_l, ["dosen pengampu", "dosen", "pengampu", "lecturer"])
                kelas_idx = _find_idx(header_l, ["kelas", "class"])
                ruang_idx = _find_idx(header_l, ["ruang", "room", "lab"])

                # Jika day/time tidak ketemu, kita fallback ke scanning cell per row (lebih tahan format berbeda)
                for row in cleaned[1:]:
                    if len(schedule_rows) >= 300:
                        break

                    # pick day & time
                    day = row[day_idx] if day_idx is not None and day_idx < len(row) else ""
                    jam = row[time_idx] if time_idx is not None and time_idx < len(row) else ""

                    # fallback search day/time inside row if missing
                    joined_l = " ".join([_norm_header(c) for c in row if _norm(c)])

                    if not day:
                        for d in _DAY_WORDS:
                            if d in joined_l:
                                day = d.title() if d.isalpha() else d
                                break

                    if not jam:
                        # cari range jam di row
                        m = _TIME_RANGE_RE.search(_normalize_time_range(" ".join(row)))
                        if m:
                            jam = f"{m.group(1).replace('.', ':')}-{m.group(2).replace('.', ':')}"

                    jam = _normalize_time_range(jam)

                    # skip kalau benar2 kosong
                    if not day and not jam:
                        continue

                    item: Dict[str, Any] = {
                        "page": page_idx,
                        "hari": _norm(day),
                        "jam": jam,
                        "kode": row[code_idx] if code_idx is not None and code_idx < len(row) else "",
                        "mata_kuliah": row[name_idx] if name_idx is not None and name_idx < len(row) else "",
                        "sks": row[sks_idx] if sks_idx is not None and sks_idx < len(row) else "",
                        "dosen": row[dosen_idx] if dosen_idx is not None and dosen_idx < len(row) else "",
                        "kelas": row[kelas_idx] if kelas_idx is not None and kelas_idx < len(row) else "",
                        "ruang": row[ruang_idx] if ruang_idx is not None and ruang_idx < len(row) else "",
                    }

                    # map extra columns if available via canon_map
                    for idx, canon in canon_map.items():
                        if canon in item:
                            continue
                        if idx < len(row):
                            item[canon] = row[idx]

                    # accept row jika ada sinyal jadwal minimal:
                    # - day ada ATAU jam ada (lebih longgar agar tidak bolong)
                    if item["hari"] or item["jam"]:
                        schedule_rows.append(item)

            else:
                # --- No header: best-effort detect schedule rows ---
                for row in cleaned:
                    if len(schedule_rows) >= 300:
                        break
                    raw = _row_to_text(row)
                    raw_n = _normalize_time_range(raw)
                    low = raw_n.lower()

                    has_day = any(d in low for d in _DAY_WORDS)
                    has_time = bool(_TIME_RANGE_RE.search(raw_n))

                    if has_day or has_time:
                        schedule_rows.append({
                            "page": page_idx,
                            "raw": raw_n,
                        })

        # --- 3) fallback from page text (very important) ---
        # beberapa PDF tabelnya sulit, tapi textnya mengandung pola hari+jam
        try:
            page_text = (page.extract_text() or "").strip()
        except Exception:
            page_text = ""

        if page_text:
            # normalize
            t = _normalize_time_range(page_text)
            t_l = t.lower()

            # cari semua time range yang muncul
            time_ranges = list(_TIME_RANGE_RE.finditer(t))
            if time_ranges:
                # untuk setiap time range, coba temukan "hari" terdekat di sekitar match
                for m in time_ranges:
                    if len(schedule_rows) >= 300:
                        break
                    span_start = max(0, m.start() - 60)
                    span_end = min(len(t_l), m.end() + 60)
                    window = t_l[span_start:span_end]

                    day_found = ""
                    for d in _DAY_WORDS:
                        if d in window:
                            day_found = d
                            break

                    jam = f"{m.group(1).replace('.', ':')}-{m.group(2).replace('.', ':')}"
                    jam = _normalize_time_range(jam)

                    # simpan minimal fallback jika belum ada row identik
                    key = (str(page_idx), day_found, jam)
                    # dedup sederhana
                    exists = False
                    for r in schedule_rows[-60:]:
                        if str(r.get("page")) == str(page_idx) and (r.get("hari") or "").lower() == day_found and (r.get("jam") or "") == jam:
                            exists = True
                            break
                    if not exists:
                        schedule_rows.append({
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
                        })

    # --- Post-process schedule_rows: clean & dedup ---
    out_rows: List[Dict[str, Any]] = []
    seen = set()
    for r in schedule_rows:
        if not isinstance(r, dict):
            continue
        hari = _norm(r.get("hari", ""))
        jam = _normalize_time_range(r.get("jam", ""))
        kode = _norm(r.get("kode", ""))
        mk = _norm(r.get("mata_kuliah", ""))
        kelas = _norm(r.get("kelas", ""))
        ruang = _norm(r.get("ruang", ""))
        page = int(r.get("page", 0) or 0)

        # normalisasi hari (kalau ada)
        hari_l = hari.lower()
        if hari_l in _DAY_WORDS:
            # title-case versi indonesia/english
            hari = hari_l.replace("jum'at", "Jum'at").title()

        # key dedup: page+hari+jam+kode+mk+kelas+ruang (best effort)
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


def process_document(doc_instance) -> bool:
    """
    Membaca file PDF/Excel/CSV/MD/TXT, memecahnya, dan menyimpan ke ChromaDB
    dengan metadata:
    - user_id (isolasi data)
    - doc_id (penting untuk delete/reingest)
    - source, file_type
    - columns (schema) termasuk PDF
    - schedule_rows (khusus KRS/Jadwal; ringkas & dibatasi)
    """
    file_path = doc_instance.file.path
    ext = file_path.split(".")[-1].lower()
    text_content = ""

    detected_columns: Optional[List[str]] = None
    schedule_rows: Optional[List[Dict[str, Any]]] = None
    semester_num: Optional[int] = _extract_semester_from_text(getattr(doc_instance, "title", ""))

    logger.info(" MULAI PARSING: %s (Type: %s)", doc_instance.title, ext)

    try:
        # =========================
        # 1) PARSING
        # =========================
        if ext == "pdf":
            with pdfplumber.open(file_path) as pdf:
                table_text, pdf_columns, pdf_schedule_rows = _extract_pdf_tables(pdf)

                if pdf_columns:
                    detected_columns = pdf_columns

                if pdf_schedule_rows:
                    schedule_rows = pdf_schedule_rows

                if table_text:
                    text_content += table_text + "\n"

                # text biasa
                for page in pdf.pages:
                    t = page.extract_text() or ""
                    t = t.strip()
                    if t:
                        text_content += t + "\n"
                        if semester_num is None:
                            semester_num = _extract_semester_from_text(t)

            logger.debug(" PDF Parsed. columns=%s schedule_rows=%s",
                         len(detected_columns or []), len(schedule_rows or []))

            # OCR fallback (optional) jika text kosong
            if not (text_content or "").strip():
                try:
                    from pdf2image import convert_from_path  # type: ignore
                    import pytesseract  # type: ignore
                    logger.warning(" PDF text kosong -> mencoba OCR fallback")
                    images = convert_from_path(file_path, first_page=1, last_page=min(2, len(pdf.pages)))
                    ocr_texts = []
                    for img in images:
                        ocr_texts.append(pytesseract.image_to_string(img))
                    ocr_blob = "\n".join([t.strip() for t in ocr_texts if t and t.strip()])
                    if ocr_blob:
                        text_content += ocr_blob + "\n"
                        if semester_num is None:
                            semester_num = _extract_semester_from_text(ocr_blob)
                except Exception as e:
                    logger.warning(" OCR fallback gagal/tdk tersedia: %s", e)

        elif ext in ["xlsx", "xls"]:
            try:
                df = pd.read_excel(file_path).fillna("")
                detected_columns = [str(c).strip() for c in list(df.columns) if str(c).strip()]
                text_content = df.to_markdown(index=False)
                logger.debug(" Excel Parsed: %s baris data.", len(df))
            except Exception as e:
                logger.error(" Gagal baca Excel %s: %s", doc_instance.title, e, exc_info=True)
                return False

        elif ext == "csv":
            try:
                df = pd.read_csv(file_path)
            except Exception as e_comma:
                logger.warning(" Gagal baca CSV pakai koma, mencoba titik-koma... (%s)", e_comma)
                try:
                    df = pd.read_csv(file_path, sep=";")
                except Exception as e_semi:
                    logger.warning(" Gagal baca CSV pakai titik-koma, mencoba encoding latin-1... (%s)", e_semi)
                    try:
                        df = pd.read_csv(file_path, sep=None, engine="python", encoding="latin-1")
                    except Exception as e_final:
                        logger.error(" CSV GAGAL TOTAL: %s. Error: %s", doc_instance.title, e_final, exc_info=True)
                        return False

            df = df.fillna("")
            detected_columns = [str(c).strip() for c in list(df.columns) if str(c).strip()]
            text_content = df.to_markdown(index=False)
            logger.debug(" CSV Parsed: %s baris data.", len(df))

        elif ext in ["md", "txt"]:
            with open(file_path, "r", encoding="utf-8") as f:
                text_content = f.read()
            logger.debug(" Text Parsed.")

        else:
            logger.warning(" Tipe file tidak didukung: %s", ext)
            return False

        if not (text_content or "").strip():
            logger.warning(" FILE KOSONG: %s tidak mengandung teks yang bisa dibaca.", doc_instance.title)
            return False

        # =========================
        # 2) CHUNKING
        # =========================
        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=120)
        chunks = splitter.split_text(text_content)

        if not chunks:
            logger.warning(" CHUNKING GAGAL: Tidak ada potongan teks untuk %s.", doc_instance.title)
            return False

        # =========================
        # 3) EMBEDDING & STORAGE
        # =========================
        vectorstore = get_vectorstore()

        base_meta: Dict[str, Any] = {
            "user_id": str(doc_instance.user.id),
            "doc_id": str(doc_instance.id),          
            "source": doc_instance.title,
            "file_type": ext,
        }

        if detected_columns:
            # Chroma metadata hanya menerima primitive -> simpan sebagai JSON string
            base_meta["columns"] = json.dumps(detected_columns, ensure_ascii=True)

        if schedule_rows:
            if semester_num is not None:
                for r in schedule_rows:
                    if isinstance(r, dict) and "semester" not in r:
                        r["semester"] = str(semester_num)
            # simpan lebih banyak (mis 220) supaya jadwal tidak kepotong,
            # tapi tetap aman (PDF KRS biasanya <= 50 baris)
            base_meta["schedule_rows"] = json.dumps(schedule_rows[:220], ensure_ascii=True)

        if semester_num is not None:
            base_meta["semester"] = int(semester_num)

        doc_type = _detect_doc_type(detected_columns, schedule_rows)
        base_meta["doc_type"] = doc_type

        metadatas = [base_meta for _ in chunks]

        logger.debug(" Menyimpan ke ChromaDB... chunks=%s cols=%s schedule_rows=%s",
                     len(chunks), len(detected_columns or []), len(schedule_rows or []))

        vectorstore.add_texts(texts=chunks, metadatas=metadatas)

        logger.info(" INGEST SELESAI: %s berhasil masuk Knowledge Base.", doc_instance.title)
        return True

    except Exception as e:
        logger.error(" CRITICAL ERROR di ingest.py pada file %s: %s", doc_instance.title, str(e), exc_info=True)
        return False
