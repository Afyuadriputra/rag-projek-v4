import os
import re
import time
import logging
from typing import Dict, Any, List

from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate
from django.core.cache import cache
from core.models import AcademicDocument

from ..config import get_vectorstore
from .hybrid import retrieve_dense, retrieve_sparse_bm25, fuse_rrf
from .rerank import rerank_documents
from .rules import _SEMESTER_RE, infer_doc_type
from .intent_router import route_intent
from .structured_analytics import run_structured_analytics, polish_structured_answer
from .utils import build_sources_from_docs
from .llm import (
    get_runtime_openrouter_config,
    get_backup_models,
    build_llm,
    invoke_text,
    llm_fallback_message,
)
from .pipelines.semantic.answer import run_answer_with_callbacks
from .pipelines.semantic.run import run_retrieval
from .pipelines.semantic import run as _semantic_run_module
from .pipelines.semantic import retrieve as _semantic_retrieve_module
from .pipelines.semantic import rerank as _semantic_rerank_module
from .domain.models import QueryContext
from .prompt import CHATBOT_SYSTEM_PROMPT
from .infrastructure.metrics import emit_rag_metric
from .config.settings import get_retrieval_settings

logger = logging.getLogger(__name__)
_STRICT_TRANSCRIPT_MARKERS = [
    "transkrip",
    "khs",
    "tabel mentah",
    "data mentah",
]


def _env_bool(name: str, default: bool = False) -> bool:
    val = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return val in {"1", "true", "yes", "on"}


def _build_chroma_filter(
    user_id: int,
    query: str,
    doc_ids: List[int] | None = None,
    forced_doc_types: List[str] | None = None,
) -> Dict[str, Any]:
    ql = (query or "").lower()

    def _is_multi_semester_recap_query(text: str) -> bool:
        has_recap = any(k in text for k in ["rekap", "ringkas", "rangkum", "semua", "keseluruhan"])
        has_semester = "semester" in text
        has_range = bool(re.search(r"semester\s*\d+\s*[-s/dampai]+\s*\d+", text))
        has_words = any(k in text for k in ["awal sampai akhir", "semua semester", "dari semester"])
        return has_semester and (has_recap or has_range or has_words)

    multi_semester_recap = _is_multi_semester_recap_query(ql)
    base_filter: Dict[str, Any] = {"user_id": str(user_id)}
    if doc_ids:
        base_filter["doc_id"] = {"$in": [str(x) for x in doc_ids]}
    sem_match = _SEMESTER_RE.search(query)
    if sem_match and not multi_semester_recap:
        try:
            base_filter["semester"] = int(sem_match.group(1))
        except Exception:
            pass
    if forced_doc_types:
        vals = [str(x).strip() for x in forced_doc_types if str(x).strip()]
        if vals:
            base_filter["doc_type"] = {"$in": vals}
    else:
        doc_type = infer_doc_type(query)
        # Untuk rekap lintas semester, hindari filter doc_type agar konteks tidak terpotong.
        if doc_type and not multi_semester_recap:
            base_filter["doc_type"] = doc_type
    if len(base_filter) == 1:
        return base_filter
    return {"$and": [{"user_id": str(user_id)}] + [{k: v} for k, v in base_filter.items() if k != "user_id"]}


def _extract_doc_mentions(query: str) -> tuple[str, List[str]]:
    q = (query or "").strip()
    if not q:
        return "", []

    # 1) Prioritas mention dengan ekstensi file (lebih presisi untuk nama dokumen panjang).
    ext_pattern = re.compile(
        r"@([A-Za-z0-9._\- ]+?\.(?:pdf|xlsx|xls|csv|md|txt))\b",
        re.IGNORECASE,
    )
    raw_mentions = [m.group(1).strip() for m in ext_pattern.finditer(q) if m.group(1).strip()]
    clean_q = ext_pattern.sub("", q)

    # 2) Fallback mention tanpa ekstensi (contoh: @jadwal), tanpa spasi agar tidak menangkap kalimat.
    token_pattern = re.compile(r"@([A-Za-z0-9._\-]{2,120})")
    extra_mentions = [m.group(1).strip() for m in token_pattern.finditer(clean_q) if m.group(1).strip()]
    if extra_mentions:
        raw_mentions.extend(extra_mentions)
        clean_q = token_pattern.sub("", clean_q)

    clean_q = re.sub(r"\s{2,}", " ", clean_q).strip()
    return clean_q, list(dict.fromkeys(raw_mentions))


