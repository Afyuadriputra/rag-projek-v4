import os
from typing import Any, Dict, List, Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter


def schedule_rows_to_parent_chunks(
    rows: Optional[List[Dict[str, Any]]],
    *,
    norm_fn,
    target_chars: int = 420,
) -> List[Dict[str, Any]]:
    if not rows:
        return []
    grouped: Dict[tuple[int, str], List[str]] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        try:
            page_num = int(r.get("page", 0) or 0)
        except Exception:
            page_num = 0
        day = norm_fn(r.get("hari", "")) or "-"
        key = (page_num, day)
        grouped.setdefault(key, [])
        cells: List[str] = []
        for col in ["sesi", "jam", "kode", "mata_kuliah", "kelas", "ruang", "dosen", "semester"]:
            val = norm_fn(r.get(col, ""))
            if val:
                cells.append(f"{col}={val}")
        if cells:
            grouped[key].append(" | ".join(cells))

    out: List[Dict[str, Any]] = []
    for (page_num, day), lines in grouped.items():
        if not lines:
            continue
        buffer = f"PARENT_SCHEDULE page={page_num} hari={day}\n"
        for line in lines:
            if len(buffer) + len(line) + 2 > target_chars and len(buffer) > 60:
                out.append({"text": buffer.strip(), "chunk_kind": "parent", "page": page_num, "section": f"hari:{day}"})
                buffer = f"PARENT_SCHEDULE page={page_num} hari={day}\n"
            buffer += f"- {line}\n"
        if buffer.strip():
            out.append({"text": buffer.strip(), "chunk_kind": "parent", "page": page_num, "section": f"hari:{day}"})
    return out


def build_chunk_payloads(
    *,
    doc_type: str,
    text_content: str,
    row_chunks: Optional[List[str]],
    schedule_rows: Optional[List[Dict[str, Any]]],
    norm_fn=None,
    deps: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    # Backward-compatible path for old tests that pass deps with _build_chunk_payloads.
    if deps and callable(deps.get("_build_chunk_payloads")):
        return list(
            deps["_build_chunk_payloads"](
                doc_type=doc_type,
                text_content=text_content,
                row_chunks=row_chunks,
                schedule_rows=schedule_rows,
            )
            or []
        )
    if norm_fn is None:
        norm_fn = lambda x: str(x or "").strip()

    profile_enabled = (os.environ.get("RAG_DOC_CHUNK_PROFILE", "1") or "1").strip().lower() in {"1", "true", "yes"}
    if profile_enabled and doc_type == "schedule":
        text_chunk_size = int(os.environ.get("RAG_SCHEDULE_TEXT_CHUNK_SIZE", "820") or 820)
        text_chunk_overlap = int(os.environ.get("RAG_SCHEDULE_TEXT_CHUNK_OVERLAP", "100") or 100)
    else:
        text_chunk_size = int(os.environ.get("RAG_TEXT_CHUNK_SIZE", "820") or 820)
        text_chunk_overlap = int(os.environ.get("RAG_TEXT_CHUNK_OVERLAP", "100") or 100)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=max(200, text_chunk_size),
        chunk_overlap=max(40, text_chunk_overlap),
    )
    text_chunks = [norm_fn(c) for c in splitter.split_text(text_content or "") if norm_fn(c)]

    payloads: List[Dict[str, Any]] = []
    seen = set()

    for rc in row_chunks or []:
        val = norm_fn(rc)
        if not val or val in seen:
            continue
        seen.add(val)
        payloads.append({"text": val, "chunk_kind": "row"})

    if profile_enabled and doc_type == "schedule":
        for p in schedule_rows_to_parent_chunks(schedule_rows, norm_fn=norm_fn):
            txt = norm_fn(p.get("text", ""))
            if not txt or txt in seen:
                continue
            seen.add(txt)
            payloads.append(
                {
                    "text": txt,
                    "chunk_kind": "parent",
                    "page": p.get("page"),
                    "section": p.get("section"),
                }
            )

    for tc in text_chunks:
        if tc in seen:
            continue
        seen.add(tc)
        payloads.append({"text": tc, "chunk_kind": "text"})

    return payloads
