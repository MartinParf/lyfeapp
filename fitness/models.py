from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.text import slugify
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class VersionedModel(TimeStampedModel):
    version = models.PositiveIntegerField(
        default=1,
        editable=False,
        help_text="Monotonic server-side version for sync/conflict detection.",
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            self.version = max(1, int(self.version or 1)) + 1

            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                update_fields = set(update_fields)
                update_fields.add("version")
                kwargs["update_fields"] = list(update_fields)

        return super().save(*args, **kwargs)


class SyncTrackedModel(VersionedModel):
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Soft-delete marker for sync-aware top-level objects.",
    )

    class Meta:
        abstract = True

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

class ExercisePattern(models.TextChoices):
    PUSH = "PUSH", "Push"
    PULL = "PULL", "Pull"
    LEGS = "LEGS", "Legs"
    CORE = "CORE", "Core"
    FULL_BODY = "FULL_BODY", "Full Body"
    CARDIO = "CARDIO", "Cardio"
    OTHER = "OTHER", "Other"


class PoolFocus(models.TextChoices):
    PUSH = "PUSH", "Push"
    PULL = "PULL", "Pull"
    LEGS = "LEGS", "Legs"
    UPPER = "UPPER", "Upper"
    LOWER = "LOWER", "Lower"
    FULL_BODY = "FULL_BODY", "Full Body"
    ARMS = "ARMS", "Arms"
    SHOULDERS = "SHOULDERS", "Shoulders"
    CUSTOM = "CUSTOM", "Custom"


class WorkoutSessionStatus(models.TextChoices):
    PLANNED = "PLANNED", "Planned"
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"


class WorkoutSetType(models.TextChoices):
    TOP = "TOP", "Top"
    BACKOFF = "BACKOFF", "Backoff"
    STRAIGHT = "STRAIGHT", "Straight"
    AMRAP = "AMRAP", "AMRAP"
    OTHER = "OTHER", "Other"


class Exercise(TimeStampedModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    primary_pattern = models.CharField(
        max_length=20,
        choices=ExercisePattern.choices,
        null=True,
        blank=True,
        help_text="Optional suggestion only, not a hard rule.",
    )
    is_custom = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="custom_exercises",
        help_text="Null means global/system exercise.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "id"]
        indexes = [
            models.Index(fields=["slug"], name="idx_exercise_slug"),
            models.Index(fields=["primary_pattern"], name="idx_exercise_pattern"),
            models.Index(fields=["created_by", "is_active"], name="idx_exercise_creator_active"),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        self.is_custom = bool(self.created_by_id)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


class ExercisePool(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="exercise_pools",
    )
    name = models.CharField(max_length=120)
    focus = models.CharField(max_length=20, choices=PoolFocus.choices, default=PoolFocus.CUSTOM)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "name"],
                name="uniq_exercise_pool_user_name",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "focus"], name="idx_pool_user_focus"),
            models.Index(fields=["user", "is_active"], name="idx_pool_user_active"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.user_id})"


class ExercisePoolItem(TimeStampedModel):
    pool = models.ForeignKey(
        ExercisePool,
        on_delete=models.CASCADE,
        related_name="items",
    )
    exercise = models.ForeignKey(
        Exercise,
        on_delete=models.CASCADE,
        related_name="pool_items",
    )
    sequence = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["pool_id", "sequence", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["pool", "sequence"],
                name="uniq_pool_item_pool_sequence",
            ),
            models.UniqueConstraint(
                fields=["pool", "exercise"],
                name="uniq_pool_item_pool_exercise",
            ),
        ]
        indexes = [
            models.Index(fields=["pool", "sequence"], name="idx_pool_item_pool_sequence"),
            models.Index(fields=["exercise"], name="idx_pool_item_exercise"),
        ]

    def __str__(self) -> str:
        return f"{self.pool_id}:{self.sequence}:{self.exercise_id}"


