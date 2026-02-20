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
from .utils import build_sources_from_docs, looks_like_markdown_table, has_interactive_sections
from .llm import get_runtime_openrouter_config, get_backup_models, build_llm, invoke_text, llm_fallback_message
from .prompt import CHATBOT_SYSTEM_PROMPT
from ...monitoring import record_rag_metric

logger = logging.getLogger(__name__)
_MENTION_RE = re.compile(r"@([A-Za-z0-9._\- ]{2,120})")


def _env_bool(name: str, default: bool = False) -> bool:
    val = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return val in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except Exception:
        return int(default)


def _build_chroma_filter(user_id: int, query: str, doc_ids: List[int] | None = None) -> Dict[str, Any]:
    base_filter: Dict[str, Any] = {"user_id": str(user_id)}
    if doc_ids:
        base_filter["doc_id"] = {"$in": [str(x) for x in doc_ids]}
    sem_match = _SEMESTER_RE.search(query)
    if sem_match:
        try:
            base_filter["semester"] = int(sem_match.group(1))
        except Exception:
            pass
    doc_type = infer_doc_type(query)
    if doc_type:
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
    ck = f"rag:user_has_docs:{int(user_id)}"
    try:
        cached = cache.get(ck)
        if cached is not None:
            return bool(cached)
        has_docs = AcademicDocument.objects.filter(user_id=user_id).exists()
        cache.set(ck, bool(has_docs), 60)
        return bool(has_docs)
    except Exception:
        return False


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


def _classify_query_intent(query: str) -> str:
    ql = (query or "").lower()
    doc_markers = [
        "rekap nilai", "nilai saya", "ipk saya", "ips saya", "transkrip",
        "jadwal saya", "jadwal kelas", "mata kuliah", "khs", "krs", "sks",
        "ruang", "jam", "semester",
    ]
    return "doc_targeted" if any(x in ql for x in doc_markers) else "general_academic"


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


