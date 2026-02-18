import time
import logging
from typing import Dict, Any

from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate

from ..config import get_vectorstore
from .rules import _SEMESTER_RE, infer_doc_type
from .utils import build_sources_from_docs, looks_like_markdown_table, has_interactive_sections
from .llm import get_runtime_openrouter_config, get_backup_models, build_llm, invoke_text, llm_fallback_message
from .prompt import LLM_FIRST_TEMPLATE

logger = logging.getLogger(__name__)


def ask_bot(user_id, query, request_id: str = "-") -> Dict[str, Any]:
    runtime_cfg = get_runtime_openrouter_config()
    api_key = (runtime_cfg.get("api_key") or "").strip()
    if not api_key:
        return {
            "answer": "OpenRouter API key belum di-set. Atur di Django Admin (LLM Configuration) atau .env.",
            "sources": [],
        }

    q = (query or "").strip()

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
    doc_type = infer_doc_type(q)
    if doc_type:
        base_filter["doc_type"] = doc_type

    # Chroma expects a single operator in where; use $and when multiple filters
    chroma_where = base_filter
    if len(base_filter) > 1:
        chroma_where = {"$and": [{"user_id": str(user_id)}] + [
            {k: v} for k, v in base_filter.items() if k != "user_id"
        ]}

    docs_with_scores = vectorstore.similarity_search_with_score(q, k=k, filter=chroma_where)
    docs = [d for d, _ in docs_with_scores] if docs_with_scores else []

    # fallback: jika terlalu ketat, retry tanpa filter tambahan
    if not docs and (len(base_filter) > 1):
        docs_with_scores = vectorstore.similarity_search_with_score(q, k=k, filter={"user_id": str(user_id)})
        docs = [d for d, _ in docs_with_scores] if docs_with_scores else []

    sources = build_sources_from_docs(docs)

    template = LLM_FIRST_TEMPLATE
    PROMPT = ChatPromptTemplate.from_template(template)

    backup_models = get_backup_models(
        str(runtime_cfg.get("model") or ""),
        runtime_cfg.get("backup_models"),
    )
    last_error = ""
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

            if idx < len(backup_models) - 1:
                time.sleep(0.8)
                continue

            logger.error(
                " All models failed last_err=%s",
                err_preview,
                extra={"request_id": request_id},
                exc_info=True,
            )

    return llm_fallback_message(last_error)
