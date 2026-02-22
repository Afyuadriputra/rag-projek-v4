from __future__ import annotations

import os
from typing import Any, Dict, List

from ...llm import build_llm, get_backup_models, get_runtime_openrouter_config, invoke_text


def _env_bool(name: str, default: bool = False) -> bool:
    val = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return val in {"1", "true", "yes", "on"}


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


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

    course_names = list(
        dict.fromkeys([_normalize_text(x.get("mata_kuliah")) for x in facts if _normalize_text(x.get("mata_kuliah"))])
    )
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


def polish(
    *,
    query: str,
    deterministic_answer: str,
    facts: List[Dict[str, Any]],
    doc_type: str,
    style_hint: str = "factual",
    invoke_polisher_fn: Any | None = None,
    validate_polished_fn: Any | None = None,
) -> Dict[str, Any]:
    if not _env_bool("RAG_ANALYTICS_POLISH_ENABLED", default=True):
        return {"answer": deterministic_answer, "validation": "skipped"}

    facts_payload = str(facts[: min(len(facts), 500)])
    style = _normalize_text(style_hint).lower()
    style_instruction = (
        "Gunakan nada evaluatif yang suportif dan beri insight singkat berbasis data."
        if style == "evaluative"
        else "Gunakan nada informatif ringkas dan fokus pada fakta."
    )
    prompt = (
        "Anda adalah Asisten Akademik.\n"
        "Data JSON di bawah ini adalah FAKTA MUTLAK dari sistem database terstruktur.\n"
        "Tugas Anda HANYA menyusun data ini menjadi kalimat yang ramah untuk pengguna.\n"
        "DILARANG KERAS menambah, mengurangi, atau mengubah nama mata kuliah/nilai/jam.\n"
        "Jika data JSON kosong, katakan: 'Maaf, data tidak ditemukan di dokumen Anda'.\n"
        "Pertahankan format markdown dengan tabel.\n\n"
        f"Gaya jawaban: {style}\n"
        f"Instruksi gaya: {style_instruction}\n\n"
        f"Jenis data: {doc_type}\n"
        f"Pertanyaan user: {query}\n"
        f"Data JSON: {facts_payload}\n\n"
        f"Draf jawaban deterministik:\n{deterministic_answer}\n"
    )
    invoker = invoke_polisher_fn or _invoke_polisher_llm
    validator = validate_polished_fn or _validate_polished_answer
    polished = invoker(prompt)
    if not polished:
        return {"answer": deterministic_answer, "validation": "failed_fallback"}
    if _env_bool("RAG_ANALYTICS_POST_VALIDATE_ENABLED", default=True):
        if not validator(polished, facts):
            return {"answer": deterministic_answer, "validation": "failed_fallback"}
    return {"answer": polished, "validation": "passed"}
