from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


ALCOHOL_LEVEL_CHOICES = [
    (0, "0 — None"),
    (1, "1 — Very low"),
    (2, "2 — Low"),
    (3, "3 — Mild"),
    (4, "4 — Moderate"),
    (5, "5 — Moderately high"),
    (6, "6 — High"),
    (7, "7 — Very high"),
    (8, "8 — Heavy"),
    (9, "9 — Very heavy"),
    (10, "10 — Extreme"),
]


def copy_alcohol_boolean_to_units(apps, schema_editor):
    DailyMetric = apps.get_model("bio", "DailyMetric")
    for metric in DailyMetric.objects.all():
        metric.alcohol_units = 1 if getattr(metric, "alcohol_consumed", False) else 0
        metric.save(update_fields=["alcohol_units"])


class Migration(migrations.Migration):

    dependencies = [
        ("bio", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="dailymetric",
            name="alcohol_units",
            field=models.PositiveSmallIntegerField(
                choices=ALCOHOL_LEVEL_CHOICES,
                default=0,
                help_text="Approximate alcohol intake on a 0-10 scale.",
                validators=[MinValueValidator(0), MaxValueValidator(10)],
            ),
        ),
        migrations.RunPython(copy_alcohol_boolean_to_units, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="dailymetric",
            name="alcohol_consumed",
        ),
        migrations.AlterField(
            model_name="dailymetric",
            name="sleep_quality",
            field=models.PositiveSmallIntegerField(
                blank=True,
                choices=[
                    (1, "Very poor"),
                    (2, "Poor"),
                    (3, "Average"),
                    (4, "Good"),
                    (5, "Excellent"),
                ],
                help_text="Sleep quality on a 1-5 scale.",
                null=True,
                validators=[MinValueValidator(1), MaxValueValidator(5)],
            ),
        ),
    ]