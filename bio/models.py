from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class DietMode(models.TextChoices):
    STANDARD = "STANDARD", "Standard"
    GLUTEN_FREE = "GLUTEN_FREE", "Gluten Free"
    LOW_CARB = "LOW_CARB", "Low Carb"
    KETO = "KETO", "Keto"
    HIGH_PROTEIN = "HIGH_PROTEIN", "High Protein"
    CUSTOM = "CUSTOM", "Custom"


class ActivityType(models.TextChoices):
    RUNNING = "RUNNING", "Running"
    CYCLING = "CYCLING", "Cycling"
    WALKING = "WALKING", "Walking"
    HIKING = "HIKING", "Hiking"
    SWIMMING = "SWIMMING", "Swimming"
    OTHER = "OTHER", "Other"


class Profile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    full_name = models.CharField(max_length=255, blank=True)
    target_calories_base = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["user_id"]

    def __str__(self) -> str:
        return f"Profile<{self.user_id}>"


class DailyMetric(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="daily_metrics",
    )
    date = models.DateField()
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    diet_mode = models.CharField(
        max_length=20,
        choices=DietMode.choices,
        null=True,
        blank=True,
    )
    sleep_quality = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Sleep quality on a 1-5 scale.",
    )
    alcohol_consumed = models.BooleanField(default=False)
    calories_planned = models.PositiveIntegerField(null=True, blank=True)
    calories_actual = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "date"],
                name="uniq_daily_metric_user_date",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "date"], name="idx_daily_metric_user_date"),
            models.Index(fields=["date"], name="idx_daily_metric_date"),
        ]

    def __str__(self) -> str:
        return f"DailyMetric<{self.user_id} {self.date}>"


class Activity(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="activities",
    )
    date = models.DateField()
    activity_type = models.CharField(max_length=20, choices=ActivityType.choices)
    duration_minutes = models.PositiveIntegerField()
    calories_burned_est = models.PositiveIntegerField(null=True, blank=True)
    distance_km = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-date", "-id"]
        indexes = [
            models.Index(fields=["user", "date"], name="idx_activity_user_date"),
            models.Index(
                fields=["user", "activity_type", "date"],
                name="idx_activity_user_type_date",
            ),
        ]

    def __str__(self) -> str:
        return f"Activity<{self.user_id} {self.activity_type} {self.date}>"