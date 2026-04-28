from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.template.response import TemplateResponse
from django.urls import include, path
from django.views.generic import RedirectView, TemplateView

from core.views import health_check, ops_dashboard


def service_worker(request):
    response = TemplateResponse(
        request,
        "sw.js",
        content_type="application/javascript",
    )
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


urlpatterns = [
    path("admin/", admin.site.urls),
    path("fitness/", include("fitness.urls", namespace="fitness")),
    path("bio/", include("bio.urls", namespace="bio")),
    path("health/", health_check, name="health"),
    path("ops/", ops_dashboard, name="ops-dashboard"),
    path(
        "offline/",
        TemplateView.as_view(template_name="offline.html"),
        name="offline",
    ),
    path(
        "sw.js",
        service_worker,
        name="service-worker",
    ),
    path(
        "favicon.ico",
        RedirectView.as_view(url="/static/core/icons/icon-192.svg", permanent=True),
        name="favicon",
    ),
    path("", RedirectView.as_view(pattern_name="bio:overview", permanent=False)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)