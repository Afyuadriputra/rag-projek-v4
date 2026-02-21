# core/views.py
import json
import logging
import time
import os

from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponseServerError
from django.core.exceptions import RequestDataTooBig
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from inertia import render as inertia_render

from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.models import User
from django.db import IntegrityError

from . import service  #  business logic dipindah ke core/service.py
from .models import UserQuota, ChatSession
from .presence import (
    cleanup_stale_presence,
    count_active_online_non_staff_users,
    is_user_online_non_staff,
    mark_presence_inactive,
    mark_presence_login,
)
from .system_settings import (
    get_concurrent_limit_state,
    get_maintenance_state,
    get_registration_enabled,
    get_registration_limit_state,
)

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("audit")

QUOTA_BYTES = 10 * 1024 * 1024  # 10MB


def _rid(request) -> str:
    return getattr(request, "request_id", "-")


def _planner_v3_enabled() -> bool:
    return str(os.environ.get("PLANNER_V3_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}


def _log_extra(request) -> dict:
    return {"request_id": _rid(request)}

def _audit_extra(request, **overrides) -> dict:
    base = getattr(request, "audit", {}) or {}
    extra = {
        "request_id": base.get("request_id", _rid(request)),
        "user": base.get("user", "-"),
        "ip": base.get("ip", "-"),
    }
    extra.update({k: v for k, v in overrides.items() if v is not None})
    return extra

def _get_client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _planner_session_state(state: dict) -> dict:
    s = state or {}
    return {
        "current_step": s.get("current_step"),
        "data_level": s.get("data_level", {}),
        "collected_data": s.get("collected_data", {}),
    }


def _normalize_planner_payload(payload: dict, state: dict) -> dict:
    out = dict(payload or {})
    planner_meta = out.get("planner_meta") or {}
    origin = str(planner_meta.get("origin") or "")
    if "event_type" not in planner_meta:
        planner_meta["event_type"] = origin or "user_input"
    out.setdefault("type", "planner_step")
    out.setdefault("answer", "")
    out.setdefault("options", [])
    out.setdefault("allow_custom", False)
    out.setdefault("planner_warning", state.get("planner_warning"))
    out.setdefault("profile_hints", state.get("profile_hints", {}))
    out["planner_step"] = planner_meta.get("step") or state.get("current_step")
    out["session_state"] = _planner_session_state(state)
    out["planner_meta"] = planner_meta
    return out


def _is_registration_enabled() -> bool:
    return get_registration_enabled()


def _non_staff_registered_count() -> int:
    return User.objects.filter(is_staff=False, is_superuser=False).count()


def _maintenance_props(forced_logout: bool = False) -> dict:
    state = get_maintenance_state()
    return {
        "maintenance_enabled": state.enabled,
        "maintenance_message": state.message,
        "maintenance_start_at": state.start_at,
        "maintenance_estimated_end_at": state.estimated_end_at,
        "forced_logout": forced_logout,
    }


def _inertia_render_with_status(request, component: str, props: dict, status: int):
    resp = inertia_render(request, component, props=props)
    resp.status_code = status
    return resp


# =========================
# AUTH VIEWS
# =========================
def register_view(request):
    maintenance_state = get_maintenance_state()
    if maintenance_state.enabled:
        ip = _get_client_ip(request)
        logger.warning(f" [REGISTER BLOCKED MAINTENANCE] ip={ip}", extra=_log_extra(request))
        audit_logger.warning(
            "action=register status=blocked reason=maintenance",
            extra=_audit_extra(request),
        )
        props = {
            "registration_enabled": False,
            "errors": {"auth": "Sistem sedang maintenance. Silakan coba beberapa saat lagi."},
            **_maintenance_props(forced_logout=False),
        }
        return _inertia_render_with_status(request, "Auth/Register", props=props, status=503)

    if request.user.is_authenticated:
        logger.info(" [AUTH] already logged in -> redirect home", extra=_log_extra(request))
        return redirect("home")

    registration_enabled = _is_registration_enabled()
    if not registration_enabled:
        ip = _get_client_ip(request)
        logger.warning(f" [REGISTER DISABLED] blocked ip={ip}", extra=_log_extra(request))
        audit_logger.warning(
            "action=register status=blocked reason=registration_disabled",
            extra=_audit_extra(request),
        )
        return _inertia_render_with_status(
            request,
            "Auth/Register",
            props={
                "registration_enabled": False,
                "errors": {"auth": "Pendaftaran saat ini dinonaktifkan oleh admin."},
                **_maintenance_props(forced_logout=False),
            },
            status=403,
        )

    registration_limit_state = get_registration_limit_state()
    registered_non_staff_count = _non_staff_registered_count()
    if (
        registration_limit_state.enabled
        and registered_non_staff_count >= registration_limit_state.max_registered_users
    ):
        ip = _get_client_ip(request)
        logger.warning(
            " [REGISTER BLOCKED LIMIT] ip=%s count=%s limit=%s",
            ip,
            registered_non_staff_count,
            registration_limit_state.max_registered_users,
            extra=_log_extra(request),
        )
        audit_logger.warning(
            "action=register status=blocked reason=registration_limit code=REGISTRATION_LIMIT_REACHED "
            f"count={registered_non_staff_count} limit={registration_limit_state.max_registered_users}",
            extra=_audit_extra(request),
        )
        return _inertia_render_with_status(
            request,
            "Auth/Register",
            props={
                "registration_enabled": False,
                "errors": {"auth": registration_limit_state.message},
                **_maintenance_props(forced_logout=False),
            },
            status=403,
        )

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
                return inertia_render(
                    request,
                    "Auth/Register",
                    props={
                        "errors": errors,
                        "registration_enabled": True,
                        **_maintenance_props(forced_logout=False),
                    },
                )

            user = User.objects.create_user(username=username, email=email, password=password)
            # default quota otomatis (10MB)
            try:
                UserQuota.objects.get_or_create(user=user)
            except Exception:
                pass
            # perlu backend eksplisit karena ada multiple auth backends (axes)
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            session_key = request.session.session_key
            if not session_key:
                request.session.save()
                session_key = request.session.session_key
            mark_presence_login(
                user=user,
                session_key=session_key or "",
                ip_address=ip,
                user_agent=request.META.get("HTTP_USER_AGENT", "") or "",
            )

            logger.info(f" [REGISTER SUCCESS] user={user.username} id={user.id} ip={ip}", extra=_log_extra(request))
            audit_logger.info(
                f"action=register status=success user_id={user.id}",
                extra=_audit_extra(request, user=user.username),
            )
            return redirect("home")

        except IntegrityError:
            logger.warning(f" [REGISTER FAIL] ip={ip} username='{username}' already used", extra=_log_extra(request))
            audit_logger.warning(
                "action=register status=fail reason=duplicate_username",
                extra=_audit_extra(request, user=username),
            )
            return inertia_render(
                request,
                "Auth/Register",
                props={
                    "errors": {"username": "Username sudah digunakan."},
                    "registration_enabled": True,
                    **_maintenance_props(forced_logout=False),
                },
            )
        except Exception as e:
            logger.error(f" [REGISTER ERROR] ip={ip} err={repr(e)}", extra=_log_extra(request), exc_info=True)
            audit_logger.error(
                f"action=register status=error err={repr(e)}",
                extra=_audit_extra(request, user=username),
            )
            return inertia_render(
                request,
                "Auth/Register",
                props={
                    "errors": {"auth": "Terjadi kesalahan server."},
                    "registration_enabled": True,
                    **_maintenance_props(forced_logout=False),
                },
            )

    return inertia_render(
        request,
        "Auth/Register",
        props={"registration_enabled": True, **_maintenance_props(forced_logout=False)},
    )


def login_view(request):
    maintenance_state = get_maintenance_state()
    if maintenance_state.enabled:
        ip = _get_client_ip(request)
        forced_logout = request.GET.get("forced") == "1"
        logger.warning(f" [LOGIN BLOCKED MAINTENANCE] ip={ip} forced={forced_logout}", extra=_log_extra(request))
        audit_logger.warning(
            "action=login status=blocked reason=maintenance",
            extra=_audit_extra(request),
        )
        props = {
            "errors": {"auth": "Sistem sedang maintenance. Silakan coba beberapa saat lagi."},
            "registration_enabled": _is_registration_enabled(),
            **_maintenance_props(forced_logout=forced_logout),
        }
        return _inertia_render_with_status(request, "Auth/Login", props=props, status=503)

    if request.user.is_authenticated:
        logger.info(" [AUTH] already logged in -> redirect home", extra=_log_extra(request))
        return redirect("home")

    registration_enabled = _is_registration_enabled()

    if request.method == "POST":
        ip = _get_client_ip(request)
        try:
            data = json.loads(request.body)
            username = data.get("username")
            password = data.get("password")

            # jika sudah terkunci oleh axes
            try:
                from axes.helpers import is_already_locked  # type: ignore
                if is_already_locked(request):
                    logger.warning(f" [LOGIN LOCKED] username={username} ip={ip}", extra=_log_extra(request))
                    audit_logger.warning(
                        "action=login status=locked",
                        extra=_audit_extra(request, user=username),
                    )
                    return _inertia_render_with_status(
                        request,
                        "Auth/Login",
                        props={
                            "errors": {"auth": "Terlalu banyak percobaan. Coba lagi nanti."},
                            "registration_enabled": registration_enabled,
                            **_maintenance_props(forced_logout=False),
                        },
                        status=403,
                    )
            except Exception:
                pass

            user = authenticate(request, username=username, password=password)
            if user is not None:
                concurrent_limit_state = get_concurrent_limit_state()
                if concurrent_limit_state.enabled:
                    cleanup_stale_presence()
                    user_is_staff = bool(user.is_staff or user.is_superuser)
                    bypass = concurrent_limit_state.staff_bypass and user_is_staff
                    current_active = count_active_online_non_staff_users()
                    already_online = is_user_online_non_staff(user)
                    if (not bypass) and (not already_online) and (
                        current_active >= concurrent_limit_state.max_concurrent_logins
                    ):
                        logger.warning(
                            " [LOGIN BLOCKED CONCURRENT] username=%s ip=%s online=%s limit=%s",
                            username,
                            ip,
                            current_active,
                            concurrent_limit_state.max_concurrent_logins,
                            extra=_log_extra(request),
                        )
                        audit_logger.warning(
                            "action=login status=blocked reason=concurrent_limit code=CONCURRENT_LIMIT_REACHED "
                            f"online={current_active} limit={concurrent_limit_state.max_concurrent_logins}",
                            extra=_audit_extra(request, user=username),
                        )
                        return _inertia_render_with_status(
                            request,
                            "Auth/Login",
                            props={
                                "errors": {"auth": concurrent_limit_state.message},
                                "registration_enabled": registration_enabled,
                                **_maintenance_props(forced_logout=False),
                            },
                            status=403,
                        )

                login(request, user)
                session_key = request.session.session_key
                if not session_key:
                    request.session.save()
                    session_key = request.session.session_key
                mark_presence_login(
                    user=user,
                    session_key=session_key or "",
                    ip_address=ip,
                    user_agent=request.META.get("HTTP_USER_AGENT", "") or "",
                )
                logger.info(f" [LOGIN SUCCESS] user={user.username} id={user.id} ip={ip}", extra=_log_extra(request))
                audit_logger.info(
                    f"action=login status=success user_id={user.id}",
                    extra=_audit_extra(request, user=user.username),
                )
                return redirect("home")

            logger.warning(f" [LOGIN FAIL] username={username} ip={ip}", extra=_log_extra(request))
            audit_logger.warning(
                "action=login status=fail reason=invalid_credentials",
                extra=_audit_extra(request, user=username),
            )
            return inertia_render(
                request,
                "Auth/Login",
                props={
                    "errors": {"auth": "Username atau password salah."},
                    "registration_enabled": registration_enabled,
                    **_maintenance_props(forced_logout=False),
                },
            )
        except Exception as e:
            logger.error(f" [LOGIN ERROR] ip={ip} err={repr(e)}", extra=_log_extra(request), exc_info=True)
            audit_logger.error(
                f"action=login status=error err={repr(e)}",
                extra=_audit_extra(request, user=username),
            )
            return inertia_render(
                request,
                "Auth/Login",
                props={
                    "errors": {"auth": "Error sistem."},
                    "registration_enabled": registration_enabled,
                    **_maintenance_props(forced_logout=False),
                },
            )

    return inertia_render(
        request,
        "Auth/Login",
        props={
            "registration_enabled": registration_enabled,
            **_maintenance_props(forced_logout=False),
        },
    )


def logout_view(request):
    if request.user.is_authenticated:
        ip = _get_client_ip(request)
        user_name = request.user.username
        session_key = request.session.session_key or ""
        if session_key:
            mark_presence_inactive(session_key=session_key)
        logout(request)
        logger.info(f" [LOGOUT] user='{user_name}' ip={ip}", extra=_log_extra(request))
        audit_logger.info(
            f"action=logout status=success session_key={session_key[:10]}",
            extra=_audit_extra(request, user=user_name),
        )
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
            audit_logger.info(
                f"action=doc_delete status=success doc_id={doc_id}",
                extra=_audit_extra(request),
            )
            return JsonResponse({"status": "success"})
        audit_logger.info(
            f"action=doc_delete status=not_found doc_id={doc_id}",
            extra=_audit_extra(request),
        )
        return JsonResponse({"status": "error", "msg": "Dokumen tidak ditemukan."}, status=404)
    except Exception as e:
        logger.error(f" [DOC DELETE ERROR] user={user.username}(id={user.id}) ip={ip} doc_id={doc_id} err={repr(e)}",
                     extra=_log_extra(request), exc_info=True)
        audit_logger.error(
            f"action=doc_delete status=error doc_id={doc_id} err={repr(e)}",
            extra=_audit_extra(request),
        )
        return JsonResponse({"status": "error", "msg": "Terjadi kesalahan server."}, status=500)


@csrf_exempt
@login_required
def upload_api(request):
    user = request.user
    ip = _get_client_ip(request)

    if request.method != "POST":
        logger.warning(f" [UPLOAD] Method not allowed method={request.method} ip={ip}", extra=_log_extra(request))
        return JsonResponse({"status": "error", "msg": "Method not allowed"}, status=405)

    try:
        files = request.FILES.getlist("files")
    except RequestDataTooBig:
        logger.warning(f" [UPLOAD] payload terlalu besar user={user.username}(id={user.id}) ip={ip}", extra=_log_extra(request))
        audit_logger.warning(
            "action=upload status=payload_too_large",
            extra=_audit_extra(request),
        )
        return JsonResponse({"status": "error", "msg": "File terlalu besar."}, status=413)
    if not files:
        logger.warning(f" [UPLOAD] submit tanpa file user={user.username}(id={user.id}) ip={ip}", extra=_log_extra(request))
        audit_logger.warning(
            "action=upload status=empty_files",
            extra=_audit_extra(request),
        )
        return JsonResponse({"status": "error", "msg": "Tidak ada file yang dikirim"}, status=400)

    logger.info(f" [BATCH START] user={user.username}(id={user.id}) ip={ip} files={len(files)}", extra=_log_extra(request))
    try:
        quota_bytes = service.get_user_quota_bytes(user=user, default_quota_bytes=QUOTA_BYTES)
        payload = service.upload_files_batch(user=user, files=files, quota_bytes=quota_bytes)
        logger.info(f" [BATCH END] user={user.username}(id={user.id}) ip={ip} status={payload.get('status')}", extra=_log_extra(request))
        total_size = sum([getattr(f, "size", 0) or 0 for f in files])
        names = [getattr(f, "name", "-") for f in files]
        names_preview = ", ".join(names[:5]) + ("..." if len(names) > 5 else "")
        audit_logger.info(
            f"action=upload status={payload.get('status')} files={len(files)} bytes={total_size} names={names_preview}",
            extra=_audit_extra(request),
        )

        # status code sesuai behavior lama
        if payload.get("status") == "success":
            return JsonResponse(payload)
        return JsonResponse(payload, status=400)

    except Exception as e:
        logger.error(f" [UPLOAD CRASH] user={user.username}(id={user.id}) ip={ip} err={repr(e)}",
                     extra=_log_extra(request), exc_info=True)
        audit_logger.error(
            f"action=upload status=error err={repr(e)}",
            extra=_audit_extra(request),
        )
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
        mode = str(data.get("mode") or "chat").strip().lower()
        option_id_raw = data.get("option_id")
        if option_id_raw is not None and (not str(option_id_raw).isdigit()):
            return JsonResponse({"error": "option_id tidak valid"}, status=400)
        option_id = int(option_id_raw) if str(option_id_raw).isdigit() else None
        session_id_raw = data.get("session_id")
        if session_id_raw is not None and (not str(session_id_raw).isdigit()):
            return JsonResponse({"error": "session_id tidak valid"}, status=400)
        session_id = int(session_id_raw) if str(session_id_raw).isdigit() else None
        if mode not in {"chat", "planner"}:
            return JsonResponse({"error": "mode tidak valid"}, status=400)

        if mode == "chat" and not query:
            logger.warning(f" [CHAT] Pesan kosong user={user.username}(id={user.id}) ip={ip}", extra=_log_extra(request))
            return JsonResponse({"error": "Pesan kosong"}, status=400)

        q_preview = (query or "") if len((query or "")) <= 120 else (query or "")[:120] + "..."
        logger.info(
            f" [CHAT REQUEST] user={user.username}(id={user.id}) ip={ip} mode={mode} q='{q_preview}'",
            extra=_log_extra(request),
        )

        if mode == "planner":
            planner_session = service.get_or_create_chat_session(user=user, session_id=session_id)
            state_map = dict(request.session.get("planner_state_by_session") or {})
            planner_state = state_map.get(str(planner_session.id))
            if not planner_state:
                planner_state = request.session.get("planner_state")

            if not planner_state:
                payload, new_state = service.planner_start(user=user, session=planner_session)
            else:
                payload, new_state = service.planner_continue(
                    user=user,
                    session=planner_session,
                    planner_state=planner_state,
                    message=query or "",
                    option_id=option_id,
                    request_id=_rid(request),
                )
            payload = _normalize_planner_payload(payload, new_state)
            payload.setdefault("session_id", planner_session.id)
            state_map[str(planner_session.id)] = new_state
            request.session["planner_state_by_session"] = state_map
            request.session["planner_state"] = new_state
            request.session.modified = True
        else:
            payload = service.chat_and_save(user=user, message=query, request_id=_rid(request), session_id=session_id)
            if isinstance(payload, dict):
                payload.setdefault("type", "chat")

        src_count = len(payload.get("sources") or [])
        logger.info(
            f" [CHAT RESPONSE] user={user.username}(id={user.id}) ip={ip} "
            f"mode={mode} len={len(payload.get('answer',''))} sources={src_count}",
            extra=_log_extra(request),
        )
        return JsonResponse(payload)

    except Exception as e:
        logger.error(f" [CHAT CRASH] user={user.username}(id={user.id}) ip={ip} err={repr(e)}",
                     extra=_log_extra(request), exc_info=True)
        return JsonResponse({"error": "Terjadi kesalahan pada server AI."}, status=500)


@csrf_exempt
@login_required
def planner_start_v3_api(request):
    user = request.user
    ip = _get_client_ip(request)
    if not _planner_v3_enabled():
        return JsonResponse({"status": "error", "error": "Planner v3 dinonaktifkan."}, status=404)
    if request.method != "POST":
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)
    try:
        session_id = None
        reuse_doc_ids = []
        files = request.FILES.getlist("files")
        if request.content_type and "application/json" in request.content_type:
            data = json.loads(request.body or "{}")
            session_id_raw = data.get("session_id")
            if session_id_raw is not None and str(session_id_raw).isdigit():
                session_id = int(session_id_raw)
            reuse_doc_ids = [
                int(x) for x in (data.get("reuse_doc_ids") or []) if str(x).isdigit()
            ]
        else:
            session_id_raw = request.POST.get("session_id")
            if session_id_raw and str(session_id_raw).isdigit():
                session_id = int(session_id_raw)
            reuse_doc_ids = [
                int(x)
                for x in request.POST.getlist("reuse_doc_ids")
                if str(x).isdigit()
            ]
        payload = service.planner_start_v3(
            user=user,
            files=files,
            reuse_doc_ids=reuse_doc_ids,
            session_id=session_id,
        )
        status = 200 if payload.get("status") == "success" else 400
        logger.info(
            " [PLANNER V3 START] user=%s(id=%s) ip=%s status=%s docs=%s",
            user.username,
            user.id,
            ip,
            payload.get("status"),
            len(payload.get("documents_summary") or []),
            extra=_log_extra(request),
        )
        return JsonResponse(payload, status=status)
    except Exception as e:
        logger.error(
            " [PLANNER V3 START ERROR] user=%s(id=%s) ip=%s err=%s",
            user.username,
            user.id,
            ip,
            repr(e),
            extra=_log_extra(request),
            exc_info=True,
        )
        return JsonResponse({"status": "error", "error": "Terjadi kesalahan server."}, status=500)


@csrf_exempt
@login_required
def planner_execute_v3_api(request):
    user = request.user
    ip = _get_client_ip(request)
    if not _planner_v3_enabled():
        return JsonResponse({"status": "error", "error": "Planner v3 dinonaktifkan."}, status=404)
    if request.method != "POST":
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)
    try:
        data = json.loads(request.body or "{}")
        planner_run_id = str(data.get("planner_run_id") or "").strip()
        answers = data.get("answers") or {}
        if not planner_run_id:
            return JsonResponse({"status": "error", "error": "planner_run_id wajib diisi."}, status=400)
        if not isinstance(answers, dict):
            return JsonResponse({"status": "error", "error": "answers harus object."}, status=400)
        session_id = data.get("session_id")
        session_id = int(session_id) if str(session_id).isdigit() else None
        client_summary = str(data.get("client_summary") or "")
        payload = service.planner_execute_v3(
            user=user,
            planner_run_id=planner_run_id,
            answers=answers,
            session_id=session_id,
            client_summary=client_summary,
            request_id=_rid(request),
        )
        status = 200 if payload.get("status") == "success" else 400
        logger.info(
            " [PLANNER V3 EXECUTE] user=%s(id=%s) ip=%s status=%s run=%s",
            user.username,
            user.id,
            ip,
            payload.get("status"),
            planner_run_id,
            extra=_log_extra(request),
        )
        return JsonResponse(payload, status=status)
    except Exception as e:
        logger.error(
            " [PLANNER V3 EXECUTE ERROR] user=%s(id=%s) ip=%s err=%s",
            user.username,
            user.id,
            ip,
            repr(e),
            extra=_log_extra(request),
            exc_info=True,
        )
        return JsonResponse({"status": "error", "error": "Terjadi kesalahan server."}, status=500)


