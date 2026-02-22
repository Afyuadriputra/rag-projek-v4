from __future__ import annotations

import os
import time
from typing import Any, Dict, List

from ...domain.models import QueryContext, StructuredResult
from .fetch import fetch_row_chunks, fetch_transcript_text_chunks
from .filter import (
    dedupe_transcript_latest,
    extract_course_query_term,
    extract_day_filter,
    extract_semester_filter,
    is_course_recap_query,
    is_low_grade_query,
)
from .normalize import normalize_schedule_from_chunk, normalize_transcript_from_chunk
from .render import (
    extract_transcript_profile,
    render_schedule_answer,
    render_sources,
    render_transcript_answer,
)


def run(query_ctx: QueryContext) -> StructuredResult:
    started = time.time()
    query = str(query_ctx.query or "")
    ql = query.lower()
    is_schedule = any(k in ql for k in ["jadwal", "krs", "hari"])
    low_grade = is_low_grade_query(query)
    course_recap = is_course_recap_query(query)
    doc_type = "schedule" if is_schedule else "transcript"
    rows_raw = fetch_row_chunks(user_id=int(query_ctx.user_id), doc_type=doc_type, doc_ids=query_ctx.doc_ids)

    if doc_type == "transcript" and (not rows_raw) and (not low_grade) and course_recap:
        fallback_schedule = fetch_row_chunks(user_id=int(query_ctx.user_id), doc_type="schedule", doc_ids=query_ctx.doc_ids)
        if fallback_schedule:
            doc_type = "schedule"
            rows_raw = fallback_schedule

    if not rows_raw:
        return StructuredResult(
            ok=False,
            answer=(
                "## Ringkasan\n"
                "Maaf, data tidak ditemukan di dokumen Anda.\n\n"
                "## Opsi Lanjut\n"
                "- Pastikan dokumen akademik sudah terunggah.\n"
                "- Jika sudah upload, coba sebutkan detail semester/hari."
            ),
            sources=[],
            doc_type=doc_type,
            facts=[],
            stats={"raw": 0, "deduped": 0, "returned": 0, "latency_ms": int((time.time() - started) * 1000)},
            reason="no_row_chunks",
        )

    if doc_type == "transcript":
        normalized = [normalize_transcript_from_chunk(chunk, meta) for chunk, meta in rows_raw]
        rows = [x for x in normalized if isinstance(x, dict)]
        deduped = dedupe_transcript_latest(rows)
        filtered = list(deduped)

        full_recap_requested = any(k in ql for k in ["rekap", "ringkas", "rangkum", "semua", "daftar"])
        semester_filter = extract_semester_filter(query)
        if semester_filter is not None:
            filtered = [x for x in filtered if int(x.get("semester") or 0) == int(semester_filter)]
        if low_grade:
            low_grade_set = {
                str(x or "").strip().upper()
                for x in str(os.environ.get("RAG_ANALYTICS_LOW_GRADES", "C,D,E,CD,D+,D-")).split(",")
                if str(x or "").strip()
            }
            filtered = [x for x in filtered if str(x.get("nilai_huruf") or "").strip().upper() in low_grade_set]

        course_term = extract_course_query_term(query)
        if course_term and not full_recap_requested:
            term_lc = course_term.lower()
            filtered_by_course = [x for x in filtered if term_lc in str(x.get("mata_kuliah") or "").lower()]
            if filtered_by_course:
                filtered = filtered_by_course

        profile = extract_transcript_profile(
            fetch_transcript_text_chunks(user_id=int(query_ctx.user_id), doc_ids=query_ctx.doc_ids)
        )
        answer = render_transcript_answer(filtered, query=query, profile=profile)
        return StructuredResult(
            ok=True,
            answer=answer,
            sources=render_sources(filtered if filtered else deduped),
            doc_type=doc_type,
            facts=filtered,
            stats={
                "raw": len(rows),
                "deduped": len(deduped),
                "returned": len(filtered),
                "latency_ms": int((time.time() - started) * 1000),
            },
            reason="structured_transcript",
        )

    normalized_schedule = [normalize_schedule_from_chunk(chunk, meta) for chunk, meta in rows_raw]
    schedule_rows = [x for x in normalized_schedule if isinstance(x, dict)]
    day_filter = extract_day_filter(query)
    filtered_schedule = list(schedule_rows)
    if day_filter:
        filtered_schedule = [x for x in schedule_rows if str(x.get("hari") or "").lower() == day_filter.lower()]
    filtered_schedule.sort(
        key=lambda x: (
            str(x.get("hari") or ""),
            str(x.get("jam_mulai") or ""),
            str(x.get("mata_kuliah") or ""),
        )
    )
    answer = render_schedule_answer(filtered_schedule, day_filter=day_filter)
    return StructuredResult(
        ok=True,
        answer=answer,
        sources=render_sources(filtered_schedule if filtered_schedule else schedule_rows),
        doc_type=doc_type,
        facts=filtered_schedule,
        stats={
            "raw": len(schedule_rows),
            "deduped": len(schedule_rows),
            "returned": len(filtered_schedule),
            "latency_ms": int((time.time() - started) * 1000),
        },
        reason="structured_schedule",
    )
