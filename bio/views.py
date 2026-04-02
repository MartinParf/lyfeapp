from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView

from .forms import ActivityForm, DailyMetricForm
from .models import Activity, DailyMetric


class DailyMetricListView(LoginRequiredMixin, ListView):
    model = DailyMetric
    template_name = "bio/dailymetric_list.html"
    context_object_name = "metrics"

    def get_queryset(self):
        return DailyMetric.objects.filter(user=self.request.user).order_by("-date", "-id")


class DailyMetricCreateView(LoginRequiredMixin, View):
    template_name = "bio/dailymetric_form.html"

    def get(self, request):
        form = DailyMetricForm()
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


class ActivityListView(LoginRequiredMixin, ListView):
    model = Activity
    template_name = "bio/activity_list.html"
    context_object_name = "activities"

    def get_queryset(self):
        return Activity.objects.filter(user=self.request.user).order_by("-date", "-id")


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