@csrf_exempt
@login_required
def planner_cancel_v3_api(request):
    user = request.user
    if not _planner_v3_enabled():
        return JsonResponse({"status": "error", "error": "Planner v3 dinonaktifkan."}, status=404)
    if request.method != "POST":
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)
    try:
        data = json.loads(request.body or "{}")
        planner_run_id = str(data.get("planner_run_id") or "").strip()
        if not planner_run_id:
            return JsonResponse({"status": "error", "error": "planner_run_id wajib diisi."}, status=400)
        payload = service.planner_cancel_v3(user=user, planner_run_id=planner_run_id)
        status = 200 if payload.get("status") == "success" else 400
        return JsonResponse(payload, status=status)
    except Exception:
        return JsonResponse({"status": "error", "error": "Terjadi kesalahan server."}, status=500)


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
        audit_logger.info(
            f"action=reingest status={payload.get('status')} doc_ids={doc_ids}",
            extra=_audit_extra(request),
        )

        if payload.get("status") == "success":
            return JsonResponse(payload)
        return JsonResponse(payload, status=400)

    except Exception as e:
        logger.error(f" [REINGEST CRASH] user={user.username}(id={user.id}) ip={ip} err={repr(e)}",
                     extra=_log_extra(request), exc_info=True)
        audit_logger.error(
            f"action=reingest status=error err={repr(e)}",
            extra=_audit_extra(request),
        )
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
            try:
                page_i = int(page)
                page_size_i = int(page_size)
            except Exception:
                return JsonResponse({"status": "error", "msg": "Parameter pagination tidak valid."}, status=400)
            payload = service.list_sessions(user=user, limit=page_size_i, page=page_i)
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
            audit_logger.info(
                f"action=session_create status=success session_id={session.get('id')}",
                extra=_audit_extra(request),
            )
            return JsonResponse({"session": session})
        except Exception as e:
            logger.error(f" [SESSIONS CREATE ERROR] user={user.username}(id={user.id}) ip={ip} err={repr(e)}",
                         extra=_log_extra(request), exc_info=True)
            audit_logger.error(
                f"action=session_create status=error err={repr(e)}",
                extra=_audit_extra(request),
            )
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
                audit_logger.info(
                    f"action=session_delete status=success session_id={session_id}",
                    extra=_audit_extra(request),
                )
                return JsonResponse({"status": "success"})
            audit_logger.info(
                f"action=session_delete status=not_found session_id={session_id}",
                extra=_audit_extra(request),
            )
            return JsonResponse({"status": "error", "msg": "Session tidak ditemukan."}, status=404)
        except Exception as e:
            logger.error(f" [SESSIONS DELETE ERROR] user={user.username}(id={user.id}) ip={ip} err={repr(e)}",
                         extra=_log_extra(request), exc_info=True)
            audit_logger.error(
                f"action=session_delete status=error session_id={session_id} err={repr(e)}",
                extra=_audit_extra(request),
            )
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
                audit_logger.info(
                    f"action=session_rename status=not_found session_id={session_id}",
                    extra=_audit_extra(request),
                )
                return JsonResponse({"status": "error", "msg": "Session tidak ditemukan."}, status=404)
            audit_logger.info(
                f"action=session_rename status=success session_id={session_id}",
                extra=_audit_extra(request),
            )
            return JsonResponse({"session": updated})
        except Exception as e:
            logger.error(f" [SESSIONS RENAME ERROR] user={user.username}(id={user.id}) ip={ip} err={repr(e)}",
                         extra=_log_extra(request), exc_info=True)
            audit_logger.error(
                f"action=session_rename status=error session_id={session_id} err={repr(e)}",
                extra=_audit_extra(request),
            )
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


