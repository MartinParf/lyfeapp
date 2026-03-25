from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.text import slugify


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


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


class WorkoutSession(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workout_sessions",
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
        indexes = [
            models.Index(fields=["user", "status"], name="idx_session_user_status"),
            models.Index(fields=["user", "focus"], name="idx_session_user_focus"),
            models.Index(fields=["user", "scheduled_date"], name="idx_session_user_sched_date"),
            models.Index(fields=["user", "started_at"], name="idx_session_user_started_at"),
        ]

    def __str__(self) -> str:
        return f"WorkoutSession<{self.user_id} {self.focus} {self.status}>"


class WorkoutSessionExercise(TimeStampedModel):
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
        ]
        indexes = [
            models.Index(fields=["session", "sequence"], name="idx_session_exercise_sequence"),
            models.Index(fields=["exercise"], name="idx_session_exercise_exercise"),
        ]

    def __str__(self) -> str:
        return f"SessionExercise<{self.session_id}:{self.sequence}:{self.exercise_id}>"


class WorkoutSet(TimeStampedModel):
    session_exercise = models.ForeignKey(
        WorkoutSessionExercise,
        on_delete=models.CASCADE,
        related_name="sets",
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
        ]
        indexes = [
            models.Index(
                fields=["session_exercise", "set_order"],
                name="idx_wset_se_order",
            ),
        ]

    def __str__(self) -> str:
        return f"WorkoutSet<{self.session_exercise_id}:{self.set_order}>"