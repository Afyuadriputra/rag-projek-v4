from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Tuple

from django.core.cache import cache

from core.models import AcademicDocument

from ..utils import polish_answer_text_light
from ..config.settings import get_retrieval_settings


def extract_mentions(query: str) -> Tuple[str, List[str]]:
    q = str(query or "").strip()
    if not q:
        return "", []

    ext_pattern = re.compile(
        r"@([A-Za-z0-9._\- ]+?\.(?:pdf|xlsx|xls|csv|md|txt))\b",
        re.IGNORECASE,
    )
    raw_mentions = [m.group(1).strip() for m in ext_pattern.finditer(q) if m.group(1).strip()]
    clean_q = ext_pattern.sub("", q)

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
        docs = list(AcademicDocument.objects.filter(user_id=user_id).values("id", "title"))
    except Exception:
        docs = []
    if not docs:
        out["unresolved_mentions"] = mentions
        return out

    doc_norm: list[tuple[int, str, str]] = []
    for d in docs:
        title = str(d.get("title") or "")
        doc_norm.append((int(d["id"]), title, _normalize_doc_key(title)))

    resolved_ids: list[int] = []
    resolved_titles: list[str] = []
    unresolved: list[str] = []
    ambiguous: list[str] = []

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


def resolve_mentions(user_id: int, mentions: List[str]) -> Dict[str, Any]:
    # Backward-compat hook: tests/consumers may patch resolver on main facade.
    try:
        from .. import main as main_facade

        resolver = getattr(main_facade, "_resolve_user_doc_mentions", _resolve_user_doc_mentions)
    except Exception:
        resolver = _resolve_user_doc_mentions

    settings = get_retrieval_settings()
    ttl_s = max(int(settings.rag_mention_cache_ttl_s), 0)
    mention_key = "|".join([str(x or "").strip().lower() for x in mentions if str(x or "").strip()])
    if ttl_s <= 0 or not mention_key:
        return resolver(user_id, mentions)
    mk_hash = hashlib.md5(mention_key.encode("utf-8")).hexdigest()
    ck = f"rag:mention:v1:{int(user_id)}:{mk_hash}"
    cached = cache.get(ck)
    if isinstance(cached, dict):
        return cached
    out = resolver(user_id, mentions)
    cache.set(ck, out, ttl_s)
    return out


def has_user_documents(user_id: int) -> bool:
    settings = get_retrieval_settings()
    ttl_s = max(int(settings.rag_user_docs_cache_ttl_s), 0)
    ck = f"rag:user_has_docs:{int(user_id)}"
    try:
        cached = cache.get(ck)
        if cached is True:
            return True
        if cached is False:
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


def build_ambiguous_response(mentions: List[str]) -> Dict[str, Any]:
    mention_text = ", ".join([f"`@{m}`" for m in mentions[:3]])
    answer = (
        "## Ringkasan\n"
        f"Aku menemukan rujukan dokumen yang ambigu: {mention_text}. Biar akurat, tolong tulis nama file lebih spesifik.\n\n"
        "## Opsi Lanjut\n"
        "- Tulis ulang dengan nama file lebih lengkap (contoh: `@Jadwal Mata Kuliah Semester GANJIL TA.2024-2025.pdf`).\n"
        "- Atau lanjut tanpa rujukan dokumen, nanti Aku jawab secara umum dulu."
    )
    answer = polish_answer_text_light(answer)
    return {
        "answer": answer,
        "sources": [],
        "meta": {
            "mode": "doc_referenced",
            "pipeline": "rag_semantic",
            "intent_route": "default_rag",
            "validation": "not_applicable",
            "analytics_stats": {},
            "referenced_documents": [],
            "unresolved_mentions": [],
            "ambiguous_mentions": list(mentions or []),
        },
    }