@csrf_exempt
@login_required
def session_timeline_api(request, session_id: int):
    user = request.user
    ip = _get_client_ip(request)

    if request.method != "GET":
        logger.warning(f" [SESSIONS TIMELINE] Method not allowed method={request.method} ip={ip}", extra=_log_extra(request))
        return JsonResponse({"status": "error", "msg": "Method not allowed"}, status=405)

    try:
        if not ChatSession.objects.filter(user=user, id=session_id).exists():
            return JsonResponse({"status": "error", "msg": "Session tidak ditemukan."}, status=404)
        page = request.GET.get("page", "1")
        page_size = request.GET.get("page_size", "100")
        try:
            page_i = int(page)
            page_size_i = int(page_size)
        except Exception:
            return JsonResponse({"status": "error", "msg": "Parameter pagination tidak valid."}, status=400)
        payload = service.get_session_timeline(user=user, session_id=session_id, page=page_i, page_size=page_size_i)
        return JsonResponse(payload)
    except Exception as e:
        logger.error(f" [SESSIONS TIMELINE ERROR] user={user.username}(id={user.id}) ip={ip} err={repr(e)}",
                     extra=_log_extra(request), exc_info=True)
        return JsonResponse({"status": "error", "msg": "Terjadi kesalahan server."}, status=500)
