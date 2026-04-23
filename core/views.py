import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import timezone as datetime_timezone
from pathlib import Path

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db import connection
from django.db.models import Count, Max
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe
from redis import Redis


REDIS_HEALTH_TIMEOUT_SECONDS = 0.75
OPS_METADATA_DIR = Path(settings.BASE_DIR) / "runtime" / "ops"


def _check_database() -> bool:
    try:
        connection.ensure_connection()
        return True
    except Exception:
        return False


def _ping_redis() -> None:
    redis_client = Redis(
        host=getattr(settings, "REDIS_HOST", "redis"),
        port=int(getattr(settings, "REDIS_PORT", 6379)),
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


@require_safe
@never_cache
def health_check(request):
    database_ok = _check_database()
    redis_ok = _check_redis_with_timeout()

    status_code = 200 if database_ok and redis_ok else 503

    payload = {
        "status": "ok" if status_code == 200 else "error",
        "database": "ok" if database_ok else "error",
        "redis": "ok" if redis_ok else "error",
    }

    response = JsonResponse(payload, status=status_code)
    response["Cache-Control"] = "no-store"
    return response


def _parse_datetime(value):
    if not value:
        return None

    parsed = parse_datetime(value)

    if parsed is None:
        return None

    if timezone.is_naive(parsed):
        parsed = parsed.replace(tzinfo=datetime_timezone.utc)

    return parsed


def _age_summary(created_at_value, warn_after_hours):
    created_at = _parse_datetime(created_at_value)

    if created_at is None:
        return {
            "state": "unknown",
            "label": "unknown",
            "hours": None,
        }

    age = timezone.now() - created_at
    age_hours = round(age.total_seconds() / 3600, 1)

    if age_hours <= warn_after_hours:
        state = "ok"
    elif age_hours <= warn_after_hours * 1.5:
        state = "warn"
    else:
        state = "error"

    if age_hours < 48:
        label = f"{age_hours:.1f} h ago"
    else:
        label = f"{age_hours / 24:.1f} d ago"

    return {
        "state": state,
        "label": label,
        "hours": age_hours,
    }


def _read_ops_json(filename, warn_after_hours):
    path = OPS_METADATA_DIR / filename

    if not path.exists():
        return {
            "exists": False,
            "state": "missing",
            "status": "missing",
            "path": str(path),
            "created_at_utc": None,
            "age": {
                "state": "missing",
                "label": "missing",
                "hours": None,
            },
            "payload": {},
        }

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "exists": True,
            "state": "error",
            "status": "error",
            "path": str(path),
            "created_at_utc": None,
            "age": {
                "state": "error",
                "label": "unreadable",
                "hours": None,
            },
            "payload": {},
        }

    age = _age_summary(payload.get("created_at_utc"), warn_after_hours)
    status = payload.get("status", "unknown")

    if status != "ok":
        state = "error"
    else:
        state = age["state"]

    return {
        "exists": True,
        "state": state,
        "status": status,
        "path": str(path),
        "created_at_utc": payload.get("created_at_utc"),
        "age": age,
        "payload": payload,
    }


def _read_service_worker_version():
    sw_path = Path(settings.BASE_DIR) / "templates" / "sw.js"

    if not sw_path.exists():
        return "unknown"

    try:
        content = sw_path.read_text(encoding="utf-8")
    except Exception:
        return "unknown"

    match = re.search(r'const\s+SW_VERSION\s*=\s*"([^"]+)"', content)
    return match.group(1) if match else "unknown"


def _build_snapshot_summary():
    try:
        from bio.models import AnalyticsSnapshot
    except Exception:
        return {
            "available": False,
            "state": "unknown",
            "total": 0,
            "by_status": [],
            "failed": 0,
            "stale": 0,
            "latest_success_at": None,
        }

    by_status = list(
        AnalyticsSnapshot.objects.values("status")
        .annotate(count=Count("id"))
        .order_by("status")
    )

    failed = AnalyticsSnapshot.objects.filter(status="FAILED").count()
    stale = AnalyticsSnapshot.objects.filter(status="STALE").count()
    total = AnalyticsSnapshot.objects.count()
    latest_success_at = AnalyticsSnapshot.objects.aggregate(
        latest=Max("last_success_at")
    )["latest"]

    if failed:
        state = "error"
    elif stale:
        state = "warn"
    else:
        state = "ok"

    return {
        "available": True,
        "state": state,
        "total": total,
        "by_status": by_status,
        "failed": failed,
        "stale": stale,
        "latest_success_at": latest_success_at,
    }


@staff_member_required
@never_cache
def ops_dashboard(request):
    database_ok = _check_database()
    redis_ok = _check_redis_with_timeout()

    health_state = "ok" if database_ok and redis_ok else "error"

    backup = _read_ops_json("last_backup.json", warn_after_hours=36)
    docker_hygiene = _read_ops_json(
        "last_docker_hygiene.json",
        warn_after_hours=24 * 8,
    )
    deploy = _read_ops_json("last_deploy.json", warn_after_hours=24 * 14)
    previous_deploy = _read_ops_json("previous_deploy.json", warn_after_hours=24 * 30)
    release_backup = _read_ops_json("last_release_backup.json", warn_after_hours=24 * 30)
    snapshots = _build_snapshot_summary()

    context = {
        "health": {
            "state": health_state,
            "database": "ok" if database_ok else "error",
            "redis": "ok" if redis_ok else "error",
        },
        "backup": backup,
        "docker_hygiene": docker_hygiene,
        "snapshots": snapshots,
        "versions": {
            "service_worker": _read_service_worker_version(),
            "app_version": deploy["payload"].get("git_sha")
            or os.environ.get("APP_VERSION")
            or os.environ.get("GIT_SHA")
            or "unknown",
        },
        "deploy": deploy,
        "previous_deploy": previous_deploy,
        "release_backup": release_backup,
        "ops_links": [
            {
                "label": "Health JSON",
                "url": "/health/",
                "external": False,
            },
            {
                "label": "Django admin",
                "url": "/admin/",
                "external": False,
            },
            {
                "label": "Uptime Kuma",
                "url": "https://monitor.lyfeapp.cz",
                "external": True,
            },
            {
                "label": "Dozzle logs",
                "url": "https://logs.lyfeapp.cz",
                "external": True,
            },
        ],
    }

    return render(request, "core/ops_dashboard.html", context)