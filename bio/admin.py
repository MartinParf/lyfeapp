from django.contrib import admin

from .models import Activity, DailyMetric, Profile


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