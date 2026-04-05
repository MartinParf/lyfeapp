from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView, TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("fitness/", include("fitness.urls", namespace="fitness")),
    path("bio/", include("bio.urls", namespace="bio")),
    path(
        "offline/",
        TemplateView.as_view(template_name="offline.html"),
        name="offline",
    ),
    path(
        "sw.js",
        TemplateView.as_view(
            template_name="sw.js",
            content_type="application/javascript",
        ),
        name="service-worker",
    ),
    path("", RedirectView.as_view(pattern_name="bio:overview", permanent=False)),
]