# core/views.py
import json
import logging
import time

from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponseServerError
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from inertia import render as inertia_render

from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.models import User
from django.db import IntegrityError

from . import service  #  business logic dipindah ke core/service.py
from .models import UserQuota

logger = logging.getLogger(__name__)

QUOTA_BYTES = 10 * 1024 * 1024  # 10MB


def _rid(request) -> str:
    return getattr(request, "request_id", "-")


def _log_extra(request) -> dict:
    return {"request_id": _rid(request)}


def _get_client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


# =========================
# AUTH VIEWS
# =========================
def register_view(request):
    if request.user.is_authenticated:
        logger.info(" [AUTH] already logged in -> redirect home", extra=_log_extra(request))
        return redirect("home")

    if request.method == "POST":
        ip = _get_client_ip(request)
        try:
            data = json.loads(request.body)
            username = data.get("username")
            email = data.get("email")
            password = data.get("password")
            confirm = data.get("password_confirmation")

            errors = {}
            if not username:
                errors["username"] = "Username wajib diisi."
            if not email:
                errors["email"] = "Email wajib diisi."
            if not password:
                errors["password"] = "Password wajib diisi."
            if password != confirm:
                errors["password_confirmation"] = "Password tidak sama."

            if errors:
                logger.warning(f" [REGISTER FAIL] ip={ip} errors={errors}", extra=_log_extra(request))
                return inertia_render(request, "Auth/Register", props={"errors": errors})

            user = User.objects.create_user(username=username, email=email, password=password)
            # default quota otomatis (10MB)
            try:
                UserQuota.objects.get_or_create(user=user)
            except Exception:
                pass
            login(request, user)

            logger.info(f" [REGISTER SUCCESS] user={user.username} id={user.id} ip={ip}", extra=_log_extra(request))
            return redirect("home")

        except IntegrityError:
            logger.warning(f" [REGISTER FAIL] ip={ip} username='{username}' already used", extra=_log_extra(request))
            return inertia_render(request, "Auth/Register", props={"errors": {"username": "Username sudah digunakan."}})
        except Exception as e:
            logger.error(f" [REGISTER ERROR] ip={ip} err={repr(e)}", extra=_log_extra(request), exc_info=True)
            return inertia_render(request, "Auth/Register", props={"errors": {"auth": "Terjadi kesalahan server."}})

    return inertia_render(request, "Auth/Register")


def login_view(request):
    if request.user.is_authenticated:
        logger.info(" [AUTH] already logged in -> redirect home", extra=_log_extra(request))
        return redirect("home")

    if request.method == "POST":
        ip = _get_client_ip(request)
        try:
            data = json.loads(request.body)
            username = data.get("username")
            password = data.get("password")

            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                logger.info(f" [LOGIN SUCCESS] user={user.username} id={user.id} ip={ip}", extra=_log_extra(request))
                return redirect("home")

            logger.warning(f" [LOGIN FAIL] username={username} ip={ip}", extra=_log_extra(request))
            return inertia_render(request, "Auth/Login", props={"errors": {"auth": "Username atau password salah."}})
        except Exception as e:
            logger.error(f" [LOGIN ERROR] ip={ip} err={repr(e)}", extra=_log_extra(request), exc_info=True)
            return inertia_render(request, "Auth/Login", props={"errors": {"auth": "Error sistem."}})

    return inertia_render(request, "Auth/Login")


def logout_view(request):
    if request.user.is_authenticated:
        ip = _get_client_ip(request)
        user_name = request.user.username
        logout(request)
        logger.info(f" [LOGOUT] user='{user_name}' ip={ip}", extra=_log_extra(request))
    return redirect("login")


