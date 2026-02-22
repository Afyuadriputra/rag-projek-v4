from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, List

from ...infrastructure.llm_client import invoke_with_model_fallback
from ...utils import has_interactive_sections, looks_like_markdown_table, polish_answer_text_light


def build_prompt(*, query: str, docs: List[Any], max_chars: int = 6000) -> str:
    chunks: List[str] = []
    total = 0
    for idx, doc in enumerate(docs[:8], start=1):
        text = str(getattr(doc, "page_content", "") or "").strip()
        if not text:
            continue
        remaining = max_chars - total
        if remaining <= 0:
            break
        piece = text[:remaining]
        chunks.append(f"[DOC {idx}]\n{piece}")
        total += len(piece)

    context = "\n\n".join(chunks).strip() or "(kosong)"
    return (
        "Anda adalah asisten akademik. Jawab ringkas, akurat, dan hanya berdasarkan konteks.\n"
        "Jika konteks tidak cukup, katakan data tidak cukup.\n\n"
        f"Pertanyaan:\n{query}\n\n"
        f"Konteks:\n{context}\n\n"
        "Jawaban:"
    )


def build_sources(docs: List[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for doc in docs:
        meta = dict(getattr(doc, "metadata", {}) or {})
        source = str(
            meta.get("source")
            or meta.get("title")
            or meta.get("doc_title")
            or meta.get("file_name")
            or "document"
        ).strip()
        item: Dict[str, Any] = {"source": source}
        page = meta.get("page")
        if page is not None:
            item["page"] = page
        out.append(item)
    return out


def _env_bool(name: str, default: bool = False) -> bool:
    val = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return val in {"1", "true", "yes", "on"}


def _has_citation(text: str) -> bool:
    candidate = str(text or "")
    return "[source:" in candidate.lower()


def _should_run_citation_enrichment() -> bool:
    optimized = _env_bool("RAG_SEMANTIC_OPTIMIZED_RETRIEVAL_ENABLED", default=False)
    if optimized:
        # Keep legacy parity by default: citation enrichment stays ON unless explicitly disabled.
        return _env_bool("RAG_OPT_CITATION_ENRICHMENT_ENABLED", default=True)
    return _env_bool("RAG_CITATION_ENRICHMENT_ENABLED", default=True)


def _append_unresolved_note(answer: str, unresolved_mentions: List[str]) -> str:
    if not unresolved_mentions:
        return answer
    missing = ", ".join([f"@{m}" for m in unresolved_mentions])
    return (
        f"{answer}\n\n"
        f"Catatan rujukan: ada file yang tidak ditemukan ({missing})."
    ).strip()


def _append_doc_referenced_weak_context_note(answer: str, mode: str, docs: List[Any]) -> str:
    if str(mode or "") != "doc_referenced" or docs:
        return answer
    return (
        f"{answer}\n\n"
        "Catatan: Aku belum menemukan konteks kuat dari file rujukan, jadi jawaban ini "
        "lebih bersifat panduan umum."
    ).strip()


def _is_multi_semester_recap_query(query: str) -> bool:
    ql = str(query or "").lower()
    if "semester" not in ql:
        return False
    has_recap = any(k in ql for k in ["rekap", "ringkas", "rangkum", "semua", "keseluruhan"])
    has_range = bool(re.search(r"semester\s*\d+\s*(?:-|s/d|sd|sampai|to)\s*\d+", ql))
    has_words = any(k in ql for k in ["awal sampai akhir", "semua semester", "dari semester"])
    has_course_focus = any(k in ql for k in ["mata kuliah", "sks", "transkrip", "khs", "krs"])
    return (has_recap or has_range or has_words) and has_course_focus


def _build_citation_prompt(answer: str) -> str:
    return (
        "Perbaiki jawaban agar setiap klaim faktual spesifik menyertakan sitasi `[source: ...]` "
        "berdasarkan konteks yang sama. Jangan tambah fakta baru.\n\n"
        f"Jawaban saat ini:\n{answer}"
    )


def _build_table_enrichment_prompt(answer: str) -> str:
    return f"""
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


def _build_prompt_query(query: str, resolved_titles: List[str]) -> str:
    q_for_prompt = str(query or "").strip()
    if resolved_titles:
        q_for_prompt = (
            f"{q_for_prompt}\n\n"
            f"[Referenced Documents]\n{', '.join(resolved_titles)}\n"
            "Instruksi: prioritaskan dokumen rujukan ini sebagai sumber utama; "
            "jika tidak cukup, jelaskan batasannya lalu beri fallback umum."
        )
    if _is_multi_semester_recap_query(q_for_prompt):
        q_for_prompt = (
            f"{q_for_prompt}\n\n"
            "[Instruksi Rekap Ketat]\n"
            "- Gunakan HANYA data di context.\n"
            "- Jangan hilangkan baris mata kuliah jika ada di context.\n"
            "- Jangan menukar semester antar mata kuliah.\n"
            "- Jika kolom kosong, tulis '-'.\n"
            "- Jangan hitung total SKS jika tidak diminta eksplisit.\n"
        )
    return q_for_prompt


def _resolve_primary_model(mode: str) -> str | None:
    if str(mode or "") == "doc_referenced":
        doc_model = str(os.environ.get("OPENROUTER_MODEL_DOC", "")).strip()
        return doc_model or None
    fast_model = str(os.environ.get("OPENROUTER_MODEL_FAST", "")).strip()
    return fast_model or None


def run_answer(
    *,
    query: str,
    docs: List[Any],
    mode: str,
    resolved_titles: List[str],
    unresolved_mentions: List[str],
) -> Dict[str, Any]:
    llm = invoke_with_model_fallback(
        prompt=build_prompt(query=_build_prompt_query(query, resolved_titles), docs=docs),
        primary_model=_resolve_primary_model(mode),
    )
    if not llm.get("ok"):
        return llm

    answer = str(llm.get("text") or "").strip() or "Maaf, tidak ada jawaban."

    # Legacy parity: try citation enrichment whenever context exists and citation is absent.
    if docs and (not _has_citation(answer)) and _should_run_citation_enrichment():
        cited = invoke_with_model_fallback(
            prompt=_build_citation_prompt(answer),
            primary_model=str(llm.get("model") or ""),
        )
        if cited.get("ok"):
            cited_text = str(cited.get("text") or "").strip()
            if cited_text and _has_citation(cited_text):
                answer = cited_text

    if _env_bool("RAG_ENABLE_TABLE_ENRICHMENT", default=False):
        if looks_like_markdown_table(answer) and (not has_interactive_sections(answer)):
            enriched = invoke_with_model_fallback(
                prompt=_build_table_enrichment_prompt(answer),
                primary_model=str(llm.get("model") or ""),
            )
            if enriched.get("ok"):
                enriched_text = str(enriched.get("text") or "").strip()
                if enriched_text:
                    answer = enriched_text

    answer = _append_doc_referenced_weak_context_note(answer, mode=mode, docs=docs)
    answer = _append_unresolved_note(answer, unresolved_mentions)
    answer = polish_answer_text_light(answer)
    return {
        "ok": True,
        "text": answer,
        "model": str(llm.get("model") or ""),
        "fallback_used": bool(llm.get("fallback_used")),
        "llm_ms": int(llm.get("llm_ms") or 0),
    }


def run_answer_with_callbacks(
    *,
    query: str,
    docs: List[Any],
    mode: str,
    resolved_titles: List[str],
    unresolved_mentions: List[str],
    runtime_cfg: Dict[str, Any],
    get_backup_models_fn: Any,
    build_llm_fn: Any,
    create_chain_fn: Any,
    invoke_text_fn: Any,
    retry_sleep_ms: int = 0,
) -> Dict[str, Any]:
    runtime_cfg_for_mode = dict(runtime_cfg or {})
    primary = _resolve_primary_model(mode)
    if primary:
        runtime_cfg_for_mode["model"] = primary

    candidates = get_backup_models_fn(
        str(runtime_cfg_for_mode.get("model") or ""),
        runtime_cfg_for_mode.get("backup_models"),
    )

    last_error = ""
    for idx, model_name in enumerate(candidates):
        t0 = time.time()
        try:
            llm = build_llm_fn(model_name, runtime_cfg_for_mode)
            qa_chain = create_chain_fn(llm)
            result = qa_chain.invoke({"input": _build_prompt_query(query, resolved_titles), "context": docs})
            if isinstance(result, dict):
                answer = result.get("answer") or result.get("output_text") or ""
            else:
                answer = str(result)
            answer = str(answer or "").strip() or "Maaf, tidak ada jawaban."

            if docs and (not _has_citation(answer)):
                cited = str(invoke_text_fn(llm, _build_citation_prompt(answer)) or "").strip()
                if cited and _has_citation(cited):
                    answer = cited

            if _env_bool("RAG_ENABLE_TABLE_ENRICHMENT", default=False):
                if looks_like_markdown_table(answer) and (not has_interactive_sections(answer)):
                    enriched = str(invoke_text_fn(llm, _build_table_enrichment_prompt(answer)) or "").strip()
                    if enriched:
                        answer = enriched

            answer = _append_doc_referenced_weak_context_note(answer, mode=mode, docs=docs)
            answer = _append_unresolved_note(answer, unresolved_mentions)
            answer = polish_answer_text_light(answer)
            return {
                "ok": True,
                "text": answer,
                "model": str(model_name or ""),
                "fallback_used": idx > 0,
                "llm_ms": int(max((time.time() - t0) * 1000, 0)),
            }
        except Exception as exc:
            last_error = str(exc)
            if idx < len(candidates) - 1:
                time.sleep(max(float(retry_sleep_ms) / 1000.0, 0.0))
                continue

    return {
        "ok": False,
        "text": "",
        "model": "",
        "fallback_used": len(candidates) > 1,
        "llm_ms": 0,
        "error": last_error,
    }
