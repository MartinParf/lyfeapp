import csv
from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Avg
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import ListView
from django.http import HttpResponse, JsonResponse

from .forms import ActivityForm, DailyMetricForm
from .models import Activity, AnalyticsSnapshotType, DailyMetric
from .services.analytics import (
    get_bio_analytics_snapshot,
    get_cached_bio_analytics,
    get_snapshot_max_age_hours,
    queue_snapshot_refresh,
)
from .tasks import (
    ensure_user_snapshots_exist,
    recompute_analytics_snapshot,
    recompute_overview_snapshot,
    recompute_recent_snapshots_for_user,
)
from .services.reports import build_bio_analytics_report, build_bio_daily_csv_rows


def _queue_snapshot_refresh_if_needed(*, user, snapshot_type: str, period_days: int) -> None:
    snapshot = get_bio_analytics_snapshot(
        user=user,
        period_days=period_days,
        snapshot_type=snapshot_type,
    )

    if snapshot is None:
        queue_snapshot_refresh(
            user=user,
            period_days=period_days,
            snapshot_type=snapshot_type,
        )
        if snapshot_type == AnalyticsSnapshotType.OVERVIEW:
            recompute_overview_snapshot(user.id)
        else:
            recompute_analytics_snapshot(user.id, period_days)
        return

    max_age_hours = get_snapshot_max_age_hours(snapshot_type)
    if snapshot.is_stale(max_age_hours=max_age_hours) and snapshot.can_enqueue_refresh():
        queue_snapshot_refresh(
            user=user,
            period_days=period_days,
            snapshot_type=snapshot_type,
        )
        if snapshot_type == AnalyticsSnapshotType.OVERVIEW:
            recompute_overview_snapshot(user.id)
        else:
            recompute_analytics_snapshot(user.id, period_days)


def _get_snapshot_or_fallback(*, user, snapshot_type: str, period_days: int) -> dict:
    snapshot = get_bio_analytics_snapshot(
        user=user,
        period_days=period_days,
        snapshot_type=snapshot_type,
    )

    if snapshot is None:
        ensure_user_snapshots_exist(user.id)
        return get_cached_bio_analytics(
            user=user,
            period_days=period_days,
            snapshot_type=snapshot_type,
        )

    _queue_snapshot_refresh_if_needed(
        user=user,
        snapshot_type=snapshot_type,
        period_days=period_days,
    )

    if snapshot.payload:
        return snapshot.payload

    return get_cached_bio_analytics(
        user=user,
        period_days=period_days,
        snapshot_type=snapshot_type,
    )


class DailyMetricListView(LoginRequiredMixin, ListView):
    model = DailyMetric
    template_name = "bio/dailymetric_list.html"
    context_object_name = "metrics"

    def get_queryset(self):
        period = self.request.GET.get("period", "7d")

        qs = DailyMetric.objects.filter(user=self.request.user).order_by("-date", "-id")

        if period == "7d":
            cutoff = timezone.localdate() - timedelta(days=7)
            qs = qs.filter(date__gte=cutoff)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        today = timezone.localdate()
        period = self.request.GET.get("period", "7d")

        filtered_metrics = self.get_queryset()

        today_metric = (
            DailyMetric.objects
            .filter(user=self.request.user, date=today)
            .first()
        )

        history_metrics = filtered_metrics.exclude(date=today)

        avg_weight = filtered_metrics.aggregate(avg=Avg("weight_kg"))["avg"]
        avg_sleep = filtered_metrics.aggregate(avg=Avg("sleep_quality"))["avg"]
        avg_alcohol = filtered_metrics.aggregate(avg=Avg("alcohol_units"))["avg"]
        entries_count = filtered_metrics.count()

        weight_values = list(
            filtered_metrics.exclude(weight_kg__isnull=True)
            .order_by("date", "id")
            .values_list("weight_kg", flat=True)
        )

        weight_trend = None
        if len(weight_values) >= 2:
            first_weight = weight_values[0]
            last_weight = weight_values[-1]

            if last_weight > first_weight:
                weight_trend = "up"
            elif last_weight < first_weight:
                weight_trend = "down"
            else:
                weight_trend = "flat"

        context["today"] = today
        context["today_metric"] = today_metric
        context["history_metrics"] = history_metrics
        context["period"] = period
        context["avg_weight"] = avg_weight
        context["avg_sleep"] = avg_sleep
        context["avg_alcohol"] = avg_alcohol
        context["entries_count"] = entries_count
        context["weight_trend"] = weight_trend

        return context


