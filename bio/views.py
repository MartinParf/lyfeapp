from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView
from django.utils import timezone
from datetime import timedelta
from django.db.models import Avg
from django.urls import reverse

from .forms import ActivityForm, DailyMetricForm
from .models import Activity, DailyMetric


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
        metric.delete()
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
        activity.delete()
        return redirect("bio:activity-list")

class BioOverviewView(LoginRequiredMixin, View):
    template_name = "bio/overview.html"

    def get(self, request):
        today = timezone.localdate()
        cutoff = today - timedelta(days=7)

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
        }

        return render(request, self.template_name, context)