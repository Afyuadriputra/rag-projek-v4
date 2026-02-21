from __future__ import annotations

from typing import Any, Dict, List, Tuple

from django.contrib.auth.models import User
from django.core.files.uploadedfile import UploadedFile

from core.models import AcademicDocument, UserQuota
from core.services.shared.utils import bytes_to_human

from .ingest_adapter import delete_vectors_for_doc_strict, process_document


def serialize_documents_for_user(user: User, limit: int = 50) -> Tuple[List[Dict[str, Any]], int]:
    docs_qs = AcademicDocument.objects.filter(user=user).order_by("-uploaded_at")[:limit]
    documents: List[Dict[str, Any]] = []
    total_bytes = 0
    for doc in docs_qs:
        size = 0
        try:
            if doc.file and hasattr(doc.file, "size"):
                size = doc.file.size or 0
        except Exception:
            size = 0
        total_bytes += size
        documents.append(
            {
                "id": doc.id,
                "title": doc.title,
                "is_embedded": doc.is_embedded,
                "uploaded_at": doc.uploaded_at.strftime("%Y-%m-%d %H:%M"),
                "size_bytes": size,
            }
        )
    return documents, total_bytes


def get_user_quota_bytes(user: User, default_quota_bytes: int) -> int:
    try:
        quota = UserQuota.objects.filter(user=user).first()
        if quota and quota.quota_bytes and quota.quota_bytes > 0:
            return int(quota.quota_bytes)
    except Exception:
        pass
    return int(default_quota_bytes)


def build_storage_payload(total_bytes: int, quota_bytes: int) -> Dict[str, Any]:
    quota_bytes = max(int(quota_bytes), 1)
    used_pct = int(min(100, (total_bytes / quota_bytes) * 100))
    return {
        "used_bytes": int(total_bytes),
        "quota_bytes": int(quota_bytes),
        "used_pct": used_pct,
        "used_human": bytes_to_human(total_bytes),
        "quota_human": bytes_to_human(quota_bytes),
    }


def get_documents_payload(user: User, quota_bytes: int) -> Dict[str, Any]:
    documents, total_bytes = serialize_documents_for_user(user=user, limit=50)
    storage = build_storage_payload(total_bytes, quota_bytes)
    return {"documents": documents, "storage": storage}


def upload_files_batch(user: User, files: List[UploadedFile], quota_bytes: int) -> Dict[str, Any]:
    success_count = 0
    error_count = 0
    errors: List[str] = []

    _, total_bytes = serialize_documents_for_user(user=user, limit=100000)
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
    return {"status": "error", "msg": f"Gagal semua. Detail: {', '.join(errors)}"}


def reingest_documents_for_user(user: User, doc_ids: List[int] | None = None) -> Dict[str, Any]:
    qs = AcademicDocument.objects.filter(user=user)
    if doc_ids:
        qs = qs.filter(id__in=doc_ids)
    docs = list(qs)
    if not docs:
        return {"status": "error", "msg": "Tidak ada dokumen yang cocok untuk reingest."}

    ok_count = 0
    fail_count = 0
    detail: List[Dict[str, Any]] = []
    for doc in docs:
        ok_del, _remaining = delete_vectors_for_doc_strict(user_id=str(user.id), doc_id=str(doc.id), source=doc.title)
        if not ok_del:
            detail.append({"doc_id": doc.id, "title": doc.title, "status": "delete_failed"})
            fail_count += 1
            continue
        ok_ingest = process_document(doc)
        if ok_ingest:
            doc.is_embedded = True
            doc.save(update_fields=["is_embedded"])
            ok_count += 1
            detail.append({"doc_id": doc.id, "title": doc.title, "status": "ok"})
        else:
            doc.is_embedded = False
            doc.save(update_fields=["is_embedded"])
            fail_count += 1
            detail.append({"doc_id": doc.id, "title": doc.title, "status": "ingest_failed"})

    status = "success" if ok_count > 0 else "error"
    msg = f"Reingest selesai. sukses={ok_count}, gagal={fail_count}"
    return {"status": status, "msg": msg, "detail": detail}


def delete_document_for_user(user: User, doc_id: int) -> bool:
    doc = AcademicDocument.objects.filter(user=user, id=doc_id).first()
    if not doc:
        return False
    ok, _remaining = delete_vectors_for_doc_strict(user_id=str(user.id), doc_id=str(doc.id), source=doc.title)
    doc.delete()
    return bool(ok)

