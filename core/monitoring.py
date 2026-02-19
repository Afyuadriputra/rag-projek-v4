from __future__ import annotations

import random
import time
from datetime import timedelta
from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.db.models import Avg, Count, Q
from django.utils import timezone

from .models import RagRequestMetric, SystemHealthSnapshot
from .presence import count_active_online_non_staff_users
from .system_settings import get_admin_dashboard_state, get_concurrent_limit_state, get_registration_limit_state

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None


SNAPSHOT_THROTTLE_SECONDS = 60
SUMMARY_CACHE_SECONDS = 5


def _cache_get_or_set(key: str, builder):
    hit = cache.get(key)
    if hit is not None:
        return hit
    data = builder()
    cache.set(key, data, SUMMARY_CACHE_SECONDS)
    return data


def _collect_system_health_now() -> dict[str, float]:
    if psutil is None:
        return {
            "cpu_percent": 0.0,
            "memory_percent": 0.0,
            "disk_percent": 0.0,
            "load_1m": 0.0,
        }

    load_1m = 0.0
    try:
        load_1m = float(psutil.getloadavg()[0])
    except Exception:
        load_1m = 0.0

    try:
        disk_percent = float(psutil.disk_usage("/").percent)
    except Exception:
        disk_percent = 0.0

    return {
        "cpu_percent": float(psutil.cpu_percent(interval=0.0)),
        "memory_percent": float(psutil.virtual_memory().percent),
        "disk_percent": disk_percent,
        "load_1m": load_1m,
    }


def maybe_collect_system_snapshot(chance: float = 0.08) -> bool:
    if random.random() > chance:
        return False

    lock_key = "monitoring:snapshot:last_ts"
    now_ts = int(time.time())
    last_ts = int(cache.get(lock_key) or 0)
    if now_ts - last_ts < SNAPSHOT_THROTTLE_SECONDS:
        return False

    health = _collect_system_health_now()
    try:
        snapshot = SystemHealthSnapshot(
            cpu_percent=health["cpu_percent"],
            memory_percent=health["memory_percent"],
            disk_percent=health["disk_percent"],
            load_1m=health["load_1m"],
            active_sessions=Session.objects.count(),
            online_users_non_staff=count_active_online_non_staff_users(),
        )
        snapshot.save()
    except Exception:
        return False
    cache.set(lock_key, now_ts, SNAPSHOT_THROTTLE_SECONDS)
    return True


def maybe_cleanup_monitoring_retention(chance: float = 0.01) -> int:
    if random.random() > chance:
        return 0
    try:
        state = get_admin_dashboard_state()
        threshold = timezone.now() - timedelta(days=state.retention_days)
        a = SystemHealthSnapshot.objects.filter(captured_at__lt=threshold).delete()[0]
        b = RagRequestMetric.objects.filter(created_at__lt=threshold).delete()[0]
        return int(a + b)
    except Exception:
        return 0


def record_rag_metric(
    *,
    request_id: str,
    user_id: int | None,
    mode: str,
    query_len: int,
    dense_hits: int,
    bm25_hits: int,
    final_docs: int,
    retrieval_ms: int,
    rerank_ms: int,
    llm_model: str,
    llm_time_ms: int,
    fallback_used: bool,
    source_count: int,
    status_code: int,
) -> None:
    # write path dibuat ringan dan fail-safe supaya tidak mengganggu request utama
    try:
        user = None
        if user_id:
            user = get_user_model().objects.filter(id=user_id).only("id").first()
        RagRequestMetric.objects.create(
            request_id=(request_id or "-")[:64],
            user=user,
            mode=(mode or "dense")[:32],
            query_len=max(int(query_len or 0), 0),
            dense_hits=max(int(dense_hits or 0), 0),
            bm25_hits=max(int(bm25_hits or 0), 0),
            final_docs=max(int(final_docs or 0), 0),
            retrieval_ms=max(int(retrieval_ms or 0), 0),
            rerank_ms=max(int(rerank_ms or 0), 0),
            llm_model=(llm_model or "")[:255],
            llm_time_ms=max(int(llm_time_ms or 0), 0),
            fallback_used=bool(fallback_used),
            source_count=max(int(source_count or 0), 0),
            status_code=max(int(status_code or 0), 0),
        )
    except Exception:
        return


def _capacity_status(usage_pct: int) -> str:
    if usage_pct >= 100:
        return "FULL"
    if usage_pct >= 80:
        return "NEAR LIMIT"
    return "OPEN"


