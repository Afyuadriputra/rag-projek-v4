from django.contrib import admin
from django.contrib import messages
from django import forms
from django.urls import path
from django.urls import reverse
from django.template.response import TemplateResponse
from django.http import JsonResponse
from django.conf import settings
from django.contrib.auth import get_user_model
from django.shortcuts import redirect
from collections import deque
from pathlib import Path
from datetime import datetime
import shutil
import logging
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import (
    AcademicDocument,
    ChatHistory,
    ChatSession,
    PlannerHistory,
    UserQuota,
    LLMConfiguration,
    SystemSetting,
    UserLoginPresence,
    RagRequestMetric,
    SystemHealthSnapshot,
)
from .monitoring import (
    build_realtime_infra_payload,
    build_realtime_overview_payload,
    build_realtime_rag_payload,
)
from .presence import build_presence_summary, cleanup_stale_presence
from .system_settings import (
    get_admin_dashboard_state,
    get_concurrent_limit_state,
    get_maintenance_state,
    get_registration_limit_state,
)

try:
    from rangefilter.filters import DateTimeRangeFilter
except Exception:  # pragma: no cover
    DateTimeRangeFilter = None

try:
    from unfold.admin import ModelAdmin as BaseAdmin
except Exception:  # pragma: no cover
    BaseAdmin = admin.ModelAdmin

audit_logger = logging.getLogger("audit")


def _dt_filter(field: str):
    if DateTimeRangeFilter:
        return (field, DateTimeRangeFilter)
    return field


class UserRolePresenceFilter(admin.SimpleListFilter):
    title = "Role User"
    parameter_name = "role"

    def lookups(self, request, model_admin):
        return (("staff", "Staff"), ("user", "Non-Staff"))

    def queryset(self, request, queryset):
        value = self.value()
        if value == "staff":
            return queryset.filter(user__is_staff=True)
        if value == "user":
            return queryset.filter(user__is_staff=False, user__is_superuser=False)
        return queryset
# --- KONFIGURASI HEADER ADMIN ---
admin.site.site_header = "Academic AI Administration"
admin.site.site_title = "Academic Admin Portal"
admin.site.index_title = "Welcome to RAG System Management"

@admin.register(AcademicDocument)
class AcademicDocumentAdmin(BaseAdmin):
    # Kolom yang muncul di tabel daftar
    list_display = ('title', 'user', 'file_link', 'is_embedded', 'uploaded_at')
    
    # Filter sidebar di sebelah kanan
    list_filter = ('is_embedded', _dt_filter('uploaded_at'), 'user')
    
    # Kotak pencarian (bisa cari judul file atau nama user)
    search_fields = ('title', 'user__username', 'user__email')
    
    # Field yang tidak boleh diedit manual (karena otomatis)
    readonly_fields = ('uploaded_at',)

    # Mengelompokkan field saat edit detail
    fieldsets = (
        (None, {
            'fields': ('user', 'title', 'file')
        }),
        ('Status System', {
            'fields': ('is_embedded', 'uploaded_at'),
            'description': 'Status apakah file ini sudah diproses oleh AI Engine.'
        }),
    )

    # Helper untuk menampilkan link file yang bisa diklik
    def file_link(self, obj):
        if obj.file:
            return obj.file.name
        return "No File"
    file_link.short_description = "File Path"

@admin.register(ChatHistory)
class ChatHistoryAdmin(BaseAdmin):
    # Kolom yang muncul (kita potong pertanyaan biar gak kepanjangan)
    list_display = ('user', 'short_question', 'short_answer', 'timestamp')
    
    # Filter berdasarkan user dan waktu
    list_filter = (_dt_filter('timestamp'), 'user')
    
    # Search bar (bisa cari isi chattingan)
    search_fields = ('question', 'answer', 'user__username')
    
    # Readonly karena history chat tidak seharusnya diedit admin
    readonly_fields = ('user', 'question', 'answer', 'timestamp')

    # Helper untuk memotong teks pertanyaan yang panjang
    def short_question(self, obj):
        return obj.question[:50] + "..." if len(obj.question) > 50 else obj.question
    short_question.short_description = "Question"

    # Helper untuk memotong teks jawaban yang panjang
    def short_answer(self, obj):
        return obj.answer[:50] + "..." if len(obj.answer) > 50 else obj.answer
    short_answer.short_description = "AI Answer"


