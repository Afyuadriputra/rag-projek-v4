# core/service.py
import time
from typing import Any, Dict, List, Tuple

from django.contrib.auth.models import User
from django.core.files.uploadedfile import UploadedFile

from .models import AcademicDocument, ChatHistory, ChatSession, UserQuota
from .ai_engine.ingest import process_document
from .ai_engine.retrieval import ask_bot
from .ai_engine.vector_ops import delete_vectors_for_doc, delete_vectors_for_doc_strict



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
        {"answer": "...", "sources": [...]}
      agar frontend bisa menampilkan "rujukan/source trace".
    """
    session: ChatSession | None = None
    if session_id:
        session = ChatSession.objects.filter(user=user, id=session_id).first()
    if not session:
        session = ChatSession.objects.create(user=user, title="Chat Baru")

    result = ask_bot(user.id, message, request_id=request_id)

    # Normalisasi output (biar backward compatible kalau suatu saat ask_bot return string)
    if isinstance(result, dict):
        answer = result.get("answer", "")
        sources = result.get("sources", []) or []
    else:
        answer = str(result)
        sources = []

    ChatHistory.objects.create(user=user, session=session, question=message, answer=answer)
    _maybe_update_session_title(session, message)
    if session:
        session.save(update_fields=["updated_at"])

    # Return ke API: answer + sources (sources bisa ditampilkan di UI)
    return {"answer": answer, "sources": sources, "session_id": session.id}


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
