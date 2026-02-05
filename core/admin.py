from django.contrib import admin
from django import forms
import logging
from .models import AcademicDocument, ChatHistory, UserQuota

audit_logger = logging.getLogger("audit")
# --- KONFIGURASI HEADER ADMIN ---
admin.site.site_header = "Academic AI Administration"
admin.site.site_title = "Academic Admin Portal"
admin.site.index_title = "Welcome to RAG System Management"

@admin.register(AcademicDocument)
class AcademicDocumentAdmin(admin.ModelAdmin):
    # Kolom yang muncul di tabel daftar
    list_display = ('title', 'user', 'file_link', 'is_embedded', 'uploaded_at')
    
    # Filter sidebar di sebelah kanan
    list_filter = ('is_embedded', 'uploaded_at', 'user')
    
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
class ChatHistoryAdmin(admin.ModelAdmin):
    # Kolom yang muncul (kita potong pertanyaan biar gak kepanjangan)
    list_display = ('user', 'short_question', 'short_answer', 'timestamp')
    
    # Filter berdasarkan user dan waktu
    list_filter = ('timestamp', 'user')
    
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


@admin.register(UserQuota)
class UserQuotaAdmin(admin.ModelAdmin):
    list_display = ("user", "quota_bytes", "updated_at")
    search_fields = ("user__username", "user__email")
    list_filter = ("updated_at",)
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
