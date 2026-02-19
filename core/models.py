from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import os


class AcademicDocument(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=255, blank=True)
    # File akan disimpan di media/documents/tahun/bulan/
    file = models.FileField(upload_to="documents/%Y/%m/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_embedded = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        # Auto-fill title dari nama file jika kosong
        if not self.title:
            self.title = os.path.basename(self.file.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {self.title}"


class ChatSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=255, default="Chat Baru")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.user.username} - {self.title}"


class ChatHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    session = models.ForeignKey(ChatSession, null=True, blank=True, on_delete=models.CASCADE)
    question = models.TextField()
    answer = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]  # Yang terbaru muncul duluan

    def __str__(self):
        return f"{self.user.username}: {self.question[:20]}..."


class PlannerHistory(models.Model):
    EVENT_START_AUTO = "start_auto"
    EVENT_OPTION_SELECT = "option_select"
    EVENT_USER_INPUT = "user_input"
    EVENT_GENERATE = "generate"
    EVENT_SAVE = "save"
    EVENT_CHOICES = [
        (EVENT_START_AUTO, "Start Auto"),
        (EVENT_OPTION_SELECT, "Option Select"),
        (EVENT_USER_INPUT, "User Input"),
        (EVENT_GENERATE, "Generate"),
        (EVENT_SAVE, "Save"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE)
    event_type = models.CharField(max_length=32, choices=EVENT_CHOICES)
    planner_step = models.CharField(max_length=64, blank=True, default="")
    text = models.TextField(blank=True, default="")
    option_id = models.IntegerField(null=True, blank=True)
    option_label = models.CharField(max_length=255, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["user", "session", "created_at"]),
            models.Index(fields=["session", "created_at"]),
            models.Index(fields=["event_type", "created_at"]),
        ]

    def __str__(self):
        return f"{self.user.username} {self.event_type} {self.planner_step}".strip()


class UserQuota(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    quota_bytes = models.BigIntegerField(default=10 * 1024 * 1024)  # default 10MB
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} quota={self.quota_bytes}B"


class LLMConfiguration(models.Model):
    """
    Konfigurasi runtime LLM berbasis DB.
    Bisa CRUD via Django Admin, dan sistem memakai konfigurasi yang aktif terbaru.
    """

    name = models.CharField(max_length=100, default="Default")
    is_active = models.BooleanField(default=True)
    openrouter_api_key = models.CharField(max_length=255, blank=True)
    openrouter_model = models.CharField(
        max_length=255,
        default="qwen/qwen3-next-80b-a3b-instruct:free",
    )
    openrouter_backup_models = models.TextField(
        blank=True,
        default="",
        help_text="Daftar model backup, pisahkan dengan baris baru atau koma.",
    )
    openrouter_timeout = models.PositiveIntegerField(default=45)
    openrouter_max_retries = models.PositiveIntegerField(default=1)
    openrouter_temperature = models.FloatField(default=0.2)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        status = "active" if self.is_active else "inactive"
        return f"{self.name} ({status})"


