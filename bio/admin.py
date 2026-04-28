from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Activity,
    AnalyticsSnapshot,
    DailyMetric,
    Profile,
)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "resolved_display_name_admin",
        "goal_mode",
        "email_verified_at",
        "onboarding_completed_at",
        "created_at",
        "updated_at",
    )
    search_fields = (
        "user__username",
        "user__email",
        "display_name",
        "full_name",
        "bio",
    )
    list_filter = (
        "goal_mode",
        "email_verified_at",
        "onboarding_completed_at",
        "updated_at",
    )
    ordering = ("user__username",)
    readonly_fields = (
        "avatar_preview",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        ("Identity", {
            "fields": (
                "user",
                "display_name",
                "full_name",
                "bio",
                "avatar",
                "avatar_preview",
            )
        }),
        ("Goals / profile", {
            "fields": (
                "goal_mode",
                "date_of_birth",
                "height_cm",
                "target_weight_kg",
                "target_calories_base",
            )
        }),
        ("Account state", {
            "fields": (
                "email_verified_at",
                "onboarding_completed_at",
            )
        }),
        ("Timestamps", {
            "fields": (
                "created_at",
                "updated_at",
            )
        }),
    )

    @admin.display(description="Display name")
    def resolved_display_name_admin(self, obj):
        return obj.resolved_display_name

    @admin.display(description="Avatar preview")
    def avatar_preview(self, obj):
        if not obj.avatar:
            return "—"
        return format_html(
            '<img src="{}" style="width:72px;height:72px;object-fit:cover;border-radius:12px;" />',
            obj.avatar.url,
        )


@admin.register(DailyMetric)
class DailyMetricAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "date",
        "weight_kg",
        "diet_mode",
        "sleep_quality",
        "alcohol_units",
        "calories_planned",
        "calories_actual",
        "updated_at",
    )
    list_filter = (
        "diet_mode",
        "sleep_quality",
        "alcohol_units",
        "date",
    )
    search_fields = ("user__username", "notes")
    date_hierarchy = "date"
    ordering = ("-date", "-id")


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "date",
        "activity_type",
        "duration_minutes",
        "calories_burned_est",
        "distance_km",
        "updated_at",
    )
    list_filter = ("activity_type", "date")
    search_fields = ("user__username", "notes")
    date_hierarchy = "date"
    ordering = ("-date", "-id")


@admin.register(AnalyticsSnapshot)
class AnalyticsSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "snapshot_type",
        "window_days",
        "status",
        "as_of_date",
        "last_enqueued_at",
        "last_success_at",
        "updated_at",
        "payload_present",
    )
    list_filter = (
        "snapshot_type",
        "window_days",
        "status",
        "as_of_date",
    )
    search_fields = ("user__username", "user__email", "last_error")
    ordering = ("user__username", "snapshot_type", "window_days")
    readonly_fields = (
        "created_at",
        "updated_at",
        "last_enqueued_at",
        "last_success_at",
        "payload_preview",
    )

    fieldsets = (
        ("Snapshot", {
            "fields": (
                "user",
                "snapshot_type",
                "window_days",
                "status",
                "as_of_date",
            )
        }),
        ("Runtime", {
            "fields": (
                "last_enqueued_at",
                "last_success_at",
                "last_error",
            )
        }),
        ("Payload", {
            "fields": ("payload_preview",)
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at")
        }),
    )

    @admin.display(boolean=True, description="Payload")
    def payload_present(self, obj):
        return bool(obj.payload)

    @admin.display(description="Payload preview")
    def payload_preview(self, obj):
        return obj.payload