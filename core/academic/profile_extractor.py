from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import pdfplumber
from core.ai_engine.config import get_vectorstore
from core.ai_engine.retrieval.llm import (
    build_llm,
    get_backup_models,
    get_runtime_openrouter_config,
    invoke_text,
)
from core.models import AcademicDocument


MAJOR_KEYWORDS: Dict[str, List[str]] = {
    "Teknik Informatika": ["teknik informatika", "informatika", "ilmu komputer", "computer science"],
    "Sistem Informasi": ["sistem informasi", "information systems"],
    "Teknik Elektro": ["teknik elektro", "elektro", "electrical engineering"],
    "Teknik Mesin": ["teknik mesin", "mesin", "mechanical engineering"],
    "Teknik Industri": ["teknik industri", "industrial engineering"],
    "Manajemen": ["manajemen", "management"],
    "Akuntansi": ["akuntansi", "accounting"],
    "Hukum": ["hukum", "law"],
    "Psikologi": ["psikologi", "psychology"],
}

CAREER_KEYWORDS: Dict[str, List[str]] = {
    "Software Engineer": ["software engineer", "backend developer", "frontend developer", "full stack"],
    "Data Scientist": ["data scientist", "machine learning", "data analyst", "ai engineer"],
    "UI/UX Designer": ["ui ux", "ux designer", "product designer", "user experience"],
    "Cybersecurity": ["cybersecurity", "security analyst", "penetration tester", "infosec"],
    "Product Manager": ["product manager", "product management"],
}

_MAJOR_LINE_RE = re.compile(r"(program studi|prodi|jurusan)\s*[:\-]?\s*([^\n\r,.;]{3,80})", re.IGNORECASE)
_CAREER_LINE_RE = re.compile(r"(target karir|career|tujuan karir)\s*[:\-]?\s*([^\n\r,.;]{3,80})", re.IGNORECASE)
_SEMESTER_RE = re.compile(r"\b(?:semester|smt|sem)\s*[:\-]?\s*(\d{1,2})\b", re.IGNORECASE)
_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)

