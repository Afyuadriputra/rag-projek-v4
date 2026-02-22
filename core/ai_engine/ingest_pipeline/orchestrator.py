import json
import logging
import time
from typing import Any, Dict, List, Optional, Union

from .chunking.normalizers import csv_preview, schedule_rows_to_csv_text, transcript_rows_to_csv_text
from .extractors.pdf_extractor import extract_pdf_page_payload, extract_pdf_tables
from .extractors.tabular_extractor import extract_csv_markdown, extract_excel_markdown
from .extractors.text_extractor import extract_text_file
from .logging_utils import (
    log_chunk_stats,
    log_ingest_done,
    log_ingest_start,
    log_parser_fail,
    log_parser_ok,
    log_stage_timing,
)
from .parsers.parser_chain import run_schedule_parser_chain, run_transcript_parser_chain
from .settings import env_bool, env_int
from .schemas import PipelineOps
from .storage.metadata_builder import build_base_metadata, build_chunk_metadatas
from .storage.vector_writer import write_chunks

logger = logging.getLogger(__name__)


def _extract_ocr_fallback(file_path: str, page_count: int) -> str:
    try:
        from pdf2image import convert_from_path  # type: ignore
        import pytesseract  # type: ignore

        images = convert_from_path(file_path, first_page=1, last_page=min(2, page_count))
        return "\n".join([(pytesseract.image_to_string(img) or "").strip() for img in images]).strip()
    except Exception:
        return ""