class DailyMetricCreateView(LoginRequiredMixin, View):
    template_name = "bio/dailymetric_form.html"

    def get(self, request):
        initial = {}

        if request.GET.get("date"):
            initial["date"] = request.GET.get("date")

        form = DailyMetricForm(initial=initial)
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "page_title": "Create Daily Metric",
                "submit_label": "Save daily metric",
            },
        )

    def post(self, request):
        form = DailyMetricForm(request.POST)

        if form.is_valid():
            metric = form.save(commit=False)
            metric.user = request.user
            metric.save()

            user_id = request.user.id
            transaction.on_commit(lambda: recompute_recent_snapshots_for_user(user_id))

            return redirect("bio:dailymetric-list")

        return render(
            request,
            self.template_name,
            {
                "form": form,
                "page_title": "Create Daily Metric",
                "submit_label": "Save daily metric",
            },
        )


class DailyMetricUpdateView(LoginRequiredMixin, View):
    template_name = "bio/dailymetric_form.html"

    def get_metric(self, request, pk):
        return get_object_or_404(DailyMetric, pk=pk, user=request.user)

    def get(self, request, pk):
        metric = self.get_metric(request, pk)
        form = DailyMetricForm(instance=metric)
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "metric": metric,
                "page_title": "Edit Daily Metric",
                "submit_label": "Save changes",
            },
        )

    def post(self, request, pk):
        metric = self.get_metric(request, pk)
        form = DailyMetricForm(request.POST, instance=metric)

        if form.is_valid():
            form.save()

            user_id = request.user.id
            transaction.on_commit(lambda: recompute_recent_snapshots_for_user(user_id))

            return redirect("bio:dailymetric-list")

        return render(
            request,
            self.template_name,
            {
                "form": form,
                "metric": metric,
                "page_title": "Edit Daily Metric",
                "submit_label": "Save changes",
            },
        )


class DailyMetricDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        metric = get_object_or_404(DailyMetric, pk=pk, user=request.user)
        
        user_id = request.user.id
        metric.delete()
        transaction.on_commit(lambda: recompute_recent_snapshots_for_user(user_id))
        return redirect("bio:dailymetric-list")


class DailyMetricTodayView(LoginRequiredMixin, View):
    def get(self, request):
        today = timezone.localdate()

        metric = (
            DailyMetric.objects
            .filter(user=request.user, date=today)
            .first()
        )

        if metric:
            return redirect("bio:dailymetric-edit", pk=metric.pk)

        create_url = f"{reverse('bio:dailymetric-create')}?date={today.isoformat()}"
        return redirect(create_url)

class ActivityListView(LoginRequiredMixin, ListView):
    model = Activity
    template_name = "bio/activity_list.html"
    context_object_name = "activities"

    def get_queryset(self):
        period = self.request.GET.get("period", "7d")

        qs = Activity.objects.filter(user=self.request.user).order_by("-date", "-id")

        if period == "7d":
            cutoff = timezone.localdate() - timedelta(days=7)
            qs = qs.filter(date__gte=cutoff)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        period = self.request.GET.get("period", "7d")
        filtered_activities = self.get_queryset()

        context["period"] = period
        context["entries_count"] = filtered_activities.count()

        return context