TABLE_FIELD_ALIASES: Dict[str, List[str]] = {
    "jurusan": ["jurusan", "program studi", "prodi", "study program", "major"],
    "semester": ["semester", "smt", "sem"],
    "career": ["target karir", "career", "tujuan karir", "karir"],
    "hari": ["hari", "day"],
    "jam": ["jam", "waktu", "time", "jadwal"],
    "ruang": ["ruang", "room", "lab"],
    "kelas": ["kelas", "class", "kls"],
    "kode": ["kode", "kode mk", "course code", "kode matakuliah", "kode matkul"],
    "mata_kuliah": ["mata kuliah", "matakuliah", "nama mata kuliah", "course name", "nama mk"],
    "dosen": ["dosen", "pengampu", "lecturer"],
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except Exception:
        return None


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _confidence_from_score(score: float) -> float:
    if score >= 5:
        return 0.95
    if score >= 3.5:
        return 0.82
    if score >= 2:
        return 0.68
    if score >= 1:
        return 0.52
    return 0.35


def _summary_confidence(max_score: float) -> str:
    if max_score >= 4:
        return "high"
    if max_score >= 2:
        return "medium"
    return "low"


def _record_hit(
    scores: Dict[str, float],
    evidences: Dict[str, List[str]],
    key: str,
    score: float,
    evidence: str,
) -> None:
    scores[key] += score
    if evidence and evidence not in evidences[key]:
        evidences[key].append(evidence[:180])


def _match_map_from_text(
    text: str,
    source: str,
    mapping: Dict[str, List[str]],
    explicit_re: re.Pattern[str] | None,
) -> Tuple[Dict[str, float], Dict[str, List[str]]]:
    scores: Dict[str, float] = defaultdict(float)
    evidences: Dict[str, List[str]] = defaultdict(list)
    low = _norm(text)

    if explicit_re:
        for m in explicit_re.finditer(text or ""):
            val = _norm(m.group(2))
            for label, aliases in mapping.items():
                if any(_norm(a) in val for a in aliases):
                    _record_hit(scores, evidences, label, 3.0, f"{source}: {m.group(0)}")

    for label, aliases in mapping.items():
        for a in aliases:
            if _norm(a) in low:
                _record_hit(scores, evidences, label, 1.1, f"{source}: {a}")
                break

    return scores, evidences


def _merge_scores(
    target_scores: Dict[str, float],
    target_evidence: Dict[str, List[str]],
    add_scores: Dict[str, float],
    add_evidence: Dict[str, List[str]],
) -> None:
    for k, v in add_scores.items():
        target_scores[k] += float(v or 0)
    for k, vals in add_evidence.items():
        for e in vals:
            if e not in target_evidence[k]:
                target_evidence[k].append(e)


def _rank_candidates(
    scores: Dict[str, float],
    evidences: Dict[str, List[str]],
    as_semester: bool = False,
) -> List[Dict[str, Any]]:
    items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    out: List[Dict[str, Any]] = []
    for key, score in items[:5]:
        if score <= 0:
            continue
        item: Dict[str, Any] = {
            "value": int(key) if as_semester else key,
            "label": f"Semester {int(key)}" if as_semester else key,
            "confidence": _confidence_from_score(score),
            "evidence": evidences.get(key, [])[:3],
        }
        out.append(item)
    return out


def _collect_semester_candidates(texts: List[Tuple[str, str]]) -> List[Dict[str, Any]]:
    scores: Dict[str, float] = defaultdict(float)
    evidences: Dict[str, List[str]] = defaultdict(list)
    for source, text in texts:
        for m in _SEMESTER_RE.finditer(text or ""):
            sem = m.group(1)
            try:
                sem_int = int(sem)
            except Exception:
                continue
            if sem_int < 1 or sem_int > 14:
                continue
            key = str(sem_int)
            _record_hit(scores, evidences, key, 1.8, f"{source}: {m.group(0)}")
    return _rank_candidates(scores, evidences, as_semester=True)


def _detect_table_fields_from_texts(texts: List[Tuple[str, str]]) -> Tuple[List[str], Dict[str, List[str]]]:
    evidence: Dict[str, List[str]] = defaultdict(list)
    fields = set()

    for source, text in texts:
        lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
        for ln in lines:
            if ("\t" not in ln) and ("|" not in ln) and not re.search(r"\S+\s{2,}\S+", ln):
                continue
            normalized_ln = _norm(ln)
            for canon, aliases in TABLE_FIELD_ALIASES.items():
                if any(_norm(alias) in normalized_ln for alias in aliases):
                    fields.add(canon)
                    if len(evidence[canon]) < 3:
                        evidence[canon].append(f"{source}: {ln[:180]}")

    return sorted(fields), dict(evidence)


def _detect_pdf_table_fields(docs: List[AcademicDocument]) -> Tuple[List[str], Dict[str, List[str]]]:
    evidence: Dict[str, List[str]] = defaultdict(list)
    fields = set()

    for doc in docs[:8]:
        file_name = str(getattr(doc.file, "name", "") or "")
        if not file_name.lower().endswith(".pdf"):
            continue
        try:
            file_path = doc.file.path
        except Exception:
            continue
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages[:2]:
                    tables = page.extract_tables() or []
                    for tb in tables[:5]:
                        if not tb:
                            continue
                        rows = [[str(c or "").strip() for c in row] for row in tb if row]
                        for row in rows[:2]:
                            row_text = " | ".join([c for c in row if c])
                            if not row_text:
                                continue
                            row_low = _norm(row_text)
                            for canon, aliases in TABLE_FIELD_ALIASES.items():
                                if any(_norm(alias) in row_low for alias in aliases):
                                    fields.add(canon)
                                    if len(evidence[canon]) < 3:
                                        evidence[canon].append(f"pdf:{doc.title}: {row_text[:180]}")
        except Exception:
            continue
    return sorted(fields), dict(evidence)


def _extract_json_object(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    txt = text.strip()
    try:
        parsed = json.loads(txt)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass
    m = _JSON_OBJ_RE.search(txt)
    if not m:
        return {}
    try:
        parsed = json.loads(m.group(0))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _llm_profile_fallback(texts: List[Tuple[str, str]]) -> Dict[str, Any]:
    runtime_cfg = get_runtime_openrouter_config()
    api_key = str(runtime_cfg.get("api_key") or "").strip()
    if not api_key:
        return {}

    snippets: List[str] = []
    for source, text in texts[:12]:
        snippet = (text or "").strip()[:500]
        if not snippet:
            continue
        snippets.append(f"[{source}]\n{snippet}")
    if not snippets:
        return {}

    prompt = (
        "Ekstrak profil akademik dari potongan dokumen berikut. "
        "Balas JSON valid SAJA dengan shape:\n"
        "{"
        "\"major\": string|null, "
        "\"career\": string|null, "
        "\"semester\": number|null, "
        "\"detected_fields\": string[], "
        "\"confidence\": \"low|medium|high\""
        "}\n\n"
        "Potongan dokumen:\n"
        + "\n\n".join(snippets)
    )

    backup_models = get_backup_models(str(runtime_cfg.get("model") or ""), runtime_cfg.get("backup_models"))
    for model_name in backup_models:
        try:
            llm = build_llm(model_name, runtime_cfg)
            raw = invoke_text(llm, prompt)
            obj = _extract_json_object(raw)
            if obj:
                obj["model"] = model_name
                return obj
        except Exception:
            continue
    return {}


def _build_dynamic_questions(
    major_candidates: List[Dict[str, Any]],
    career_candidates: List[Dict[str, Any]],
    semester_candidates: List[Dict[str, Any]],
    detected_fields: List[str],
    confidence_summary: str,
) -> List[Dict[str, Any]]:
    questions: List[Dict[str, Any]] = []

    top_major = major_candidates[0] if major_candidates else {}
    top_career = career_candidates[0] if career_candidates else {}
    top_sem = semester_candidates[0] if semester_candidates else {}

    if top_major and _safe_float(top_major.get("confidence")) >= 0.8:
        questions.append(
            {
                "step": "profile_jurusan",
                "question": f"Kami mendeteksi jurusan kamu kemungkinan {top_major.get('label')}. Benar?",
                "mode": "confirm",
            }
        )
    else:
        questions.append(
            {
                "step": "profile_jurusan",
                "question": "Jurusan kamu apa? (pilih kandidat dari dokumen atau ketik manual)",
                "mode": "collect",
            }
        )

    if top_career and _safe_float(top_career.get("confidence")) >= 0.75:
        questions.append(
            {
                "step": "career",
                "question": f"Kami juga mendeteksi target karir: {top_career.get('label')}. Mau pakai ini?",
                "mode": "confirm",
            }
        )
    else:
        questions.append(
            {
                "step": "career",
                "question": "Target karir kamu apa? (opsi dari dokumen + input manual tersedia)",
                "mode": "collect",
            }
        )

    if top_sem and _safe_float(top_sem.get("confidence")) >= 0.75:
        questions.append(
            {
                "step": "profile_semester",
                "question": f"Terdeteksi semester {top_sem.get('value')}. Apakah ini sesuai?",
                "mode": "confirm",
            }
        )

    if "jam" in detected_fields or "hari" in detected_fields:
        questions.append(
            {
                "step": "preferences_time",
                "question": "Dari tabel jadwal kamu, preferensi slot kuliah mana yang ingin diprioritaskan?",
                "mode": "collect",
            }
        )
        questions.append(
            {
                "step": "preferences_free_day",
                "question": "Di jadwal kampus kamu ada beberapa slot hari. Hari mana yang mau dikosongkan?",
                "mode": "collect",
            }
        )
    elif confidence_summary == "low":
        questions.append(
            {
                "step": "preferences_time",
                "question": "Data jadwal belum terbaca stabil. Kamu lebih nyaman kuliah pagi/siang/fleksibel?",
                "mode": "collect",
            }
        )

    return questions


def _gather_texts(user) -> Tuple[List[Tuple[str, str]], List[str], List[AcademicDocument]]:
    docs = AcademicDocument.objects.filter(user=user, is_embedded=True).order_by("-uploaded_at")
    doc_titles = [str(d.title or "") for d in docs]
    texts: List[Tuple[str, str]] = []

    for t in doc_titles:
        if t:
            texts.append((f"title:{t}", t))

    try:
        vectorstore = get_vectorstore()
        chunks = vectorstore.similarity_search(
            "program studi prodi jurusan semester target karir career pekerjaan",
            k=25,
            filter={"user_id": str(user.id)},
        )
        for c in chunks:
            content = str(getattr(c, "page_content", "") or "").strip()
            if not content:
                continue
            source = str((getattr(c, "metadata", {}) or {}).get("source") or "chunk")
            texts.append((f"chunk:{source}", content[:1500]))
    except Exception:
        # fallback: title-only mode
        pass

    return texts, doc_titles, list(docs)


def extract_profile_hints(user) -> Dict[str, Any]:
    texts, doc_titles, docs = _gather_texts(user)
    has_docs = bool(doc_titles)

    major_scores: Dict[str, float] = defaultdict(float)
    major_evidence: Dict[str, List[str]] = defaultdict(list)
    career_scores: Dict[str, float] = defaultdict(float)
    career_evidence: Dict[str, List[str]] = defaultdict(list)

    for source, text in texts:
        m_scores, m_evidence = _match_map_from_text(
            text=text,
            source=source,
            mapping=MAJOR_KEYWORDS,
            explicit_re=_MAJOR_LINE_RE,
        )
        c_scores, c_evidence = _match_map_from_text(
            text=text,
            source=source,
            mapping=CAREER_KEYWORDS,
            explicit_re=_CAREER_LINE_RE,
        )
        _merge_scores(major_scores, major_evidence, m_scores, m_evidence)
        _merge_scores(career_scores, career_evidence, c_scores, c_evidence)

    major_candidates = _rank_candidates(major_scores, major_evidence)
    career_candidates = _rank_candidates(career_scores, career_evidence)
    semester_candidates = _collect_semester_candidates(texts)

    text_table_fields, text_table_evidence = _detect_table_fields_from_texts(texts)
    pdf_table_fields, pdf_table_evidence = _detect_pdf_table_fields(docs)
    detected_fields = sorted(set(text_table_fields) | set(pdf_table_fields))

    max_major = max(major_scores.values(), default=0.0)
    max_career = max(career_scores.values(), default=0.0)
    max_semester = max((x.get("confidence", 0.0) for x in semester_candidates), default=0.0) * 5
    max_score = max(max_major, max_career, max_semester, 2.5 if detected_fields else 0.0)

    confidence_summary = _summary_confidence(max_score)
    has_relevant_docs = bool(major_candidates or career_candidates or semester_candidates or detected_fields)

    llm_fallback_used = False
    if has_docs and (not major_candidates or not career_candidates) and confidence_summary == "low":
        llm_data = _llm_profile_fallback(texts)
        llm_fallback_used = bool(llm_data)
        llm_major = str(llm_data.get("major") or "").strip()
        llm_career = str(llm_data.get("career") or "").strip()
        llm_semester = _safe_int(llm_data.get("semester"))
        llm_fields = llm_data.get("detected_fields") or []

        if llm_major:
            major_candidates = [
                {
                    "value": llm_major,
                    "label": llm_major,
                    "confidence": 0.66,
                    "evidence": [f"llm_fallback:{llm_data.get('model', '-')}: major"],
                }
            ] + major_candidates
        if llm_career:
            career_candidates = [
                {
                    "value": llm_career,
                    "label": llm_career,
                    "confidence": 0.64,
                    "evidence": [f"llm_fallback:{llm_data.get('model', '-')}: career"],
                }
            ] + career_candidates
        if llm_semester and not semester_candidates:
            semester_candidates = [
                {
                    "value": llm_semester,
                    "label": f"Semester {llm_semester}",
                    "confidence": 0.62,
                    "evidence": [f"llm_fallback:{llm_data.get('model', '-')}: semester"],
                }
            ]
        if isinstance(llm_fields, list):
            for f in llm_fields:
                fv = str(f or "").strip().lower()
                if fv in TABLE_FIELD_ALIASES:
                    detected_fields.append(fv)
        detected_fields = sorted(set(detected_fields))
        has_relevant_docs = bool(major_candidates or career_candidates or semester_candidates or detected_fields)
        if has_relevant_docs and confidence_summary == "low":
            confidence_summary = "medium"

    warning = None
    if not has_docs:
        warning = "Upload sumber dengan data yang relevan agar jawaban konsisten."
    elif not has_relevant_docs or confidence_summary == "low":
        warning = "Upload sumber dengan data yang relevan agar jawaban konsisten."
    else:
        # konflik kandidat jika skor dua teratas berdekatan
        sorted_major = sorted(major_scores.values(), reverse=True)
        sorted_career = sorted(career_scores.values(), reverse=True)
        major_conflict = len(sorted_major) > 1 and abs(sorted_major[0] - sorted_major[1]) <= 0.5
        career_conflict = len(sorted_career) > 1 and abs(sorted_career[0] - sorted_career[1]) <= 0.5
        if major_conflict or career_conflict:
            warning = "Data dokumen terdeteksi beragam. Upload sumber yang lebih relevan agar jawaban konsisten."

    question_candidates = _build_dynamic_questions(
        major_candidates=major_candidates,
        career_candidates=career_candidates,
        semester_candidates=semester_candidates,
        detected_fields=detected_fields,
        confidence_summary=confidence_summary,
    )

    return {
        "major_candidates": major_candidates,
        "career_candidates": career_candidates,
        "semester_candidates": semester_candidates,
        "detected_fields": detected_fields,
        "field_evidence": {
            **text_table_evidence,
            **{
                k: list(dict.fromkeys((text_table_evidence.get(k) or []) + (pdf_table_evidence.get(k) or [])))[:3]
                for k in set(text_table_evidence.keys()) | set(pdf_table_evidence.keys())
            },
        },
        "question_candidates": question_candidates,
        "llm_fallback_used": llm_fallback_used,
        "confidence_summary": confidence_summary,
        "has_relevant_docs": has_relevant_docs,
        "warning": warning,
    }
