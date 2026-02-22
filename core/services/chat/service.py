from __future__ import annotations

from typing import Any, Dict, List

from django.contrib.auth.models import User

from core.ai_engine.retrieval.main import ask_bot
from core.ai_engine.retrieval.rules import extract_grade_calc_input, is_grade_rescue_query
from core.models import ChatHistory, ChatSession
from core.academic.grade_calculator import calculate_required_score
from core.services.documents.service import build_storage_payload, serialize_documents_for_user

from .serializers import serialize_history_for_session, serialize_sessions_for_user, serialize_timeline_items


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
    ChatHistory.objects.filter(user=user, session__isnull=True).update(session=session)


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


def chat_and_save(
    user: User,
    message: str,
    request_id: str = "-",
    session_id: int | None = None,
    *,
    ask_bot_fn: Any | None = None,
) -> Dict[str, Any]:
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
        bot_fn = ask_bot_fn or ask_bot
        result = bot_fn(user.id, message, request_id=request_id)

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
    session.save(update_fields=["updated_at"])
    return {"answer": answer, "sources": sources, "meta": meta, "session_id": session.id}


def get_dashboard_props(user: User, quota_bytes: int) -> Dict[str, Any]:
    session = _get_or_create_default_session(user)
    _attach_legacy_history_to_session(user, session)
    history_data = serialize_history_for_session(user=user, session=session)
    documents, total_bytes = serialize_documents_for_user(user=user, limit=50)
    storage = build_storage_payload(total_bytes, quota_bytes)
    sessions = serialize_sessions_for_user(user=user, limit=50)
    return {
        "user": {"id": user.id, "username": user.username, "email": user.email},
        "activeSessionId": session.id,
        "sessions": sessions,
        "initialHistory": history_data,
        "documents": documents,
        "storage": storage,
    }


def list_sessions(user: User, limit: int = 50, page: int = 1) -> Dict[str, Any]:
    page = max(int(page), 1)
    limit = max(int(limit), 1)
    offset = (page - 1) * limit
    total = ChatSession.objects.filter(user=user).count()
    sessions = serialize_sessions_for_user(user=user, limit=limit, offset=offset)
    return {
        "sessions": sessions,
        "pagination": {"page": page, "page_size": limit, "total": total, "has_next": (offset + limit) < total},
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
    session.title = (title or "").strip() or "Chat Baru"
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
    return serialize_history_for_session(user=user, session=session)


def get_session_timeline(user: User, session_id: int, page: int = 1, page_size: int = 100) -> Dict[str, Any]:
    session = ChatSession.objects.filter(user=user, id=session_id).first()
    if not session:
        return {"items": [], "pagination": {"page": page, "page_size": page_size, "total": 0, "has_next": False}}
    return serialize_timeline_items(user=user, session=session, page=page, page_size=page_size)
