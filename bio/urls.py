from django.urls import path

from .views import (
    ActivityCreateView,
    ActivityDeleteView,
    ActivityListView,
    ActivityUpdateView,
    DailyMetricCreateView,
    DailyMetricDeleteView,
    DailyMetricListView,
    DailyMetricUpdateView,
    DailyMetricTodayView,
    BioOverviewView,
)

app_name = "bio"

urlpatterns = [
    path("", BioOverviewView.as_view(), name="overview"),
    path("daily-metrics/", DailyMetricListView.as_view(), name="dailymetric-list"),
    path("daily-metrics/create/", DailyMetricCreateView.as_view(), name="dailymetric-create"),
    path("daily-metrics/today/", DailyMetricTodayView.as_view(), name="dailymetric-today"),
    path("daily-metrics/<int:pk>/edit/", DailyMetricUpdateView.as_view(), name="dailymetric-edit"),
    path("daily-metrics/<int:pk>/delete/", DailyMetricDeleteView.as_view(), name="dailymetric-delete"),
    path("activities/", ActivityListView.as_view(), name="activity-list"),
    path("activities/create/", ActivityCreateView.as_view(), name="activity-create"),
    path("activities/<int:pk>/edit/", ActivityUpdateView.as_view(), name="activity-edit"),
    path("activities/<int:pk>/delete/", ActivityDeleteView.as_view(), name="activity-delete"),
    
]