def ask_bot(user_id, query, request_id: str = "-") -> Dict[str, Any]:
    runtime_cfg = get_runtime_openrouter_config()
    api_key = (runtime_cfg.get("api_key") or "").strip()
    if not api_key:
        record_rag_metric(
            request_id=request_id,
            user_id=user_id,
            mode="dense",
            query_len=len((query or "").strip()),
            dense_hits=0,
            bm25_hits=0,
            final_docs=0,
            retrieval_ms=0,
            rerank_ms=0,
            llm_model="",
            llm_time_ms=0,
            fallback_used=False,
            source_count=0,
            status_code=503,
        )
        return {
            "answer": "OpenRouter API key belum di-set. Atur di Django Admin (LLM Configuration) atau .env.",
            "sources": [],
        }

    q_raw = (query or "").strip()
    q, mentions = _extract_doc_mentions(q_raw)
    if not q:
        q = q_raw
    # Safety harus mengevaluasi query mentah supaya mention @... tidak menutupi niat berbahaya.
    safety = _classify_query_safety(q_raw)
    decision = str(safety.get("decision") or "allow")

    if decision in {"refuse_crime", "refuse_political", "redirect_weird"}:
        if decision == "redirect_weird":
            answer = _build_redirect_response(q)
        else:
            answer = _build_refusal_response(decision, q)
        answer = _polish_answer_text(answer)

        logger.info(
            " RAG guard hit decision=%s reason=%s tags=%s",
            decision,
            safety.get("reason"),
            safety.get("tags"),
            extra={"request_id": request_id},
        )
        record_rag_metric(
            request_id=request_id,
            user_id=user_id,
            mode="guard",
            query_len=len(q),
            dense_hits=0,
            bm25_hits=0,
            final_docs=0,
            retrieval_ms=0,
            rerank_ms=0,
            llm_model="",
            llm_time_ms=0,
            fallback_used=False,
            source_count=0,
            status_code=200,
        )
        return {"answer": answer, "sources": [], "meta": {"mode": "guard"}}

    mention_resolution = _resolve_user_doc_mentions(user_id, mentions)
    resolved_doc_ids = mention_resolution.get("resolved_doc_ids", [])
    unresolved_mentions = mention_resolution.get("unresolved_mentions", [])
    ambiguous_mentions = mention_resolution.get("ambiguous_mentions", [])
    resolved_titles = mention_resolution.get("resolved_titles", [])

    if ambiguous_mentions:
        answer = _build_mention_ambiguous_response(ambiguous_mentions)
        answer = _polish_answer_text(answer)
        record_rag_metric(
            request_id=request_id,
            user_id=user_id,
            mode="doc_referenced",
            query_len=len(q),
            dense_hits=0,
            bm25_hits=0,
            final_docs=0,
            retrieval_ms=0,
            rerank_ms=0,
            llm_model="",
            llm_time_ms=0,
            fallback_used=False,
            source_count=0,
            status_code=200,
        )
        return {
            "answer": answer,
            "sources": [],
            "meta": {
                "referenced_documents": [],
                "unresolved_mentions": unresolved_mentions,
                "ambiguous_mentions": ambiguous_mentions,
            },
        }

    t0 = time.time()
    has_docs = _has_user_documents(user_id)
    query_intent = _classify_query_intent(q)
    mode = "llm_only"
    if has_docs and resolved_doc_ids:
        mode = "doc_referenced"
    elif has_docs:
        mode = "doc_background"

    dense_k = _env_int("RAG_DENSE_K", 30)
    bm25_k = _env_int("RAG_BM25_K", 40)
    rerank_top_n = _env_int("RAG_RERANK_TOP_N", 8)
    use_hybrid = _env_bool("RAG_HYBRID_RETRIEVAL", default=False)
    use_rerank = _env_bool("RAG_RERANK_ENABLED", default=False)
    use_query_rewrite = _env_bool("RAG_QUERY_REWRITE", default=False)

    if mode == "doc_background":
        dense_k = _env_int("RAG_GENERAL_DENSE_K", 6)
        bm25_k = _env_int("RAG_GENERAL_BM25_K", 8)
        rerank_top_n = _env_int("RAG_GENERAL_RERANK_TOP_N", 4)
        use_hybrid = _env_bool("RAG_GENERAL_HYBRID_RETRIEVAL", default=False)
        use_rerank = _env_bool("RAG_GENERAL_RERANK_ENABLED", default=False)
        use_query_rewrite = _env_bool("RAG_GENERAL_QUERY_REWRITE", default=False)
    elif mode == "doc_referenced":
        dense_k = _env_int("RAG_DOC_DENSE_K", 12)
        bm25_k = _env_int("RAG_DOC_BM25_K", 20)
        rerank_top_n = _env_int("RAG_DOC_RERANK_TOP_N", 4)
        use_hybrid = _env_bool("RAG_DOC_HYBRID_RETRIEVAL", default=False)
        use_rerank = _env_bool("RAG_DOC_RERANK_ENABLED", default=True)
        use_query_rewrite = _env_bool("RAG_DOC_QUERY_REWRITE", default=False)

    rerank_model = str(os.environ.get("RAG_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")).strip()
    query_preview = q if len(q) <= 140 else q[:140] + "..."

    rag_mode = mode if mode == "llm_only" else ("hybrid" if use_hybrid else "dense")
    logger.info(
        " RAG start user_id=%s dense_k=%s bm25_k=%s rerank_n=%s mode=%s intent=%s mentions=%s resolved=%s q='%s'",
        user_id,
        dense_k,
        bm25_k,
        rerank_top_n,
        rag_mode,
        query_intent,
        len(mentions),
        len(resolved_doc_ids),
        query_preview,
        extra={"request_id": request_id},
    )

    dense_all: List[Any] = []
    dense_scored = []
    final_docs: List[Any] = []
    final_scored: List[Any] = []
    bm25_hits = 0
    retrieval_ms = 0
    rerank_ms = 0

    if mode != "llm_only":
        vectorstore = get_vectorstore()
        chroma_where = _build_chroma_filter(user_id=user_id, query=q, doc_ids=resolved_doc_ids if resolved_doc_ids else None)

        retrieval_t0 = time.time()
        query_variants = _rewrite_queries(q) if use_query_rewrite else [q]
        for query_variant in query_variants:
            scored = retrieve_dense(vectorstore=vectorstore, query=query_variant, k=dense_k, filter_where=chroma_where)
            if scored:
                dense_scored.extend(scored)
        dense_docs = [d for d, _ in dense_scored]
        dense_docs = _dedup_docs(dense_docs)
        dense_all.extend(dense_docs)

        if not dense_all and isinstance(chroma_where, dict) and "$and" in chroma_where:
            fallback_scored = retrieve_dense(
                vectorstore=vectorstore,
                query=q,
                k=dense_k,
                filter_where={"user_id": str(user_id)},
            )
            dense_all = _dedup_docs([d for d, _ in fallback_scored])
            dense_scored = fallback_scored

        final_docs = list(dense_all)
        final_scored = list(dense_scored)
        if use_hybrid and dense_all:
            sparse_scored = retrieve_sparse_bm25(query=q, docs_pool=dense_all, k=bm25_k)
            bm25_hits = len(sparse_scored)
            fused = fuse_rrf(dense_docs=dense_scored, sparse_docs=sparse_scored, k=max(dense_k, bm25_k))
            final_docs = [d for d, _ in fused]
            final_scored = list(fused)

        retrieval_ms = int((time.time() - retrieval_t0) * 1000)

        if use_rerank and final_docs:
            rerank_t0 = time.time()
            final_docs = rerank_documents(
                query=q,
                docs=final_docs[: max(dense_k, bm25_k)],
                model_name=rerank_model,
                top_n=rerank_top_n,
            )
            rerank_ms = int((time.time() - rerank_t0) * 1000)

    final_limit = rerank_top_n if use_rerank else dense_k
    docs = final_docs[: max(1, final_limit)]
    top_score = float(final_scored[0][1]) if final_scored else 0.0
    if mode == "doc_background" and query_intent == "general_academic":
        low_rel_threshold = float(os.environ.get("RAG_GENERAL_RELEVANCE_THRESHOLD", "0.18"))
        if top_score < low_rel_threshold:
            docs = []

    sources = build_sources_from_docs(docs)

    logger.info(
        " RAG retrieval done mode=%s dense_hits=%s bm25_hits=%s final_docs=%s top_score=%.4f retrieval_ms=%s rerank_ms=%s has_docs=%s docs_used=%s",
        mode,
        len(dense_all),
        bm25_hits,
        len(docs),
        top_score,
        retrieval_ms,
        rerank_ms,
        has_docs,
        bool(docs),
        extra={"request_id": request_id},
    )

    template = CHATBOT_SYSTEM_PROMPT
    PROMPT = ChatPromptTemplate.from_template(template)

    runtime_cfg_for_mode = dict(runtime_cfg)
    if mode == "doc_referenced":
        doc_model = str(os.environ.get("OPENROUTER_MODEL_DOC", "")).strip()
        if doc_model:
            runtime_cfg_for_mode["model"] = doc_model
    else:
        fast_model = str(os.environ.get("OPENROUTER_MODEL_FAST", "")).strip()
        if fast_model:
            runtime_cfg_for_mode["model"] = fast_model

    backup_models = get_backup_models(
        str(runtime_cfg_for_mode.get("model") or ""),
        runtime_cfg_for_mode.get("backup_models"),
    )
    last_error = ""
    llm_model_name = ""
    llm_time_ms = 0
    fallback_used = False
    for idx, model_name in enumerate(backup_models):
        model_t0 = time.time()
        try:
            logger.info(
                " LLM try idx=%s model=%s",
                idx, model_name,
                extra={"request_id": request_id},
            )

            llm = build_llm(model_name, runtime_cfg_for_mode)
            qa_chain = create_stuff_documents_chain(llm, PROMPT)
            q_for_prompt = q
            if resolved_titles:
                q_for_prompt = (
                    f"{q}\n\n"
                    f"[Referenced Documents]\n{', '.join(resolved_titles)}\n"
                    "Instruksi: prioritaskan dokumen rujukan ini sebagai sumber utama; "
                    "jika tidak cukup, jelaskan batasannya lalu beri fallback umum."
                )
            result = qa_chain.invoke({"input": q_for_prompt, "context": docs})

            if isinstance(result, dict):
                answer = result.get("answer") or result.get("output_text") or ""
            else:
                answer = str(result)
            answer = (answer or "").strip() or "Maaf, tidak ada jawaban."

            if docs and not _has_citation(answer):
                citation_prompt = (
                    "Perbaiki jawaban agar setiap klaim faktual spesifik menyertakan sitasi `[source: ...]` "
                    "berdasarkan konteks yang sama. Jangan tambah fakta baru.\n\n"
                    f"Jawaban saat ini:\n{answer}"
                )
                cited = invoke_text(llm, citation_prompt).strip()
                if cited and _has_citation(cited):
                    answer = cited

            if (not docs) and _needs_doc_grounding(q) and _is_personal_document_query(q):
                answer = (
                    f"{answer}\n\n"
                    "Catatan: untuk analisis personal yang akurat (jadwal/nilai milikmu), "
                    "Aku masih butuh data dokumenmu."
                ).strip()

            use_table_enrichment = _env_bool("RAG_ENABLE_TABLE_ENRICHMENT", default=False)
            if use_table_enrichment and looks_like_markdown_table(answer) and (not has_interactive_sections(answer)):
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
                enriched = invoke_text(llm, enrich_prompt).strip()
                if enriched:
                    answer = enriched

            answer = _polish_answer_text(answer)

            model_dur = round(time.time() - model_t0, 2)
            total_dur = round(time.time() - t0, 2)
            logger.info(
                " LLM ok idx=%s model=%s model_time=%ss total_time=%ss answer_len=%s sources=%s",
                idx, model_name, model_dur, total_dur, len(answer), len(sources),
                extra={"request_id": request_id},
            )
            llm_model_name = model_name
            llm_time_ms = int((time.time() - model_t0) * 1000)

            if idx > 0:
                logger.warning(
                    " Fallback used idx=%s model=%s",
                    idx, model_name,
                    extra={"request_id": request_id},
                )
                fallback_used = True

            record_rag_metric(
                request_id=request_id,
                user_id=user_id,
                mode=mode,
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
                status_code=200,
            )

            if mode == "doc_referenced" and not docs:
                answer = (
                    f"{answer}\n\n"
                    "Catatan: Aku belum menemukan konteks kuat dari file rujukan, jadi jawaban ini "
                    "lebih bersifat panduan umum."
                ).strip()

            if unresolved_mentions:
                answer = (
                    f"{answer}\n\n"
                    f"Catatan rujukan: ada file yang tidak ditemukan ({', '.join([f'@{m}' for m in unresolved_mentions])})."
                ).strip()

            return {
                "answer": answer,
                "sources": sources,
                "meta": {
                    "mode": mode,
                    "referenced_documents": resolved_titles,
                    "unresolved_mentions": unresolved_mentions,
                    "ambiguous_mentions": ambiguous_mentions,
                },
            }

        except Exception as e:
            model_dur = round(time.time() - model_t0, 2)
            last_error = str(e)
            err_preview = last_error if len(last_error) <= 200 else last_error[:200] + "..."

            logger.warning(
                " LLM fail idx=%s model=%s dur=%ss err=%s",
                idx, model_name, model_dur, err_preview,
                extra={"request_id": request_id},
            )

            if idx < len(backup_models) - 1:
                retry_sleep_ms = _env_int("RAG_RETRY_SLEEP_MS", 300)
                time.sleep(max(0.0, float(retry_sleep_ms) / 1000.0))
                continue

            logger.error(
                " All models failed last_err=%s",
                err_preview,
                extra={"request_id": request_id},
                exc_info=True,
            )

    record_rag_metric(
        request_id=request_id,
        user_id=user_id,
        mode=mode,
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
        status_code=500,
    )

    return llm_fallback_message(last_error)
