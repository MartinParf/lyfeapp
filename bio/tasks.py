from django.contrib.auth import get_user_model
from huey import crontab
from huey.contrib.djhuey import db_periodic_task, db_task

from bio.models import AnalyticsSnapshotStatus, AnalyticsSnapshotType
from bio.services.analytics import (
    get_bio_analytics_snapshot,
    get_snapshot_max_age_hours,
    mark_snapshot_error,
    queue_snapshot_refresh,
    store_bio_analytics_snapshot,
)

User = get_user_model()

ANALYTICS_WINDOWS = (7, 14, 30)


@db_task()
def recompute_analytics_snapshot(user_id: int, period_days: int) -> dict:
    user = User.objects.get(pk=user_id)

    try:
        store_bio_analytics_snapshot(
            user=user,
            period_days=period_days,
            snapshot_type=AnalyticsSnapshotType.ANALYTICS,
        )
    except Exception as exc:
        mark_snapshot_error(
            user=user,
            period_days=period_days,
            snapshot_type=AnalyticsSnapshotType.ANALYTICS,
            error=str(exc),
        )
        raise

    return {
        "user_id": user_id,
        "snapshot_type": AnalyticsSnapshotType.ANALYTICS,
        "window_days": period_days,
    }


@db_task()
def recompute_overview_snapshot(user_id: int) -> dict:
    user = User.objects.get(pk=user_id)

    try:
        store_bio_analytics_snapshot(
            user=user,
            period_days=7,
            snapshot_type=AnalyticsSnapshotType.OVERVIEW,
        )
    except Exception as exc:
        mark_snapshot_error(
            user=user,
            period_days=7,
            snapshot_type=AnalyticsSnapshotType.OVERVIEW,
            error=str(exc),
        )
        raise

    return {
        "user_id": user_id,
        "snapshot_type": AnalyticsSnapshotType.OVERVIEW,
        "window_days": 7,
    }


@db_task()
def recompute_recent_snapshots_for_user(user_id: int) -> dict:
    user = User.objects.get(pk=user_id)

    try:
        store_bio_analytics_snapshot(
            user=user,
            period_days=7,
            snapshot_type=AnalyticsSnapshotType.OVERVIEW,
        )

        for window_days in ANALYTICS_WINDOWS:
            store_bio_analytics_snapshot(
                user=user,
                period_days=window_days,
                snapshot_type=AnalyticsSnapshotType.ANALYTICS,
            )
    except Exception as exc:
        mark_snapshot_error(
            user=user,
            period_days=7,
            snapshot_type=AnalyticsSnapshotType.OVERVIEW,
            error=str(exc),
        )
        raise

    return {
        "user_id": user_id,
        "windows": list(ANALYTICS_WINDOWS),
        "overview": True,
    }


@db_task()
def ensure_user_snapshots_exist(user_id: int) -> dict:
    user = User.objects.get(pk=user_id)
    created = []

    overview = get_bio_analytics_snapshot(
        user=user,
        period_days=7,
        snapshot_type=AnalyticsSnapshotType.OVERVIEW,
    )
    if overview is None:
        store_bio_analytics_snapshot(
            user=user,
            period_days=7,
            snapshot_type=AnalyticsSnapshotType.OVERVIEW,
        )
        created.append(("OVERVIEW", 7))

    for window_days in ANALYTICS_WINDOWS:
        snapshot = get_bio_analytics_snapshot(
            user=user,
            period_days=window_days,
            snapshot_type=AnalyticsSnapshotType.ANALYTICS,
        )
        if snapshot is None:
            store_bio_analytics_snapshot(
                user=user,
                period_days=window_days,
                snapshot_type=AnalyticsSnapshotType.ANALYTICS,
            )
            created.append(("ANALYTICS", window_days))

    return {
        "user_id": user_id,
        "created": created,
    }


@db_task()
def repair_stale_snapshots_for_user(user_id: int) -> dict:
    user = User.objects.get(pk=user_id)
    repaired = []

    overview = get_bio_analytics_snapshot(
        user=user,
        period_days=7,
        snapshot_type=AnalyticsSnapshotType.OVERVIEW,
    )
    if overview is None:
        store_bio_analytics_snapshot(
            user=user,
            period_days=7,
            snapshot_type=AnalyticsSnapshotType.OVERVIEW,
        )
        repaired.append(("OVERVIEW", 7, "created"))
    elif (
        overview.is_stale(max_age_hours=get_snapshot_max_age_hours(AnalyticsSnapshotType.OVERVIEW))
        or overview.status != AnalyticsSnapshotStatus.FRESH
        or overview.last_success_at is None
    ):
        store_bio_analytics_snapshot(
            user=user,
            period_days=7,
            snapshot_type=AnalyticsSnapshotType.OVERVIEW,
        )
        repaired.append(("OVERVIEW", 7, "refreshed"))

    for window_days in ANALYTICS_WINDOWS:
        snapshot = get_bio_analytics_snapshot(
            user=user,
            period_days=window_days,
            snapshot_type=AnalyticsSnapshotType.ANALYTICS,
        )
        if snapshot is None:
            store_bio_analytics_snapshot(
                user=user,
                period_days=window_days,
                snapshot_type=AnalyticsSnapshotType.ANALYTICS,
            )
            repaired.append(("ANALYTICS", window_days, "created"))
        elif (
            snapshot.is_stale(max_age_hours=get_snapshot_max_age_hours(AnalyticsSnapshotType.ANALYTICS))
            or snapshot.status != AnalyticsSnapshotStatus.FRESH
            or snapshot.last_success_at is None
        ):
            store_bio_analytics_snapshot(
                user=user,
                period_days=window_days,
                snapshot_type=AnalyticsSnapshotType.ANALYTICS,
            )
            repaired.append(("ANALYTICS", window_days, "refreshed"))

    return {
        "user_id": user_id,
        "repaired": repaired,
    }


@db_periodic_task(crontab(hour="2", minute="15"))
def nightly_recompute_recent_snapshots() -> None:
    for user_id in User.objects.values_list("id", flat=True):
        recompute_recent_snapshots_for_user(user_id)


@db_periodic_task(crontab(hour="3", minute="10"))
def nightly_repair_snapshots() -> None:
    for user_id in User.objects.values_list("id", flat=True):
        repair_stale_snapshots_for_user(user_id)