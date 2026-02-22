import json
from typing import Any, Dict, List, Optional

from ..settings import env_bool


def build_base_metadata(
    *,
    doc_instance: Any,
    ext: str,
    detected_columns: Optional[List[str]],
    schedule_rows: Optional[List[Dict[str, Any]]],
    transcript_rows: Optional[List[Dict[str, Any]]],
    semester_num: Optional[int],
    doc_type: str,
    row_chunks: Optional[List[str]],
) -> Dict[str, Any]:
    base_meta: Dict[str, Any] = {
        "user_id": str(doc_instance.user.id),
        "doc_id": str(doc_instance.id),
        "source": doc_instance.title,
        "file_type": ext,
        "doc_type": doc_type,
    }
    if detected_columns:
        base_meta["columns"] = json.dumps(detected_columns, ensure_ascii=True)
    if schedule_rows:
        base_meta["schedule_rows"] = json.dumps(schedule_rows[:1200], ensure_ascii=True)
        base_meta["hybrid_repair"] = "on" if env_bool("PDF_HYBRID_LLM_REPAIR", True) else "off"
    if transcript_rows:
        base_meta["transcript_rows"] = json.dumps(transcript_rows[:1200], ensure_ascii=True)
    if semester_num is not None:
        base_meta["semester"] = int(semester_num)
    if row_chunks:
        base_meta["table_format"] = "csv_canonical"
    base_meta["chunk_profile"] = "on" if env_bool("RAG_DOC_CHUNK_PROFILE", True) else "off"
    return base_meta


def build_chunk_metadatas(base_meta: Dict[str, Any], chunk_payloads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for payload in chunk_payloads:
        meta = dict(base_meta)
        meta["chunk_kind"] = str(payload.get("chunk_kind") or "text")
        page = payload.get("page")
        if page is not None and str(page).strip():
            try:
                meta["page"] = int(page)
            except Exception:
                pass
        section = str(payload.get("section") or "").strip()
        if section:
            meta["section"] = section
        out.append(meta)
    return out

