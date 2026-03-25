from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("fitness/", include("fitness.urls", namespace="fitness")),
    path("", RedirectView.as_view(pattern_name="fitness:exercise-list", permanent=False)),
]