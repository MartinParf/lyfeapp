from django.contrib import admin

from .models import (
    Activity,
    AnalyticsSnapshot,
    DailyMetric,
    Profile,
)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "full_name", "target_calories_base", "created_at", "updated_at")
    search_fields = ("user__username", "full_name")
    ordering = ("user__username",)


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