from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from redis import Redis


REDIS_HEALTH_TIMEOUT_SECONDS = 0.75


def _ping_redis() -> None:
    redis_client = Redis(
        host=getattr(settings, "REDIS_HOST", "redis"),
        port=getattr(settings, "REDIS_PORT", 6379),
        socket_connect_timeout=0.25,
        socket_timeout=0.25,
        retry_on_timeout=False,
        health_check_interval=0,
    )
    redis_client.ping()


def _check_redis_with_timeout() -> bool:
    executor = ThreadPoolExecutor(max_workers=1)

    try:
        future = executor.submit(_ping_redis)
        future.result(timeout=REDIS_HEALTH_TIMEOUT_SECONDS)
        return True
    except (FutureTimeoutError, Exception):
        return False
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


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

    if _check_redis_with_timeout():
        checks["redis"] = "ok"
    else:
        checks["redis"] = "error"
        status_code = 503

    payload = {
        "status": "ok" if status_code == 200 else "error",
        **checks,
    }

    response = JsonResponse(payload, status=status_code)
    response["Cache-Control"] = "no-store"
    return response