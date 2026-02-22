from typing import Any


def log_ingest_start(logger: Any, source: str, ext: str) -> None:
    logger.info(" MULAI PARSING: %s (Type: %s)", source, ext)


def log_parser_ok(logger: Any, parser_name: str, source: str, rows: int, model: str = "") -> None:
    logger.info(" %s_OK source=%s rows=%s model=%s", parser_name, source, rows, model or "-")


def log_parser_fail(logger: Any, parser_name: str, source: str, reason: str, fallback: str = "legacy") -> None:
    logger.warning(" %s_FAIL source=%s reason=%s fallback=%s", parser_name, source, reason or "unknown_error", fallback)


def log_chunk_stats(logger: Any, source: str, chunks: int, cols: int, rows: int) -> None:
    logger.debug(" Menyimpan ke ChromaDB... chunks=%s cols=%s schedule_rows=%s", chunks, cols, rows)


def log_ingest_done(logger: Any, source: str) -> None:
    logger.info(" INGEST SELESAI: %s berhasil masuk Knowledge Base.", source)


def log_stage_timing(
    logger: Any,
    source: str,
    *,
    extract_ms: int,
    parse_ms: int,
    chunk_ms: int,
    write_ms: int,
    total_ms: int,
) -> None:
    logger.info(
        " INGEST_TIMING source=%s extract_ms=%s parse_ms=%s chunk_ms=%s write_ms=%s total_ms=%s",
        source,
        extract_ms,
        parse_ms,
        chunk_ms,
        write_ms,
        total_ms,
    )
