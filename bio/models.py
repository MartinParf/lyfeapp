from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models
from django.utils import timezone
from django_resized import ResizedImageField



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


class SleepQualityLevel(models.IntegerChoices):
    VERY_POOR = 1, "Very poor"
    POOR = 2, "Poor"
    AVERAGE = 3, "Average"
    GOOD = 4, "Good"
    EXCELLENT = 5, "Excellent"


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


class ActivityType(models.TextChoices):
    RUNNING = "RUNNING", "Running"
    CYCLING = "CYCLING", "Cycling"
    WALKING = "WALKING", "Walking"
    HIKING = "HIKING", "Hiking"
    SWIMMING = "SWIMMING", "Swimming"
    OTHER = "OTHER", "Other"

def avatar_upload_to(instance, filename):
    return f"avatars/user_{instance.user_id}/{uuid4().hex}.webp"


def validate_avatar_file_size(file):
    max_bytes = 2 * 1024 * 1024  # 2 MB
    if file.size > max_bytes:
        raise ValidationError("Avatar must be 2 MB or smaller.")


def validate_not_future_date(value):
    if value and value > timezone.localdate():
        raise ValidationError("Date of birth cannot be in the future.")


class GoalMode(models.TextChoices):
    MAINTAIN = "maintain", "Maintain"
    LOSE_WEIGHT = "lose_weight", "Lose weight"
    GAIN_WEIGHT = "gain_weight", "Gain weight"


class Profile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )

    # Legacy / existing fields
    full_name = models.CharField(max_length=255, blank=True)
    target_calories_base = models.PositiveIntegerField(null=True, blank=True)

    # New identity / profile foundation
    display_name = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Primary app-facing nickname / display name.",
    )
    bio = models.CharField(
        max_length=280,
        blank=True,
        default="",
        help_text="Short profile bio.",
    )
    avatar = ResizedImageField(
        size=[512, 512],
        crop=["middle", "center"],
        quality=85,
        force_format="WEBP",
        upload_to=avatar_upload_to,
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png", "webp"]),
            validate_avatar_file_size,
        ],
        help_text="Allowed: jpg, jpeg, png, webp. Max size 2 MB. Stored as 512x512 WEBP.",
    )
    date_of_birth = models.DateField(
        blank=True,
        null=True,
        validators=[validate_not_future_date],
    )
    height_cm = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(80), MaxValueValidator(260)],
        help_text="Optional height in centimeters.",
    )
    target_weight_kg = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        blank=True,
        null=True,
        validators=[
            MinValueValidator(Decimal("25.0")),
            MaxValueValidator(Decimal("400.0")),
        ],
        help_text="Optional long-term target weight.",
    )
    goal_mode = models.CharField(
        max_length=20,
        choices=GoalMode.choices,
        default=GoalMode.MAINTAIN,
        help_text="Primary user goal for onboarding and analytics.",
    )
    email_verified_at = models.DateTimeField(
        blank=True,
        null=True,
    )
    onboarding_completed_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ["user_id"]
        indexes = [
            models.Index(fields=["updated_at"], name="idx_profile_updated_at"),
            models.Index(fields=["goal_mode"], name="idx_profile_goal_mode"),
            models.Index(
                fields=["onboarding_completed_at"],
                name="idx_profile_onboarding_done",
            ),
        ]

    def __str__(self) -> str:
        return f"Profile<{self.user_id} {self.resolved_display_name}>"

    @property
    def resolved_display_name(self) -> str:
        if self.display_name:
            return self.display_name
        if self.full_name:
            return self.full_name
        if getattr(self.user, "username", ""):
            return self.user.username
        if getattr(self.user, "email", ""):
            return self.user.email.split("@")[0]
        return f"user-{self.user_id}"

    def clean(self):
        super().clean()

        self.display_name = (self.display_name or "").strip()
        self.bio = (self.bio or "").strip()
        self.full_name = (self.full_name or "").strip()

        if self.display_name and len(self.display_name) < 2:
            raise ValidationError({"display_name": "Display name must be at least 2 characters long."})


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
        choices=SleepQualityLevel.choices,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Sleep quality on a 1-5 scale.",
    )
    alcohol_units = models.PositiveSmallIntegerField(
        default=0,
        choices=ALCOHOL_LEVEL_CHOICES,
        validators=[MinValueValidator(0), MaxValueValidator(10)],
        help_text="Approximate alcohol intake on a 0-10 scale.",
    )
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

class AnalyticsSnapshotType(models.TextChoices):
    OVERVIEW = "OVERVIEW", "Overview"
    ANALYTICS = "ANALYTICS", "Analytics"

class AnalyticsSnapshotStatus(models.TextChoices):
    FRESH = "FRESH", "Fresh"
    QUEUED = "QUEUED", "Queued"
    ERROR = "ERROR", "Error"

class AnalyticsSnapshot(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="analytics_snapshots",
    )
    snapshot_type = models.CharField(
        max_length=20,
        choices=AnalyticsSnapshotType.choices,
    )
    window_days = models.PositiveSmallIntegerField()
    as_of_date = models.DateField()
    payload = models.JSONField(default=dict, blank=True)

    status = models.CharField(
        max_length=20,
        choices=AnalyticsSnapshotStatus.choices,
        default=AnalyticsSnapshotStatus.QUEUED,
    )
    last_enqueued_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["user_id", "snapshot_type", "window_days"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "snapshot_type", "window_days"],
                name="uniq_analytics_snapshot_user_type_window",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "snapshot_type", "window_days"],
                name="idx_analytics_snapshot_lookup",
            ),
            models.Index(fields=["as_of_date"], name="idx_analytics_snapshot_as_of"),
            models.Index(fields=["status"], name="idx_analytics_snapshot_status"),
        ]

    def __str__(self) -> str:
        return f"AnalyticsSnapshot<{self.user_id} {self.snapshot_type} {self.window_days}d>"

    @property
    def has_payload(self) -> bool:
        return bool(self.payload)

    def is_stale(self, *, max_age_hours: int) -> bool:
        now = timezone.now()

        if self.status in {AnalyticsSnapshotStatus.ERROR, AnalyticsSnapshotStatus.QUEUED}:
            return True
        if self.last_success_at is None:
            return True
        if not self.payload:
            return True
        if self.as_of_date < timezone.localdate():
            return True
        if self.updated_at <= now - timedelta(hours=max_age_hours):
            return True

        return False

    def can_enqueue_refresh(self, *, cooldown_minutes: int = 5) -> bool:
        now = timezone.now()

        if (
            self.status == AnalyticsSnapshotStatus.QUEUED
            and self.last_enqueued_at
            and self.last_enqueued_at >= now - timedelta(minutes=cooldown_minutes)
        ):
            return False

        return True