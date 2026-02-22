from __future__ import annotations

from typing import Any, Dict, List

from django.contrib.auth.models import User

from core.models import ChatHistory, ChatSession, PlannerHistory


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


def serialize_history_for_session(user: User, session: ChatSession) -> List[Dict[str, Any]]:
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


def serialize_timeline_items(user: User, session: ChatSession, page: int = 1, page_size: int = 100) -> Dict[str, Any]:
    page = max(int(page), 1)
    page_size = max(int(page_size), 1)
    offset = (page - 1) * page_size

    chat_qs = ChatHistory.objects.filter(user=user, session=session).order_by("timestamp")
    planner_qs = PlannerHistory.objects.filter(user=user, session=session).order_by("created_at")
    mixed = []
    for item in chat_qs:
        ts = item.timestamp
        mixed.append(
            {
                "type": "chat",
                "timestamp": ts,
                "payload": {
                    "question": item.question,
                    "answer": item.answer,
                    "time": ts.strftime("%H:%M"),
                    "date": ts.strftime("%Y-%m-%d"),
                },
            }
        )
    for item in planner_qs:
        ts = getattr(item, "created_at", None) or getattr(item, "timestamp", None)
        mixed.append(
            {
                "type": "planner",
                "timestamp": ts,
                "payload": {
                    "payload_type": getattr(item, "event_type", ""),
                    "payload": item.payload,
                    "planner_step": getattr(item, "planner_step", ""),
                    "text": getattr(item, "text", ""),
                    "time": ts.strftime("%H:%M") if ts else "",
                    "date": ts.strftime("%Y-%m-%d") if ts else "",
                },
            }
        )
    mixed.sort(key=lambda x: x["timestamp"])
    total = len(mixed)
    items = mixed[offset:offset + page_size]
    timeline: List[Dict[str, Any]] = []
    for item in items:
        payload = item.get("payload") or {}
        if item.get("type") == "chat":
            timeline.append(
                {
                    "kind": "chat_user",
                    "text": payload.get("question", ""),
                    "time": payload.get("time", ""),
                    "date": payload.get("date", ""),
                }
            )
            timeline.append(
                {
                    "kind": "chat_assistant",
                    "text": payload.get("answer", ""),
                    "time": payload.get("time", ""),
                    "date": payload.get("date", ""),
                }
            )
        else:
            timeline.append(
                {
                    "kind": "planner_milestone",
                    "text": payload.get("text", ""),
                    "time": payload.get("time", ""),
                    "date": payload.get("date", ""),
                }
            )

    return {
        "items": items,
        "timeline": timeline,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "has_next": (offset + page_size) < total,
        },
    }