class ActivityCreateView(LoginRequiredMixin, View):
    template_name = "bio/activity_form.html"

    def get(self, request):
        form = ActivityForm()
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "page_title": "Create Activity",
                "submit_label": "Save activity",
            },
        )

    def post(self, request):
        form = ActivityForm(request.POST)

        if form.is_valid():
            activity = form.save(commit=False)
            activity.user = request.user
            activity.save()

            user_id = request.user.id
            transaction.on_commit(lambda: recompute_recent_snapshots_for_user(user_id))

            return redirect("bio:activity-list")

        return render(
            request,
            self.template_name,
            {
                "form": form,
                "page_title": "Create Activity",
                "submit_label": "Save activity",
            },
        )


class ActivityUpdateView(LoginRequiredMixin, View):
    template_name = "bio/activity_form.html"

    def get_activity(self, request, pk):
        return get_object_or_404(Activity, pk=pk, user=request.user)

    def get(self, request, pk):
        activity = self.get_activity(request, pk)
        form = ActivityForm(instance=activity)
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "activity": activity,
                "page_title": "Edit Activity",
                "submit_label": "Save changes",
            },
        )

    def post(self, request, pk):
        activity = self.get_activity(request, pk)
        form = ActivityForm(request.POST, instance=activity)

        if form.is_valid():
            form.save()

            user_id = request.user.id
            transaction.on_commit(lambda: recompute_recent_snapshots_for_user(user_id))

            return redirect("bio:activity-list")

        return render(
            request,
            self.template_name,
            {
                "form": form,
                "activity": activity,
                "page_title": "Edit Activity",
                "submit_label": "Save changes",
            },
        )


class ActivityDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        activity = get_object_or_404(Activity, pk=pk, user=request.user)

        user_id = request.user.id
        activity.delete()
        transaction.on_commit(lambda: recompute_recent_snapshots_for_user(user_id))
        return redirect("bio:activity-list")

class BioOverviewView(LoginRequiredMixin, View):
    template_name = "bio/overview.html"
    

    def get(self, request):
        today = timezone.localdate()
        cutoff = today - timedelta(days=7)

        overview_analytics = _get_snapshot_or_fallback(
            user=request.user,
            period_days=7,
            snapshot_type=AnalyticsSnapshotType.OVERVIEW,
        )

        today_metric = (
            DailyMetric.objects
            .filter(user=request.user, date=today)
            .first()
        )

        today_activities = (
            Activity.objects
            .filter(user=request.user, date=today)
            .order_by("-id")
        )

        recent_metrics = (
            DailyMetric.objects
            .filter(user=request.user, date__gte=cutoff)
            .order_by("-date", "-id")
        )

        recent_activities = (
            Activity.objects
            .filter(user=request.user, date__gte=cutoff)
            .order_by("-date", "-id")
        )

        activities_count = today_activities.count()
        has_activities = activities_count > 0
        is_metric_complete = bool(today_metric)
        day_started = bool(today_metric) or has_activities
        day_complete = bool(today_metric) and has_activities

        metric_days_count = recent_metrics.count()
        activity_entries_count = recent_activities.count()

        avg_sleep = recent_metrics.exclude(sleep_quality__isnull=True).aggregate(avg=Avg("sleep_quality"))["avg"]
        avg_alcohol = recent_metrics.aggregate(avg=Avg("alcohol_units"))["avg"]

        sleep_alcohol_hint = None
        if avg_sleep is not None and avg_alcohol is not None:
            if avg_alcohol >= 4 and avg_sleep <= 2.5:
                sleep_alcohol_hint = "Higher alcohol intake may be affecting your sleep."
            elif avg_alcohol <= 1 and avg_sleep >= 4:
                sleep_alcohol_hint = "Low alcohol intake and good sleep look consistent."
            elif avg_sleep <= 2.5:
                sleep_alcohol_hint = "Your recent sleep quality looks low."
            elif avg_sleep >= 4:
                sleep_alcohol_hint = "Your recent sleep quality looks strong."

        consistency_hint = None
        if metric_days_count >= 6:
            consistency_hint = "Daily tracking looks very consistent."
        elif metric_days_count >= 3:
            consistency_hint = "You have a usable tracking baseline for the last week."
        else:
            consistency_hint = "You need more daily entries to build useful trends."

        activity_hint = None
        if activity_entries_count >= 5:
            activity_hint = "You have logged activities on a strong weekly rhythm."
        elif activity_entries_count >= 2:
            activity_hint = "You have some activity data for the week."
        else:
            activity_hint = "Activity logging is still sparse this week."

        context = {
            "today": today,
            "today_metric": today_metric,
            "today_activities": today_activities,
            "is_metric_complete": is_metric_complete,
            "activities_count": activities_count,
            "has_activities": has_activities,
            "day_started": day_started,
            "day_complete": day_complete,
            "sleep_alcohol_hint": sleep_alcohol_hint,
            "consistency_hint": consistency_hint,
            "activity_hint": activity_hint,
            "metric_days_count": metric_days_count,
            "activity_entries_count": activity_entries_count,
            "overview_analytics": overview_analytics,
        }

        return render(request, self.template_name, context)

