import os
import re
import time
import logging
from typing import Dict, Any, List

from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate

from ..config import get_vectorstore
from .hybrid import retrieve_dense, retrieve_sparse_bm25, fuse_rrf
from .rerank import rerank_documents
from .rules import _SEMESTER_RE, infer_doc_type
from .utils import build_sources_from_docs, looks_like_markdown_table, has_interactive_sections
from .llm import get_runtime_openrouter_config, get_backup_models, build_llm, invoke_text, llm_fallback_message
from .prompt import LLM_FIRST_TEMPLATE
from ...monitoring import record_rag_metric

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    val = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return val in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except Exception:
        return int(default)


def _build_chroma_filter(user_id: int, query: str) -> Dict[str, Any]:
    base_filter: Dict[str, Any] = {"user_id": str(user_id)}
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

    q = (query or "").strip()

    t0 = time.time()
    dense_k = _env_int("RAG_DENSE_K", 30)
    bm25_k = _env_int("RAG_BM25_K", 40)
    rerank_top_n = _env_int("RAG_RERANK_TOP_N", 8)
    use_hybrid = _env_bool("RAG_HYBRID_RETRIEVAL", default=False)
    use_rerank = _env_bool("RAG_RERANK_ENABLED", default=False)
    use_query_rewrite = _env_bool("RAG_QUERY_REWRITE", default=False)
    rerank_model = str(os.environ.get("RAG_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")).strip()
    query_preview = q if len(q) <= 140 else q[:140] + "..."

    rag_mode = "hybrid" if use_hybrid else "dense"
    logger.info(
        " RAG start user_id=%s dense_k=%s bm25_k=%s rerank_n=%s mode=%s q='%s'",
        user_id,
        dense_k,
        bm25_k,
        rerank_top_n,
        rag_mode,
        query_preview,
        extra={"request_id": request_id},
    )

    vectorstore = get_vectorstore()
    chroma_where = _build_chroma_filter(user_id=user_id, query=q)
    dense_all: List[Any] = []
    dense_scored = []

    retrieval_t0 = time.time()
    query_variants = _rewrite_queries(q) if use_query_rewrite else [q]
    for query_variant in query_variants:
        scored = retrieve_dense(vectorstore=vectorstore, query=query_variant, k=dense_k, filter_where=chroma_where)
        if scored:
            dense_scored.extend(scored)
    dense_docs = [d for d, _ in dense_scored]
    dense_docs = _dedup_docs(dense_docs)
    dense_all.extend(dense_docs)

    # fallback: jika filter ketat tidak kena, retry user-only filter.
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
    bm25_hits = 0
    if use_hybrid and dense_all:
        sparse_scored = retrieve_sparse_bm25(query=q, docs_pool=dense_all, k=bm25_k)
        bm25_hits = len(sparse_scored)
        fused = fuse_rrf(dense_docs=dense_scored, sparse_docs=sparse_scored, k=max(dense_k, bm25_k))
        final_docs = [d for d, _ in fused]
        final_scored = list(fused)

    retrieval_ms = int((time.time() - retrieval_t0) * 1000)

    rerank_ms = 0
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
    sources = build_sources_from_docs(docs)

    top_score = float(final_scored[0][1]) if final_scored else 0.0
    logger.info(
        " RAG retrieval done mode=%s query_variants=%s dense_hits=%s bm25_hits=%s final_docs=%s top_score=%.4f retrieval_ms=%s rerank_ms=%s",
        rag_mode,
        len(query_variants),
        len(dense_all),
        bm25_hits,
        len(docs),
        top_score,
        retrieval_ms,
        rerank_ms,
        extra={"request_id": request_id},
    )

    template = LLM_FIRST_TEMPLATE
    PROMPT = ChatPromptTemplate.from_template(template)

    backup_models = get_backup_models(
        str(runtime_cfg.get("model") or ""),
        runtime_cfg.get("backup_models"),
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

            llm = build_llm(model_name, runtime_cfg)
            qa_chain = create_stuff_documents_chain(llm, PROMPT)
            result = qa_chain.invoke({"input": q, "context": docs})

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

            if (not docs) and _needs_doc_grounding(q):
                answer = (
                    "Informasi dari dokumen belum cukup untuk menjawab dengan akurat. "
                    "Upload/cek dokumen jadwal/transkrip yang relevan, atau jelaskan semester/hari/kelas yang dimaksud."
                )

            # Pastikan ada lapisan interaktif
            if looks_like_markdown_table(answer) and (not has_interactive_sections(answer)):
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
                mode=rag_mode,
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

            if idx < len(backup_models) - 1:
                time.sleep(0.8)
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
        mode=rag_mode,
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
