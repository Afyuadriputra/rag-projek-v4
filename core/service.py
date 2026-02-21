# core/service.py
import time
import logging
import os
import json
import re
from datetime import timedelta
from typing import Any, Dict, List, Tuple

from django.contrib.auth.models import User
from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone

from .models import AcademicDocument, ChatHistory, ChatSession, PlannerHistory, PlannerRun, UserQuota
from .ai_engine.ingest import process_document
from .ai_engine.retrieval import ask_bot
from .ai_engine.vector_ops import delete_vectors_for_doc, delete_vectors_for_doc_strict
from .ai_engine.config import get_vectorstore
from .ai_engine.retrieval.llm import (
    build_llm,
    get_backup_models,
    get_runtime_openrouter_config,
    invoke_text,
)
from .ai_engine.retrieval.prompt import PLANNER_OUTPUT_TEMPLATE
from .ai_engine.retrieval.rules import extract_grade_calc_input, is_grade_rescue_query
from .academic import planner as planner_engine
from .academic.profile_extractor import extract_profile_hints
from .academic.grade_calculator import (
    analyze_transcript_risks,
    calculate_required_score,
)


logger = logging.getLogger(__name__)



# =========================
# Helpers (logic layer)
# =========================
def bytes_to_human(n: int) -> str:
    """
    [HELPER] Konversi ukuran byte -> teks ramah manusia (KB/MB/GB).
    Dipakai untuk menampilkan storage usage di UI dashboard/documents.
    """
    try:
        n = int(n)
    except Exception:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(n)
    for u in units:
        if size < 1024 or u == units[-1]:
            return f"{size:.2f} {u}" if u != "B" else f"{int(size)} {u}"
        size /= 1024
    return f"{int(n)} B"


def serialize_documents_for_user(user: User, limit: int = 50) -> Tuple[List[Dict[str, Any]], int]:
    """
    [HELPER] Ambil daftar dokumen milik user dari DB + hitung total ukuran file.
    Output:
      - documents: list dict (untuk ditampilkan di frontend)
      - total_bytes: total ukuran semua file (buat progress quota)
    """
    docs_qs = AcademicDocument.objects.filter(user=user).order_by("-uploaded_at")[:limit]
    documents: List[Dict[str, Any]] = []
    total_bytes = 0

    for d in docs_qs:
        size = 0
        try:
            if d.file and hasattr(d.file, "size"):
                size = d.file.size or 0
        except Exception:
            size = 0

        total_bytes += size
        documents.append({
            "id": d.id,
            "title": d.title,
            "is_embedded": d.is_embedded,
            "uploaded_at": d.uploaded_at.strftime("%Y-%m-%d %H:%M"),
            "size_bytes": size,
        })

    return documents, total_bytes


