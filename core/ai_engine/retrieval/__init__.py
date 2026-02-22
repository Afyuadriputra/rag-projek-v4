from __future__ import annotations

import os
import time
from typing import Any, List

from core.ai_engine.config import get_vectorstore
from .main import ask_bot as ask_bot_v2

try:
    from langchain_openai import ChatOpenAI  # type: ignore
except Exception:  # pragma: no cover
    ChatOpenAI = None  # type: ignore

try:
    from langchain_classic.chains.combine_documents import create_stuff_documents_chain  # type: ignore
except Exception:  # pragma: no cover
    create_stuff_documents_chain = None  # type: ignore

try:
    from langchain_core.prompts import ChatPromptTemplate  # type: ignore
except Exception:  # pragma: no cover
    ChatPromptTemplate = None  # type: ignore

try:
    from langchain_classic.chains import create_retrieval_chain  # type: ignore
except Exception:  # pragma: no cover
    create_retrieval_chain = None  # type: ignore


# Backward-compatible globals for legacy tests that patch module attributes.
BACKUP_MODELS: List[str] = [
    str(os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash-lite")).strip()
]


def _normalize_models() -> List[str]:
    out: List[str] = []
    for m in BACKUP_MODELS:
        name = str(m or "").strip()
        if name and name not in out:
            out.append(name)
    if out:
        return out
    env_model = str(os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash-lite")).strip()
    return [env_model] if env_model else ["google/gemini-2.5-flash-lite"]


def _legacy_fallback_message(last_error: str) -> str:
    if last_error:
        return f"Maaf, semua server AI sedang sibuk. Error: {last_error}"
    return "Maaf, semua server AI sedang sibuk. Coba lagi sebentar ya."


def ask_bot(user_id: int, query: str, request_id: str = "-") -> str:
    """
    Legacy compatibility facade for historical unit tests under `core/test/test_llm_*`
    and `core/test/test_user_isolation.py`.

    Production services use `core.ai_engine.retrieval.main.ask_bot` directly.
    """
    _ = request_id  # kept for signature compatibility
    api_key = str(os.environ.get("OPENROUTER_API_KEY", "")).strip()
    if not api_key:
        return "OpenRouter API key belum di-set. Atur di Django Admin (LLM Configuration) atau .env."

    vectorstore = get_vectorstore()
    retriever = vectorstore.as_retriever(search_kwargs={"k": 20, "filter": {"user_id": str(user_id)}})
    last_error = ""

    for idx, model_name in enumerate(_normalize_models()):
        try:
            if ChatOpenAI is None or create_stuff_documents_chain is None or create_retrieval_chain is None:
                raise RuntimeError("LangChain dependency unavailable for legacy retrieval facade")

            llm = ChatOpenAI(
                model_name=model_name,
                openai_api_key=api_key,
                openai_api_base="https://openrouter.ai/api/v1",
                temperature=0.0,
            )
            prompt = (
                ChatPromptTemplate.from_template(
                    "Gunakan konteks berikut untuk menjawab pertanyaan user.\n\n{context}\n\nPertanyaan: {input}"
                )
                if ChatPromptTemplate is not None
                else object()
            )
            qa_chain = create_stuff_documents_chain(llm, prompt)
            rag_chain = create_retrieval_chain(retriever, qa_chain)
            result = rag_chain.invoke({"input": str(query or "").strip()})
            if isinstance(result, dict):
                answer = result.get("answer") or result.get("output_text") or ""
            else:
                answer = str(result or "")
            answer = str(answer).strip()
            return answer or "Maaf, tidak ada jawaban."
        except Exception as exc:  # pragma: no cover - exercised by fallback tests
            last_error = str(exc)
            if idx < len(_normalize_models()) - 1:
                time.sleep(1)
                continue
            return _legacy_fallback_message(last_error)

    return _legacy_fallback_message(last_error)


__all__ = [
    "ask_bot",
    "ask_bot_v2",
    "get_vectorstore",
    "ChatOpenAI",
    "create_stuff_documents_chain",
    "create_retrieval_chain",
    "BACKUP_MODELS",
    "time",
]
