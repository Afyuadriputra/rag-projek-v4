import re
from typing import List


def build_sources_from_docs(docs, max_sources: int = 8, snippet_len: int = 220):
    if not docs:
        return []
    seen = set()
    sources = []
    for d in docs:
        meta = getattr(d, "metadata", {}) or {}
        src = meta.get("source") or "unknown"
        page = meta.get("page")
        source_label = f"{src} (p.{page})" if page else src
        if source_label in seen:
            continue
        seen.add(source_label)

        snippet = (getattr(d, "page_content", "") or "").strip().replace("\n", " ")
        if len(snippet) > snippet_len:
            snippet = snippet[:snippet_len] + "..."

        sources.append({"source": source_label, "snippet": snippet})
        if len(sources) >= max_sources:
            break
    return sources


def has_interactive_sections(answer: str) -> bool:
    a = (answer or "").lower()
    return ("insight singkat" in a) and (("pertanyaan lanjutan" in a) or ("opsi cepat" in a))


def looks_like_markdown_table(answer: str) -> bool:
    a = (answer or "")
    return ("|" in a) and ("---" in a)


def polish_answer_text_light(answer: str) -> str:
    text = str(answer or "").strip()
    if not text:
        return text

    typo_map = {
        "kiatar": "maksud",
        "prosfek": "prospek",
        "karir": "karier",
        "di karenakan": "dikarenakan",
    }
    for wrong, right in typo_map.items():
        text = re.sub(rf"\b{re.escape(wrong)}\b", right, text, flags=re.IGNORECASE)

    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