# =========================
# DASHBOARD
# =========================
@login_required
def chat_view(request):
    t0 = time.time()
    user = request.user
    ip = _get_client_ip(request)

    try:
        logger.info(f" [VIEW START] user={user.username}(id={user.id}) ip={ip}", extra=_log_extra(request))

        quota_bytes = service.get_user_quota_bytes(user=user, default_quota_bytes=QUOTA_BYTES)
        props = service.get_dashboard_props(user=user, quota_bytes=quota_bytes)

        dur = round(time.time() - t0, 4)
        logger.info(
            f" [VIEW OK] user={user.username}(id={user.id}) hist={len(props['initialHistory'])} "
            f"docs={len(props['documents'])} storage={props['storage']['used_human']}/{props['storage']['quota_human']} "
            f"({props['storage']['used_pct']}%) in {dur}s",
            extra=_log_extra(request),
        )

        return inertia_render(request, "Chat/Index", props=props)

    except Exception as e:
        logger.critical(
            f" [VIEW ERROR] user={user.username}(id={user.id}) ip={ip} err={repr(e)}",
            extra=_log_extra(request),
            exc_info=True,
        )
        try:
            return render(request, "500.html")
        except Exception:
            return HttpResponseServerError("500 - Internal Server Error (Cek Terminal)")


# =========================
# API ENDPOINTS
# =========================
@csrf_exempt
@login_required
def documents_api(request):
    user = request.user
    ip = _get_client_ip(request)

    if request.method != "GET":
        logger.warning(f" [DOCS API] Method not allowed method={request.method} ip={ip}", extra=_log_extra(request))
        return JsonResponse({"status": "error", "msg": "Method not allowed"}, status=405)

    try:
        quota_bytes = service.get_user_quota_bytes(user=user, default_quota_bytes=QUOTA_BYTES)
        payload = service.get_documents_payload(user=user, quota_bytes=quota_bytes)
        logger.info(
            f" [DOCS API OK] user={user.username}(id={user.id}) ip={ip} docs={len(payload['documents'])} "
            f"storage={payload['storage']['used_human']}({payload['storage']['used_pct']}%)",
            extra=_log_extra(request),
        )
        return JsonResponse(payload)
    except Exception as e:
        logger.error(f" [DOCS API ERROR] user={user.username}(id={user.id}) ip={ip} err={repr(e)}",
                     extra=_log_extra(request), exc_info=True)
        return JsonResponse({"status": "error", "msg": "Terjadi kesalahan server."}, status=500)


@csrf_exempt
@login_required
def document_detail_api(request, doc_id: int):
    user = request.user
    ip = _get_client_ip(request)

    if request.method != "DELETE":
        logger.warning(f" [DOCS DETAIL] Method not allowed method={request.method} ip={ip}", extra=_log_extra(request))
        return JsonResponse({"status": "error", "msg": "Method not allowed"}, status=405)

    try:
        ok = service.delete_document_for_user(user=user, doc_id=doc_id)
        if ok:
            logger.info(f" [DOC DELETE OK] user={user.username}(id={user.id}) ip={ip} doc_id={doc_id}",
                        extra=_log_extra(request))
            return JsonResponse({"status": "success"})
        return JsonResponse({"status": "error", "msg": "Dokumen tidak ditemukan."}, status=404)
    except Exception as e:
        logger.error(f" [DOC DELETE ERROR] user={user.username}(id={user.id}) ip={ip} doc_id={doc_id} err={repr(e)}",
                     extra=_log_extra(request), exc_info=True)
        return JsonResponse({"status": "error", "msg": "Terjadi kesalahan server."}, status=500)


