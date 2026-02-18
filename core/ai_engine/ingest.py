# core/ai_engine/ingest.py

import os
import re
import pdfplumber
import pandas as pd
import logging
import json
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from langchain_text_splitters import RecursiveCharacterTextSplitter
from .config import get_vectorstore
try:
    from langchain_openai import ChatOpenAI  # type: ignore
except Exception:  # pragma: no cover - optional dependency for hybrid mode
    ChatOpenAI = None  # type: ignore

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
    "sesi": "sesi",
    "session": "sesi",
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
    "smt": "semester",
    "sm t": "semester",
    "s m t": "semester",
}

_CANON_LABELS = {
    "kode": "Kode",
    "mata_kuliah": "Mata Kuliah",
    "hari": "Hari",
    "jam": "Jam",
    "sesi": "Sesi",
    "sks": "SKS",
    "dosen": "Dosen Pengampu",
    "kelas": "Kelas",
    "ruang": "Ruang",
    "semester": "Semester",
}

_SCHEDULE_CANON_ORDER = [
    "hari",
    "sesi",
    "jam",
    "kode",
    "mata_kuliah",
    "sks",
    "kelas",
    "ruang",
    "dosen",
    "semester",
    "page",
]

_MAX_SCHEDULE_ROWS = 2500
_DAY_CANON = {
    "senin": "Senin",
    "selasa": "Selasa",
    "rabu": "Rabu",
    "kamis": "Kamis",
    "jumat": "Jumat",
    "jumat": "Jumat",
    "sabtu": "Sabtu",
    "minggu": "Minggu",
    "monday": "Monday",
    "tuesday": "Tuesday",
    "wednesday": "Wednesday",
    "thursday": "Thursday",
    "friday": "Friday",
    "saturday": "Saturday",
    "sunday": "Sunday",
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
    # rapikan digit yang terpecah: "0 7 : 0 0" -> "07:00"
    s = re.sub(r"(?<=\d)\s+(?=\d)", "", s)
    s = re.sub(r"(?<=\d)\s*:\s*(?=\d)", ":", s)
    s = re.sub(r"\s+", " ", s).strip()
    # normalize spaces around dash
    s = re.sub(r"\s*-\s*", "-", s)
    # handle "07:30- 10:00" -> "07:30-10:00"
    s = s.replace("- ", "-")
    m = _TIME_RANGE_RE.search(s)
    if m:
        try:
            h1, m1 = [int(x) for x in m.group(1).replace(".", ":").split(":")]
            h2, m2 = [int(x) for x in m.group(2).replace(".", ":").split(":")]
            if 0 <= h1 <= 23 and 0 <= h2 <= 23 and 0 <= m1 <= 59 and 0 <= m2 <= 59:
                return f"{h1:02d}:{m1:02d}-{h2:02d}:{m2:02d}"
        except Exception:
            pass

    # fallback untuk kasus digit kebalik/acak ringan:
    # contoh "0 5 :7 0-0 0 :7 0" -> "07:00-07:50"
    digits = re.sub(r"\D+", "", s)
    if len(digits) == 8:
        def _chunk_reverse_4(d: str) -> str:
            return d[:4][::-1] + d[4:][::-1]

        candidates = [
            digits,
            digits[::-1],
            _chunk_reverse_4(digits),
            digits[4:] + digits[:4],
        ]
        for cand in candidates:
            h1, m1, h2, m2 = int(cand[:2]), int(cand[2:4]), int(cand[4:6]), int(cand[6:8])
            if 0 <= h1 <= 23 and 0 <= h2 <= 23 and 0 <= m1 <= 59 and 0 <= m2 <= 59:
                a = h1 * 60 + m1
                b = h2 * 60 + m2
                if b < a:
                    h1, m1, h2, m2 = h2, m2, h1, m1
                return f"{h1:02d}:{m1:02d}-{h2:02d}:{m2:02d}"
    return s.strip()


def _is_valid_time_range(s: str) -> bool:
    m = _TIME_RANGE_RE.search(_normalize_time_range(s or ""))
    if not m:
        return False
    try:
        h1, m1 = [int(x) for x in m.group(1).replace(".", ":").split(":")]
        h2, m2 = [int(x) for x in m.group(2).replace(".", ":").split(":")]
        return 0 <= h1 <= 23 and 0 <= h2 <= 23 and 0 <= m1 <= 59 and 0 <= m2 <= 59
    except Exception:
        return False


def _normalize_day_text(s: str) -> str:
    raw = _norm(s)
    if not raw:
        return ""
    letters = re.sub(r"[^a-z]+", "", raw.lower())
    if not letters:
        return raw
    if letters in _DAY_CANON:
        return _DAY_CANON[letters]
    rev = letters[::-1]
    if rev in _DAY_CANON:
        return _DAY_CANON[rev]
    return raw


def _is_noise_numbering_row(row: List[str]) -> bool:
    """
    Baris noise seperti "1 2 3 4 5 6 7 8 9 10" pada header tiap halaman.
    """
    vals = []
    for c in row:
        v = _norm(c).replace(".", "").replace(",", "")
        if v:
            vals.append(v)
    if len(vals) < 5:
        return False
    if not all(v.isdigit() for v in vals):
        return False
    nums = [int(v) for v in vals]
    return nums == list(range(1, len(nums) + 1))


def _is_noise_header_repeat_row(row: List[str]) -> bool:
    joined = _norm_header(" ".join([_norm(x) for x in row if _norm(x)]))
    if not joined:
        return False
    return ("no" in joined and "hari" in joined and "jam" in joined and "mata kuliah" in joined)


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


def _schedule_rows_to_csv_text(rows: Optional[List[Dict[str, Any]]]) -> Tuple[str, int, int]:
    """
    Bentuk representasi CSV canonical dari schedule_rows agar konten tabel
    lebih terstruktur untuk RAG.
    """
    if not rows:
        return "", 0, 0

    normalized_rows: List[Dict[str, Any]] = []
    no_counter = 0
    for r in rows:
        if not isinstance(r, dict):
            continue
        hari = _normalize_day_text(r.get("hari", ""))
        hari = hari.upper() if hari else ""
        sesi = _norm(r.get("sesi", ""))
        jam = _normalize_time_range(r.get("jam", ""))
        ruang = _norm(r.get("ruang", ""))
        ruang = re.sub(r"(?<=\d),(?=\d)", ".", ruang)  # 1,10 -> 1.10
        smt = _norm(r.get("semester", ""))
        mk = _norm(r.get("mata_kuliah", ""))
        sks = _norm(r.get("sks", ""))
        kls = _norm(r.get("kelas", ""))
        dosen = _norm(r.get("dosen", ""))

        # Hindari row fallback (hasil page-text) yang hanya berisi slot waktu.
        # Untuk CSV canonical, wajib ada mata kuliah atau kode.
        if not (mk or _norm(r.get("kode", ""))):
            continue

        no_counter += 1
        normalized_rows.append({
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
        })

    if not normalized_rows:
        return "", 0, 0

    df = pd.DataFrame(normalized_rows).fillna("")
    ordered_cols = [
        "NO",
        "HARI",
        "SESI",
        "JAM",
        "Ruang",
        "SMT",
        "MATA_KULIAH",
        "SKS",
        "KLS",
        "DOSEN_PENGAMPU_TEAM_TEACHING",
    ]
    df = df[[c for c in ordered_cols if c in df.columns]]
    return df.to_csv(index=False), int(len(df.index)), int(len(df.columns))


def _csv_preview(csv_text: str, max_lines: int = 12, max_chars: int = 3500) -> str:
    """
    Preview CSV untuk log terminal agar mudah review tanpa membanjiri output.
    """
    lines = (csv_text or "").splitlines()
    if not lines:
        return "-"
    preview = "\n".join(lines[:max_lines])
    if len(lines) > max_lines:
        preview += f"\n... (+{len(lines) - max_lines} rows)"
    if len(preview) > max_chars:
        preview = preview[:max_chars] + "\n... (truncated)"
    return preview


def _schedule_rows_to_row_chunks(rows: Optional[List[Dict[str, Any]]], limit: int = 2000) -> List[str]:
    """
    Row-level chunking berbasis pasangan kolom=nilai supaya query detail
    (hari/jam/kelas/dosen) lebih mudah kena di retrieval.
    """
    if not rows:
        return []

    out: List[str] = []
    for idx, r in enumerate(rows[:limit], start=1):
        if not isinstance(r, dict):
            continue
        cells: List[str] = []
        for key in _SCHEDULE_CANON_ORDER:
            val = _norm(r.get(key, ""))
            if val:
                cells.append(f"{key}={val}")
        # tambahan kolom non-canonical
        for key, value in r.items():
            if key in _SCHEDULE_CANON_ORDER:
                continue
            val = _norm(value)
            if val:
                cells.append(f"{key}={val}")
        if len(cells) >= 2:
            out.append(f"CSV_ROW {idx}: " + " | ".join(cells))
    return out


def _row_confidence(row: Dict[str, Any]) -> Tuple[float, List[str]]:
    """
    Hitung confidence sederhana untuk memutuskan apakah row perlu diperbaiki LLM.
    """
    issues: List[str] = []
    score = 1.0

    hari = _normalize_day_text(row.get("hari", ""))
    sesi = _norm(row.get("sesi", ""))
    jam = _normalize_time_range(row.get("jam", ""))
    mk = _norm(row.get("mata_kuliah", ""))
    dosen = _norm(row.get("dosen", ""))
    kls = _norm(row.get("kelas", ""))
    smt = _norm(row.get("semester", ""))
    ruang = _norm(row.get("ruang", ""))

    if not hari:
        score -= 0.15
        issues.append("missing_hari")
    if not sesi:
        score -= 0.12
        issues.append("missing_sesi")
    if not jam or not _is_valid_time_range(jam):
        score -= 0.25
        issues.append("invalid_jam")
    if not mk:
        score -= 0.45
        issues.append("missing_mata_kuliah")
    if not dosen:
        score -= 0.20
        issues.append("missing_dosen")
    if not ruang:
        score -= 0.10
        issues.append("missing_ruang")
    if not kls:
        score -= 0.08
        issues.append("missing_kelas")
    if not smt:
        score -= 0.08
        issues.append("missing_semester")

    return max(0.0, min(1.0, score)), issues


def _build_repair_llm() -> Optional[Any]:
    """
    Build LLM client for hybrid repair. Return None if unavailable.
    """
    if ChatOpenAI is None:
        return None

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return None

    model_name = os.environ.get("INGEST_REPAIR_MODEL") or os.environ.get(
        "OPENROUTER_MODEL", "qwen/qwen3-next-80b-a3b-instruct:free"
    )

    try:
        return ChatOpenAI(
            openai_api_key=api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            model_name=model_name,
            temperature=float(os.environ.get("INGEST_REPAIR_TEMPERATURE", "0.0")),
            request_timeout=int(os.environ.get("INGEST_REPAIR_TIMEOUT", "60")),
            max_retries=int(os.environ.get("INGEST_REPAIR_RETRIES", "1")),
            default_headers={
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "AcademicChatbot-Ingest",
            },
        )
    except Exception as e:
        logger.warning(" Hybrid LLM init gagal: %s", e)
        return None


def _extract_json_from_llm_response(text: str) -> Optional[List[Dict[str, Any]]]:
    if not text:
        return None

    raw = text.strip()
    # try direct JSON
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except Exception:
        pass

    # try fenced json block
    m = re.search(r"```json\s*(.*?)\s*```", raw, flags=re.DOTALL | re.IGNORECASE)
    if m:
        try:
            data = json.loads(m.group(1).strip())
            if isinstance(data, list):
                return data
        except Exception:
            pass

    # fallback first array blob
    m2 = re.search(r"(\[\s*\{.*\}\s*\])", raw, flags=re.DOTALL)
    if m2:
        try:
            data = json.loads(m2.group(1))
            if isinstance(data, list):
                return data
        except Exception:
            pass

    return None


def _repair_rows_with_llm(rows: List[Dict[str, Any]], source: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Hybrid step: only repair low-confidence rows with LLM strict JSON output.
    """
    if not rows:
        return rows, {"enabled": False, "checked": 0, "repaired": 0}

    enabled = (os.environ.get("PDF_HYBRID_LLM_REPAIR", "1") or "1").strip() in {"1", "true", "yes"}
    if not enabled:
        return rows, {"enabled": False, "checked": 0, "repaired": 0}

    llm = _build_repair_llm()
    if llm is None:
        return rows, {"enabled": False, "checked": 0, "repaired": 0, "reason": "llm_unavailable"}

    threshold = float(os.environ.get("INGEST_REPAIR_THRESHOLD", "0.82"))
    max_rows = int(os.environ.get("INGEST_REPAIR_MAX_ROWS", "220"))
    batch_size = int(os.environ.get("INGEST_REPAIR_BATCH_SIZE", "25"))

    candidates: List[Tuple[int, Dict[str, Any], List[str], float]] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        # skip very weak fallback rows that have no class content
        if not (_norm(row.get("mata_kuliah", "")) or _norm(row.get("kode", ""))):
            continue
        conf, issues = _row_confidence(row)
        row["_confidence"] = conf
        row["_issues"] = issues
        if conf < threshold:
            candidates.append((idx, row, issues, conf))

    if not candidates:
        return rows, {"enabled": True, "checked": len(rows), "repaired": 0}

    candidates = candidates[:max_rows]
    repaired = 0
    run_id = uuid4().hex[:8]

    for start in range(0, len(candidates), max(1, batch_size)):
        batch = candidates[start:start + max(1, batch_size)]
        payload: List[Dict[str, Any]] = []
        for i, row, issues, conf in batch:
            payload.append(
                {
                    "idx": i,
                    "issues": issues,
                    "confidence": round(conf, 3),
                    "row": {
                        "hari": _norm(row.get("hari", "")),
                        "sesi": _norm(row.get("sesi", "")),
                        "jam": _norm(row.get("jam", "")),
                        "ruang": _norm(row.get("ruang", "")),
                        "semester": _norm(row.get("semester", "")),
                        "mata_kuliah": _norm(row.get("mata_kuliah", "")),
                        "sks": _norm(row.get("sks", "")),
                        "kelas": _norm(row.get("kelas", "")),
                        "dosen": _norm(row.get("dosen", "")),
                        "kode": _norm(row.get("kode", "")),
                        "page": int(row.get("page", 0) or 0),
                    },
                }
            )

        prompt = (
            "Anda memperbaiki data jadwal kuliah hasil OCR/PDF.\n"
            "Tugas: perbaiki hanya field yang rusak/kosong. Jangan halusinasi.\n"
            "Jika tidak yakin, biarkan nilai lama.\n"
            "Wajib output JSON ARRAY valid tanpa teks tambahan.\n"
            "Setiap item wajib punya keys: idx, hari, sesi, jam, ruang, semester, mata_kuliah, sks, kelas, dosen, kode.\n"
            "Format jam wajib HH:MM-HH:MM.\n"
            "Hari gunakan: SENIN/SELASA/RABU/KAMIS/JUMAT/SABTU/MINGGU jika bahasa Indonesia.\n"
            f"Source: {source}\n"
            f"Run: {run_id}\n"
            f"Input rows:\n{json.dumps(payload, ensure_ascii=True)}"
        )

        try:
            out = llm.invoke(prompt)
            content = out.content if hasattr(out, "content") else str(out)
            parsed = _extract_json_from_llm_response(content if isinstance(content, str) else str(content))
            if not parsed:
                continue

            for item in parsed:
                if not isinstance(item, dict):
                    continue
                idx = item.get("idx")
                if not isinstance(idx, int) or idx < 0 or idx >= len(rows):
                    continue
                row = rows[idx]
                if not isinstance(row, dict):
                    continue

                updates = {
                    "hari": _normalize_day_text(item.get("hari", row.get("hari", ""))),
                    "sesi": _norm(item.get("sesi", row.get("sesi", ""))),
                    "jam": _normalize_time_range(item.get("jam", row.get("jam", ""))),
                    "ruang": _norm(item.get("ruang", row.get("ruang", ""))),
                    "semester": _norm(item.get("semester", row.get("semester", ""))),
                    "mata_kuliah": _norm(item.get("mata_kuliah", row.get("mata_kuliah", ""))),
                    "sks": _norm(item.get("sks", row.get("sks", ""))),
                    "kelas": _norm(item.get("kelas", row.get("kelas", ""))),
                    "dosen": _norm(item.get("dosen", row.get("dosen", ""))),
                    "kode": _norm(item.get("kode", row.get("kode", ""))),
                }

                before_conf, _ = _row_confidence(row)
                row.update({k: v for k, v in updates.items() if v != ""})
                after_conf, after_issues = _row_confidence(row)
                row["_confidence"] = after_conf
                row["_issues"] = after_issues
                if after_conf > before_conf:
                    repaired += 1
        except Exception as e:
            logger.warning(" Hybrid LLM repair batch gagal: %s", e)

    return rows, {
        "enabled": True,
        "checked": len(rows),
        "candidates": len(candidates),
        "repaired": repaired,
        "run_id": run_id,
    }


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
    carry_day = ""
    carry_sesi = ""
    carry_jam = ""

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
                sesi_idx = _find_idx(header_l, ["sesi", "session"])
                time_idx = _find_idx(header_l, ["jam", "waktu", "time"])
                code_idx = _find_idx(header_l, ["kode mk", "kode", "course code", "kode matakuliah", "kode matkul"])
                name_idx = _find_idx(header_l, ["nama matakuliah", "nama mata kuliah", "mata kuliah", "matakuliah", "course name", "nama"])
                sks_idx = _find_idx(header_l, ["sks", "credit", "credits"])
                dosen_idx = _find_idx(header_l, ["dosen pengampu", "dosen", "pengampu", "lecturer"])
                kelas_idx = _find_idx(header_l, ["kelas", "kls", "class"])
                ruang_idx = _find_idx(header_l, ["ruang", "room", "lab"])
                semester_idx = _find_idx(header_l, ["semester", "smt", "smt.", "sm t", "s m t", "sm"])

                # Untuk PDF dengan merged cells: baris lanjutan sering kosong di hari/sesi/jam.
                # Kita carry-forward nilai terakhir agar tiap row menjadi rekaman jadwal lengkap.
                last_day = carry_day
                last_sesi = carry_sesi
                last_jam = carry_jam

                # Jika day/time tidak ketemu, kita fallback ke scanning cell per row (lebih tahan format berbeda)
                for row in cleaned[1:]:
                    if len(schedule_rows) >= _MAX_SCHEDULE_ROWS:
                        break
                    if _is_noise_numbering_row(row) or _is_noise_header_repeat_row(row):
                        continue

                    # pick day & time
                    day = row[day_idx] if day_idx is not None and day_idx < len(row) else ""
                    sesi = row[sesi_idx] if sesi_idx is not None and sesi_idx < len(row) else ""
                    jam = row[time_idx] if time_idx is not None and time_idx < len(row) else ""
                    semester_cell = row[semester_idx] if semester_idx is not None and semester_idx < len(row) else ""

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

                    # forward fill untuk baris merged-cell
                    day = _normalize_day_text(day) or last_day
                    sesi = _norm(sesi) or last_sesi
                    jam = _normalize_time_range(jam) or last_jam
                    if day:
                        last_day = day
                    if sesi:
                        last_sesi = sesi
                    if jam:
                        last_jam = jam

                    # skip kalau benar2 kosong (tidak ada sinyal slot)
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
                        "semester": _norm(semester_cell),
                    }

                    # Fallback: beberapa PDF menggeser kolom dosen ke sel paling kanan.
                    if not _norm(item.get("dosen", "")):
                        for c in reversed(row):
                            c_norm = _norm(c)
                            if not c_norm:
                                continue
                            if c_norm in {
                                _norm(item.get("kode", "")),
                                _norm(item.get("mata_kuliah", "")),
                                _norm(item.get("sks", "")),
                                _norm(item.get("kelas", "")),
                                _norm(item.get("ruang", "")),
                                _norm(item.get("semester", "")),
                            }:
                                continue
                            if "," in c_norm or "." in c_norm or len(c_norm.split()) >= 2:
                                item["dosen"] = c_norm
                                break

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

                # simpan slot terakhir lintas tabel/halaman
                carry_day = last_day
                carry_sesi = last_sesi
                carry_jam = last_jam

            else:
                # --- No header: best-effort detect schedule rows ---
                for row in cleaned:
                    if len(schedule_rows) >= _MAX_SCHEDULE_ROWS:
                        break
                    if _is_noise_numbering_row(row) or _is_noise_header_repeat_row(row):
                        continue
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
                    if len(schedule_rows) >= _MAX_SCHEDULE_ROWS:
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
        hari = _normalize_day_text(hari)
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
    row_chunks: List[str] = []

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
                    schedule_rows, repair_stats = _repair_rows_with_llm(schedule_rows, doc_instance.title)
                    if repair_stats.get("enabled"):
                        logger.info(
                            " HYBRID_REPAIR source=%s checked=%s candidates=%s repaired=%s run=%s",
                            doc_instance.title,
                            repair_stats.get("checked", 0),
                            repair_stats.get("candidates", 0),
                            repair_stats.get("repaired", 0),
                            repair_stats.get("run_id", "-"),
                        )
                    row_chunks = _schedule_rows_to_row_chunks(schedule_rows)
                    csv_repr, csv_rows, csv_cols = _schedule_rows_to_csv_text(schedule_rows)
                    if csv_repr:
                        text_content += "\n[CSV_CANONICAL]\n" + csv_repr + "\n"
                        preview_lines = int(os.getenv("CSV_REVIEW_PREVIEW_LINES", "12") or 12)
                        preview = _csv_preview(csv_repr, max_lines=max(3, preview_lines))
                        logger.info(
                            " CSV canonical review source=%s rows=%s cols=%s\n%s",
                            doc_instance.title,
                            csv_rows,
                            csv_cols,
                            preview,
                        )
                    # Simpan JSON canonical ringkas untuk retrieval dengan format terstruktur.
                    json_preview_limit = int(os.getenv("JSON_CANONICAL_EMBED_ROWS", "300") or 300)
                    if schedule_rows:
                        try:
                            json_blob = json.dumps(schedule_rows[:max(20, json_preview_limit)], ensure_ascii=True)
                            text_content += "\n[JSON_CANONICAL]\n" + json_blob + "\n"
                        except Exception:
                            pass

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
        chunks = list(row_chunks)
        chunks.extend(splitter.split_text(text_content))
        # dedup chunk agar embedding tidak boros untuk konten identik
        chunks = [c for c in dict.fromkeys([_norm(c) for c in chunks if _norm(c)])]

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
            # simpan lebih banyak agar dokumen jadwal besar tidak banyak terpotong.
            base_meta["schedule_rows"] = json.dumps(schedule_rows[:1200], ensure_ascii=True)
            # Tandai mode hybrid agar mudah audit hasil ingest.
            hybrid_enabled = (os.environ.get("PDF_HYBRID_LLM_REPAIR", "1") or "1").strip() in {"1", "true", "yes"}
            base_meta["hybrid_repair"] = "on" if hybrid_enabled else "off"

        if semester_num is not None:
            base_meta["semester"] = int(semester_num)

        doc_type = _detect_doc_type(detected_columns, schedule_rows)
        base_meta["doc_type"] = doc_type
        if row_chunks:
            base_meta["table_format"] = "csv_canonical"

        metadatas = [base_meta for _ in chunks]

        logger.debug(" Menyimpan ke ChromaDB... chunks=%s cols=%s schedule_rows=%s",
                     len(chunks), len(detected_columns or []), len(schedule_rows or []))

        vectorstore.add_texts(texts=chunks, metadatas=metadatas)

        logger.info(" INGEST SELESAI: %s berhasil masuk Knowledge Base.", doc_instance.title)
        return True

    except Exception as e:
        logger.error(" CRITICAL ERROR di ingest.py pada file %s: %s", doc_instance.title, str(e), exc_info=True)
        return False
