from typing import List


def build_sources_from_docs(docs, max_sources: int = 8, snippet_len: int = 220):
    if not docs:
        return []
    seen = set()
    sources = []
    for d in docs:
        meta = getattr(d, "metadata", {}) or {}
        src = meta.get("source") or "unknown"
        if src in seen:
            continue
        seen.add(src)

        snippet = (getattr(d, "page_content", "") or "").strip().replace("\n", " ")
        if len(snippet) > snippet_len:
            snippet = snippet[:snippet_len] + "..."

        sources.append({"source": src, "snippet": snippet})
        if len(sources) >= max_sources:
            break
    return sources


def has_interactive_sections(answer: str) -> bool:
    a = (answer or "").lower()
    return ("insight singkat" in a) and (("pertanyaan lanjutan" in a) or ("opsi cepat" in a))


def looks_like_markdown_table(answer: str) -> bool:
    a = (answer or "")
    return ("|" in a) and ("---" in a)
