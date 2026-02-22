# core/ai_engine/ingest.py

import pdfplumber
import logging
from typing import Any, Dict, List, Optional, Tuple

from .config import get_vectorstore
try:
    from langchain_openai import ChatOpenAI  # type: ignore
except Exception:  # pragma: no cover - optional dependency for hybrid mode
    ChatOpenAI = None  # type: ignore
try:
    from langchain_core.messages import HumanMessage, SystemMessage  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    HumanMessage = None  # type: ignore
    SystemMessage = None  # type: ignore
try:
    import fitz  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    fitz = None  # type: ignore

logger = logging.getLogger(__name__)

from .ingest_pipeline.constants import (
    MAX_SCHEDULE_ROWS as _MAX_SCHEDULE_ROWS,
    SCHEDULE_CANON_ORDER as _SCHEDULE_CANON_ORDER,
    SCHEDULE_COL_HINTS as _SCHEDULE_COL_HINTS,
    SCHEDULE_TITLE_HINTS as _SCHEDULE_TITLE_HINTS,
    TIME_RANGE_RE as _TIME_RANGE_RE,
    TRANSCRIPT_COL_HINTS as _TRANSCRIPT_COL_HINTS,
    TRANSCRIPT_GRADE_PREFIX_RE as _TRANSCRIPT_GRADE_PREFIX_RE,
    TRANSCRIPT_GRADE_WHITELIST as _TRANSCRIPT_GRADE_WHITELIST,
    TRANSCRIPT_PENDING_RE as _TRANSCRIPT_PENDING_RE,
    TRANSCRIPT_ROW_RE as _TRANSCRIPT_ROW_RE,
    TRANSCRIPT_TITLE_HINTS as _TRANSCRIPT_TITLE_HINTS,
    UNIVERSAL_SCHEDULE_SYSTEM_PROMPT as _UNIVERSAL_SCHEDULE_SYSTEM_PROMPT,
    UNIVERSAL_TRANSCRIPT_SYSTEM_PROMPT as _UNIVERSAL_TRANSCRIPT_SYSTEM_PROMPT,
)
from .ingest_pipeline.utils import legacy_helpers as _legacy_helpers
from .ingest_pipeline.schemas import PipelineOps
# Small helpers
_norm = _legacy_helpers.norm
_norm_header = _legacy_helpers.norm_header
_normalize_time_range = _legacy_helpers.normalize_time_range
_normalize_hhmm = _legacy_helpers.normalize_hhmm
_is_valid_time_range = _legacy_helpers.is_valid_time_range
_normalize_day_text = _legacy_helpers.normalize_day_text
_is_noise_numbering_row = _legacy_helpers.is_noise_numbering_row
_is_noise_header_repeat_row = _legacy_helpers.is_noise_header_repeat_row
_looks_like_header_row = _legacy_helpers.looks_like_header_row
_canonical_header = _legacy_helpers.canonical_header
_canonical_columns_from_header = _legacy_helpers.canonical_columns_from_header
_display_columns_from_mapping = _legacy_helpers.display_columns_from_mapping
_find_idx = _legacy_helpers.find_idx
_row_to_text = _legacy_helpers.row_to_text
_extract_semester_from_text = _legacy_helpers.extract_semester_from_text
_detect_doc_type = _legacy_helpers.detect_doc_type


def _schedule_rows_to_csv_text(rows: Optional[List[Dict[str, Any]]]) -> Tuple[str, int, int]:
    from .ingest_pipeline.chunking.row_serializers import schedule_rows_to_csv_text

    return schedule_rows_to_csv_text(
        rows,
        deps={"_norm": _norm, "_normalize_day_text": _normalize_day_text, "_normalize_time_range": _normalize_time_range},
    )


_csv_preview = _legacy_helpers.csv_preview


def _schedule_rows_to_row_chunks(rows: Optional[List[Dict[str, Any]]], limit: int = 2000) -> List[str]:
    from .ingest_pipeline.chunking.row_serializers import schedule_rows_to_row_chunks

    return schedule_rows_to_row_chunks(rows, deps={"_norm": _norm, "_SCHEDULE_CANON_ORDER": _SCHEDULE_CANON_ORDER}, limit=limit)


def _schedule_rows_to_parent_chunks(rows: Optional[List[Dict[str, Any]]], target_chars: int = 420) -> List[Dict[str, Any]]:
    from .ingest_pipeline.chunking.chunk_builder import schedule_rows_to_parent_chunks

    return schedule_rows_to_parent_chunks(rows, norm_fn=_norm, target_chars=target_chars)