class WorkoutSession(SyncTrackedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workout_sessions",
    )
    client_uuid = models.UUIDField(
        null=True,
        blank=True,
        editable=False,
        help_text="Client-generated idempotency key for mobile/offline create.",
    )
    focus = models.CharField(max_length=20, choices=PoolFocus.choices, default=PoolFocus.CUSTOM)
    source_pool = models.ForeignKey(
        ExercisePool,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workout_sessions",
        help_text="Optional pool used as recommendation source.",
    )
    status = models.CharField(
        max_length=20,
        choices=WorkoutSessionStatus.choices,
        default=WorkoutSessionStatus.PLANNED,
    )
    scheduled_date = models.DateField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "client_uuid"],
                condition=models.Q(client_uuid__isnull=False),
                name="uniq_wsession_user_client_uuid",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "status"], name="idx_session_user_status"),
            models.Index(fields=["user", "focus"], name="idx_session_user_focus"),
            models.Index(fields=["user", "scheduled_date"], name="idx_session_user_sched_date"),
            models.Index(fields=["user", "started_at"], name="idx_session_user_started_at"),
            models.Index(fields=["user", "updated_at"], name="idx_session_user_updated"),
            models.Index(fields=["user", "deleted_at"], name="idx_session_user_deleted"),
        ]

    def __str__(self) -> str:
        return f"WorkoutSession<{self.user_id} {self.focus} {self.status}>"

    @property
    def ui_status(self) -> str:
        if self.status == WorkoutSessionStatus.COMPLETED or (
            self.started_at and self.ended_at and self.ended_at >= self.started_at
        ):
            return WorkoutSessionStatus.COMPLETED
        return WorkoutSessionStatus.PLANNED

    @property
    def is_ui_completed(self) -> bool:
        return self.ui_status == WorkoutSessionStatus.COMPLETED

    @property
    def is_ui_planned(self) -> bool:
        return self.ui_status == WorkoutSessionStatus.PLANNED

    @property
    def effective_date(self):
        if self.scheduled_date:
            return self.scheduled_date
        if self.started_at:
            return self.started_at.date()
        if self.ended_at:
            return self.ended_at.date()
        return self.created_at.date()

    @property
    def duration_minutes(self):
        if self.started_at and self.ended_at and self.ended_at > self.started_at:
            return int((self.ended_at - self.started_at).total_seconds() // 60)
        return None

    @property
    def duration_label(self) -> str:
        minutes = self.duration_minutes
        if minutes is None:
            return "—"
        hours, remaining = divmod(minutes, 60)
        if hours and remaining:
            return f"{hours}h {remaining}m"
        if hours:
            return f"{hours}h"
        return f"{remaining}m"


class WorkoutSessionExercise(VersionedModel):
    session = models.ForeignKey(
        WorkoutSession,
        on_delete=models.CASCADE,
        related_name="session_exercises",
    )
    exercise = models.ForeignKey(
        Exercise,
        on_delete=models.CASCADE,
        related_name="session_entries",
    )
    client_uuid = models.UUIDField(
        null=True,
        blank=True,
        editable=False,
        help_text="Client-generated idempotency key for mobile/offline create.",
    )
    sequence = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    source_pool_item = models.ForeignKey(
        ExercisePoolItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="session_entries",
        help_text="Optional source recommendation item.",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["session_id", "sequence", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "sequence"],
                name="uniq_session_exercise_session_sequence",
            ),
            models.UniqueConstraint(
                fields=["session", "client_uuid"],
                condition=models.Q(client_uuid__isnull=False),
                name="uniq_session_exercise_client_uuid",
            ),
        ]
        indexes = [
            models.Index(fields=["session", "sequence"], name="idx_session_exercise_sequence"),
            models.Index(fields=["exercise"], name="idx_session_exercise_exercise"),
            models.Index(fields=["session", "updated_at"], name="idx_session_exercise_updated"),
        ]

    def __str__(self) -> str:
        return f"SessionExercise<{self.session_id}:{self.sequence}:{self.exercise_id}>"


class WorkoutSet(VersionedModel):
    session_exercise = models.ForeignKey(
        WorkoutSessionExercise,
        on_delete=models.CASCADE,
        related_name="sets",
    )
    client_uuid = models.UUIDField(
        null=True,
        blank=True,
        editable=False,
        help_text="Client-generated idempotency key for mobile/offline create.",
    )
    set_order = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    set_type = models.CharField(
        max_length=20,
        choices=WorkoutSetType.choices,
        null=True,
        blank=True,
    )
    weight_kg = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    reps = models.PositiveSmallIntegerField(null=True, blank=True)
    rpe = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["session_exercise_id", "set_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["session_exercise", "set_order"],
                name="uniq_workout_set_session_exercise_order",
            ),
            models.UniqueConstraint(
                fields=["session_exercise", "client_uuid"],
                condition=models.Q(client_uuid__isnull=False),
                name="uniq_workout_set_client_uuid",
            ),
        ]
        indexes = [
            models.Index(
                fields=["session_exercise", "set_order"],
                name="idx_wset_se_order",
            ),
            models.Index(
                fields=["session_exercise", "updated_at"],
                name="idx_wset_se_updated",
            ),
        ]

    def __str__(self) -> str:
        return f"WorkoutSet<{self.session_exercise_id}:{self.set_order}>"