import time
import uuid
import logging

logger = logging.getLogger("request")

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
            # audit metadata (dipakai oleh audit logger)
            user_obj = getattr(request, "user", None)
            username = getattr(user_obj, "username", "-") if user_obj and getattr(user_obj, "is_authenticated", False) else "-"
            user_id = getattr(user_obj, "id", "-") if user_obj and getattr(user_obj, "is_authenticated", False) else "-"
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