def _resolve_period_days(period_param: str) -> int:
    period_map = {
        "7d": 7,
        "14d": 14,
        "30d": 30,
    }
    return period_map.get(period_param, 7)

class BioAnalyticsView(LoginRequiredMixin, View):
    template_name = "bio/analytics.html"

    def get(self, request):
        period_param = request.GET.get("period", "7d")
        period_days = _resolve_period_days(period_param)

        analytics = _get_snapshot_or_fallback(
            user=request.user,
            period_days=period_days,
            snapshot_type=AnalyticsSnapshotType.ANALYTICS,
        )

        context = {
            "period": period_param,
            "analytics": analytics,
        }
        return render(request, self.template_name, context)

class BioAnalyticsExportJsonView(LoginRequiredMixin, View):
    def get(self, request):
        period_param = request.GET.get("period", "7d")
        period_days = _resolve_period_days(period_param)

        report = build_bio_analytics_report(
            user=request.user,
            period_days=period_days,
        )
        return JsonResponse(report, json_dumps_params={"indent": 2})

class BioAnalyticsExportCsvView(LoginRequiredMixin, View):
    def get(self, request):
        period_param = request.GET.get("period", "7d")
        period_days = _resolve_period_days(period_param)

        end_date = timezone.localdate()
        start_date = end_date - timedelta(days=period_days - 1)

        rows = build_bio_daily_csv_rows(
            user=request.user,
            start_date=start_date,
            end_date=end_date,
        )

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="bio-daily-export-{request.user.username}-{period_param}.csv"'
        )

        fieldnames = [
            "date",
            "metric_logged",
            "has_metric",
            "weight_kg",
            "sleep_quality",
            "alcohol_units",
            "calories_planned",
            "calories_actual",
            "diet_mode",
            "activity_logged",
            "has_activity",
            "activity_entries",
            "activity_minutes_raw",
            "activity_minutes",
            "activity_calories_raw",
            "activity_calories",
            "activity_distance_km_raw",
            "activity_distance_km",
            "activity_duration_outlier_count",
            "activity_distance_outlier_count",
            "activity_calories_outlier_count",
            "activity_type_count",
            "activity_types",
            "strength_sessions",
            "strength_exercise_count",
            "strength_set_count",
            "strength_volume_load",
            "strength_training_load_score",
            "strength_training_day",
            "calorie_delta",
            "calorie_target_hit",
            "weight_change_1d",
            "sleep_low_flag",
            "alcohol_high_flag",
        ]

        writer = csv.DictWriter(response, fieldnames=fieldnames)
        writer.writeheader()

        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})

        return response