@csrf_exempt
@login_required
def upload_api(request):
    user = request.user
    ip = _get_client_ip(request)

    if request.method != "POST":
        logger.warning(f" [UPLOAD] Method not allowed method={request.method} ip={ip}", extra=_log_extra(request))
        return JsonResponse({"status": "error", "msg": "Method not allowed"}, status=405)

    files = request.FILES.getlist("files")
    if not files:
        logger.warning(f" [UPLOAD] submit tanpa file user={user.username}(id={user.id}) ip={ip}", extra=_log_extra(request))
        return JsonResponse({"status": "error", "msg": "Tidak ada file yang dikirim"}, status=400)

    logger.info(f" [BATCH START] user={user.username}(id={user.id}) ip={ip} files={len(files)}", extra=_log_extra(request))
    try:
        quota_bytes = service.get_user_quota_bytes(user=user, default_quota_bytes=QUOTA_BYTES)
        payload = service.upload_files_batch(user=user, files=files, quota_bytes=quota_bytes)
        logger.info(f" [BATCH END] user={user.username}(id={user.id}) ip={ip} status={payload.get('status')}", extra=_log_extra(request))

        # status code sesuai behavior lama
        if payload.get("status") == "success":
            return JsonResponse(payload)
        return JsonResponse(payload, status=400)

    except Exception as e:
        logger.error(f" [UPLOAD CRASH] user={user.username}(id={user.id}) ip={ip} err={repr(e)}",
                     extra=_log_extra(request), exc_info=True)
        return JsonResponse({"status": "error", "msg": "Terjadi kesalahan server."}, status=500)


@csrf_exempt
@login_required
def chat_api(request):
    user = request.user
    ip = _get_client_ip(request)

    if request.method != "POST":
        logger.warning(f" [CHAT] Method not allowed method={request.method} ip={ip}", extra=_log_extra(request))
        return JsonResponse({"status": "error", "msg": "Method not allowed"}, status=405)

    try:
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            logger.warning(f" [CHAT] Invalid JSON user={user.username}(id={user.id}) ip={ip}", extra=_log_extra(request))
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        query = data.get("message")
        session_id_raw = data.get("session_id")
        session_id = int(session_id_raw) if str(session_id_raw).isdigit() else None
        if not query:
            logger.warning(f" [CHAT] Pesan kosong user={user.username}(id={user.id}) ip={ip}", extra=_log_extra(request))
            return JsonResponse({"error": "Pesan kosong"}, status=400)

        q_preview = query if len(query) <= 120 else query[:120] + "..."
        logger.info(f" [CHAT REQUEST] user={user.username}(id={user.id}) ip={ip} q='{q_preview}'", extra=_log_extra(request))

        payload = service.chat_and_save(user=user, message=query, request_id=_rid(request), session_id=session_id)

        src_count = len(payload.get("sources") or [])
        logger.info(
            f" [CHAT RESPONSE] user={user.username}(id={user.id}) ip={ip} "
            f"len={len(payload.get('answer',''))} sources={src_count}",
            extra=_log_extra(request),
        )
        return JsonResponse(payload)

    except Exception as e:
        logger.error(f" [CHAT CRASH] user={user.username}(id={user.id}) ip={ip} err={repr(e)}",
                     extra=_log_extra(request), exc_info=True)
        return JsonResponse({"error": "Terjadi kesalahan pada server AI."}, status=500)


@csrf_exempt
@login_required
def reingest_api(request):
    user = request.user
    ip = _get_client_ip(request)

    if request.method != "POST":
        logger.warning(f" [REINGEST] Method not allowed method={request.method} ip={ip}", extra=_log_extra(request))
        return JsonResponse({"status": "error", "msg": "Method not allowed"}, status=405)

    try:
        # optional: body bisa berisi {"doc_ids":[1,2,3]} atau kosong untuk reingest semua
        doc_ids = None
        if request.body:
            try:
                data = json.loads(request.body)
                raw_ids = data.get("doc_ids")
                if isinstance(raw_ids, list):
                    doc_ids = [int(x) for x in raw_ids if str(x).isdigit()]
            except Exception:
                doc_ids = None

        logger.info(f" [REINGEST START] user={user.username}(id={user.id}) ip={ip} doc_ids={doc_ids}", extra=_log_extra(request))

        payload = service.reingest_documents_for_user(user=user, doc_ids=doc_ids)

        logger.info(f" [REINGEST END] user={user.username}(id={user.id}) ip={ip} status={payload.get('status')}", extra=_log_extra(request))

        if payload.get("status") == "success":
            return JsonResponse(payload)
        return JsonResponse(payload, status=400)

    except Exception as e:
        logger.error(f" [REINGEST CRASH] user={user.username}(id={user.id}) ip={ip} err={repr(e)}",
                     extra=_log_extra(request), exc_info=True)
        return JsonResponse({"status": "error", "msg": "Terjadi kesalahan server."}, status=500)


