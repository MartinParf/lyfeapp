from django.contrib import admin

from .models import (
    Exercise,
    ExercisePool,
    ExercisePoolItem,
    WorkoutSession,
    WorkoutSessionExercise,
    WorkoutSet,
)


class ExercisePoolItemInline(admin.TabularInline):
    model = ExercisePoolItem
    extra = 1
    autocomplete_fields = ("exercise",)
    ordering = ("sequence", "id")


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "slug",
        "primary_pattern",
        "is_custom",
        "created_by",
        "is_active",
    )
    list_filter = ("primary_pattern", "is_custom", "is_active")
    search_fields = ("name", "slug", "created_by__username", "created_by__email")
    list_select_related = ("created_by",)
    ordering = ("name", "id")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(ExercisePool)
class ExercisePoolAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "user", "focus", "is_active", "created_at")
    list_filter = ("focus", "is_active")
    search_fields = ("name", "description", "user__username", "user__email")
    list_select_related = ("user",)
    ordering = ("name", "id")
    inlines = [ExercisePoolItemInline]


@admin.register(ExercisePoolItem)
class ExercisePoolItemAdmin(admin.ModelAdmin):
    list_display = ("id", "pool", "sequence", "exercise", "is_active", "created_at")
    list_filter = ("is_active", "pool__focus")
    search_fields = ("pool__name", "exercise__name", "notes")
    list_select_related = ("pool", "exercise")
    ordering = ("pool_id", "sequence", "id")
    autocomplete_fields = ("pool", "exercise")


class WorkoutSessionExerciseInline(admin.TabularInline):
    model = WorkoutSessionExercise
    extra = 1
    autocomplete_fields = ("exercise", "source_pool_item")
    ordering = ("sequence", "id")


@admin.register(WorkoutSession)
class WorkoutSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "focus",
        "status",
        "source_pool",
        "scheduled_date",
        "started_at",
        "ended_at",
    )
    list_filter = ("focus", "status", "scheduled_date")
    search_fields = ("user__username", "user__email", "notes")
    list_select_related = ("user", "source_pool")
    ordering = ("-created_at", "-id")
    inlines = [WorkoutSessionExerciseInline]


@admin.register(WorkoutSessionExercise)
class WorkoutSessionExerciseAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "sequence", "exercise", "source_pool_item", "created_at")
    list_filter = ("session__focus", "session__status")
    search_fields = ("exercise__name", "session__user__username", "notes")
    list_select_related = ("session", "exercise", "source_pool_item")
    ordering = ("session_id", "sequence", "id")
    autocomplete_fields = ("session", "exercise", "source_pool_item")


@admin.register(WorkoutSet)
class WorkoutSetAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "session_exercise",
        "set_order",
        "set_type",
        "weight_kg",
        "reps",
        "rpe",
        "created_at",
    )
    list_filter = ("set_type",)
    search_fields = ("session_exercise__exercise__name", "notes")
    list_select_related = ("session_exercise",)
    ordering = ("session_exercise_id", "set_order", "id")
    autocomplete_fields = ("session_exercise",)