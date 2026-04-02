from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("fitness/", include("fitness.urls", namespace="fitness")),
    path("bio/", include("bio.urls", namespace="bio")),
    path("", RedirectView.as_view(pattern_name="fitness:session-list", permanent=False)),
]