@admin.register(ChatSession)
class ChatSessionAdmin(BaseAdmin):
    list_display = ("id", "user", "title", "created_at", "updated_at")
    list_filter = ("user", _dt_filter("created_at"), _dt_filter("updated_at"))
    search_fields = ("title", "user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(PlannerHistory)
class PlannerHistoryAdmin(BaseAdmin):
    list_display = ("user", "session", "event_type", "planner_step", "short_text", "created_at")
    list_filter = ("event_type", "planner_step", _dt_filter("created_at"))
    search_fields = ("user__username", "text", "option_label")
    readonly_fields = (
        "user",
        "session",
        "event_type",
        "planner_step",
        "text",
        "option_id",
        "option_label",
        "payload",
        "created_at",
    )

    def short_text(self, obj):
        return obj.text[:80] + "..." if len(obj.text) > 80 else obj.text
    short_text.short_description = "Summary"


@admin.register(UserQuota)
class UserQuotaAdmin(BaseAdmin):
    list_display = ("user", "quota_bytes", "updated_at")
    search_fields = ("user__username", "user__email")
    list_filter = (_dt_filter("updated_at"),)
    form = None

    def save_model(self, request, obj, form, change):
        old_quota = None
        if change and obj.pk:
            try:
                old_quota = UserQuota.objects.get(pk=obj.pk).quota_bytes
            except Exception:
                old_quota = None
        super().save_model(request, obj, form, change)
        action = "quota_update" if change else "quota_create"
        audit_logger.info(
            f"action={action} target_user={obj.user.username} target_user_id={obj.user.id} old_quota={old_quota} new_quota={obj.quota_bytes}",
            extra=getattr(request, "audit", {}),
        )


class UserQuotaForm(forms.ModelForm):
    quota_mb = forms.IntegerField(
        required=False,
        min_value=1,
        label="Quota (MB)",
        help_text="Masukkan kuota dalam MB. Contoh: 10 untuk 10MB."
    )

    class Meta:
        model = UserQuota
        fields = ("user", "quota_mb")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.quota_bytes:
            self.fields["quota_mb"].initial = int(self.instance.quota_bytes / (1024 * 1024))

    def save(self, commit=True):
        obj = super().save(commit=False)
        quota_mb = self.cleaned_data.get("quota_mb")
        if quota_mb:
            obj.quota_bytes = int(quota_mb) * 1024 * 1024
        if commit:
            obj.save()
        return obj


UserQuotaAdmin.form = UserQuotaForm


@admin.register(UserLoginPresence)
class UserLoginPresenceAdmin(BaseAdmin):
    list_display = (
        "user",
        "session_key_short",
        "is_active",
        "ip_address",
        "logged_in_at",
        "last_seen_at",
        "logged_out_at",
    )
    list_filter = ("is_active", UserRolePresenceFilter, _dt_filter("logged_in_at"), _dt_filter("last_seen_at"))
    search_fields = ("user__username", "session_key", "ip_address", "user_agent")
    readonly_fields = (
        "user",
        "session_key",
        "ip_address",
        "user_agent",
        "logged_in_at",
        "last_seen_at",
        "logged_out_at",
        "is_active",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def session_key_short(self, obj):
        return f"{obj.session_key[:12]}..." if obj.session_key else "-"

    session_key_short.short_description = "Session"

    actions = ("mark_selected_inactive",)

    @admin.action(description="Tandai session terpilih sebagai non-aktif")
    def mark_selected_inactive(self, request, queryset):
        now = timezone.now()
        updated = queryset.filter(is_active=True).update(is_active=False, logged_out_at=now)
        self.message_user(request, f"{updated} session berhasil dinonaktifkan.", level=messages.SUCCESS)


@admin.register(RagRequestMetric)
class RagRequestMetricAdmin(BaseAdmin):
    list_display = (
        "created_at",
        "request_id",
        "username",
        "mode",
        "retrieval_ms",
        "llm_time_ms",
        "fallback_used",
        "source_count",
        "status_code",
    )
    list_filter = (
        "mode",
        "fallback_used",
        "status_code",
        _dt_filter("created_at"),
    )
    search_fields = ("request_id", "user__username", "llm_model")
    readonly_fields = (
        "request_id",
        "user",
        "mode",
        "query_len",
        "dense_hits",
        "bm25_hits",
        "final_docs",
        "retrieval_ms",
        "rerank_ms",
        "llm_model",
        "llm_time_ms",
        "fallback_used",
        "source_count",
        "status_code",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def username(self, obj):
        return obj.user.username if obj.user_id else "-"

    username.short_description = "User"


@admin.register(SystemHealthSnapshot)
class SystemHealthSnapshotAdmin(BaseAdmin):
    list_display = (
        "captured_at",
        "cpu_percent",
        "memory_percent",
        "disk_percent",
        "load_1m",
        "active_sessions",
        "online_users_non_staff",
    )
    list_filter = (_dt_filter("captured_at"),)
    readonly_fields = (
        "captured_at",
        "cpu_percent",
        "memory_percent",
        "disk_percent",
        "load_1m",
        "active_sessions",
        "online_users_non_staff",
        "notes",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class LLMConfigurationAdminForm(forms.ModelForm):
    openrouter_api_key = forms.CharField(
        required=False,
        label="OpenRouter API Key",
        widget=forms.PasswordInput(render_value=True),
        help_text="Gunakan tombol mata untuk show/hide API key. Kosongkan jika ingin fallback ke OPENROUTER_API_KEY dari environment.",
    )
    openrouter_backup_models = forms.CharField(
        required=False,
        label="OpenRouter Backup Models",
        widget=forms.Textarea(attrs={"rows": 6, "style": "font-family: monospace;"}),
        help_text="Satu model per baris (atau pisahkan dengan koma). Dipakai sebagai fallback setelah model utama.",
    )

    class Meta:
        model = LLMConfiguration
        fields = (
            "name",
            "is_active",
            "openrouter_api_key",
            "openrouter_model",
            "openrouter_backup_models",
            "openrouter_timeout",
            "openrouter_max_retries",
            "openrouter_temperature",
        )


@admin.register(LLMConfiguration)
class LLMConfigurationAdmin(BaseAdmin):
    form = LLMConfigurationAdminForm
    list_display = (
        "id",
        "name",
        "is_active",
        "masked_api_key",
        "openrouter_model",
        "backup_count",
        "openrouter_timeout",
        "openrouter_max_retries",
        "openrouter_temperature",
        "updated_at",
    )
    list_filter = ("is_active", _dt_filter("updated_at"))
    search_fields = ("name", "openrouter_model")
    readonly_fields = ("updated_at",)

    fieldsets = (
        ("OpenRouter", {
            "fields": (
                "name",
                "is_active",
                "openrouter_api_key",
                "openrouter_model",
                "openrouter_backup_models",
                "openrouter_timeout",
                "openrouter_max_retries",
                "openrouter_temperature",
                "updated_at",
            )
        }),
    )

    def masked_api_key(self, obj):
        raw = (obj.openrouter_api_key or "").strip()
        if not raw:
            return "(fallback .env)"
        if len(raw) <= 8:
            return "********"
        return f"{raw[:4]}...{raw[-4:]}"
    masked_api_key.short_description = "API Key"

    def backup_count(self, obj):
        raw = (obj.openrouter_backup_models or "").strip()
        if not raw:
            return 0
        parts = [p.strip() for p in raw.replace("\r", "\n").replace(",", "\n").split("\n")]
        return len([p for p in parts if p])
    backup_count.short_description = "Backup #"

    class Media:
        js = ("admin/js/api_key_toggle.js",)


class SystemSettingAdminForm(forms.ModelForm):
    class Meta:
        model = SystemSetting
        fields = "__all__"

    def clean_admin_realtime_poll_seconds(self):
        value = int(self.cleaned_data.get("admin_realtime_poll_seconds") or 5)
        if value < 3:
            raise ValidationError("Interval realtime minimal 3 detik.")
        return value

    def clean_admin_realtime_max_rows(self):
        value = int(self.cleaned_data.get("admin_realtime_max_rows") or 100)
        if value < 10 or value > 500:
            raise ValidationError("Maksimal baris harus di rentang 10 sampai 500.")
        return value


@admin.register(SystemSetting)
class SystemSettingAdmin(BaseAdmin):
    form = SystemSettingAdminForm
    list_display = (
        "id",
        "registration_enabled",
        "registration_limit_enabled",
        "concurrent_login_limit_enabled",
        "admin_realtime_poll_seconds",
        "maintenance_enabled",
        "allow_staff_bypass",
        "updated_at",
    )
    readonly_fields = ("updated_at",)
    fieldsets = (
        ("Authentication Feature Toggle", {
            "fields": ("registration_enabled", "updated_at"),
            "description": "Aktif/nonaktifkan fitur pendaftaran user baru (register).",
        }),
        ("Maintenance Mode", {
            "fields": (
                "maintenance_enabled",
                "maintenance_message",
                "maintenance_start_at",
                "maintenance_estimated_end_at",
                "allow_staff_bypass",
            ),
            "description": (
                "Saat aktif, user non-staff akan dipaksa logout dan endpoint auth/API menampilkan "
                "pesan maintenance. Staff/superuser bisa bypass jika opsi bypass aktif."
            ),
        }),
        ("Capacity Control", {
            "fields": (
                "registration_limit_enabled",
                "max_registered_users",
                "registration_limit_message",
                "concurrent_login_limit_enabled",
                "max_concurrent_logins",
                "concurrent_limit_message",
                "staff_bypass_concurrent_limit",
            ),
            "description": (
                "Atur kapasitas tahap uji coba: batas total user non-staff terdaftar dan batas "
                "jumlah user online bersamaan."
            ),
        }),
        ("Admin Realtime Dashboard", {
            "fields": (
                "admin_realtime_poll_seconds",
                "admin_realtime_max_rows",
                "admin_metrics_retention_days",
                "admin_dashboard_locale",
            ),
            "description": (
                "Konfigurasi monitoring realtime command center. "
                "Disarankan polling 5 detik untuk beban server yang seimbang."
            ),
        }),
    )

    def has_add_permission(self, request):
        if SystemSetting.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False


def _tail_file(path: Path, lines: int = 200) -> list[str]:
    if not path.exists() or not path.is_file():
        return [f"[file tidak ditemukan] {path}"]
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            return list(deque(f, maxlen=lines))
    except Exception as e:
        return [f"[gagal membaca file] {path} err={e!r}"]


def _build_logs_payload(lines: int = 300) -> dict:
    log_dir = Path(settings.BASE_DIR) / "logs"
    app_log_path = log_dir / "app.log"
    audit_log_path = log_dir / "audit.log"
    app_lines = _tail_file(app_log_path, lines=lines)
    audit_lines = _tail_file(audit_log_path, lines=lines)
    return {
        "app_log_path": str(app_log_path),
        "audit_log_path": str(audit_log_path),
        "app_log_size_kb": round((app_log_path.stat().st_size / 1024), 2) if app_log_path.exists() else 0,
        "audit_log_size_kb": round((audit_log_path.stat().st_size / 1024), 2) if audit_log_path.exists() else 0,
        "app_log_lines": app_lines,
        "audit_log_lines": audit_lines,
        "app_log_text": "".join(app_lines),
        "audit_log_text": "".join(audit_lines),
    }


def _resolve_log_path(log_type: str) -> tuple[str, Path]:
    log_dir = Path(settings.BASE_DIR) / "logs"
    if log_type == "audit":
        return "audit", log_dir / "audit.log"
    return "app", log_dir / "app.log"


def _build_single_log_payload(log_type: str, lines: int = 300) -> dict:
    log_type, log_path = _resolve_log_path(log_type)
    title = "Audit Log" if log_type == "audit" else "App Log"

    log_lines = _tail_file(log_path, lines=lines)
    return {
        "log_type": log_type,
        "log_title": title,
        "log_path": str(log_path),
        "log_size_kb": round((log_path.stat().st_size / 1024), 2) if log_path.exists() else 0,
        "log_lines": log_lines,
        "log_text": "".join(log_lines),
    }


def _build_dashboard_metrics() -> dict:
    User = get_user_model()
    cleanup_stale_presence()

    total_users = User.objects.count()
    registered_non_staff_count = User.objects.filter(is_staff=False, is_superuser=False).count()
    total_docs = AcademicDocument.objects.count()
    embedded_docs = AcademicDocument.objects.filter(is_embedded=True).count()
    total_sessions = ChatSession.objects.count()
    total_messages = ChatHistory.objects.count()
    total_llm_configs = LLMConfiguration.objects.count()
    active_llm_configs = LLMConfiguration.objects.filter(is_active=True).count()
    latest_doc = AcademicDocument.objects.order_by("-uploaded_at").first()
    latest_chat = ChatHistory.objects.order_by("-timestamp").first()
    latest_cfg = LLMConfiguration.objects.order_by("-updated_at").first()

    maintenance = get_maintenance_state()
    maintenance_message = (maintenance.message or "").strip()
    registration_limit = get_registration_limit_state()
    concurrent_limit = get_concurrent_limit_state()
    admin_dash = get_admin_dashboard_state()
    presence = build_presence_summary(limit=admin_dash.max_rows)
    overview = build_realtime_overview_payload().get("summary", {})
    rag_live = build_realtime_rag_payload(limit=min(20, admin_dash.max_rows))
    infra_live = build_realtime_infra_payload(limit=min(20, admin_dash.max_rows))

    reg_limit = max(registration_limit.max_registered_users, 1)
    conc_limit = max(concurrent_limit.max_concurrent_logins, 1)

    reg_pct = int(min((registered_non_staff_count / reg_limit) * 100, 100))
    conc_pct = int(min((presence.active_online_non_staff_count / conc_limit) * 100, 100))

    def _cap_status(pct: int) -> str:
        if pct >= 100:
            return "FULL"
        if pct >= 80:
            return "NEAR LIMIT"
        return "OPEN"

    return {
        "kpi_total_users": total_users,
        "kpi_registered_non_staff_count": registered_non_staff_count,
        "kpi_total_docs": total_docs,
        "kpi_embedded_docs": embedded_docs,
        "kpi_total_sessions": total_sessions,
        "kpi_total_messages": total_messages,
        "kpi_total_llm_configs": total_llm_configs,
        "kpi_active_llm_configs": active_llm_configs,
        "kpi_latest_doc_time": getattr(latest_doc, "uploaded_at", None),
        "kpi_latest_chat_time": getattr(latest_chat, "timestamp", None),
        "kpi_latest_cfg_time": getattr(latest_cfg, "updated_at", None),
        "kpi_maintenance_enabled": maintenance.enabled,
        "kpi_maintenance_message": maintenance_message,
        "kpi_maintenance_start_at": maintenance.start_at,
        "kpi_maintenance_estimated_end_at": maintenance.estimated_end_at,
        "kpi_registration_limit_enabled": registration_limit.enabled,
        "kpi_registered_limit": registration_limit.max_registered_users,
        "kpi_registered_usage_pct": reg_pct,
        "kpi_registered_capacity_status": _cap_status(reg_pct),
        "kpi_concurrent_limit_enabled": concurrent_limit.enabled,
        "kpi_concurrent_limit": concurrent_limit.max_concurrent_logins,
        "kpi_active_online_non_staff_count": presence.active_online_non_staff_count,
        "kpi_concurrent_usage_pct": conc_pct,
        "kpi_concurrent_capacity_status": _cap_status(conc_pct),
        "kpi_online_users": presence.online_users,
        "kpi_recent_registered_users": presence.recent_registered_users,
        "kpi_admin_poll_seconds": admin_dash.poll_seconds,
        "kpi_alert_state": overview.get("alert_state", "Normal"),
        "kpi_rag_error_rate_pct": overview.get("rag_error_rate_pct", 0),
        "kpi_rag_fallback_rate_pct": overview.get("rag_fallback_rate_pct", 0),
        "kpi_avg_retrieval_ms": overview.get("avg_retrieval_ms", 0),
        "kpi_avg_llm_ms": overview.get("avg_llm_ms", 0),
        "kpi_cpu_percent": overview.get("cpu_percent", 0),
        "kpi_memory_percent": overview.get("memory_percent", 0),
        "kpi_disk_percent": overview.get("disk_percent", 0),
        "kpi_rag_events": rag_live.get("events", []),
        "kpi_rag_p95_retrieval_ms": rag_live.get("p95_retrieval_ms", 0),
        "kpi_infra_snapshots": infra_live.get("snapshots", []),
    }


def system_logs_view(request):
    context = {
        **admin.site.each_context(request),
        "title": "System Logs",
        "app_logs_url": reverse("admin:system_logs_detail", kwargs={"log_type": "app"}),
        "audit_logs_url": reverse("admin:system_logs_detail", kwargs={"log_type": "audit"}),
    }
    return TemplateResponse(request, "admin/system_logs.html", context)


def system_logs_tail_api(request):
    payload = _build_logs_payload(lines=300)
    return JsonResponse(payload)


def realtime_users_api(request):
    cleanup_stale_presence()
    admin_dash = get_admin_dashboard_state()
    registration_limit = get_registration_limit_state()
    concurrent_limit = get_concurrent_limit_state()
    presence = build_presence_summary(limit=admin_dash.max_rows)
    registered_non_staff_count = get_user_model().objects.filter(is_staff=False, is_superuser=False).count()

    payload = {
        "summary": {
            "registered_non_staff_count": registered_non_staff_count,
            "registered_limit_enabled": registration_limit.enabled,
            "registered_limit": registration_limit.max_registered_users,
            "active_online_non_staff_count": presence.active_online_non_staff_count,
            "concurrent_limit_enabled": concurrent_limit.enabled,
            "concurrent_limit": concurrent_limit.max_concurrent_logins,
        },
        "online_users": presence.online_users,
        "recent_registered_users": presence.recent_registered_users,
    }
    return JsonResponse(payload)


def realtime_overview_api(request):
    payload = build_realtime_overview_payload()
    return JsonResponse(payload)


def realtime_rag_api(request):
    max_rows = get_admin_dashboard_state().max_rows
    payload = build_realtime_rag_payload(limit=min(50, max_rows))
    return JsonResponse(payload)


def realtime_infra_api(request):
    max_rows = get_admin_dashboard_state().max_rows
    payload = build_realtime_infra_payload(limit=min(30, max_rows))
    return JsonResponse(payload)


def system_log_detail_view(request, log_type: str):
    payload = _build_single_log_payload(log_type=log_type, lines=300)
    context = {
        **admin.site.each_context(request),
        "title": payload["log_title"],
        **payload,
        "app_logs_url": reverse("admin:system_logs_detail", kwargs={"log_type": "app"}),
        "audit_logs_url": reverse("admin:system_logs_detail", kwargs={"log_type": "audit"}),
    }
    return TemplateResponse(request, "admin/system_log_detail.html", context)


def system_log_detail_tail_api(request, log_type: str):
    payload = _build_single_log_payload(log_type=log_type, lines=300)
    return JsonResponse(payload)


def system_log_backup_view(request, log_type: str):
    if request.method != "POST":
        return redirect(reverse("admin:system_logs_detail", kwargs={"log_type": log_type}))

    log_type, log_path = _resolve_log_path(log_type)
    backup_dir = log_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"{log_type}-{stamp}.log"

    try:
        if log_path.exists():
            shutil.copy2(log_path, backup_path)
            messages.success(request, f"Backup berhasil: {backup_path.name}")
        else:
            backup_path.write_text("", encoding="utf-8")
            messages.warning(request, f"File log belum ada. Backup kosong dibuat: {backup_path.name}")
    except Exception as e:
        messages.error(request, f"Gagal backup log: {e!r}")

    return redirect(reverse("admin:system_logs_detail", kwargs={"log_type": log_type}))


def system_log_clear_view(request, log_type: str):
    if request.method != "POST":
        return redirect(reverse("admin:system_logs_detail", kwargs={"log_type": log_type}))

    log_type, log_path = _resolve_log_path(log_type)

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # truncate file -> log start fresh
        with log_path.open("w", encoding="utf-8"):
            pass
        messages.success(request, f"{log_type}.log berhasil di-reset.")
    except Exception as e:
        messages.error(request, f"Gagal reset log: {e!r}")

    return redirect(reverse("admin:system_logs_detail", kwargs={"log_type": log_type}))


_original_get_urls = admin.site.get_urls


def _custom_admin_get_urls():
    urls = _original_get_urls()
    custom_urls = [
        path(
            "system-logs/",
            admin.site.admin_view(system_logs_view),
            name="system_logs",
        ),
        path(
            "system-logs/tail/",
            admin.site.admin_view(system_logs_tail_api),
            name="system_logs_tail",
        ),
        path(
            "realtime-users/",
            admin.site.admin_view(realtime_users_api),
            name="realtime_users",
        ),
        path(
            "realtime-overview/",
            admin.site.admin_view(realtime_overview_api),
            name="realtime_overview",
        ),
        path(
            "realtime-rag/",
            admin.site.admin_view(realtime_rag_api),
            name="realtime_rag",
        ),
        path(
            "realtime-infra/",
            admin.site.admin_view(realtime_infra_api),
            name="realtime_infra",
        ),
        path(
            "system-logs/<str:log_type>/",
            admin.site.admin_view(system_log_detail_view),
            name="system_logs_detail",
        ),
        path(
            "system-logs/<str:log_type>/tail/",
            admin.site.admin_view(system_log_detail_tail_api),
            name="system_logs_detail_tail",
        ),
        path(
            "system-logs/<str:log_type>/backup/",
            admin.site.admin_view(system_log_backup_view),
            name="system_logs_backup",
        ),
        path(
            "system-logs/<str:log_type>/clear/",
            admin.site.admin_view(system_log_clear_view),
            name="system_logs_clear",
        ),
    ]
    return custom_urls + urls


admin.site.get_urls = _custom_admin_get_urls


_original_admin_index = admin.site.index


def _system_logs_url() -> str:
    return reverse("admin:system_logs")


def _custom_admin_index(request, extra_context=None):
    payload = _build_logs_payload(lines=120)
    metrics = _build_dashboard_metrics()
    context = dict(extra_context or {})
    context.update(payload)
    context.update(metrics)
    context["system_logs_url"] = _system_logs_url()
    context["quick_docs_url"] = "/admin/core/academicdocument/"
    context["quick_chats_url"] = "/admin/core/chathistory/"
    context["quick_sessions_url"] = "/admin/core/chatsession/"
    context["quick_llm_url"] = "/admin/core/llmconfiguration/"
    context["quick_presence_url"] = "/admin/core/userloginpresence/"
    context["quick_rag_metrics_url"] = "/admin/core/ragrequestmetric/"
    context["quick_health_url"] = "/admin/core/systemhealthsnapshot/"
    return _original_admin_index(request, extra_context=context)


admin.site.index = _custom_admin_index


_original_each_context = admin.site.each_context


def _custom_each_context(request):
    context = _original_each_context(request)
    context["system_logs_url"] = _system_logs_url()
    context["system_logs_button_label"] = "System Logs"
    return context


admin.site.each_context = _custom_each_context
