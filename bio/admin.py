from django.contrib import admin

from .models import Activity, DailyMetric, Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "full_name", "target_calories_base", "created_at", "updated_at")
    search_fields = ("user__username", "user__email", "full_name")
    list_select_related = ("user",)
    ordering = ("user_id",)


@admin.register(DailyMetric)
class DailyMetricAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "date",
        "weight_kg",
        "diet_mode",
        "sleep_quality",
        "alcohol_consumed",
        "calories_planned",
        "calories_actual",
    )
    list_filter = ("diet_mode", "alcohol_consumed", "date")
    search_fields = ("user__username", "user__email", "notes")
    list_select_related = ("user",)
    ordering = ("-date", "-id")
    date_hierarchy = "date"


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "date",
        "activity_type",
        "duration_minutes",
        "distance_km",
        "calories_burned_est",
    )
    list_filter = ("activity_type", "date")
    search_fields = ("user__username", "user__email", "notes")
    list_select_related = ("user",)
    ordering = ("-date", "-id")
    date_hierarchy = "date"