# =========================
# CHAT SESSIONS API
# =========================
@csrf_exempt
@login_required
def sessions_api(request):
    user = request.user
    ip = _get_client_ip(request)

    if request.method == "GET":
        try:
            page = request.GET.get("page", "1")
            page_size = request.GET.get("page_size", "20")
            payload = service.list_sessions(user=user, limit=int(page_size), page=int(page))
            return JsonResponse(payload)
        except Exception as e:
            logger.error(f" [SESSIONS LIST ERROR] user={user.username}(id={user.id}) ip={ip} err={repr(e)}",
                         extra=_log_extra(request), exc_info=True)
            return JsonResponse({"status": "error", "msg": "Terjadi kesalahan server."}, status=500)

    if request.method == "POST":
        try:
            title = ""
            if request.body:
                try:
                    data = json.loads(request.body)
                    title = data.get("title") or ""
                except Exception:
                    title = ""

            session = service.create_session(user=user, title=title)
            return JsonResponse({"session": session})
        except Exception as e:
            logger.error(f" [SESSIONS CREATE ERROR] user={user.username}(id={user.id}) ip={ip} err={repr(e)}",
                         extra=_log_extra(request), exc_info=True)
            return JsonResponse({"status": "error", "msg": "Terjadi kesalahan server."}, status=500)

    logger.warning(f" [SESSIONS] Method not allowed method={request.method} ip={ip}", extra=_log_extra(request))
    return JsonResponse({"status": "error", "msg": "Method not allowed"}, status=405)


@csrf_exempt
@login_required
def session_detail_api(request, session_id: int):
    user = request.user
    ip = _get_client_ip(request)

    if request.method == "DELETE":
        try:
            ok = service.delete_session(user=user, session_id=session_id)
            if ok:
                return JsonResponse({"status": "success"})
            return JsonResponse({"status": "error", "msg": "Session tidak ditemukan."}, status=404)
        except Exception as e:
            logger.error(f" [SESSIONS DELETE ERROR] user={user.username}(id={user.id}) ip={ip} err={repr(e)}",
                         extra=_log_extra(request), exc_info=True)
            return JsonResponse({"status": "error", "msg": "Terjadi kesalahan server."}, status=500)

    if request.method == "PATCH":
        try:
            title = ""
            if request.body:
                try:
                    data = json.loads(request.body)
                    title = data.get("title") or ""
                except Exception:
                    title = ""
            updated = service.rename_session(user=user, session_id=session_id, title=title)
            if not updated:
                return JsonResponse({"status": "error", "msg": "Session tidak ditemukan."}, status=404)
            return JsonResponse({"session": updated})
        except Exception as e:
            logger.error(f" [SESSIONS RENAME ERROR] user={user.username}(id={user.id}) ip={ip} err={repr(e)}",
                         extra=_log_extra(request), exc_info=True)
            return JsonResponse({"status": "error", "msg": "Terjadi kesalahan server."}, status=500)

    if request.method == "GET":
        try:
            history = service.get_session_history(user=user, session_id=session_id)
            return JsonResponse({"history": history})
        except Exception as e:
            logger.error(f" [SESSIONS HISTORY ERROR] user={user.username}(id={user.id}) ip={ip} err={repr(e)}",
                         extra=_log_extra(request), exc_info=True)
            return JsonResponse({"status": "error", "msg": "Terjadi kesalahan server."}, status=500)

    logger.warning(f" [SESSIONS DETAIL] Method not allowed method={request.method} ip={ip}", extra=_log_extra(request))
    return JsonResponse({"status": "error", "msg": "Method not allowed"}, status=405)