def build_realtime_overview_payload() -> dict[str, Any]:
    state = get_admin_dashboard_state()

    def _builder():
        maybe_collect_system_snapshot(chance=1.0)

        User = get_user_model()
        registration_limit = get_registration_limit_state()
        concurrent_limit = get_concurrent_limit_state()
        registered_non_staff_count = User.objects.filter(is_staff=False, is_superuser=False).count()
        active_online_non_staff_count = count_active_online_non_staff_users()

        reg_limit = max(registration_limit.max_registered_users, 1)
        conc_limit = max(concurrent_limit.max_concurrent_logins, 1)
        reg_pct = int(min((registered_non_staff_count / reg_limit) * 100, 100))
        conc_pct = int(min((active_online_non_staff_count / conc_limit) * 100, 100))

        now = timezone.now()
        rag_window = now - timedelta(minutes=10)
        try:
            rag_agg = RagRequestMetric.objects.filter(created_at__gte=rag_window).aggregate(
                total=Count("id"),
                fallback=Count("id", filter=Q(fallback_used=True)),
                errors=Count("id", filter=Q(status_code__gte=500)),
                avg_retrieval=Avg("retrieval_ms"),
                avg_llm=Avg("llm_time_ms"),
            )
        except Exception:
            rag_agg = {"total": 0, "fallback": 0, "errors": 0, "avg_retrieval": 0, "avg_llm": 0}
        total_req = int(rag_agg["total"] or 0)
        fallback_rate = int(((rag_agg["fallback"] or 0) / total_req) * 100) if total_req else 0
        error_rate = int(((rag_agg["errors"] or 0) / total_req) * 100) if total_req else 0

        try:
            latest_snapshot = SystemHealthSnapshot.objects.only(
                "cpu_percent",
                "memory_percent",
                "disk_percent",
                "load_1m",
                "captured_at",
            ).order_by("-captured_at").first()
        except Exception:
            latest_snapshot = None

        cpu = float(getattr(latest_snapshot, "cpu_percent", 0.0) or 0.0)
        mem = float(getattr(latest_snapshot, "memory_percent", 0.0) or 0.0)
        disk = float(getattr(latest_snapshot, "disk_percent", 0.0) or 0.0)

        alert_state = "Normal"
        if max(cpu, mem, disk) >= 90 or error_rate >= 20:
            alert_state = "Kritis"
        elif max(cpu, mem, disk) >= 75 or error_rate >= 10:
            alert_state = "Waspada"

        return {
            "poll_seconds": state.poll_seconds,
            "summary": {
                "registered_non_staff_count": registered_non_staff_count,
                "registered_limit_enabled": registration_limit.enabled,
                "registered_limit": reg_limit,
                "registered_usage_pct": reg_pct,
                "registered_capacity_status": _capacity_status(reg_pct),
                "active_online_non_staff_count": active_online_non_staff_count,
                "concurrent_limit_enabled": concurrent_limit.enabled,
                "concurrent_limit": conc_limit,
                "concurrent_usage_pct": conc_pct,
                "concurrent_capacity_status": _capacity_status(conc_pct),
                "rag_error_rate_pct": error_rate,
                "rag_fallback_rate_pct": fallback_rate,
                "avg_retrieval_ms": int(rag_agg["avg_retrieval"] or 0),
                "avg_llm_ms": int(rag_agg["avg_llm"] or 0),
                "rpm_10m": total_req,
                "cpu_percent": round(cpu, 1),
                "memory_percent": round(mem, 1),
                "disk_percent": round(disk, 1),
                "alert_state": alert_state,
            },
        }

    return _cache_get_or_set("monitoring:overview", _builder)


def build_realtime_rag_payload(limit: int = 50) -> dict[str, Any]:
    state = get_admin_dashboard_state()
    limit = max(min(int(limit), state.max_rows), 1)

    def _builder():
        try:
            rows = (
                RagRequestMetric.objects.select_related("user")
                .only(
                    "request_id",
                    "user__username",
                    "mode",
                    "retrieval_ms",
                    "llm_time_ms",
                    "fallback_used",
                    "status_code",
                    "source_count",
                    "llm_model",
                    "created_at",
                )
                .order_by("-created_at")[:limit]
            )
        except Exception:
            rows = []
        items = [
            {
                "request_id": row.request_id,
                "username": row.user.username if row.user_id else "-",
                "mode": row.mode,
                "retrieval_ms": row.retrieval_ms,
                "llm_time_ms": row.llm_time_ms,
                "fallback_used": row.fallback_used,
                "status_code": row.status_code,
                "source_count": row.source_count,
                "llm_model": row.llm_model,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
        p95_retrieval = 0
        if items:
            sorted_ms = sorted(x["retrieval_ms"] for x in items)
            idx = min(int(len(sorted_ms) * 0.95), len(sorted_ms) - 1)
            p95_retrieval = int(sorted_ms[idx])

        return {"events": items, "p95_retrieval_ms": p95_retrieval}

    return _cache_get_or_set("monitoring:rag", _builder)


def build_realtime_infra_payload(limit: int = 20) -> dict[str, Any]:
    state = get_admin_dashboard_state()
    limit = max(min(int(limit), state.max_rows), 1)

    def _builder():
        maybe_collect_system_snapshot(chance=1.0)
        try:
            rows = SystemHealthSnapshot.objects.only(
                "captured_at",
                "cpu_percent",
                "memory_percent",
                "disk_percent",
                "load_1m",
                "active_sessions",
                "online_users_non_staff",
            ).order_by("-captured_at")[:limit]
        except Exception:
            rows = []
        return {
            "snapshots": [
                {
                    "captured_at": row.captured_at.isoformat() if row.captured_at else None,
                    "cpu_percent": round(float(row.cpu_percent or 0), 1),
                    "memory_percent": round(float(row.memory_percent or 0), 1),
                    "disk_percent": round(float(row.disk_percent or 0), 1),
                    "load_1m": round(float(row.load_1m or 0), 2),
                    "active_sessions": int(row.active_sessions or 0),
                    "online_users_non_staff": int(row.online_users_non_staff or 0),
                }
                for row in rows
            ]
        }

    return _cache_get_or_set("monitoring:infra", _builder)
