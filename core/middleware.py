import time
import uuid
import logging
from urllib.parse import urlencode

from django.contrib.auth import logout
from django.http import JsonResponse
from django.shortcuts import redirect

from .presence import (
    PRESENCE_TOUCH_THROTTLE_SECONDS,
    mark_presence_inactive,
    maybe_cleanup_stale_presence,
    touch_presence,
)
from .monitoring import maybe_cleanup_monitoring_retention, maybe_collect_system_snapshot
from .system_settings import get_maintenance_state

logger = logging.getLogger("request")
audit_logger = logging.getLogger("audit")


class RequestContextMiddleware:
    """
    Menambahkan request_id pada request dan membuat 1 baris access log:
    HTTP METHOD PATH -> STATUS (ms) user ip
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = uuid.uuid4().hex[:10]
        t0 = time.time()
        response = None
        try:
            user_obj = getattr(request, "user", None)
            username = (
                getattr(user_obj, "username", "-")
                if user_obj and getattr(user_obj, "is_authenticated", False)
                else "-"
            )
            user_id = (
                getattr(user_obj, "id", "-")
                if user_obj and getattr(user_obj, "is_authenticated", False)
                else "-"
            )
            ip = request.META.get("HTTP_X_FORWARDED_FOR") or request.META.get("REMOTE_ADDR") or "-"
            ip = ip.split(",")[0].strip() if ip else "-"
            agent = request.META.get("HTTP_USER_AGENT") or "-"
            referer = request.META.get("HTTP_REFERER") or "-"
            request.audit = {
                "request_id": request.request_id,
                "user": username,
                "user_id": user_id,
                "ip": ip,
                "agent": agent,
                "referer": referer,
                "method": request.method,
                "path": request.path,
            }
            response = self.get_response(request)
            return response
        finally:
            dur_ms = int((time.time() - t0) * 1000)
            status = getattr(response, "status_code", 500)
            user = getattr(getattr(request, "user", None), "username", "anon")

            ip = request.META.get("HTTP_X_FORWARDED_FOR") or request.META.get("REMOTE_ADDR") or "-"
            ip = ip.split(",")[0].strip() if ip else "-"
            agent = request.META.get("HTTP_USER_AGENT") or "-"
            referer = request.META.get("HTTP_REFERER") or "-"

            logger.info(
                "HTTP %s %s -> %s (%sms) user=%s ip=%s",
                request.method,
                request.path,
                status,
                dur_ms,
                user,
                ip,
                extra={
                    "request_id": request.request_id,
                    "user": user,
                    "ip": ip,
                    "method": request.method,
                    "path": request.path,
                    "status": status,
                    "duration_ms": dur_ms,
                    "agent": agent,
                    "referer": referer,
                },
            )


class UserPresenceMiddleware:
    """
    Memperbarui last_seen user login aktif secara throttled.
    """

    SESSION_TOUCH_KEY = "__presence_last_touch_ts"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        maybe_cleanup_stale_presence(chance=0.01)
        maybe_cleanup_monitoring_retention(chance=0.01)
        maybe_collect_system_snapshot(chance=0.08)

        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return self.get_response(request)

        session_key = getattr(request.session, "session_key", "")
        if not session_key:
            return self.get_response(request)

        now_ts = int(time.time())
        last_touch = int(request.session.get(self.SESSION_TOUCH_KEY, 0) or 0)
        if now_ts - last_touch < PRESENCE_TOUCH_THROTTLE_SECONDS:
            return self.get_response(request)

        try:
            touched = touch_presence(session_key=session_key, throttle_seconds=PRESENCE_TOUCH_THROTTLE_SECONDS)
            if touched:
                request.session[self.SESSION_TOUCH_KEY] = now_ts
                request.session.modified = True
        except Exception:
            # tracking presence tidak boleh mengganggu request utama
            pass

        return self.get_response(request)


class MaintenanceModeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _is_api_path(path: str) -> bool:
        return path.startswith("/api/")

    @staticmethod
    def _is_allowed_public_path(path: str) -> bool:
        # Halaman yang perlu tetap bisa diakses saat maintenance:
        # - login/register
        # - admin (agar staff/superuser bisa login ke admin)
        # - static/media/vite assets
        allowed_prefixes = (
            "/login/",
            "/register/",
            "/admin/",
            "/static/",
            "/media/",
            "/@vite/",
            "/vite/",
        )
        return path.startswith(allowed_prefixes)

    @staticmethod
    def _maintenance_payload(state):
        return {
            "status": "error",
            "code": "MAINTENANCE_MODE",
            "message": state.message,
            "maintenance": {
                "enabled": state.enabled,
                "message": state.message,
                "start_at": state.start_at,
                "estimated_end_at": state.estimated_end_at,
            },
        }

    def __call__(self, request):
        state = get_maintenance_state()
        if not state.enabled:
            return self.get_response(request)

        user = getattr(request, "user", None)
        is_authenticated = bool(user and getattr(user, "is_authenticated", False))
        is_staff = bool(user and (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)))
        path = request.path or "/"
        is_api = self._is_api_path(path)

        if is_authenticated and state.allow_staff_bypass and is_staff:
            return self.get_response(request)

        if is_authenticated and not (state.allow_staff_bypass and is_staff):
            username = getattr(user, "username", "-")
            user_id = getattr(user, "id", "-")
            ip = (request.META.get("HTTP_X_FORWARDED_FOR") or request.META.get("REMOTE_ADDR") or "-").split(",")[0].strip()
            session_key = getattr(request.session, "session_key", "")
            if session_key:
                mark_presence_inactive(session_key=session_key)
            logout(request)
            audit_logger.warning(
                f"action=maintenance_forced_logout status=success user_id={user_id} path={path}",
                extra={
                    "request_id": getattr(request, "request_id", "-"),
                    "user": username,
                    "ip": ip,
                },
            )
            if is_api:
                return JsonResponse(self._maintenance_payload(state), status=503)
            query = urlencode({"maintenance": "1", "forced": "1"})
            return redirect(f"/login/?{query}")

        if is_api:
            return JsonResponse(self._maintenance_payload(state), status=503)

        if self._is_allowed_public_path(path):
            return self.get_response(request)

        return self.get_response(request)
