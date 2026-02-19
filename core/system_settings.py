from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models import SystemSetting


DEFAULT_MAINTENANCE_MESSAGE = (
    "Kami sedang melakukan pemeliharaan terjadwal untuk meningkatkan kualitas layanan. "
    "Layanan login sementara tidak tersedia. Silakan coba kembali beberapa saat lagi."
)

DEFAULT_REGISTRATION_LIMIT_MESSAGE = (
    "Pendaftaran akun baru sementara ditutup karena kuota pengguna tahap uji coba telah penuh."
)

DEFAULT_CONCURRENT_LIMIT_MESSAGE = (
    "Sistem sedang mencapai batas pengguna aktif bersamaan. "
    "Silakan coba login kembali beberapa saat lagi."
)


@dataclass(frozen=True)
class MaintenanceState:
    enabled: bool
    message: str
    start_at: Optional[str]
    estimated_end_at: Optional[str]
    allow_staff_bypass: bool


@dataclass(frozen=True)
class RegistrationLimitState:
    enabled: bool
    max_registered_users: int
    message: str


@dataclass(frozen=True)
class ConcurrentLimitState:
    enabled: bool
    max_concurrent_logins: int
    message: str
    staff_bypass: bool


@dataclass(frozen=True)
class AdminDashboardState:
    poll_seconds: int
    max_rows: int
    retention_days: int
    locale: str


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt is not None else None


def _get_cfg() -> SystemSetting | None:
    try:
        return SystemSetting.objects.first()
    except Exception:
        return None


def get_maintenance_state() -> MaintenanceState:
    cfg = _get_cfg()
    if cfg is None:
        return MaintenanceState(
            enabled=False,
            message=DEFAULT_MAINTENANCE_MESSAGE,
            start_at=None,
            estimated_end_at=None,
            allow_staff_bypass=True,
        )

    msg = cfg.get_effective_maintenance_message() or DEFAULT_MAINTENANCE_MESSAGE
    return MaintenanceState(
        enabled=bool(cfg.maintenance_enabled),
        message=msg,
        start_at=_iso(cfg.maintenance_start_at),
        estimated_end_at=_iso(cfg.maintenance_estimated_end_at),
        allow_staff_bypass=bool(cfg.allow_staff_bypass),
    )


def get_registration_enabled() -> bool:
    cfg = _get_cfg()
    if cfg is None:
        return True
    return bool(cfg.registration_enabled)


def get_registration_limit_state() -> RegistrationLimitState:
    cfg = _get_cfg()
    if cfg is None:
        return RegistrationLimitState(
            enabled=False,
            max_registered_users=1000,
            message=DEFAULT_REGISTRATION_LIMIT_MESSAGE,
        )

    return RegistrationLimitState(
        enabled=bool(cfg.registration_limit_enabled),
        max_registered_users=max(int(cfg.max_registered_users or 0), 1),
        message=cfg.get_effective_registration_limit_message() or DEFAULT_REGISTRATION_LIMIT_MESSAGE,
    )


def get_concurrent_limit_state() -> ConcurrentLimitState:
    cfg = _get_cfg()
    if cfg is None:
        return ConcurrentLimitState(
            enabled=False,
            max_concurrent_logins=300,
            message=DEFAULT_CONCURRENT_LIMIT_MESSAGE,
            staff_bypass=True,
        )

    return ConcurrentLimitState(
        enabled=bool(cfg.concurrent_login_limit_enabled),
        max_concurrent_logins=max(int(cfg.max_concurrent_logins or 0), 1),
        message=cfg.get_effective_concurrent_limit_message() or DEFAULT_CONCURRENT_LIMIT_MESSAGE,
        staff_bypass=bool(cfg.staff_bypass_concurrent_limit),
    )


def get_admin_dashboard_state() -> AdminDashboardState:
    cfg = _get_cfg()
    if cfg is None:
        return AdminDashboardState(
            poll_seconds=5,
            max_rows=100,
            retention_days=7,
            locale="id",
        )

    poll_seconds = max(int(getattr(cfg, "admin_realtime_poll_seconds", 5) or 5), 3)
    max_rows = max(min(int(getattr(cfg, "admin_realtime_max_rows", 100) or 100), 500), 10)
    retention_days = max(int(getattr(cfg, "admin_metrics_retention_days", 7) or 7), 1)
    locale = (getattr(cfg, "admin_dashboard_locale", "id") or "id").strip() or "id"
    return AdminDashboardState(
        poll_seconds=poll_seconds,
        max_rows=max_rows,
        retention_days=retention_days,
        locale=locale,
    )