def _build_chunk_payloads(
    *,
    doc_type: str,
    text_content: str,
    row_chunks: List[str],
    schedule_rows: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    from .ingest_pipeline.chunking.chunk_builder import build_chunk_payloads

    return build_chunk_payloads(
        doc_type=doc_type,
        text_content=text_content,
        row_chunks=row_chunks,
        schedule_rows=schedule_rows,
        norm_fn=_norm,
    )


def _row_confidence(row: Dict[str, Any]) -> Tuple[float, List[str]]:
    from .ingest_pipeline.parsers.repair import row_confidence

    return row_confidence(
        row,
        deps={
            "_normalize_day_text": _normalize_day_text,
            "_norm": _norm,
            "_normalize_time_range": _normalize_time_range,
            "_is_valid_time_range": _is_valid_time_range,
        },
    )


def _build_repair_llm() -> Optional[Any]:
    from .ingest_pipeline.parsers.repair import build_repair_llm

    return build_repair_llm(deps={"ChatOpenAI": ChatOpenAI}, logger=logger)


def _extract_json_from_llm_response(text: str) -> Optional[List[Dict[str, Any]]]:
    from .ingest_pipeline.parsers.repair import extract_json_from_llm_response

    return extract_json_from_llm_response(text)


def _extract_transcript_json_object(text: str) -> Optional[Dict[str, Any]]:
    from .ingest_pipeline.parsers.structured_rows import extract_transcript_json_object

    return extract_transcript_json_object(text)


def _extract_schedule_json_object(text: str) -> Optional[Dict[str, Any]]:
    from .ingest_pipeline.parsers.structured_rows import extract_schedule_json_object

    return extract_schedule_json_object(text)


def _safe_int(v: Any) -> Optional[int]:
    from .ingest_pipeline.parsers.structured_rows import safe_int

    return safe_int(v, norm_fn=_norm)


def _normalize_transcript_rows(rows: List[Dict[str, Any]], fallback_semester: Optional[int]) -> List[Dict[str, Any]]:
    from .ingest_pipeline.parsers.structured_rows import normalize_transcript_rows

    return normalize_transcript_rows(
        rows,
        fallback_semester,
        deps={"_norm": _norm, "_safe_int": _safe_int, "_TRANSCRIPT_GRADE_WHITELIST": _TRANSCRIPT_GRADE_WHITELIST},
    )


def _normalize_schedule_rows(rows: List[Dict[str, Any]], fallback_semester: Optional[int]) -> List[Dict[str, Any]]:
    from .ingest_pipeline.parsers.structured_rows import normalize_schedule_rows

    return normalize_schedule_rows(
        rows,
        fallback_semester,
        deps={
            "_normalize_day_text": _normalize_day_text,
            "_norm": _norm,
            "_safe_int": _safe_int,
            "_normalize_hhmm": _normalize_hhmm,
            "_normalize_time_range": _normalize_time_range,
            "_TIME_RANGE_RE": _TIME_RANGE_RE,
        },
    )


def _is_transcript_candidate(title: str, detected_columns: Optional[List[str]] = None) -> bool:
    from .ingest_pipeline.parsers.structured_rows import is_transcript_candidate

    return is_transcript_candidate(
        title,
        detected_columns,
        deps={"_norm": _norm, "_TRANSCRIPT_TITLE_HINTS": _TRANSCRIPT_TITLE_HINTS, "_TRANSCRIPT_COL_HINTS": _TRANSCRIPT_COL_HINTS},
    )


def _is_schedule_candidate(title: str, detected_columns: Optional[List[str]] = None) -> bool:
    from .ingest_pipeline.parsers.structured_rows import is_schedule_candidate

    return is_schedule_candidate(
        title,
        detected_columns,
        deps={"_norm": _norm, "_SCHEDULE_TITLE_HINTS": _SCHEDULE_TITLE_HINTS, "_SCHEDULE_COL_HINTS": _SCHEDULE_COL_HINTS},
    )


def _canonical_schedule_to_legacy_rows(
    rows: List[Dict[str, Any]],
    fallback_semester: Optional[int] = None,
) -> List[Dict[str, Any]]:
    from .ingest_pipeline.parsers.structured_rows import canonical_schedule_to_legacy_rows

    return canonical_schedule_to_legacy_rows(
        rows,
        fallback_semester,
        deps={"_norm": _norm, "_normalize_hhmm": _normalize_hhmm, "_normalize_day_text": _normalize_day_text, "_safe_int": _safe_int},
    )


def _extract_pdf_page_raw_payload(pdf: pdfplumber.PDF, file_path: str = "") -> List[Dict[str, Any]]:
    from .ingest_pipeline.extractors.pdf_extractor import extract_pdf_page_raw_payload_legacy

    return extract_pdf_page_raw_payload_legacy(
        pdf,
        file_path=file_path,
        deps={"_norm": _norm, "fitz": fitz},
    )


def _transcript_rows_to_row_chunks(rows: Optional[List[Dict[str, Any]]], limit: int = 2500) -> List[str]:
    from .ingest_pipeline.chunking.row_serializers import transcript_rows_to_row_chunks

    return transcript_rows_to_row_chunks(rows, deps={"_norm": _norm, "_safe_int": _safe_int}, limit=limit)


def _transcript_rows_to_csv_text(rows: Optional[List[Dict[str, Any]]]) -> Tuple[str, int, int]:
    from .ingest_pipeline.chunking.row_serializers import transcript_rows_to_csv_text

    return transcript_rows_to_csv_text(rows, deps={"_norm": _norm, "_safe_int": _safe_int})


def _extract_transcript_rows_deterministic(
    text_blob: str,
    fallback_semester: Optional[int] = None,
) -> Dict[str, Any]:
    from .ingest_pipeline.parsers.structured_rows import extract_transcript_rows_deterministic

    return extract_transcript_rows_deterministic(
        text_blob,
        fallback_semester,
        deps={
            "_norm": _norm,
            "_safe_int": _safe_int,
            "_TRANSCRIPT_ROW_RE": _TRANSCRIPT_ROW_RE,
            "_TRANSCRIPT_PENDING_RE": _TRANSCRIPT_PENDING_RE,
            "_TRANSCRIPT_GRADE_PREFIX_RE": _TRANSCRIPT_GRADE_PREFIX_RE,
            "_TRANSCRIPT_GRADE_WHITELIST": _TRANSCRIPT_GRADE_WHITELIST,
        },
    )


from .ingest_pipeline.parsers.facade_parsers import (
    UniversalScheduleParserFacade as UniversalScheduleParser,
    UniversalTranscriptParserFacade as UniversalTranscriptParser,
)


def _repair_rows_with_llm(rows: List[Dict[str, Any]], source: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    from .ingest_pipeline.parsers.repair import repair_rows_with_llm

    return repair_rows_with_llm(
        rows,
        source,
        deps={
            "_norm": _norm,
            "_row_confidence": _row_confidence,
            "_extract_json_from_llm_response": _extract_json_from_llm_response,
            "_build_repair_llm": _build_repair_llm,
        },
        logger=logger,
    )


# =========================
# PDF extraction
# =========================
def _legacy_parser_deps() -> Dict[str, Any]:
    names = [
        "_norm",
        "_norm_header",
        "_looks_like_header_row",
        "_canonical_columns_from_header",
        "_display_columns_from_mapping",
        "_find_idx",
        "_row_to_text",
        "_normalize_time_range",
        "_normalize_day_text",
        "_is_noise_numbering_row",
        "_is_noise_header_repeat_row",
    ]
    out = {name: globals()[name] for name in names}
    out.update({"_DAY_WORDS": _legacy_helpers.DAY_WORDS, "_TIME_RANGE_RE": _TIME_RANGE_RE, "_MAX_SCHEDULE_ROWS": _MAX_SCHEDULE_ROWS})
    return out


def _extract_pdf_tables(pdf: pdfplumber.PDF) -> Tuple[str, List[str], List[Dict[str, Any]]]:
    from .ingest_pipeline.extractors.pdf_extractor import extract_pdf_tables_legacy

    return extract_pdf_tables_legacy(pdf, deps=_legacy_parser_deps())


def _build_process_document_deps() -> PipelineOps:
    return PipelineOps(
        pdfplumber=pdfplumber,
        get_vectorstore=get_vectorstore,
        UniversalTranscriptParser=UniversalTranscriptParser,
        UniversalScheduleParser=UniversalScheduleParser,
        extract_semester_from_text=_extract_semester_from_text,
        extract_pdf_tables=_extract_pdf_tables,
        extract_pdf_page_raw_payload=_extract_pdf_page_raw_payload,
        is_schedule_candidate=_is_schedule_candidate,
        is_transcript_candidate=_is_transcript_candidate,
        canonical_schedule_to_legacy_rows=_canonical_schedule_to_legacy_rows,
        repair_rows_with_llm=_repair_rows_with_llm,
        schedule_rows_to_row_chunks=_schedule_rows_to_row_chunks,
        schedule_rows_to_csv_text=_schedule_rows_to_csv_text,
        transcript_rows_to_row_chunks=_transcript_rows_to_row_chunks,
        transcript_rows_to_csv_text=_transcript_rows_to_csv_text,
        csv_preview=_csv_preview,
        norm=_norm,
        extract_transcript_rows_deterministic=_extract_transcript_rows_deterministic,
        detect_doc_type=_detect_doc_type,
        build_chunk_payloads=_build_chunk_payloads,
    )


def process_document(doc_instance) -> bool:
    from .ingest_pipeline.orchestrator import process_document as _process_document_impl

    return bool(_process_document_impl(doc_instance, deps=_build_process_document_deps()))