def process_document(doc_instance: Any, *, deps: Union[Dict[str, Any], PipelineOps]) -> bool:
    t0 = time.perf_counter()
    extract_ms = 0
    parse_ms = 0
    chunk_ms = 0
    write_ms = 0

    ops = deps if isinstance(deps, PipelineOps) else PipelineOps.from_mapping(deps)
    deps_map = ops.as_legacy_mapping()
    file_path = doc_instance.file.path
    ext = file_path.split(".")[-1].lower()
    text_content = ""
    row_chunks: List[str] = []

    detected_columns: Optional[List[str]] = None
    schedule_rows: Optional[List[Dict[str, Any]]] = None
    transcript_rows: Optional[List[Dict[str, Any]]] = None
    semester_num: Optional[int] = ops.extract_semester_from_text(getattr(doc_instance, "title", ""))

    log_ingest_start(logger, doc_instance.title, ext)

    try:
        if ext == "pdf":
            with ops.pdfplumber.open(file_path) as pdf:
                t_extract = time.perf_counter()
                table_text, pdf_columns, pdf_schedule_rows = extract_pdf_tables(pdf, deps_map)
                if pdf_columns:
                    detected_columns = pdf_columns
                page_payload = extract_pdf_page_payload(pdf, file_path=file_path, deps=deps_map)
                extract_ms += int((time.perf_counter() - t_extract) * 1000)

                t_parse = time.perf_counter()
                schedule_chain = run_schedule_parser_chain(
                    enabled=env_bool("SCHEDULE_LLM_PARSER_ENABLED", True),
                    candidate=ops.is_schedule_candidate(title=getattr(doc_instance, "title", ""), detected_columns=detected_columns),
                    parser_cls=ops.UniversalScheduleParser,
                    page_payload=page_payload,
                    source=doc_instance.title,
                    fallback_semester=semester_num,
                    table_schedule_rows=pdf_schedule_rows,
                    deps=deps_map,
                )
                schedule_rows = schedule_chain.get("schedule_rows") or []
                schedule_parser_used = bool(schedule_chain.get("schedule_parser_used"))

                if schedule_rows and schedule_parser_used:
                    log_parser_ok(logger, "SCHEDULE_PARSER", doc_instance.title, len(schedule_rows), env_int("SCHEDULE_LLM_TIMEOUT", 45) and getattr(ops.UniversalScheduleParser(), "model_name", ""))
                elif env_bool("SCHEDULE_LLM_PARSER_ENABLED", True) and ops.is_schedule_candidate(title=getattr(doc_instance, "title", ""), detected_columns=detected_columns):
                    log_parser_fail(logger, "SCHEDULE_PARSER", doc_instance.title, "empty_or_fallback", "legacy")

                if schedule_rows:
                    if not schedule_parser_used:
                        schedule_rows, repair_stats = ops.repair_rows_with_llm(schedule_rows, doc_instance.title)
                        if repair_stats.get("enabled"):
                            logger.info(
                                " HYBRID_REPAIR source=%s checked=%s candidates=%s repaired=%s run=%s",
                                doc_instance.title,
                                repair_stats.get("checked", 0),
                                repair_stats.get("candidates", 0),
                                repair_stats.get("repaired", 0),
                                repair_stats.get("run_id", "-"),
                            )

                    row_chunks = ops.schedule_rows_to_row_chunks(schedule_rows)
                    csv_repr, csv_rows, csv_cols = schedule_rows_to_csv_text(schedule_rows, deps_map)
                    if csv_repr:
                        text_content += "\n[CSV_CANONICAL]\n" + csv_repr + "\n"
                        preview_lines = env_int("CSV_REVIEW_PREVIEW_LINES", 12)
                        preview = csv_preview(csv_repr, deps_map, max_lines=preview_lines)
                        logger.info(" CSV canonical review source=%s rows=%s cols=%s\n%s", doc_instance.title, csv_rows, csv_cols, preview)
                    try:
                        json_blob = json.dumps(schedule_rows[: max(20, env_int("JSON_CANONICAL_EMBED_ROWS", 300))], ensure_ascii=True)
                        text_content += "\n[JSON_CANONICAL]\n" + json_blob + "\n"
                    except Exception:
                        pass

                transcript_chain = run_transcript_parser_chain(
                    enabled=env_bool("TRANSCRIPT_LLM_PARSER_ENABLED", True),
                    candidate=ops.is_transcript_candidate(title=getattr(doc_instance, "title", ""), detected_columns=detected_columns),
                    parser_cls=ops.UniversalTranscriptParser,
                    page_payload=page_payload,
                    source=doc_instance.title,
                    fallback_semester=semester_num,
                    deps=deps_map,
                )
                transcript_rows = transcript_chain.get("transcript_rows") or []
                transcript_source = str(transcript_chain.get("source") or "")
                if transcript_source == "deterministic" and transcript_rows:
                    stats = transcript_chain.get("stats") or {}
                    logger.info(
                        " TRANSCRIPT_DETERMINISTIC_OK source=%s rows_valid=%s rows_detected=%s pending=%s ipk=%s sks=%s/%s",
                        doc_instance.title,
                        len(transcript_rows),
                        int(stats.get("rows_detected") or 0),
                        int(stats.get("rows_pending") or 0),
                        str(stats.get("ipk") or "-"),
                        str(stats.get("sks_done") or "-"),
                        str(stats.get("sks_required") or "-"),
                    )
                elif transcript_source == "llm" and transcript_rows:
                    log_parser_ok(logger, "TRANSCRIPT_PARSER", doc_instance.title, len(transcript_rows), getattr(ops.UniversalTranscriptParser(), "model_name", ""))
                elif transcript_source == "llm_fail":
                    log_parser_fail(logger, "TRANSCRIPT_PARSER", doc_instance.title, transcript_chain.get("error") or "unknown_error", "legacy")

                if transcript_rows:
                    row_chunks = ops.transcript_rows_to_row_chunks(transcript_rows)
                    t_csv, t_rows, t_cols = transcript_rows_to_csv_text(transcript_rows, deps_map)
                    if t_csv:
                        text_content += "\n[TRANSCRIPT_CSV_CANONICAL]\n" + t_csv + "\n"
                        t_preview = csv_preview(t_csv, deps_map, max_lines=env_int("CSV_REVIEW_PREVIEW_LINES", 12))
                        logger.info(" TRANSCRIPT canonical review source=%s rows=%s cols=%s\n%s", doc_instance.title, t_rows, t_cols, t_preview)
                    try:
                        text_content += "\n[TRANSCRIPT_JSON_CANONICAL]\n" + json.dumps(transcript_rows[:1200], ensure_ascii=True) + "\n"
                    except Exception:
                        pass
                parse_ms += int((time.perf_counter() - t_parse) * 1000)

                t_extract_text = time.perf_counter()
                if table_text:
                    text_content += table_text + "\n"
                for page in pdf.pages:
                    page_text = (page.extract_text() or "").strip()
                    if page_text:
                        text_content += page_text + "\n"
                        if semester_num is None:
                            semester_num = ops.extract_semester_from_text(page_text)

                if not text_content.strip():
                    ocr_blob = _extract_ocr_fallback(file_path, len(pdf.pages))
                    if ocr_blob:
                        text_content += ocr_blob + "\n"
                        if semester_num is None:
                            semester_num = ops.extract_semester_from_text(ocr_blob)
                extract_ms += int((time.perf_counter() - t_extract_text) * 1000)

        elif ext in {"xlsx", "xls"}:
            t_extract = time.perf_counter()
            parsed = extract_excel_markdown(file_path)
            text_content = parsed["text_content"]
            detected_columns = list(parsed["detected_columns"])
            logger.debug(" Excel Parsed: %s baris data.", parsed["rows_count"])
            extract_ms += int((time.perf_counter() - t_extract) * 1000)

        elif ext == "csv":
            t_extract = time.perf_counter()
            parsed = extract_csv_markdown(file_path)
            text_content = parsed["text_content"]
            detected_columns = list(parsed["detected_columns"])
            logger.debug(" CSV Parsed: %s baris data.", parsed["rows_count"])
            extract_ms += int((time.perf_counter() - t_extract) * 1000)

        elif ext in {"md", "txt"}:
            t_extract = time.perf_counter()
            text_content = extract_text_file(file_path)
            logger.debug(" Text Parsed.")
            extract_ms += int((time.perf_counter() - t_extract) * 1000)
        else:
            logger.warning(" Tipe file tidak didukung: %s", ext)
            return False

        if not text_content.strip():
            logger.warning(" FILE KOSONG: %s tidak mengandung teks yang bisa dibaca.", doc_instance.title)
            return False

        t_chunk = time.perf_counter()
        doc_type = "transcript" if transcript_rows else ops.detect_doc_type(detected_columns, schedule_rows)
        if doc_type == "transcript" and transcript_rows:
            row_chunks = ops.transcript_rows_to_row_chunks(transcript_rows)

        chunk_payloads_all = ops.build_chunk_payloads(
            doc_type=doc_type,
            text_content=text_content,
            row_chunks=row_chunks,
            schedule_rows=schedule_rows,
        )
        chunk_payloads = [x for x in chunk_payloads_all if str(x.get("text") or "").strip()]
        if not chunk_payloads:
            logger.warning(" CHUNKING GAGAL: Tidak ada potongan teks untuk %s.", doc_instance.title)
            return False

        chunks = [str(x.get("text") or "") for x in chunk_payloads]
        if schedule_rows and semester_num is not None:
            for row in schedule_rows:
                if isinstance(row, dict) and "semester" not in row:
                    row["semester"] = str(semester_num)

        vectorstore = ops.get_vectorstore()
        base_meta = build_base_metadata(
            doc_instance=doc_instance,
            ext=ext,
            detected_columns=detected_columns,
            schedule_rows=schedule_rows,
            transcript_rows=transcript_rows,
            semester_num=semester_num,
            doc_type=doc_type,
            row_chunks=row_chunks,
        )
        metadatas = build_chunk_metadatas(base_meta, chunk_payloads)
        chunk_ms += int((time.perf_counter() - t_chunk) * 1000)

        t_write = time.perf_counter()
        log_chunk_stats(logger, doc_instance.title, len(chunks), len(detected_columns or []), len(schedule_rows or []))
        write_chunks(vectorstore, chunks, metadatas)
        write_ms += int((time.perf_counter() - t_write) * 1000)

        total_ms = int((time.perf_counter() - t0) * 1000)
        log_stage_timing(
            logger,
            doc_instance.title,
            extract_ms=extract_ms,
            parse_ms=parse_ms,
            chunk_ms=chunk_ms,
            write_ms=write_ms,
            total_ms=total_ms,
        )
        log_ingest_done(logger, doc_instance.title)
        return True
    except Exception as exc:
        logger.error(" CRITICAL ERROR di ingest.py pada file %s: %s", doc_instance.title, str(exc), exc_info=True)
        return False
