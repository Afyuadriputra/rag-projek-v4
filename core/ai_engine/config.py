import logging
import os
from typing import Iterable, List

from django.conf import settings
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from pydantic import PrivateAttr

logger = logging.getLogger(__name__)

CHROMA_PERSIST_DIR = os.path.join(settings.BASE_DIR, "chroma_db")
DEFAULT_EMBEDDING_MODEL = "intfloat/multilingual-e5-large"
LEGACY_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
_EMBEDDING_SINGLETON: HuggingFaceEmbeddings | None = None


def _env_bool(name: str, default: bool = False) -> bool:
    val = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return val in {"1", "true", "yes", "on"}


class PrefixAwareHuggingFaceEmbeddings(HuggingFaceEmbeddings):
    """
    Prefix e5-style query/passage agar retrieval lintas bahasa lebih stabil.
    """
    _use_e5_prefix: bool = PrivateAttr(default=False)

    def __init__(self, *args, use_e5_prefix: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self._use_e5_prefix = bool(use_e5_prefix)

    def _with_query_prefix(self, text: str) -> str:
        t = str(text or "").strip()
        if not self._use_e5_prefix:
            return t
        if t.startswith("query:"):
            return t
        return f"query: {t}"

    def _with_passage_prefix(self, text: str) -> str:
        t = str(text or "").strip()
        if not self._use_e5_prefix:
            return t
        if t.startswith("passage:"):
            return t
        return f"passage: {t}"

    def embed_query(self, text: str) -> List[float]:
        return super().embed_query(self._with_query_prefix(text))

    def embed_documents(self, texts: Iterable[str]) -> List[List[float]]:
        prepared = [self._with_passage_prefix(t) for t in texts]
        return super().embed_documents(prepared)


def _build_embedding(model_name: str, normalize: bool) -> HuggingFaceEmbeddings:
    use_e5_prefix = "e5" in model_name.lower()
    return PrefixAwareHuggingFaceEmbeddings(
        model_name=model_name,
        encode_kwargs={"normalize_embeddings": bool(normalize)},
        use_e5_prefix=use_e5_prefix,
    )


def get_embedding_function() -> HuggingFaceEmbeddings:
    global _EMBEDDING_SINGLETON
    if _EMBEDDING_SINGLETON is not None:
        return _EMBEDDING_SINGLETON

    model_name = str(os.environ.get("RAG_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)).strip() or DEFAULT_EMBEDDING_MODEL
    normalize = _env_bool("RAG_EMBEDDING_NORMALIZE", default=True)

    try:
        _EMBEDDING_SINGLETON = _build_embedding(model_name=model_name, normalize=normalize)
        logger.info("RAG embedding loaded model=%s normalize=%s", model_name, normalize)
        return _EMBEDDING_SINGLETON
    except Exception as e:
        logger.warning("RAG embedding primary model gagal model=%s err=%s", model_name, e)

    _EMBEDDING_SINGLETON = _build_embedding(model_name=LEGACY_EMBEDDING_MODEL, normalize=normalize)
    logger.warning("RAG embedding fallback ke legacy model=%s", LEGACY_EMBEDDING_MODEL)
    return _EMBEDDING_SINGLETON


def preprocess_embedding_query(text: str) -> str:
    t = str(text or "").strip()
    model_name = str(os.environ.get("RAG_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)).strip().lower()
    if "e5" not in model_name:
        return t
    if t.startswith("query:"):
        return t
    return f"query: {t}"


def preprocess_embedding_passage(text: str) -> str:
    t = str(text or "").strip()
    model_name = str(os.environ.get("RAG_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)).strip().lower()
    if "e5" not in model_name:
        return t
    if t.startswith("passage:"):
        return t
    return f"passage: {t}"


def get_vectorstore():
    return Chroma(
        persist_directory=CHROMA_PERSIST_DIR,
        embedding_function=get_embedding_function(),
        collection_name="academic_rag",
    )
