from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0021_plannerrun_adaptive_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="plannerrun",
            name="estimated_total_snapshot",
            field=models.PositiveSmallIntegerField(default=4),
        ),
        migrations.AddField(
            model_name="plannerrun",
            name="major_state_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="plannerrun",
            name="ui_state_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]