class SystemSetting(models.Model):
    """
    Singleton pengaturan sistem global.
    """

    registration_enabled = models.BooleanField(default=True)
    maintenance_enabled = models.BooleanField(default=False)
    maintenance_message = models.TextField(blank=True, default="")
    maintenance_start_at = models.DateTimeField(null=True, blank=True)
    maintenance_estimated_end_at = models.DateTimeField(null=True, blank=True)
    allow_staff_bypass = models.BooleanField(default=True)

    registration_limit_enabled = models.BooleanField(default=False)
    max_registered_users = models.PositiveIntegerField(default=1000)
    registration_limit_message = models.TextField(blank=True, default="")

    concurrent_login_limit_enabled = models.BooleanField(default=False)
    max_concurrent_logins = models.PositiveIntegerField(default=300)
    concurrent_limit_message = models.TextField(blank=True, default="")
    staff_bypass_concurrent_limit = models.BooleanField(default=True)

    admin_realtime_poll_seconds = models.PositiveIntegerField(default=5)
    admin_realtime_max_rows = models.PositiveIntegerField(default=100)
    admin_metrics_retention_days = models.PositiveIntegerField(default=7)
    admin_dashboard_locale = models.CharField(max_length=16, default="id")

    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def get_effective_maintenance_message(self) -> str:
        msg = (self.maintenance_message or "").strip()
        if msg:
            return msg
        return (
            "Kami sedang melakukan pemeliharaan terjadwal untuk meningkatkan kualitas layanan. "
            "Layanan login sementara tidak tersedia."
        )

    def get_effective_registration_limit_message(self) -> str:
        msg = (self.registration_limit_message or "").strip()
        if msg:
            return msg
        return (
            "Pendaftaran akun baru sementara ditutup karena kuota pengguna tahap uji coba "
            "telah penuh."
        )

    def get_effective_concurrent_limit_message(self) -> str:
        msg = (self.concurrent_limit_message or "").strip()
        if msg:
            return msg
        return (
            "Sistem sedang mencapai batas pengguna aktif bersamaan. "
            "Silakan coba login kembali beberapa saat lagi."
        )

    def __str__(self):
        return (
            "SystemSetting("
            f"registration_enabled={self.registration_enabled}, "
            f"maintenance_enabled={self.maintenance_enabled}, "
            f"allow_staff_bypass={self.allow_staff_bypass}, "
            f"registration_limit_enabled={self.registration_limit_enabled}, "
            f"concurrent_login_limit_enabled={self.concurrent_login_limit_enabled}, "
            f"admin_realtime_poll_seconds={self.admin_realtime_poll_seconds}, "
            f"admin_realtime_max_rows={self.admin_realtime_max_rows}"
            ")"
        )


class UserLoginPresence(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="login_presences")
    session_key = models.CharField(max_length=128, unique=True)
    ip_address = models.CharField(max_length=64, blank=True, default="")
    user_agent = models.CharField(max_length=512, blank=True, default="")
    logged_in_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(default=timezone.now)
    logged_out_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=["is_active", "last_seen_at"]),
            models.Index(fields=["user", "is_active"]),
        ]
        ordering = ["-last_seen_at"]

    def __str__(self):
        state = "active" if self.is_active else "inactive"
        return f"{self.user.username} [{state}] {self.session_key[:10]}"


class SystemHealthSnapshot(models.Model):
    captured_at = models.DateTimeField(auto_now_add=True)
    cpu_percent = models.FloatField(default=0.0)
    memory_percent = models.FloatField(default=0.0)
    disk_percent = models.FloatField(default=0.0)
    load_1m = models.FloatField(default=0.0)
    active_sessions = models.PositiveIntegerField(default=0)
    online_users_non_staff = models.PositiveIntegerField(default=0)
    notes = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-captured_at"]
        indexes = [
            models.Index(fields=["captured_at"]),
            models.Index(fields=["captured_at", "cpu_percent"]),
        ]

    def __str__(self):
        return (
            f"Health {self.captured_at.isoformat()} "
            f"cpu={self.cpu_percent:.1f}% mem={self.memory_percent:.1f}% disk={self.disk_percent:.1f}%"
        )


class RagRequestMetric(models.Model):
    request_id = models.CharField(max_length=64, db_index=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="rag_metrics")
    mode = models.CharField(max_length=32, default="dense")
    query_len = models.PositiveIntegerField(default=0)
    dense_hits = models.PositiveIntegerField(default=0)
    bm25_hits = models.PositiveIntegerField(default=0)
    final_docs = models.PositiveIntegerField(default=0)
    retrieval_ms = models.PositiveIntegerField(default=0)
    rerank_ms = models.PositiveIntegerField(default=0)
    llm_model = models.CharField(max_length=255, blank=True, default="")
    llm_time_ms = models.PositiveIntegerField(default=0)
    fallback_used = models.BooleanField(default=False)
    source_count = models.PositiveIntegerField(default=0)
    status_code = models.PositiveIntegerField(default=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["status_code", "created_at"]),
            models.Index(fields=["fallback_used", "created_at"]),
        ]

    def __str__(self):
        user_part = self.user.username if self.user_id else "anon"
        return (
            f"RAG {self.request_id} user={user_part} mode={self.mode} "
            f"retrieval={self.retrieval_ms}ms llm={self.llm_time_ms}ms status={self.status_code}"
        )
