from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0018_rename_core_ragreq_created_56a5b7_idx_core_ragreq_created_0e1d24_idx_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlannerRun",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("started", "Started"),
                            ("ready", "Ready"),
                            ("executing", "Executing"),
                            ("completed", "Completed"),
                            ("cancelled", "Cancelled"),
                            ("expired", "Expired"),
                        ],
                        default="started",
                        max_length=16,
                    ),
                ),
                ("wizard_blueprint", models.JSONField(blank=True, default=dict)),
                ("documents_snapshot", models.JSONField(blank=True, default=list)),
                ("answers_snapshot", models.JSONField(blank=True, default=dict)),
                ("expires_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "session",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="core.chatsession"),
                ),
                (
                    "user",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="auth.user"),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="plannerrun",
            index=models.Index(fields=["user", "status", "created_at"], name="core_planne_user_id_81de39_idx"),
        ),
        migrations.AddIndex(
            model_name="plannerrun",
            index=models.Index(fields=["expires_at"], name="core_planne_expires_73ca74_idx"),
        ),
    ]
