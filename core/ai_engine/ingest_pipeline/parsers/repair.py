import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4


def row_confidence(row: Dict[str, Any], *, deps: Dict[str, Any]) -> Tuple[float, List[str]]:
    normalize_day_text = deps["_normalize_day_text"]
    norm = deps["_norm"]
    normalize_time_range = deps["_normalize_time_range"]
    is_valid_time_range = deps["_is_valid_time_range"]
    issues: List[str] = []
    score = 1.0
    hari = normalize_day_text(row.get("hari", ""))
    sesi = norm(row.get("sesi", ""))
    jam = normalize_time_range(row.get("jam", ""))
    mk = norm(row.get("mata_kuliah", ""))
    dosen = norm(row.get("dosen", ""))
    kls = norm(row.get("kelas", ""))
    smt = norm(row.get("semester", ""))
    ruang = norm(row.get("ruang", ""))
    if not hari:
        score -= 0.15; issues.append("missing_hari")
    if not sesi:
        score -= 0.12; issues.append("missing_sesi")
    if not jam or not is_valid_time_range(jam):
        score -= 0.25; issues.append("invalid_jam")
    if not mk:
        score -= 0.45; issues.append("missing_mata_kuliah")
    if not dosen:
        score -= 0.20; issues.append("missing_dosen")
    if not ruang:
        score -= 0.10; issues.append("missing_ruang")
    if not kls:
        score -= 0.08; issues.append("missing_kelas")
    if not smt:
        score -= 0.08; issues.append("missing_semester")
    return max(0.0, min(1.0, score)), issues


def build_repair_llm(*, deps: Dict[str, Any], logger) -> Optional[Any]:
    chat_cls = deps.get("ChatOpenAI")
    if chat_cls is None:
        return None
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return None
    model_name = os.environ.get("INGEST_REPAIR_MODEL") or os.environ.get("OPENROUTER_MODEL", "qwen/qwen3-next-80b-a3b-instruct:free")
    try:
        return chat_cls(
            openai_api_key=api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            model_name=model_name,
            temperature=float(os.environ.get("INGEST_REPAIR_TEMPERATURE", "0.0")),
            request_timeout=int(os.environ.get("INGEST_REPAIR_TIMEOUT", "60")),
            max_retries=int(os.environ.get("INGEST_REPAIR_RETRIES", "1")),
            default_headers={"HTTP-Referer": "http://localhost:8000", "X-Title": "AcademicChatbot-Ingest"},
        )
    except Exception as e:
        logger.warning(" Hybrid LLM init gagal: %s", e)
        return None


def extract_json_from_llm_response(text: str) -> Optional[List[Dict[str, Any]]]:
    if not text:
        return None
    raw = text.strip()
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    m = re.search(r"```json\s*(.*?)\s*```", raw, flags=re.DOTALL | re.IGNORECASE)
    if m:
        try:
            data = json.loads(m.group(1).strip())
            if isinstance(data, list):
                return data
        except Exception:
            pass
    m2 = re.search(r"(\[\s*\{.*\}\s*\])", raw, flags=re.DOTALL)
    if m2:
        try:
            data = json.loads(m2.group(1))
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return None


def repair_rows_with_llm(rows: List[Dict[str, Any]], source: str, *, deps: Dict[str, Any], logger) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not rows:
        return rows, {"enabled": False, "checked": 0, "repaired": 0}
    norm = deps["_norm"]
    row_conf = deps["_row_confidence"]
    extract_json = deps["_extract_json_from_llm_response"]
    enabled = (os.environ.get("PDF_HYBRID_LLM_REPAIR", "1") or "1").strip() in {"1", "true", "yes"}
    if not enabled:
        return rows, {"enabled": False, "checked": 0, "repaired": 0}
    llm = deps["_build_repair_llm"]()
    if llm is None:
        return rows, {"enabled": False, "checked": 0, "repaired": 0, "reason": "llm_unavailable"}
    threshold = float(os.environ.get("INGEST_REPAIR_THRESHOLD", "0.82"))
    max_rows = int(os.environ.get("INGEST_REPAIR_MAX_ROWS", "220"))
    batch_size = int(os.environ.get("INGEST_REPAIR_BATCH_SIZE", "25"))
    candidates: List[Tuple[int, Dict[str, Any], List[str], float]] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        if not (norm(row.get("mata_kuliah", "")) or norm(row.get("kode", ""))):
            continue
        conf, issues = row_conf(row)
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
            payload.append({"idx": i, "issues": issues, "confidence": round(conf, 3), "row": {k: norm(row.get(k, "")) for k in ["hari", "sesi", "jam", "ruang", "semester", "mata_kuliah", "sks", "kelas", "dosen", "kode"]} | {"page": int(row.get("page", 0) or 0)}})
        prompt = (
            "Anda memperbaiki data jadwal kuliah hasil OCR/PDF.\n"
            "Tugas: perbaiki hanya field yang rusak/kosong. Jangan halusinasi.\n"
            "Jika tidak yakin, biarkan nilai lama.\n"
            "Wajib output JSON ARRAY valid tanpa teks tambahan.\n"
            "Setiap item wajib punya keys: idx, hari, sesi, jam, ruang, semester, mata_kuliah, sks, kelas, dosen, kode.\n"
            "Format jam wajib HH:MM-HH:MM.\n"
            "Hari gunakan: SENIN/SELASA/RABU/KAMIS/JUMAT/SABTU/MINGGU jika bahasa Indonesia.\n"
            f"Source: {source}\nRun: {run_id}\nInput rows:\n{json.dumps(payload, ensure_ascii=True)}"
        )
        try:
            out = llm.invoke(prompt)
            content = out.content if hasattr(out, "content") else str(out)
            parsed = extract_json(content if isinstance(content, str) else str(content))
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
                updates = {k: norm(item.get(k, row.get(k, ""))) for k in ["hari", "sesi", "jam", "ruang", "semester", "mata_kuliah", "sks", "kelas", "dosen", "kode"]}
                before_conf, _ = row_conf(row)
                row.update({k: v for k, v in updates.items() if v != ""})
                after_conf, after_issues = row_conf(row)
                row["_confidence"] = after_conf
                row["_issues"] = after_issues
                if after_conf > before_conf:
                    repaired += 1
        except Exception as e:
            logger.warning(" Hybrid LLM repair batch gagal: %s", e)
    return rows, {"enabled": True, "checked": len(rows), "candidates": len(candidates), "repaired": repaired, "run_id": run_id}

