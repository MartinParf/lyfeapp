from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from redis import Redis


@require_GET
@never_cache
def health_check(request):
    checks = {
        "database": "unknown",
        "redis": "unknown",
    }

    status_code = 200

    try:
        connection.ensure_connection()
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
        status_code = 503

    try:
        redis_client = Redis(
            host=getattr(settings, "REDIS_HOST", "redis"),
            port=getattr(settings, "REDIS_PORT", 6379),
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        redis_client.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"
        status_code = 503

    payload = {
        "status": "ok" if status_code == 200 else "error",
        **checks,
    }

    response = JsonResponse(payload, status=status_code)
    response["Cache-Control"] = "no-store"
    return response