def _normalize_doc_key(text: str) -> str:
    t = str(text or "").strip().lower()
    t = re.sub(r"\.(pdf|xlsx|xls|csv|md|txt)$", "", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def _has_user_documents(user_id: int) -> bool:
    settings = get_retrieval_settings()
    ttl_s = max(int(settings.rag_user_docs_cache_ttl_s), 0)
    ck = f"rag:user_has_docs:{int(user_id)}"
    try:
        cached = cache.get(ck)
        if cached is True:
            return True
        if cached is False:
            # Negative cache bisa stale setelah upload/re-ingest; verifikasi ringan.
            has_docs_now = AcademicDocument.objects.filter(user_id=user_id).exists()
            if has_docs_now:
                cache.set(ck, True, ttl_s)
                return True
            return False
        has_docs = AcademicDocument.objects.filter(user_id=user_id).exists()
        cache.set(ck, bool(has_docs), ttl_s)
        return bool(has_docs)
    except Exception:
        return False


def _record_metric(**payload: Any) -> None:
    mode = str(payload.get("mode") or "")
    if "pipeline" not in payload:
        if mode.startswith("structured_"):
            payload["pipeline"] = "structured_analytics"
        elif mode in {"guard", "out_of_domain"}:
            payload["pipeline"] = "route_guard"
        else:
            payload["pipeline"] = "rag_semantic"
    payload.setdefault("intent_route", "default_rag")
    payload.setdefault("validation", "not_applicable")
    payload.setdefault("answer_mode", "factual")
    emit_rag_metric(payload)


def _resolve_user_doc_mentions(user_id: int, mentions: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "resolved_doc_ids": [],
        "resolved_titles": [],
        "unresolved_mentions": [],
        "ambiguous_mentions": [],
    }
    if not mentions:
        return out

    try:
        docs = list(
            AcademicDocument.objects.filter(user_id=user_id).values("id", "title")
        )
    except Exception:
        docs = []
    if not docs:
        out["unresolved_mentions"] = mentions
        return out

    doc_norm = []
    for d in docs:
        title = str(d.get("title") or "")
        doc_norm.append((int(d["id"]), title, _normalize_doc_key(title)))

    resolved_ids: List[int] = []
    resolved_titles: List[str] = []
    unresolved: List[str] = []
    ambiguous: List[str] = []

    for m in mentions:
        mk = _normalize_doc_key(m)
        if not mk:
            unresolved.append(m)
            continue

        exact = [(did, title) for (did, title, nk) in doc_norm if nk == mk]
        if len(exact) == 1:
            resolved_ids.append(exact[0][0])
            resolved_titles.append(exact[0][1])
            continue
        if len(exact) > 1:
            ambiguous.append(m)
            continue

        contains = [(did, title) for (did, title, nk) in doc_norm if mk in nk or nk in mk]
        if len(contains) == 1:
            resolved_ids.append(contains[0][0])
            resolved_titles.append(contains[0][1])
        elif len(contains) > 1:
            ambiguous.append(m)
        else:
            unresolved.append(m)

    out["resolved_doc_ids"] = list(dict.fromkeys(resolved_ids))
    out["resolved_titles"] = list(dict.fromkeys(resolved_titles))
    out["unresolved_mentions"] = unresolved
    out["ambiguous_mentions"] = ambiguous
    return out


def _build_mention_ambiguous_response(mentions: List[str]) -> str:
    mention_text = ", ".join([f"`@{m}`" for m in mentions[:3]])
    return (
        "## Ringkasan\n"
        f"Aku menemukan rujukan dokumen yang ambigu: {mention_text}. Biar akurat, tolong tulis nama file lebih spesifik.\n\n"
        "## Opsi Lanjut\n"
        "- Tulis ulang dengan nama file lebih lengkap (contoh: `@Jadwal Mata Kuliah Semester GANJIL TA.2024-2025.pdf`).\n"
        "- Atau lanjut tanpa rujukan dokumen, nanti Aku jawab secara umum dulu."
    )


def _dedup_docs(docs: List[Any]) -> List[Any]:
    seen = set()
    out = []
    for d in docs:
        meta = getattr(d, "metadata", {}) or {}
        key = (
            str(meta.get("doc_id") or ""),
            str(meta.get("source") or ""),
            str(meta.get("page") or ""),
            str(getattr(d, "page_content", "") or "")[:120],
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out


def _rewrite_queries(query: str) -> List[str]:
    q = (query or "").strip()
    if not q:
        return []
    variants = [q]
    if "jam" in q.lower() and "waktu" not in q.lower():
        variants.append(q + " waktu kuliah")
    if "hari" in q.lower() and "day" not in q.lower():
        variants.append(q + " day schedule")
    if "kelas" in q.lower() and "ruang" not in q.lower():
        variants.append(q + " ruang kelas")
    return list(dict.fromkeys([v.strip() for v in variants if v.strip()]))[:3]


_CITATION_RE = re.compile(r"\[(?:source:[^\]]+|\d+)\]", re.IGNORECASE)


def _has_citation(answer: str) -> bool:
    return bool(_CITATION_RE.search(str(answer or "")))


def _needs_doc_grounding(query: str) -> bool:
    doc_type = infer_doc_type(query)
    return doc_type in {"schedule", "transcript"}


def _is_personal_document_query(query: str) -> bool:
    ql = (query or "").lower()
    personal_markers = [
        "saya",
        "aku",
        "punya saya",
        "milik saya",
        "ipk saya",
        "ips saya",
        "transkrip saya",
        "jadwal saya",
        "nilai saya",
    ]
    return any(m in ql for m in personal_markers)


def _classify_transcript_answer_mode(query: str) -> str:
    ql = str(query or "").lower()
    factual_markers = [
        "berapa",
        "nilai",
        "ipk",
        "ips",
        "sks",
        "semester",
        "daftar",
        "rekap",
        "matakuliah",
        "mata kuliah",
        "khs",
        "transkrip",
    ]
    evaluative_markers = [
        "bagaimana",
        "gimana",
        "evaluasi",
        "analisis",
        "progress",
        "perkembangan",
        "saran",
        "rekomendasi",
        "kelebihan",
        "kekurangan",
        "perbaiki",
        "strategi",
    ]
    if any(k in ql for k in evaluative_markers):
        return "evaluative"
    if any(k in ql for k in factual_markers):
        return "factual"
    return "general"


def _build_no_grounding_response() -> str:
    return (
        "## Ringkasan\n"
        "Aku belum menemukan data dokumen yang cukup untuk menjawab pertanyaan personalmu secara akurat.\n\n"
        "## Opsi Lanjut\n"
        "- Pastikan dokumen KHS/Transkrip/Jadwal sudah terunggah dan berhasil diproses.\n"
        "- Jika dokumen sudah ada, coba sebutkan nama file dengan `@nama_file` agar pencarian lebih presisi.\n"
        "- Kamu juga bisa ulang pertanyaan dengan detail semester atau mata kuliah."
    )


def _contains_any_pattern(text: str, patterns: List[str]) -> List[str]:
    hits: List[str] = []
    for p in patterns:
        if re.search(p, text, flags=re.IGNORECASE):
            hits.append(p)
    return hits


def _classify_query_safety(query: str) -> Dict[str, Any]:
    q = (query or "").strip()
    ql = q.lower()
    if not q:
        return {"decision": "allow", "reason": "empty_query", "tags": []}

    crime_patterns = [
        r"\bjudi\b",
        r"\bjudi online\b",
        r"\bslot\b",
        r"\btaruhan\b",
        r"\bphishing\b",
        r"\bcarding\b",
        r"\bscam\b",
        r"\bpenipuan\b",
        r"\bhack(?:ing)?\b",
        r"\bmeretas?\b",
        r"\bbobol\b",
        r"\bbypass\b",
        r"\bexploit\b",
        r"\bnarkoba\b",
    ]
    political_persuasion_patterns = [
        r"\bkampanye\b",
        r"\bpropaganda\b",
        r"\bmanipulasi opini\b",
        r"\bblack campaign\b",
        r"\bmenangkan calon\b",
        r"\bserang lawan politik\b",
    ]

    crime_hits = _contains_any_pattern(ql, crime_patterns)
    if crime_hits:
        return {"decision": "refuse_crime", "reason": "crime_or_harmful_request", "tags": crime_hits}

    political_hits = _contains_any_pattern(ql, political_persuasion_patterns)
    if political_hits:
        return {"decision": "refuse_political", "reason": "political_persuasion_request", "tags": political_hits}

    # Redirect pertanyaan absurd/non-akademik yang biasanya tidak bernilai untuk asisten kampus.
    weird_markers = [
        "ramalan hoki",
        "cara jadi dukun",
        "santet",
        "pesugihan",
        "cara hipnotis orang",
    ]
    if any(m in ql for m in weird_markers):
        return {"decision": "redirect_weird", "reason": "out_of_scope_weird_query", "tags": weird_markers}

    return {"decision": "allow", "reason": "safe", "tags": []}


def _build_refusal_response(decision: str, query: str) -> str:
    if decision == "refuse_crime":
        return (
            "## Ringkasan\n"
            "Aku paham Kamu lagi cari arah, dan itu valid. Tapi Aku tidak bisa bantu hal yang melanggar hukum atau berpotensi membahayakan.\n\n"
            "- Aku bisa bantu Kamu cari jalur akademik yang legal dan tetap realistis buat masa depan.\n"
            "- Kita bisa ubah fokus ke skill yang benar-benar kepakai di dunia kerja.\n\n"
            "## Opsi Lanjut\n"
            "- Kalau goal Kamu di HR/Tech/Bisnis, Aku bisa rekomendasikan jurusan dan roadmap skill yang valid.\n"
            "- Aku juga bisa bantu rencana semester singkat 3-6 bulan biar progres kamu jelas.\n"
            "- Kalau mau, kirim target kariermu, nanti Aku bikinin langkah konkretnya."
        )
    return (
        "## Ringkasan\n"
        "Aku tidak bisa bantu strategi propaganda atau manipulasi politik praktis. Namun, Aku tetap bisa bantu dari sisi akademik yang netral dan edukatif.\n\n"
        "- Fokusku adalah membantu Kamu memahami topik secara objektif.\n"
        "- Kita tetap bisa bahas jalur studi dan prospek karier yang relevan.\n\n"
        "## Opsi Lanjut\n"
        "- Aku bisa jelaskan jurusan Ilmu Politik, Hukum, Administrasi Publik, dan prospek kariernya.\n"
        "- Aku juga bisa bantu ringkas konsep sistem politik secara objektif untuk belajar."
    )


def _build_redirect_response(query: str) -> str:
    return (
        "## Ringkasan\n"
        "Pertanyaan tadi agak di luar fokus akademik kampus. Biar tetap berguna, Aku bantu arahkan ke hal yang lebih relevan untuk kuliah dan karier Kamu.\n\n"
        "- Kita bisa ubah jadi pertanyaan yang hasilnya benar-benar kepakai.\n"
        "- Aku siap bantu dengan jawaban yang ringkas dan konkret.\n\n"
        "## Opsi Lanjut\n"
        "- Mau Aku bantu pilih jurusan sesuai minat dan target kerja?\n"
        "- Atau Aku buatin rencana belajar singkat biar IPK dan skill kamu naik?"
    )


def _polish_answer_text(answer: str) -> str:
    text = str(answer or "").strip()
    if not text:
        return text

    # Perapihan typo umum ringan (tanpa mengubah makna inti).
    typo_map = {
        "kiatar": "maksud",
        "prosfek": "prospek",
        "karir": "karier",
        "di karenakan": "dikarenakan",
    }
    for wrong, right in typo_map.items():
        text = re.sub(rf"\b{re.escape(wrong)}\b", right, text, flags=re.IGNORECASE)

    # Rapikan spasi berlebih.
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _ask_bot_legacy(user_id, query, request_id: str = "-") -> Dict[str, Any]:
    from .application.chat_service import ask_bot_legacy_compat

    return ask_bot_legacy_compat(user_id=int(user_id), query=str(query or ""), request_id=str(request_id or "-"))


def run_semantic_legacy_only(
    *,
    user_id: int,
    query: str,
    request_id: str,
    intent_route: str,
    has_docs_hint: bool,
    resolved_doc_ids: List[int],
    resolved_titles: List[str],
    unresolved_mentions: List[str],
    ambiguous_mentions: List[str],
    runtime_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    q = str(query or "").strip()
    has_docs = bool(has_docs_hint)
    mode = "llm_only"
    if has_docs and resolved_doc_ids:
        mode = "doc_referenced"
    elif has_docs:
        mode = "doc_background"

    dense_all: List[Any] = []
    bm25_hits = 0
    retrieval_ms = 0
    rerank_ms = 0
    top_score = 0.0
    docs: List[Any] = []

    if mode != "llm_only":
        vectorstore = get_vectorstore()
        forced_doc_types = ["guideline", "general"] if intent_route == "semantic_policy" else None
        chroma_where = _build_chroma_filter(
            user_id=user_id,
            query=q,
            doc_ids=resolved_doc_ids if resolved_doc_ids else None,
            forced_doc_types=forced_doc_types,
        )

        # Bridge legacy patch targets into the semantic pipeline module.
        original_dense = _semantic_retrieve_module.retrieve_dense_docs
        original_hybrid = _semantic_retrieve_module.retrieve_hybrid_docs
        original_rerank = _semantic_rerank_module.rerank
        original_run_dense = _semantic_run_module.retrieve_dense_docs
        original_run_hybrid = _semantic_run_module.retrieve_hybrid_docs
        original_run_rerank = _semantic_run_module.rerank

        def _retrieve_dense_docs_proxy(vectorstore: Any, query: str, k: int, filter_where: Dict[str, Any] | None = None):
            return retrieve_dense(vectorstore=vectorstore, query=query, k=k, filter_where=filter_where)

        def _retrieve_hybrid_docs_proxy(query: str, dense_scored: List[Any], docs_pool: List[Any], bm25_k: int):
            sparse_scored = retrieve_sparse_bm25(query=query, docs_pool=docs_pool, k=bm25_k)
            return fuse_rrf(dense_docs=dense_scored, sparse_docs=sparse_scored, k=bm25_k)

        def _rerank_proxy(query: str, docs: List[Any], model_name: str, top_n: int):
            return rerank_documents(query=query, docs=docs, model_name=model_name, top_n=top_n)

        _semantic_retrieve_module.retrieve_dense_docs = _retrieve_dense_docs_proxy
        _semantic_retrieve_module.retrieve_hybrid_docs = _retrieve_hybrid_docs_proxy
        _semantic_rerank_module.rerank = _rerank_proxy
        _semantic_run_module.retrieve_dense_docs = _retrieve_dense_docs_proxy
        _semantic_run_module.retrieve_hybrid_docs = _retrieve_hybrid_docs_proxy
        _semantic_run_module.rerank = _rerank_proxy
        try:
            retrieval = run_retrieval(
                vectorstore=vectorstore,
                query_ctx=QueryContext(
                    user_id=int(user_id),
                    query=q,
                    request_id=str(request_id or "-"),
                    doc_ids=list(resolved_doc_ids or []),
                ),
                filter_where=chroma_where,
                has_docs_hint=bool(has_docs_hint),
            )
        finally:
            _semantic_retrieve_module.retrieve_dense_docs = original_dense
            _semantic_retrieve_module.retrieve_hybrid_docs = original_hybrid
            _semantic_rerank_module.rerank = original_rerank
            _semantic_run_module.retrieve_dense_docs = original_run_dense
            _semantic_run_module.retrieve_hybrid_docs = original_run_hybrid
            _semantic_run_module.rerank = original_run_rerank

        docs = list(retrieval.get("docs") or [])
        dense_all = [d for d, _ in list(retrieval.get("dense_scored") or [])]
        bm25_hits = int(retrieval.get("bm25_hits") or 0)
        retrieval_ms = int(retrieval.get("retrieval_ms") or 0)
        rerank_ms = int(retrieval.get("rerank_ms") or 0)
        top_score = float(retrieval.get("top_score") or 0.0)
        mode = str(retrieval.get("mode") or mode)
    query_preview = q if len(q) <= 140 else q[:140] + "..."
    logger.info(
        " RAG retrieval done mode=%s dense_hits=%s bm25_hits=%s final_docs=%s top_score=%.4f retrieval_ms=%s rerank_ms=%s has_docs=%s docs_used=%s q='%s'",
        mode,
        len(dense_all),
        bm25_hits,
        len(docs),
        top_score,
        retrieval_ms,
        rerank_ms,
        has_docs,
        bool(docs),
        query_preview,
        extra={"request_id": request_id},
    )

    sources = build_sources_from_docs(docs)
    if (not docs) and _needs_doc_grounding(q) and _is_personal_document_query(q):
        answer = _polish_answer_text(_build_no_grounding_response())
        _record_metric(
            request_id=request_id,
            user_id=user_id,
            mode=mode,
            query_len=len(q),
            dense_hits=len(dense_all),
            bm25_hits=bm25_hits,
            final_docs=0,
            retrieval_ms=retrieval_ms,
            rerank_ms=rerank_ms,
            llm_model="",
            llm_time_ms=0,
            fallback_used=False,
            source_count=0,
            pipeline="rag_semantic",
            intent_route=intent_route,
            validation="no_grounding_evidence",
            answer_mode="factual",
            status_code=200,
        )
        return {
            "answer": answer,
            "sources": [],
            "meta": {
                "mode": mode,
                "pipeline": "rag_semantic",
                "intent_route": intent_route,
                "validation": "no_grounding_evidence",
                "analytics_stats": {},
                "referenced_documents": resolved_titles,
                "unresolved_mentions": unresolved_mentions,
                "ambiguous_mentions": ambiguous_mentions,
                "retrieval_ms": retrieval_ms,
                "llm_time_ms": 0,
                "stage_timings_ms": {"retrieval_ms": retrieval_ms, "llm_ms": 0},
            },
        }

    prompt = ChatPromptTemplate.from_template(CHATBOT_SYSTEM_PROMPT)

    def _create_legacy_chain(llm: Any) -> Any:
        return create_stuff_documents_chain(llm, prompt)

    semantic_answer = run_answer_with_callbacks(
        query=q,
        docs=docs,
        mode=mode,
        resolved_titles=resolved_titles,
        unresolved_mentions=unresolved_mentions,
        runtime_cfg=runtime_cfg,
        get_backup_models_fn=get_backup_models,
        build_llm_fn=build_llm,
        create_chain_fn=_create_legacy_chain,
        invoke_text_fn=invoke_text,
        retry_sleep_ms=max(int(get_retrieval_settings().rag_retry_sleep_ms), 0),
    )
    if not semantic_answer.get("ok"):
        llm_model_name = str(semantic_answer.get("model") or "")
        llm_time_ms = int(semantic_answer.get("llm_ms") or 0)
        fallback_used = bool(semantic_answer.get("fallback_used"))
        last_error = str(semantic_answer.get("error") or "")
        _record_metric(
            request_id=request_id,
            user_id=user_id,
            mode="semantic_policy" if intent_route == "semantic_policy" else mode,
            query_len=len(q),
            dense_hits=len(dense_all),
            bm25_hits=bm25_hits,
            final_docs=len(docs),
            retrieval_ms=retrieval_ms,
            rerank_ms=rerank_ms,
            llm_model=llm_model_name,
            llm_time_ms=llm_time_ms,
            fallback_used=fallback_used,
            source_count=len(sources),
            pipeline="rag_semantic",
            intent_route=intent_route,
            validation="failed_fallback",
            answer_mode="factual",
            status_code=500,
        )
        return llm_fallback_message(last_error)

    answer = str(semantic_answer.get("text") or "").strip() or "Maaf, tidak ada jawaban."
    llm_model_name = str(semantic_answer.get("model") or "")
    llm_time_ms = int(semantic_answer.get("llm_ms") or 0)
    fallback_used = bool(semantic_answer.get("fallback_used"))
    _record_metric(
        request_id=request_id,
        user_id=user_id,
        mode="semantic_policy" if intent_route == "semantic_policy" else mode,
        query_len=len(q),
        dense_hits=len(dense_all),
        bm25_hits=bm25_hits,
        final_docs=len(docs),
        retrieval_ms=retrieval_ms,
        rerank_ms=rerank_ms,
        llm_model=llm_model_name,
        llm_time_ms=llm_time_ms,
        fallback_used=fallback_used,
        source_count=len(sources),
        pipeline="rag_semantic",
        intent_route=intent_route,
        validation="not_applicable",
        answer_mode="factual",
        status_code=200,
    )
    return {
        "answer": answer,
        "sources": sources,
        "meta": {
            "mode": mode,
            "pipeline": "rag_semantic",
            "intent_route": intent_route,
            "validation": "not_applicable",
            "analytics_stats": {},
            "referenced_documents": resolved_titles,
            "unresolved_mentions": unresolved_mentions,
            "ambiguous_mentions": ambiguous_mentions,
            "retrieval_ms": retrieval_ms,
            "llm_time_ms": llm_time_ms,
            "stage_timings_ms": {
                "retrieval_ms": retrieval_ms,
                "llm_ms": llm_time_ms,
            },
        },
    }


def ask_bot(user_id, query, request_id: str = "-") -> Dict[str, Any]:
    """
    Legacy compatibility adapter.
    Always route to legacy core implementation for stable fallback behavior.
    """
    return _ask_bot_legacy(user_id=user_id, query=query, request_id=request_id)