def serialize_sessions_for_user(user: User, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    qs = ChatSession.objects.filter(user=user).order_by("-updated_at")
    sessions = qs[offset:offset + limit]
    return [
        {
            "id": s.id,
            "title": s.title,
            "created_at": s.created_at.strftime("%Y-%m-%d %H:%M"),
            "updated_at": s.updated_at.strftime("%Y-%m-%d %H:%M"),
        }
        for s in sessions
    ]


def _get_or_create_default_session(user: User) -> ChatSession:
    session = ChatSession.objects.filter(user=user).order_by("-updated_at").first()
    if session:
        return session
    return ChatSession.objects.create(user=user, title="Chat Baru")


def get_or_create_chat_session(user: User, session_id: int | None = None) -> ChatSession:
    if session_id:
        session = ChatSession.objects.filter(user=user, id=session_id).first()
        if session:
            return session
    return _get_or_create_default_session(user)


def _attach_legacy_history_to_session(user: User, session: ChatSession) -> None:
    """
    Migrasi ringan: history lama tanpa session diarahkan ke session default.
    """
    ChatHistory.objects.filter(user=user, session__isnull=True).update(session=session)


def build_storage_payload(total_bytes: int, quota_bytes: int) -> Dict[str, Any]:
    """
    [HELPER] Bentuk payload storage (used/quota/persen) untuk UI.
    Dipakai di dashboard & endpoint documents.
    """
    quota_bytes = max(int(quota_bytes), 1)
    used_pct = int(min(100, (total_bytes / quota_bytes) * 100))
    return {
        "used_bytes": int(total_bytes),
        "quota_bytes": int(quota_bytes),
        "used_pct": used_pct,
        "used_human": bytes_to_human(total_bytes),
        "quota_human": bytes_to_human(quota_bytes),
    }


# =========================
# Use-cases (business logic)
# =========================
def get_dashboard_props(user: User, quota_bytes: int) -> Dict[str, Any]:
    """
    [USE-CASE UTAMA: DASHBOARD]
    Menyusun semua data awal untuk halaman utama chat (Inertia page):
      1) Profile user
      2) Riwayat chat user (initialHistory)
      3) Daftar dokumen user
      4) Informasi storage/quota
    """
    session = _get_or_create_default_session(user)
    _attach_legacy_history_to_session(user, session)

    histories = ChatHistory.objects.filter(user=user, session=session).order_by("timestamp")
    history_data = [
        {
            "question": h.question,
            "answer": h.answer,
            "time": h.timestamp.strftime("%H:%M"),
            "date": h.timestamp.strftime("%Y-%m-%d"),
        }
        for h in histories
    ]

    documents, total_bytes = serialize_documents_for_user(user, limit=50)
    storage = build_storage_payload(total_bytes, quota_bytes)
    sessions = serialize_sessions_for_user(user, limit=50)

    return {
        "user": {"id": user.id, "username": user.username, "email": user.email},
        "activeSessionId": session.id,
        "sessions": sessions,
        "initialHistory": history_data,
        "documents": documents,
        "storage": storage,
    }


def get_user_quota_bytes(user: User, default_quota_bytes: int) -> int:
    try:
        quota = UserQuota.objects.filter(user=user).first()
        if quota and quota.quota_bytes and quota.quota_bytes > 0:
            return int(quota.quota_bytes)
    except Exception:
        pass
    return int(default_quota_bytes)


def get_documents_payload(user: User, quota_bytes: int) -> Dict[str, Any]:
    """
    [USE-CASE UTAMA: LIST DOKUMEN]
    Payload untuk endpoint GET /api/documents/:
      - daftar dokumen milik user
      - storage usage/quota
    """
    documents, total_bytes = serialize_documents_for_user(user, limit=50)
    storage = build_storage_payload(total_bytes, quota_bytes)
    return {"documents": documents, "storage": storage}


def upload_files_batch(user: User, files: List[UploadedFile], quota_bytes: int) -> Dict[str, Any]:
    """
    [USE-CASE UTAMA: UPLOAD + INGEST]
    Dipanggil oleh endpoint POST /api/upload/
    Alur sistem:
      1) Simpan file ke AcademicDocument (DB + media/)
      2) Ingest ke vector DB (Chroma) via process_document()
      3) Jika sukses -> is_embedded=True
      4) Jika gagal parsing -> hapus record agar DB bersih
    """
    success_count = 0
    error_count = 0
    errors: List[str] = []

    # cek kuota (total file yang sudah ada)
    _, total_bytes = serialize_documents_for_user(user, limit=100000)
    remaining_bytes = max(0, int(quota_bytes) - int(total_bytes))

    for file_obj in files:
        file_size = getattr(file_obj, "size", 0) or 0
        if (total_bytes + file_size) > quota_bytes:
            error_count += 1
            errors.append(
                f"{file_obj.name} (Melebihi kuota. Sisa {bytes_to_human(remaining_bytes)}, file {bytes_to_human(file_size)})"
            )
            continue
        try:
            doc = AcademicDocument.objects.create(user=user, file=file_obj)
            total_bytes += file_size
            remaining_bytes = max(0, int(quota_bytes) - int(total_bytes))

            ok = process_document(doc)
            if ok:
                doc.is_embedded = True
                doc.save(update_fields=["is_embedded"])
                success_count += 1
            else:
                doc.delete()
                error_count += 1
                errors.append(f"{file_obj.name} (Gagal Parsing)")

        except Exception:
            error_count += 1
            errors.append(f"{file_obj.name} (System Error)")

    if success_count > 0:
        msg = f"Berhasil memproses {success_count} file."
        if error_count > 0:
            msg += f" (Gagal: {error_count})"
        return {"status": "success", "msg": msg}
    else:
        return {"status": "error", "msg": f"Gagal semua. Detail: {', '.join(errors)}"}


def _maybe_update_session_title(session: ChatSession, message: str) -> None:
    if not session or not message:
        return
    if (session.title or "").strip().lower() == "chat baru":
        title = message.strip()
        if len(title) > 60:
            title = title[:60] + "..."
        session.title = title
        session.save(update_fields=["title", "updated_at"])


def _build_grade_rescue_response(parsed: Dict[str, Any], calc: Dict[str, Any]) -> str:
    current_score = float(parsed.get("current_score", 0) or 0)
    current_weight = float(parsed.get("current_weight", 0) or 0)
    target_score = float(parsed.get("target_score", 70) or 70)
    remaining_weight = float(parsed.get("remaining_weight", 0) or 0)

    required = calc.get("required")
    possible = bool(calc.get("possible"))
    required_text = "-"
    if required is not None:
        required_text = f"{float(required):.2f}"

    status_text = "Masih memungkinkan." if possible else "Target ini sulit/tidak memungkinkan pada bobot tersisa."

    return (
        "## Ringkasan Grade Rescue\n"
        f"- Nilai saat ini: **{current_score:.2f}** (bobot **{current_weight:.0f}%**)\n"
        f"- Target akhir: **{target_score:.2f}**\n"
        f"- Bobot tersisa: **{remaining_weight:.0f}%**\n"
        f"- Nilai minimal pada komponen tersisa: **{required_text}**\n\n"
        "## Insight\n"
        f"- Status: **{status_text}**\n"
        f"- Poin yang masih dibutuhkan: **{float(calc.get('needed_points', 0) or 0):.2f}**\n\n"
        "## Opsi Lanjut\n"
        "1. Kirim detail komponen nilai (tugas/UTS/UAS) agar simulasi lebih akurat.\n"
        "2. Saya bisa bantu strategi belajar 2-4 minggu untuk kejar target."
    )


def _build_grade_rescue_markdown(calc_input: Dict[str, Any] | None, calc_result: Dict[str, Any] | None) -> str:
    if not calc_input or not calc_result:
        return "- Tidak ada data grade rescue spesifik dari input user."

    required = calc_result.get("required")
    required_text = "-" if required is None else f"{float(required):.2f}"
    possible_text = "Ya" if calc_result.get("possible") else "Tidak"

    return (
        f"- Nilai saat ini: {float(calc_input.get('current_score', 0) or 0):.2f}\n"
        f"- Bobot saat ini: {float(calc_input.get('current_weight', 0) or 0):.0f}%\n"
        f"- Target akhir: {float(calc_input.get('target_score', 70) or 70):.2f}\n"
        f"- Bobot tersisa: {float(calc_input.get('remaining_weight', 0) or 0):.0f}%\n"
        f"- Minimal nilai komponen tersisa: {required_text}\n"
        f"- Target mungkin dicapai: {possible_text}"
    )


def _append_verified_grade_rescue(
    answer: str,
    calc_input: Dict[str, Any] | None,
    calc_result: Dict[str, Any] | None,
) -> str:
    if not calc_input or not calc_result:
        return answer

    required = calc_result.get("required")
    required_text = "-" if required is None else f"{float(required):.2f}"
    possible_text = "Ya" if calc_result.get("possible") else "Tidak"
    verified_block = (
        "\n\n## Grade Rescue (Kalkulasi Sistem)\n"
        f"- Nilai saat ini: **{float(calc_input.get('current_score', 0) or 0):.2f}** "
        f"(bobot **{float(calc_input.get('current_weight', 0) or 0):.0f}%**)\n"
        f"- Target akhir: **{float(calc_input.get('target_score', 70) or 70):.2f}**\n"
        f"- Bobot tersisa: **{float(calc_input.get('remaining_weight', 0) or 0):.0f}%**\n"
        f"- Nilai minimal komponen tersisa: **{required_text}**\n"
        f"- Target mungkin dicapai: **{possible_text}**"
    )

    # Hindari duplikasi jika block sudah ada.
    if "Grade Rescue (Kalkulasi Sistem)" in (answer or ""):
        return answer
    return (answer or "").rstrip() + verified_block


def _planner_context_for_user(user: User, query: str) -> str:
    try:
        vectorstore = get_vectorstore()
        docs = vectorstore.similarity_search(query or "rencana studi", k=8, filter={"user_id": str(user.id)})
    except Exception:
        return ""

    if not docs:
        return ""

    parts: List[str] = []
    for i, doc in enumerate(docs[:5], start=1):
        content = (getattr(doc, "page_content", "") or "").strip()
        if not content:
            continue
        content = content[:1200]
        parts.append(f"[Doc {i}]\n{content}")
    return "\n\n".join(parts)


def _generate_planner_with_llm(
    user: User,
    collected: Dict[str, Any],
    grade_rescue_data: str,
    request_id: str = "-",
) -> str:
    runtime_cfg = get_runtime_openrouter_config()
    api_key = (runtime_cfg.get("api_key") or "").strip()
    if not api_key:
        return ""

    prompt = PLANNER_OUTPUT_TEMPLATE.format(
        jurusan=collected.get("jurusan") or "-",
        semester=collected.get("semester") or "-",
        goal=collected.get("goal") or "-",
        career=collected.get("career") or "-",
        time_pref=collected.get("time_pref") or "-",
        free_day=collected.get("free_day") or "-",
        balance_pref="merata" if collected.get("balance_load") else "fleksibel",
        context=_planner_context_for_user(user, "rencana studi dan jadwal"),
        grade_rescue_data=grade_rescue_data,
    )

    backup_models = get_backup_models(
        str(runtime_cfg.get("model") or ""),
        runtime_cfg.get("backup_models"),
    )
    last_error = ""
    for model_name in backup_models:
        try:
            llm = build_llm(model_name, runtime_cfg)
            answer = invoke_text(llm, prompt).strip()
            if answer:
                return answer
        except Exception as e:
            last_error = str(e)
            continue

    if last_error:
        logger.warning("planner llm failed request_id=%s err=%s", request_id, last_error)
    return ""


def chat_and_save(user: User, message: str, request_id: str = "-", session_id: int | None = None) -> Dict[str, Any]:
    """
    [USE-CASE UTAMA: CHAT RAG + SIMPAN HISTORY]
    Dipanggil oleh endpoint POST /api/chat/
    Alur sistem:
      1) Jalankan RAG (retrieval + LLM) via ask_bot()
      2) Simpan jawaban ke ChatHistory (DB)
      3) Kembalikan response ke frontend

     Pembaruan penting:
    - ask_bot() sekarang mengembalikan dict:
        {"answer": "...", "sources": [...], "meta": {...}}
      agar frontend bisa menampilkan "rujukan/source trace".
    """
    session = get_or_create_chat_session(user=user, session_id=session_id)

    parsed_grade = extract_grade_calc_input(message) if is_grade_rescue_query(message) else None
    if parsed_grade:
        calc = calculate_required_score(
            achieved_components=parsed_grade.get("achieved_components") or [],
            target_final_score=float(parsed_grade.get("target_final_score", 70) or 70),
            remaining_weight=float(parsed_grade.get("remaining_weight", 0) or 0),
        )
        result: Dict[str, Any] = {"answer": _build_grade_rescue_response(parsed_grade, calc), "sources": []}
    else:
        result = ask_bot(user.id, message, request_id=request_id)

    # Normalisasi output (biar backward compatible kalau suatu saat ask_bot return string)
    if isinstance(result, dict):
        answer = result.get("answer", "")
        sources = result.get("sources", []) or []
        meta = result.get("meta", {}) or {}
    else:
        answer = str(result)
        sources = []
        meta = {}

    ChatHistory.objects.create(user=user, session=session, question=message, answer=answer)
    _maybe_update_session_title(session, message)
    if session:
        session.save(update_fields=["updated_at"])

    # Return ke API: answer + sources (sources bisa ditampilkan di UI)
    return {"answer": answer, "sources": sources, "meta": meta, "session_id": session.id}


def list_sessions(user: User, limit: int = 50, page: int = 1) -> Dict[str, Any]:
    page = max(int(page), 1)
    limit = max(int(limit), 1)
    offset = (page - 1) * limit
    total = ChatSession.objects.filter(user=user).count()
    sessions = serialize_sessions_for_user(user, limit=limit, offset=offset)
    has_next = (offset + limit) < total
    return {
        "sessions": sessions,
        "pagination": {
            "page": page,
            "page_size": limit,
            "total": total,
            "has_next": has_next,
        },
    }


def create_session(user: User, title: str | None = None) -> Dict[str, Any]:
    t = (title or "").strip() or "Chat Baru"
    session = ChatSession.objects.create(user=user, title=t)
    return {
        "id": session.id,
        "title": session.title,
        "created_at": session.created_at.strftime("%Y-%m-%d %H:%M"),
        "updated_at": session.updated_at.strftime("%Y-%m-%d %H:%M"),
    }


def rename_session(user: User, session_id: int, title: str | None = None) -> Dict[str, Any] | None:
    session = ChatSession.objects.filter(user=user, id=session_id).first()
    if not session:
        return None
    t = (title or "").strip() or "Chat Baru"
    session.title = t
    session.save(update_fields=["title", "updated_at"])
    return {
        "id": session.id,
        "title": session.title,
        "created_at": session.created_at.strftime("%Y-%m-%d %H:%M"),
        "updated_at": session.updated_at.strftime("%Y-%m-%d %H:%M"),
    }


def delete_session(user: User, session_id: int) -> bool:
    session = ChatSession.objects.filter(user=user, id=session_id).first()
    if not session:
        return False
    session.delete()
    return True


def get_session_history(user: User, session_id: int) -> List[Dict[str, Any]]:
    session = ChatSession.objects.filter(user=user, id=session_id).first()
    if not session:
        return []
    histories = ChatHistory.objects.filter(user=user, session=session).order_by("timestamp")
    return [
        {
            "question": h.question,
            "answer": h.answer,
            "time": h.timestamp.strftime("%H:%M"),
            "date": h.timestamp.strftime("%Y-%m-%d"),
        }
        for h in histories
    ]


def _planner_option_label_from_payload(payload: Dict[str, Any], option_id: int | None) -> str:
    if option_id is None:
        return ""
    for opt in payload.get("options", []) or []:
        try:
            if int(opt.get("id")) == int(option_id):
                return str(opt.get("label") or "").strip()
        except Exception:
            continue
    return ""


def _trim_text(value: str, max_len: int = 300) -> str:
    txt = (value or "").strip()
    if len(txt) <= max_len:
        return txt
    return txt[:max_len].rstrip() + "..."


def record_planner_history(
    *,
    user: User,
    session: ChatSession,
    event_type: str,
    planner_step: str,
    text: str,
    option_id: int | None = None,
    option_label: str = "",
    payload: Dict[str, Any] | None = None,
) -> None:
    PlannerHistory.objects.create(
        user=user,
        session=session,
        event_type=event_type,
        planner_step=(planner_step or "")[:64],
        text=_trim_text(text, max_len=1000),
        option_id=option_id,
        option_label=(option_label or "")[:255],
        payload=payload or {},
    )


def get_session_timeline(user: User, session_id: int, page: int = 1, page_size: int = 100) -> Dict[str, Any]:
    session = ChatSession.objects.filter(user=user, id=session_id).first()
    if not session:
        return {
            "timeline": [],
            "pagination": {"page": max(int(page), 1), "page_size": max(int(page_size), 1), "total": 0, "has_next": False},
        }

    events: List[Tuple[Any, int, Dict[str, Any]]] = []
    chat_qs = ChatHistory.objects.filter(user=user, session=session).order_by("timestamp")
    planner_qs = PlannerHistory.objects.filter(user=user, session=session).order_by("created_at")

    for h in chat_qs:
        events.append(
            (
                h.timestamp,
                0,
                {
                    "id": f"chat-user-{h.id}",
                    "kind": "chat_user",
                    "text": h.question,
                    "time": h.timestamp.strftime("%H:%M"),
                    "date": h.timestamp.strftime("%Y-%m-%d"),
                },
            )
        )
        events.append(
            (
                h.timestamp,
                1,
                {
                    "id": f"chat-assistant-{h.id}",
                    "kind": "chat_assistant",
                    "text": h.answer,
                    "time": h.timestamp.strftime("%H:%M"),
                    "date": h.timestamp.strftime("%Y-%m-%d"),
                },
            )
        )

    for p in planner_qs:
        kind = "planner_output" if p.event_type == PlannerHistory.EVENT_GENERATE else "planner_milestone"
        meta = {
            "planner_step": p.planner_step,
            "event_type": p.event_type,
            "option_id": p.option_id,
            "option_label": p.option_label,
            "warning": (p.payload or {}).get("planner_warning"),
            "confidence_summary": ((p.payload or {}).get("profile_hints") or {}).get("confidence_summary"),
        }
        events.append(
            (
                p.created_at,
                2,
                {
                    "id": f"planner-{p.id}",
                    "kind": kind,
                    "text": p.text,
                    "time": p.created_at.strftime("%H:%M"),
                    "date": p.created_at.strftime("%Y-%m-%d"),
                    "meta": meta,
                },
            )
        )

    events.sort(key=lambda x: (x[0], x[1]))
    rows = [e[2] for e in events]
    page = max(int(page), 1)
    page_size = max(int(page_size), 1)
    offset = (page - 1) * page_size
    selected = rows[offset : offset + page_size]
    total = len(rows)
    has_next = (offset + page_size) < total
    return {
        "timeline": selected,
        "pagination": {"page": page, "page_size": page_size, "total": total, "has_next": has_next},
    }

def reingest_documents_for_user(user: User, doc_ids: List[int] | None = None) -> Dict[str, Any]:
    """
    Re-ingest dokumen milik user tanpa upload ulang.
    - Hapus embedding lama dulu (by doc_id)
    - Jalankan process_document lagi
    """
    qs = AcademicDocument.objects.filter(user=user).order_by("-uploaded_at")
    if doc_ids:
        qs = qs.filter(id__in=doc_ids)

    total = qs.count()
    if total == 0:
        return {"status": "error", "msg": "Tidak ada dokumen untuk di-reingest."}

    ok_count = 0
    fail_count = 0
    fails: List[str] = []

    for doc in qs:
        try:
            #  delete embeddings lama
            delete_vectors_for_doc(user_id=str(user.id), doc_id=str(doc.id), source=getattr(doc, "title", None))

            #  ingest ulang
            ok = process_document(doc)
            if ok:
                doc.is_embedded = True
                doc.save(update_fields=["is_embedded"])
                ok_count += 1
            else:
                fail_count += 1
                fails.append(f"{doc.title} (Gagal Parsing)")

        except Exception:
            fail_count += 1
            fails.append(f"{doc.title} (System Error)")

    if ok_count > 0:
        msg = f"Re-ingest berhasil: {ok_count}/{total} dokumen."
        if fail_count > 0:
            msg += f" Gagal: {fail_count} ({', '.join(fails[:5])}{'...' if len(fails) > 5 else ''})"
        return {"status": "success", "msg": msg}

    return {"status": "error", "msg": f"Gagal re-ingest semua dokumen. Detail: {', '.join(fails)}"}


def delete_document_for_user(user: User, doc_id: int) -> bool:
    doc = AcademicDocument.objects.filter(user=user, id=doc_id).first()
    if not doc:
        return False
    # Strict delete: jika vector masih tersisa, batalkan delete dokumen.
    ok, remaining = delete_vectors_for_doc_strict(
        user_id=str(user.id),
        doc_id=str(doc.id),
        source=getattr(doc, "title", None),
    )
    if not ok:
        raise RuntimeError(
            f"Gagal menghapus vector dokumen secara tuntas (doc_id={doc.id}, remaining={remaining})"
        )
    # Hapus file dari storage
    try:
        if doc.file:
            doc.file.delete(save=False)
    except Exception:
        pass
    doc.delete()
    return True


def planner_start(user: User, session: ChatSession) -> tuple[Dict[str, Any], Dict[str, Any]]:
    data_level = planner_engine.detect_data_level(user)
    profile_hints = extract_profile_hints(user)
    state = planner_engine.build_initial_state(data_level=data_level)
    state["profile_hints"] = profile_hints
    state["planner_warning"] = profile_hints.get("warning")
    payload = planner_engine.get_step_payload(state)
    payload["planner_meta"] = {
        **(payload.get("planner_meta") or {}),
        "data_level": data_level,
        "mode": "planner",
        "origin": "start_auto",
        "event_type": PlannerHistory.EVENT_START_AUTO,
    }
    record_planner_history(
        user=user,
        session=session,
        event_type=PlannerHistory.EVENT_START_AUTO,
        planner_step=str((payload.get("planner_meta") or {}).get("step") or state.get("current_step") or "data"),
        text=str(payload.get("answer") or "Planner dimulai."),
        payload={
            "planner_warning": state.get("planner_warning"),
            "profile_hints": state.get("profile_hints", {}),
            "data_level": state.get("data_level", {}),
        },
    )
    return payload, state


def _build_planner_markdown(
    collected: Dict[str, Any],
    scenario: str | None = None,
    grade_rescue_md: str | None = None,
) -> str:
    jurusan = collected.get("jurusan") or "-"
    semester = collected.get("semester") or "-"
    goal = collected.get("goal") or "-"
    career = collected.get("career") or "-"
    time_pref = collected.get("time_pref") or "fleksibel"
    free_day = collected.get("free_day") or "tidak ada"

    scenario_text = ""
    if scenario == "dense":
        scenario_text = "Mode skenario: **Padat / Lulus Cepat**"
    elif scenario == "relaxed":
        scenario_text = "Mode skenario: **Santai / Beban Ringan**"

    return (
        "## 📅 Jadwal\n"
        "| Hari | Mata Kuliah | Jam | SKS |\n"
        "|---|---|---|---|\n"
        "| Senin | Mata Kuliah Inti | 08:00-10:00 | 3 |\n"
        "| Selasa | Mata Kuliah Wajib | 10:00-12:00 | 3 |\n"
        "| Rabu | Mata Kuliah Pilihan | 13:00-15:00 | 3 |\n\n"
        "## 🎯 Rekomendasi Mata Kuliah\n"
        f"- Prioritaskan mata kuliah inti untuk jurusan **{jurusan}** semester **{semester}**.\n"
        f"- Tujuan saat ini: **{goal}**.\n\n"
        "## 💼 Keselarasan Karir\n"
        f"- Target karir: **{career}**.\n"
        "- Fokuskan proyek/mata kuliah yang mendekatkan ke role tersebut.\n\n"
        "## ⚖️ Distribusi Beban\n"
        f"- Preferensi waktu: **{time_pref}**.\n"
        f"- Hari kosong: **{free_day}**.\n"
        f"- Skenario: {scenario_text or 'Mode normal'}.\n\n"
        "## ⚠️ Grade Rescue\n"
        f"{grade_rescue_md or '- Tidak ada input grade rescue khusus.'}\n\n"
        "## Selanjutnya\n"
        "1. 🔄 Buat opsi Padat\n"
        "2. 🔄 Buat opsi Santai\n"
        "3. ✏️ Ubah sesuatu\n"
        "4. ✅ Simpan rencana ini\n"
    ).strip()


def _ensure_planner_required_sections(answer: str, grade_rescue_md: str) -> str:
    text = (answer or "").strip()
    if not text:
        text = "## 📅 Jadwal\n- Belum ada output."

    checks = {
        "jadwal": "## 📅 Jadwal\n- Jadwal belum tersedia.",
        "rekomendasi mata kuliah": "## 🎯 Rekomendasi Mata Kuliah\n- Rekomendasi belum tersedia.",
        "keselarasan karir": "## 💼 Keselarasan Karir\n- Keselarasan karir belum tersedia.",
        "distribusi beban": "## ⚖️ Distribusi Beban\n- Distribusi beban belum tersedia.",
        "grade rescue": f"## ⚠️ Grade Rescue\n{grade_rescue_md}",
        "selanjutnya": (
            "## Selanjutnya\n"
            "1. 🔄 Buat opsi Padat\n"
            "2. 🔄 Buat opsi Santai\n"
            "3. ✏️ Ubah sesuatu\n"
            "4. ✅ Simpan rencana ini"
        ),
    }

    low = text.lower()
    for key, block in checks.items():
        if key not in low:
            text = f"{text}\n\n{block}"
            low = text.lower()
    return text


def planner_generate(user: User, state: Dict[str, Any], request_id: str = "-") -> Dict[str, Any]:
    collected = dict(state.get("collected_data") or {})
    scenario = str(collected.get("iterate_action") or "").strip().lower()
    grade_calc_input = collected.get("grade_calc_input")
    grade_calc_result = collected.get("grade_calc_result")
    grade_rescue_md = _build_grade_rescue_markdown(grade_calc_input, grade_calc_result)

    answer = _generate_planner_with_llm(
        user=user,
        collected=collected,
        grade_rescue_data=grade_rescue_md,
        request_id=request_id,
    )
    if not answer:
        # fallback deterministic agar planner tetap jalan tanpa LLM.
        _ = analyze_transcript_risks([])
        answer = _build_planner_markdown(collected, scenario=scenario, grade_rescue_md=grade_rescue_md)
    answer = _ensure_planner_required_sections(answer, grade_rescue_md=grade_rescue_md)
    answer = _append_verified_grade_rescue(answer, grade_calc_input, grade_calc_result)

    return {
        "type": "planner_output",
        "answer": answer,
        "options": [
            {"id": 1, "label": "🔄 Buat opsi Padat", "value": "dense"},
            {"id": 2, "label": "🔄 Buat opsi Santai", "value": "relaxed"},
            {"id": 3, "label": "✏️ Ubah sesuatu", "value": "edit"},
            {"id": 4, "label": "✅ Simpan rencana ini", "value": "save"},
        ],
        "allow_custom": False,
        "planner_meta": {"step": "iterate", "mode": "planner", "request_id": request_id},
    }


def planner_continue(
    user: User,
    session: ChatSession,
    planner_state: Dict[str, Any],
    message: str = "",
    option_id: int | None = None,
    request_id: str = "-",
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    working_state = dict(planner_state or {})
    # Refresh data level setiap request agar planner membaca upload terbaru user.
    fresh_data_level = planner_engine.detect_data_level(user)
    fresh_profile_hints = extract_profile_hints(user)
    working_state["data_level"] = fresh_data_level
    working_state["profile_hints"] = fresh_profile_hints
    working_state["planner_warning"] = fresh_profile_hints.get("warning")
    collected_data = dict(working_state.get("collected_data") or {})
    collected_data["has_transcript"] = bool(fresh_data_level.get("has_transcript"))
    collected_data["has_schedule"] = bool(fresh_data_level.get("has_schedule"))
    collected_data["has_curriculum"] = bool(fresh_data_level.get("has_curriculum"))
    working_state["collected_data"] = collected_data

    if message and is_grade_rescue_query(message):
        parsed = extract_grade_calc_input(message)
        if parsed:
            calc = calculate_required_score(
                achieved_components=parsed.get("achieved_components") or [],
                target_final_score=float(parsed.get("target_final_score", 70) or 70),
                remaining_weight=float(parsed.get("remaining_weight", 0) or 0),
            )
            collected_data["grade_calc_input"] = parsed
            collected_data["grade_calc_result"] = calc
            working_state["collected_data"] = collected_data

    prev_step = str(working_state.get("current_step") or "")
    prev_collected = dict(working_state.get("collected_data") or {})
    state = planner_engine.process_answer(working_state, message=message, option_id=option_id)
    origin = "option_select" if option_id is not None else "user_input"
    event_type = PlannerHistory.EVENT_OPTION_SELECT if option_id is not None else PlannerHistory.EVENT_USER_INPUT
    if option_id is not None and str(state.get("collected_data", {}).get("iterate_action") or "") == "save":
        event_type = PlannerHistory.EVENT_SAVE

    if state.get("current_step") == "generate":
        payload = planner_generate(user=user, state=state, request_id=request_id)
        state["current_step"] = "iterate"
        event_type = PlannerHistory.EVENT_GENERATE
        payload["planner_meta"] = {
            **(payload.get("planner_meta") or {}),
            "data_level": state.get("data_level", {}),
            "origin": origin,
            "event_type": event_type,
        }
    else:
        payload = planner_engine.get_step_payload(state)
        payload["planner_meta"] = {
            **(payload.get("planner_meta") or {}),
            "data_level": state.get("data_level", {}),
            "mode": "planner",
            "origin": origin,
            "event_type": event_type,
        }

    should_log = True
    if event_type == PlannerHistory.EVENT_USER_INPUT:
        # Milestone-only: log user input hanya jika benar-benar bermakna.
        has_validation_error = bool(str(state.get("validation_error") or "").strip())
        message_clean = (message or "").strip()
        progressed = prev_step != str(state.get("current_step") or "")
        changed_collected = dict(state.get("collected_data") or {}) != prev_collected
        should_log = bool(message_clean and not has_validation_error and (progressed or changed_collected))

    if should_log:
        step_name = str((payload.get("planner_meta") or {}).get("step") or state.get("current_step") or prev_step)
        option_label = _planner_option_label_from_payload(payload, option_id)
        event_text = str(payload.get("answer") or "")
        if event_type in {PlannerHistory.EVENT_OPTION_SELECT, PlannerHistory.EVENT_SAVE} and option_id is not None:
            event_text = f"Pilih opsi {option_id}: {option_label or '-'}"
        elif event_type == PlannerHistory.EVENT_USER_INPUT:
            event_text = f"Input user: {(message or '').strip()}"

        record_planner_history(
            user=user,
            session=session,
            event_type=event_type,
            planner_step=step_name,
            text=event_text,
            option_id=option_id,
            option_label=option_label,
            payload={
                "planner_warning": state.get("planner_warning"),
                "profile_hints": state.get("profile_hints", {}),
                "data_level": state.get("data_level", {}),
                "origin": origin,
            },
        )
    return payload, state


def _planner_v3_expiry_hours() -> int:
    try:
        return max(1, int(os.environ.get("PLANNER_V3_EXPIRE_HOURS", "24")))
    except Exception:
        return 24


def _planner_v3_progress_hints() -> List[str]:
    return [
        "Memvalidasi dokumen",
        "Mengekstrak teks",
        "Mengenali tipe dokumen",
        "Menyusun sesi planner",
    ]


def _serialize_embedded_docs_for_user(user: User, only_ids: List[int] | None = None) -> List[Dict[str, Any]]:
    qs = AcademicDocument.objects.filter(user=user, is_embedded=True).order_by("-uploaded_at")
    if only_ids:
        qs = qs.filter(id__in=only_ids)
    rows: List[Dict[str, Any]] = []
    for d in qs[:20]:
        rows.append(
            {
                "id": d.id,
                "title": d.title,
                "uploaded_at": d.uploaded_at.isoformat(),
            }
        )
    return rows


def _build_planner_v3_user_summary(answers: Dict[str, Any], docs: List[Dict[str, Any]]) -> str:
    focus = str(answers.get("focus") or answers.get("goal") or "analisis akademik").strip()
    docs_text = ", ".join([str(d.get("title") or "-") for d in docs[:3]]) or "dokumen akademik"
    return f"Tolong analisis {docs_text} dengan fokus {focus}."


def _safe_json_obj(text: str) -> Dict[str, Any]:
    txt = (text or "").strip()
    if not txt:
        return {}
    try:
        obj = json.loads(txt)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    m = re.search(r"\{.*\}", txt, flags=re.DOTALL)
    if not m:
        return {}
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _collect_planner_context_snippets(user: User, docs_summary: List[Dict[str, Any]], k: int = 5) -> List[Dict[str, str]]:
    snippets: List[Dict[str, str]] = []
    try:
        vectorstore = get_vectorstore()
    except Exception:
        return snippets

    doc_titles = [str(d.get("title") or "").strip() for d in docs_summary if d.get("title")]
    query = " ".join(doc_titles[:3]) or "khs krs jadwal transkrip"
    try:
        docs = vectorstore.similarity_search(query, k=max(1, k), filter={"user_id": str(user.id)})
    except Exception:
        return snippets

    for d in docs[:k]:
        source = str((getattr(d, "metadata", {}) or {}).get("source") or "unknown")
        text = str(getattr(d, "page_content", "") or "").strip()
        if not text:
            continue
        snippets.append({"source": source, "snippet": text[:420]})
    return snippets


def _sanitize_intent_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for i, c in enumerate(candidates[:4], start=1):
        if not isinstance(c, dict):
            continue
        label = str(c.get("label") or "").strip()[:140]
        value = str(c.get("value") or "").strip()[:120]
        reason = str(c.get("reason") or "").strip()[:220]
        if not label:
            continue
        if not value:
            value = f"intent_{i}"
        low = value.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append({"id": i, "label": label, "value": value, "reason": reason})
    return out


def _build_default_intent_candidates(
    docs_summary: List[Dict[str, Any]],
    profile_hints: Dict[str, Any],
) -> List[Dict[str, Any]]:
    question_candidates = profile_hints.get("question_candidates") or []
    dynamic: List[Dict[str, Any]] = []
    for q in question_candidates:
        if not isinstance(q, dict):
            continue
        step = str(q.get("step") or "").strip().lower()
        text = str(q.get("question") or "").strip()
        if not step or not text:
            continue
        label = text if len(text) <= 80 else text[:80].rstrip() + "..."
        dynamic.append(
            {
                "label": label,
                "value": f"focus_{step}",
                "reason": "Ditetapkan dari profil dan konteks dokumen.",
            }
        )
    if dynamic:
        return _sanitize_intent_candidates(dynamic)
    docs_text = ", ".join([str(d.get("title") or "") for d in docs_summary[:3]])
    return [
        {
            "id": 1,
            "label": "Evaluasi IPK dan tren nilai per semester",
            "value": "ipk_trend",
            "reason": f"Dokumen terdeteksi: {docs_text}",
        },
        {
            "id": 2,
            "label": "Rekomendasi SKS dan prioritas mata kuliah berikutnya",
            "value": "sks_plan",
            "reason": "Cocok untuk perencanaan semester berikut.",
        },
        {
            "id": 3,
            "label": "Strategi perbaikan nilai pada mata kuliah berisiko",
            "value": "grade_recovery",
            "reason": "Fokus untuk peningkatan performa akademik.",
        },
    ]


def _generate_intent_candidates_llm(
    *,
    user: User,
    docs_summary: List[Dict[str, Any]],
    profile_hints: Dict[str, Any],
) -> List[Dict[str, Any]]:
    runtime_cfg = get_runtime_openrouter_config()
    if not str(runtime_cfg.get("api_key") or "").strip():
        return []
    cfg = {
        **runtime_cfg,
        "timeout": max(4, int(os.environ.get("PLANNER_BLUEPRINT_TIMEOUT_SEC", "12"))),
        "max_retries": 0,
    }
    snippets = _collect_planner_context_snippets(user=user, docs_summary=docs_summary, k=4)
    docs_text = "\n".join([f"- {d.get('title')}" for d in docs_summary[:6]])
    snippets_text = "\n".join([f"- [{s.get('source')}] {s.get('snippet')}" for s in snippets[:4]])
    prompt = (
        "Kamu adalah AI Academic Planner Indonesia. "
        "Buat 3-4 intent pertanyaan awal paling relevan berdasarkan dokumen user.\n"
        "Output HARUS JSON valid berupa array object: "
        "[{\"label\":str,\"value\":str,\"reason\":str}]\n"
        "Aturan: fokus akademik, singkat, tidak duplikat, tidak hardcode generik.\n\n"
        f"Profile hints: confidence={profile_hints.get('confidence_summary')} "
        f"major={(profile_hints.get('major_candidates') or [])[:2]}\n"
        f"Dokumen:\n{docs_text}\n"
        f"Top snippets:\n{snippets_text}\n"
    )
    backup_models = get_backup_models(str(cfg.get("model") or ""), cfg.get("backup_models"))
    max_models = max(1, int(os.environ.get("PLANNER_BLUEPRINT_MAX_MODELS", "1")))
    for model_name in backup_models[:max_models]:
        try:
            llm = build_llm(model_name, cfg)
            raw = invoke_text(llm, prompt).strip()
            parsed = json.loads(raw) if raw else []
            if not isinstance(parsed, list):
                continue
            cleaned = _sanitize_intent_candidates([x for x in parsed if isinstance(x, dict)])
            if cleaned:
                return cleaned
        except Exception:
            continue
    return []


def _build_intent_step(intent_candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    options = [
        {"id": int(x.get("id") or i + 1), "label": str(x.get("label") or f"Opsi {i + 1}"), "value": str(x.get("value") or f"intent_{i+1}")}
        for i, x in enumerate(intent_candidates[:4])
    ]
    return {
        "step_key": "intent",
        "title": "Pilih Fokus Pertanyaan",
        "question": "Berikut kemungkinan pertanyaan berdasarkan dokumenmu. Pilih salah satu atau tulis manual.",
        "options": options,
        "allow_manual": True,
        "required": True,
        "source_hint": "mixed",
        "reason": "Intent dibentuk dari deteksi dokumen dan profil.",
    }


def _sanitize_dynamic_step(step: Dict[str, Any], fallback_step_key: str) -> Dict[str, Any]:
    if not isinstance(step, dict):
        return {}
    options = step.get("options") if isinstance(step.get("options"), list) else []
    clean_opts = []
    for i, o in enumerate(options[:4], start=1):
        if not isinstance(o, dict):
            continue
        label = str(o.get("label") or "").strip()[:120]
        value = str(o.get("value") or "").strip()[:100]
        if not label:
            continue
        if not value:
            value = f"opt_{i}"
        clean_opts.append({"id": int(o.get("id") or i), "label": label, "value": value})
    allow_manual = bool(step.get("allow_manual", True))
    if not allow_manual and len(clean_opts) < 2:
        return {}
    step_key = str(step.get("step_key") or "").strip()[:40] or fallback_step_key
    return {
        "step_key": step_key,
        "title": str(step.get("title") or "Pertanyaan Lanjutan")[:120],
        "question": str(step.get("question") or "Lanjutkan analisis planner.")[:320],
        "options": clean_opts,
        "allow_manual": allow_manual,
        "required": bool(step.get("required", True)),
        "source_hint": str(step.get("source_hint") or "mixed")[:20],
        "reason": str(step.get("reason") or "Pertanyaan ini membantu mempertajam analisis.")[:240],
    }


def _planner_path_summary(path_taken: List[Dict[str, Any]]) -> str:
    if not path_taken:
        return "Belum ada jawaban."
    tails = path_taken[-3:]
    parts = [f"{x.get('step_key')}: {x.get('answer_value')}" for x in tails]
    return " -> ".join(parts)


def _generate_next_step_llm(
    *,
    user: User,
    run: PlannerRun,
    latest_step_key: str,
    latest_answer: str,
) -> Dict[str, Any]:
    runtime_cfg = get_runtime_openrouter_config()
    if not str(runtime_cfg.get("api_key") or "").strip():
        return {}
    cfg = {
        **runtime_cfg,
        "timeout": max(4, int(os.environ.get("PLANNER_NEXT_TIMEOUT_SEC", "8"))),
        "max_retries": max(0, int(os.environ.get("PLANNER_NEXT_MAX_RETRIES", "1"))),
    }
    docs_summary = run.documents_snapshot if isinstance(run.documents_snapshot, list) else []
    snippets = _collect_planner_context_snippets(user=user, docs_summary=docs_summary, k=4)
    snippets_text = "\n".join([f"- [{s.get('source')}] {s.get('snippet')}" for s in snippets[:4]])
    answers = run.answers_snapshot if isinstance(run.answers_snapshot, dict) else {}
    path = run.path_taken if isinstance(run.path_taken, list) else []
    prompt = (
        "Kamu adalah AI Academic Planner Indonesia. "
        "Berdasarkan path jawaban user, buat SATU pertanyaan lanjutan paling informatif.\n"
        "Jika informasi sudah cukup, set ready_to_generate=true.\n"
        "Output HARUS JSON object valid: "
        "{\"ready_to_generate\":bool,\"step\":{step_key,title,question,options,allow_manual,required,source_hint,reason}}\n"
        "step boleh null jika ready_to_generate=true.\n"
        "Hindari mengulang pertanyaan sebelumnya.\n\n"
        f"Depth saat ini: {run.current_depth}/{run.max_depth}\n"
        f"Jawaban terkini: {latest_step_key}={latest_answer}\n"
        f"Semua jawaban: {answers}\n"
        f"Path: {path}\n"
        f"Top snippets:\n{snippets_text}\n"
    )
    backup_models = get_backup_models(str(cfg.get("model") or ""), cfg.get("backup_models"))
    max_models = max(1, int(os.environ.get("PLANNER_BLUEPRINT_MAX_MODELS", "1")))
    for model_name in backup_models[:max_models]:
        try:
            llm = build_llm(model_name, cfg)
            raw = invoke_text(llm, prompt).strip()
            obj = _safe_json_obj(raw)
            if not obj:
                continue
            ready = bool(obj.get("ready_to_generate"))
            step = obj.get("step")
            clean_step = _sanitize_dynamic_step(step, fallback_step_key=f"followup_{run.current_depth + 1}") if isinstance(step, dict) else {}
            if ready and not clean_step:
                return {"ready_to_generate": True}
            if clean_step:
                return {"ready_to_generate": ready, "step": clean_step}
        except Exception:
            continue
    return {}


def _fallback_next_step(run: PlannerRun) -> Dict[str, Any]:
    depth = int(run.current_depth or 0)
    if depth >= int(run.max_depth or 4):
        return {"ready_to_generate": True}
    key = f"followup_{depth + 1}"
    return {
        "ready_to_generate": False,
        "step": {
            "step_key": key,
            "title": "Pendalaman Analisis",
            "question": "Agar hasil lebih tajam, aspek mana yang ingin diperdalam lagi?",
            "options": [
                {"id": 1, "label": "Prioritas mata kuliah", "value": "priority_subject"},
                {"id": 2, "label": "Manajemen beban SKS", "value": "credit_load"},
                {"id": 3, "label": "Strategi belajar", "value": "study_strategy"},
            ],
            "allow_manual": True,
            "required": True,
            "source_hint": "mixed",
            "reason": "Langkah fallback untuk mempertajam keputusan sebelum generate.",
        },
    }


def assess_documents_relevance(user: User, docs_summary: List[Dict[str, Any]]) -> Dict[str, Any]:
    titles = [str(d.get("title") or "").lower() for d in docs_summary]
    reasons: List[str] = []
    strong_keywords = {
        "khs", "krs", "jadwal", "transkrip", "kurikulum", "mata kuliah", "nilai", "ipk", "ips", "sks", "semester",
    }
    weak_keywords = {
        "dosen", "kelas", "ruang", "kuliah", "akademik", "prodi", "jurusan",
    }

    strong_hits = 0
    weak_hits = 0
    for t in titles:
        title_strong = [kw for kw in strong_keywords if kw in t]
        title_weak = [kw for kw in weak_keywords if kw in t]
        if title_strong:
            strong_hits += len(title_strong)
            reasons.append(f"Judul dokumen mengandung sinyal akademik kuat: {', '.join(title_strong[:3])}")
        if title_weak:
            weak_hits += len(title_weak)

    snippets = _collect_planner_context_snippets(user=user, docs_summary=docs_summary, k=4)
    snippet_strong_hits = 0
    snippet_weak_hits = 0
    for s in snippets:
        low = (s.get("snippet") or "").lower()
        if not low:
            continue
        snippet_strong_hits += len([kw for kw in strong_keywords if kw in low])
        snippet_weak_hits += len([kw for kw in weak_keywords if kw in low])
    if snippet_strong_hits or snippet_weak_hits:
        reasons.append("Cuplikan dokumen mendukung konteks akademik.")

    if strong_hits >= 1:
        score = max(
            0.75,
            min(
                1.0,
                (strong_hits * 0.35) + (weak_hits * 0.08) + (snippet_strong_hits * 0.06) + (snippet_weak_hits * 0.02),
            ),
        )
    else:
        score = min(
            1.0,
            (strong_hits * 0.35) + (weak_hits * 0.08) + (snippet_strong_hits * 0.06) + (snippet_weak_hits * 0.02),
        )
    is_relevant = score >= 0.55
    blocked_reason = "" if is_relevant else (
        "Dokumen belum terdeteksi relevan untuk perencanaan akademik. "
        "Upload dokumen seperti KHS, KRS, Jadwal, Transkrip, atau Kurikulum."
    )
    return {
        "is_relevant": is_relevant,
        "relevance_score": round(score, 3),
        "relevance_reasons": reasons[:3],
        "blocked_reason": blocked_reason,
    }


def _sanitize_blueprint_payload(blueprint: Dict[str, Any], profile_hints: Dict[str, Any], mode: str) -> Dict[str, Any]:
    steps = blueprint.get("steps") if isinstance(blueprint, dict) else None
    if not isinstance(steps, list):
        steps = []
    out_steps: List[Dict[str, Any]] = []
    seen = set()
    for s in steps[:3]:
        if not isinstance(s, dict):
            continue
        step_key = str(s.get("step_key") or "").strip()[:40]
        if (not step_key) or (step_key in seen):
            continue
        seen.add(step_key)
        options = s.get("options") if isinstance(s.get("options"), list) else []
        norm_opts = []
        for idx, o in enumerate(options[:6], start=1):
            if not isinstance(o, dict):
                continue
            norm_opts.append({
                "id": int(o.get("id") or idx),
                "label": str(o.get("label") or f"Opsi {idx}")[:120],
                "value": str(o.get("value") or f"opt_{idx}")[:80],
            })
        allow_manual = bool(s.get("allow_manual", True))
        if not allow_manual and len(norm_opts) < 2:
            continue
        out_steps.append(
            {
                "step_key": step_key,
                "title": str(s.get("title") or step_key.title())[:120],
                "question": str(s.get("question") or "Lanjutkan planner")[:320],
                "options": norm_opts,
                "allow_manual": allow_manual,
                "required": bool(s.get("required", True)),
                "source_hint": str(s.get("source_hint") or "mixed")[:20],
            }
        )

    if not out_steps:
        return {}

    meta = blueprint.get("meta") if isinstance(blueprint.get("meta"), dict) else {}
    major_candidates = profile_hints.get("major_candidates") or []
    top_major = major_candidates[0] if major_candidates else {}
    has_major_step = any(
        ("jurusan" in str(s.get("step_key") or "").lower()) or ("major" in str(s.get("step_key") or "").lower())
        for s in out_steps
    )
    requires_major_confirmation = bool(
        meta.get("requires_major_confirmation", profile_hints.get("confidence_summary") != "high")
    )
    # Jangan memaksa konfirmasi jurusan jika blueprint tidak menyediakan step untuk itu.
    if requires_major_confirmation and not has_major_step:
        requires_major_confirmation = False

    return {
        "version": "v3_dynamic",
        "steps": out_steps,
        "meta": {
            "doc_type_detected": str(meta.get("doc_type_detected") or "academic_document")[:80],
            "major_inferred": str(meta.get("major_inferred") or top_major.get("label") or "")[:120] or None,
            "major_confidence": float(meta.get("major_confidence") or top_major.get("confidence") or 0.0),
            "generation_mode": mode,
            "requires_major_confirmation": requires_major_confirmation,
        },
    }


def _generate_planner_blueprint_llm(
    *,
    user: User,
    docs_summary: List[Dict[str, Any]],
    data_level: Dict[str, Any],
    profile_hints: Dict[str, Any],
) -> Dict[str, Any]:
    runtime_cfg = get_runtime_openrouter_config()
    api_key = str(runtime_cfg.get("api_key") or "").strip()
    if not api_key:
        return {}
    # Planner start harus responsif; pakai timeout khusus agar tidak menahan UI terlalu lama.
    planner_timeout = max(4, int(os.environ.get("PLANNER_BLUEPRINT_TIMEOUT_SEC", "12")))
    runtime_cfg = {
        **runtime_cfg,
        "timeout": planner_timeout,
        "max_retries": 0,
    }

    snippets = _collect_planner_context_snippets(user=user, docs_summary=docs_summary, k=5)
    snippets_text = "\n".join([f"- [{x.get('source')}] {x.get('snippet')}" for x in snippets[:5]])
    docs_text = "\n".join([f"- {d.get('title')}" for d in docs_summary[:8]])

    prompt = (
        "Kamu adalah AI Academic Planner Indonesia. "
        "Tugasmu membuat JSON blueprint wizard planner berdasarkan dokumen user. "
        "Hasil HARUS JSON valid saja, tanpa teks lain.\n\n"
        "Aturan ketat:\n"
        "1) Langkah 1-3 saja.\n"
        "2) Setiap langkah wajib: step_key,title,question,options,allow_manual,required,source_hint.\n"
        "3) Jika confidence jurusan tidak tinggi, wajib ada langkah konfirmasi jurusan.\n"
        "4) Jangan tanya data yang sudah jelas ada di dokumen.\n"
        "5) options minimal 2 jika allow_manual=false.\n"
        "6) source_hint hanya: document|profile|mixed.\n\n"
        "Schema output:\n"
        "{\"version\":\"v3_dynamic\",\"steps\":[...],\"meta\":{\"doc_type_detected\":str,\"major_inferred\":str|null,\"major_confidence\":float,\"generation_mode\":\"llm\",\"requires_major_confirmation\":bool}}\n\n"
        f"Data level: {data_level}\n"
        f"Profile hints summary: confidence={profile_hints.get('confidence_summary')} major_candidates={(profile_hints.get('major_candidates') or [])[:3]}\n"
        f"Dokumen user:\n{docs_text}\n"
        f"Top snippets:\n{snippets_text}\n"
    )

    backup_models = get_backup_models(str(runtime_cfg.get("model") or ""), runtime_cfg.get("backup_models"))
    # Batasi jumlah model untuk fase start agar latency tetap rendah.
    max_models = max(1, int(os.environ.get("PLANNER_BLUEPRINT_MAX_MODELS", "1")))
    for model_name in backup_models[:max_models]:
        try:
            llm = build_llm(model_name, runtime_cfg)
            raw = invoke_text(llm, prompt).strip()
            obj = _safe_json_obj(raw)
            if not obj:
                continue
            clean = _sanitize_blueprint_payload(obj, profile_hints=profile_hints, mode="llm")
            if clean.get("steps"):
                return clean
        except Exception:
            continue
    return {}


def planner_start_v3(
    *,
    user: User,
    files: List[UploadedFile] | None = None,
    reuse_doc_ids: List[int] | None = None,
    session_id: int | None = None,
) -> Dict[str, Any]:
    planner_session = get_or_create_chat_session(user=user, session_id=session_id)
    reuse_doc_ids = reuse_doc_ids or []
    had_upload = bool(files)

    if files:
        quota_bytes = get_user_quota_bytes(user=user, default_quota_bytes=10 * 1024 * 1024)
        upload_result = upload_files_batch(user=user, files=files, quota_bytes=quota_bytes)
        if upload_result.get("status") != "success":
            return {
                "status": "error",
                "error": upload_result.get("msg") or "Upload gagal.",
                "required_upload": True,
            }

    docs_summary = _serialize_embedded_docs_for_user(user=user, only_ids=reuse_doc_ids if reuse_doc_ids else None)
    if not docs_summary:
        return {
            "status": "error",
            "error": "Belum ada dokumen embedded yang valid. Upload atau pilih dokumen existing dulu.",
            "required_upload": True,
            "progress_hints": _planner_v3_progress_hints(),
            "recommended_docs": ["KHS", "KRS", "Jadwal", "Transkrip", "Kurikulum"],
        }

    relevance = assess_documents_relevance(user=user, docs_summary=docs_summary)
    if not relevance.get("is_relevant"):
        return {
            "status": "error",
            "error_code": "IRRELEVANT_DOCUMENTS",
            "error": relevance.get("blocked_reason") or "Dokumen tidak relevan.",
            "required_upload": True,
            "doc_relevance": {
                "is_relevant": False,
                "score": relevance.get("relevance_score", 0.0),
                "reasons": relevance.get("relevance_reasons") or [],
            },
            "recommended_docs": ["KHS", "KRS", "Jadwal", "Transkrip", "Kurikulum"],
            "progress_hints": _planner_v3_progress_hints(),
        }

    data_level = planner_engine.detect_data_level(user)
    profile_hints = extract_profile_hints(user)

    wizard_blueprint = _generate_planner_blueprint_llm(
        user=user,
        docs_summary=docs_summary,
        data_level=data_level,
        profile_hints=profile_hints,
    )

    generation_mode = "llm"
    if not wizard_blueprint:
        fallback = planner_engine.build_wizard_blueprint_v3(
            data_level=data_level,
            profile_hints=profile_hints,
            documents_summary=docs_summary,
        )
        wizard_blueprint = _sanitize_blueprint_payload(fallback, profile_hints=profile_hints, mode="fallback_rule")
        generation_mode = "fallback_rule"

    if not wizard_blueprint:
        return {
            "status": "error",
            "error": "Gagal menyusun blueprint planner. Coba upload dokumen yang lebih jelas.",
            "required_upload": True,
        }

    intent_candidates = _generate_intent_candidates_llm(
        user=user,
        docs_summary=docs_summary,
        profile_hints=profile_hints,
    )
    if not intent_candidates:
        intent_candidates = _build_default_intent_candidates(
            docs_summary=docs_summary,
            profile_hints=profile_hints,
        )

    intent_step = _build_intent_step(intent_candidates)
    start_blueprint = {
        "version": "v3_dynamic",
        "steps": [intent_step],
        "meta": {
            **(wizard_blueprint.get("meta") or {}),
            "generation_mode": "adaptive_start",
        },
    }

    run = PlannerRun.objects.create(
        user=user,
        session=planner_session,
        status=PlannerRun.STATUS_READY,
        wizard_blueprint=start_blueprint,
        documents_snapshot=docs_summary,
        intent_candidates_snapshot=intent_candidates,
        decision_tree_state={"expected_step_key": "intent", "next_seq": 1, "can_generate_now": False},
        path_taken=[],
        current_depth=0,
        max_depth=4,
        grounding_policy="doc_first_fallback",
        profile_hints_snapshot=profile_hints,
        doc_relevance_snapshot={
            "is_relevant": True,
            "score": relevance.get("relevance_score", 0.0),
            "reasons": relevance.get("relevance_reasons") or [],
        },
        expires_at=timezone.now() + timedelta(hours=_planner_v3_expiry_hours()),
    )
    return {
        "status": "success",
        "planner_run_id": str(run.id),
        "session_id": planner_session.id,
        "wizard_blueprint": start_blueprint,
        "documents_summary": docs_summary,
        "required_upload": False,
        "progress_hints": _planner_v3_progress_hints(),
        "doc_relevance": {
            "is_relevant": True,
            "score": relevance.get("relevance_score", 0.0),
            "reasons": relevance.get("relevance_reasons") or [],
        },
        "profile_hints_summary": {
            "major_candidates": (profile_hints.get("major_candidates") or [])[:3],
            "confidence_summary": profile_hints.get("confidence_summary"),
        },
        "intent_candidates": intent_candidates,
        "manual_intent_enabled": True,
        "next_action": "choose_intent",
        "planner_meta": {
            "event_type": "start_v3",
            "had_upload": had_upload,
            "reuse_count": len(reuse_doc_ids),
            "generation_mode": generation_mode,
        },
    }


def planner_next_step_v3(
    *,
    user: User,
    planner_run_id: str,
    step_key: str,
    answer_value: str,
    answer_mode: str,
    client_step_seq: int,
) -> Dict[str, Any]:
    run = get_planner_run_for_user(user=user, run_id=planner_run_id)
    if not run:
        return {"status": "error", "error": "planner_run_id tidak ditemukan."}
    if run.status in {PlannerRun.STATUS_CANCELLED, PlannerRun.STATUS_EXPIRED, PlannerRun.STATUS_COMPLETED}:
        return {"status": "error", "error": f"Planner run sudah {run.status}."}
    if timezone.now() > run.expires_at:
        run.status = PlannerRun.STATUS_EXPIRED
        run.save(update_fields=["status", "updated_at"])
        return {"status": "error", "error": "Planner run sudah kedaluwarsa."}

    tree = run.decision_tree_state if isinstance(run.decision_tree_state, dict) else {}
    expected_step = str(tree.get("expected_step_key") or "intent")
    next_seq = int(tree.get("next_seq") or 1)
    if int(client_step_seq or 0) != next_seq:
        return {
            "status": "error",
            "error": "Urutan langkah tidak valid (client_step_seq).",
            "error_code": "INVALID_STEP_SEQUENCE",
            "expected_step_key": expected_step,
            "expected_seq": next_seq,
        }
    submitted_step = str(step_key or "").strip()
    if submitted_step != expected_step:
        # Self-heal: pada beberapa kondisi UI bisa stale dan mengirim step sebelumnya.
        # Selama urutan seq benar dan expected_step tersedia, lanjutkan dengan expected_step
        # agar flow planner tidak macet di 400 berulang.
        if submitted_step and expected_step and submitted_step in set((run.answers_snapshot or {}).keys()):
            logger.warning(
                "planner_next_step_v3 step mismatch recovered run=%s submitted=%s expected=%s seq=%s",
                run.id,
                submitted_step,
                expected_step,
                next_seq,
            )
            submitted_step = expected_step
        else:
            return {
                "status": "error",
                "error": "step_key tidak sesuai urutan planner.",
                "error_code": "STEP_KEY_MISMATCH",
                "expected_step_key": expected_step,
                "expected_seq": next_seq,
            }

    normalized_mode = str(answer_mode or "").strip().lower()
    if normalized_mode not in {"option", "manual"}:
        return {"status": "error", "error": "answer_mode tidak valid."}
    answer_text = str(answer_value or "").strip()
    if not answer_text:
        return {"status": "error", "error": "answer_value wajib diisi."}

    answers = dict(run.answers_snapshot or {})
    answers[submitted_step] = answer_text
    path = list(run.path_taken or [])
    path.append(
        {
            "seq": next_seq,
            "step_key": submitted_step,
            "answer_value": answer_text,
            "answer_mode": normalized_mode,
        }
    )

    run.current_depth = int(run.current_depth or 0) + 1
    reached_max = run.current_depth >= int(run.max_depth or 4)
    next_payload: Dict[str, Any] = {"ready_to_generate": reached_max}
    if not reached_max:
        next_payload = _generate_next_step_llm(
            user=user,
            run=run,
            latest_step_key=submitted_step,
            latest_answer=answer_text,
        ) or {}
        if not next_payload:
            next_payload = _fallback_next_step(run)
    ready_to_generate = bool(next_payload.get("ready_to_generate"))
    next_step = next_payload.get("step") if isinstance(next_payload.get("step"), dict) else None

    run.answers_snapshot = answers
    run.path_taken = path
    run.status = PlannerRun.STATUS_COLLECTING
    tree["next_seq"] = next_seq + 1
    tree["can_generate_now"] = bool(ready_to_generate or reached_max)
    if next_step:
        tree["expected_step_key"] = str(next_step.get("step_key") or f"followup_{run.current_depth+1}")
    else:
        tree["expected_step_key"] = ""
    run.decision_tree_state = tree
    run.save(
        update_fields=[
            "answers_snapshot",
            "path_taken",
            "current_depth",
            "status",
            "decision_tree_state",
            "updated_at",
        ]
    )

    return {
        "status": "success",
        "step": next_step,
        "done_recommendation": "Data sudah cukup untuk generate." if not next_step else "",
        "progress": {"current": int(run.current_depth), "max": int(run.max_depth or 4)},
        "can_generate_now": bool(tree.get("can_generate_now")),
        "path_summary": _planner_path_summary(path),
        "path_taken": path,
    }
def get_planner_run_for_user(user: User, run_id: str) -> PlannerRun | None:
    try:
        return PlannerRun.objects.filter(user=user, id=run_id).first()
    except Exception:
        return None


def _validate_planner_answers(blueprint: Dict[str, Any], answers: Dict[str, Any]) -> str:
    steps = blueprint.get("steps") if isinstance(blueprint, dict) else None
    if not isinstance(steps, list) or not steps:
        return "Blueprint planner tidak valid."

    valid_step_keys = []
    seen = set()
    required_keys = set()
    for s in steps:
        if not isinstance(s, dict):
            continue
        key = str(s.get("step_key") or "").strip()
        if not key:
            return "Blueprint planner tidak memiliki step_key valid."
        if key in seen:
            return f"Blueprint planner duplikat step_key: {key}"
        seen.add(key)
        valid_step_keys.append(key)
        if bool(s.get("required", True)):
            required_keys.add(key)
        allow_manual = bool(s.get("allow_manual", True))
        options = s.get("options") if isinstance(s.get("options"), list) else []
        if (not allow_manual) and len(options) < 2:
            return f"Blueprint step '{key}' tidak valid: options kurang dari 2."

    unknown_keys = [k for k in answers.keys() if k not in set(valid_step_keys)]
    if unknown_keys:
        return f"Jawaban memuat step tidak dikenal: {', '.join(sorted(unknown_keys))}"

    missing_required = [k for k in sorted(required_keys) if str(answers.get(k) or "").strip() == ""]
    if missing_required:
        return f"Jawaban required belum lengkap: {', '.join(missing_required)}"

    for k, v in answers.items():
        if not isinstance(v, (str, int, float, bool, dict, list)):
            return f"Tipe jawaban untuk step '{k}' tidak valid."

    meta = blueprint.get("meta") if isinstance(blueprint.get("meta"), dict) else {}
    if bool(meta.get("requires_major_confirmation")):
        major_keys = [k for k in valid_step_keys if ("jurusan" in k.lower()) or ("major" in k.lower())]
        if not major_keys:
            return ""
        has_major_answer = any(str(answers.get(k) or "").strip() for k in major_keys)
        if not has_major_answer:
            return "Konfirmasi jurusan wajib diisi karena confidence jurusan belum tinggi."
    return ""
def planner_execute_v3(
    *,
    user: User,
    planner_run_id: str,
    answers: Dict[str, Any],
    path_taken: List[Dict[str, Any]] | None = None,
    session_id: int | None = None,
    client_summary: str = "",
    request_id: str = "-",
) -> Dict[str, Any]:
    run = get_planner_run_for_user(user=user, run_id=planner_run_id)
    if not run:
        return {"status": "error", "error": "planner_run_id tidak ditemukan."}
    if run.status in {PlannerRun.STATUS_CANCELLED, PlannerRun.STATUS_EXPIRED}:
        return {"status": "error", "error": f"Planner run sudah {run.status}."}
    if run.status not in {PlannerRun.STATUS_READY, PlannerRun.STATUS_STARTED, PlannerRun.STATUS_COLLECTING}:
        return {"status": "error", "error": "Planner run tidak dalam status siap eksekusi."}
    if timezone.now() > run.expires_at:
        run.status = PlannerRun.STATUS_EXPIRED
        run.save(update_fields=["status", "updated_at"])
        return {"status": "error", "error": "Planner run sudah kedaluwarsa."}

    if path_taken is not None:
        if not isinstance(path_taken, list):
            return {"status": "error", "error": "path_taken harus array."}
        server_path = list(run.path_taken or [])
        if path_taken != server_path:
            return {"status": "error", "error": "path_taken tidak konsisten dengan state server."}

    merged_answers = {**(run.answers_snapshot or {}), **(answers or {})}
    if not merged_answers:
        return {"status": "error", "error": "Belum ada jawaban planner untuk dieksekusi."}
    valid_keys = {str(x.get("step_key")) for x in (run.path_taken or []) if isinstance(x, dict) and x.get("step_key")}
    if valid_keys:
        unknown = [k for k in merged_answers.keys() if k not in valid_keys]
        if unknown:
            return {"status": "error", "error": f"Jawaban memuat step tidak dikenal: {', '.join(sorted(unknown))}"}
    # Backward compatibility untuk test/flow lama yang masih mengirim wizard blueprint.
    if not valid_keys:
        err = _validate_planner_answers(run.wizard_blueprint, merged_answers)
        if err:
            return {"status": "error", "error": err}

    run.status = PlannerRun.STATUS_EXECUTING
    run.answers_snapshot = merged_answers
    run.save(update_fields=["status", "answers_snapshot", "updated_at"])

    session = get_or_create_chat_session(user=user, session_id=session_id or run.session_id)
    summary = (client_summary or "").strip() or _build_planner_v3_user_summary(answers=merged_answers, docs=run.documents_snapshot)
    context_payload = {
        "planner_run_id": str(run.id),
        "documents": run.documents_snapshot,
        "answers": merged_answers,
        "path_taken": run.path_taken,
        "grounding_policy": run.grounding_policy,
    }
    planner_prompt = (
        "Buat analisis akademik berbasis dokumen user dan jawaban wizard berikut.\n"
        "Aturan grounding: utamakan fakta dari dokumen. Jika data dokumen tidak cukup, beri disclaimer jelas "
        "('Data dokumen rujukan belum cukup ...') lalu lanjutkan panduan umum akademik.\n"
        f"Data: {context_payload}\n\n"
        f"Permintaan user: {summary}"
    )
    rag_result = ask_bot(user.id, planner_prompt, request_id=request_id)
    answer = str((rag_result or {}).get("answer") or "Maaf, belum ada jawaban.")
    sources = list((rag_result or {}).get("sources") or [])

    ChatHistory.objects.create(user=user, session=session, question=summary, answer=answer)
    session.save(update_fields=["updated_at"])
    run.status = PlannerRun.STATUS_COMPLETED
    run.save(update_fields=["status", "updated_at"])

    fallback_used = (len(sources) == 0) or ("Data dokumen rujukan belum cukup" in answer)
    return {
        "status": "success",
        "answer": answer,
        "sources": sources,
        "session_id": session.id,
        "planner_meta": {
            "event_type": "generate",
            "planner_run_id": str(run.id),
            "grounding_mode": "doc_first_fallback",
            "fallback_used": bool(fallback_used),
            "path_depth": len(run.path_taken or []),
        },
    }


def planner_cancel_v3(*, user: User, planner_run_id: str) -> Dict[str, Any]:
    run = get_planner_run_for_user(user=user, run_id=planner_run_id)
    if not run:
        return {"status": "error", "error": "planner_run_id tidak ditemukan."}
    if run.status in {PlannerRun.STATUS_COMPLETED, PlannerRun.STATUS_CANCELLED}:
        return {"status": "success", "status_detail": run.status}
    run.status = PlannerRun.STATUS_CANCELLED
    run.save(update_fields=["status", "updated_at"])
    return {"status": "success", "status_detail": "cancelled"}



