from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0020_rename_core_planne_user_id_81de39_idx_core_planne_user_id_a063a4_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="plannerrun",
            name="intent_candidates_snapshot",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="plannerrun",
            name="decision_tree_state",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="plannerrun",
            name="path_taken",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="plannerrun",
            name="current_depth",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="plannerrun",
            name="max_depth",
            field=models.PositiveSmallIntegerField(default=4),
        ),
        migrations.AddField(
            model_name="plannerrun",
            name="grounding_policy",
            field=models.CharField(default="doc_first_fallback", max_length=64),
        ),
        migrations.AddField(
            model_name="plannerrun",
            name="profile_hints_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="plannerrun",
            name="doc_relevance_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="plannerrun",
            name="status",
            field=models.CharField(
                choices=[
                    ("started", "Started"),
                    ("ready", "Ready"),
                    ("collecting", "Collecting"),
                    ("executing", "Executing"),
                    ("completed", "Completed"),
                    ("cancelled", "Cancelled"),
                    ("expired", "Expired"),
                ],
                default="started",
                max_length=16,
            ),
        ),
    ]
