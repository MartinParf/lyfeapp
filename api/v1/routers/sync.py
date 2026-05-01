from django.db.models import Prefetch
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from ninja import Router
from datetime import timezone as dt_timezone

from api.exceptions import ApiError
from api.v1.schemas.common import ApiErrorResponseSchema
from api.v1.schemas.sync import SyncChangesResponseSchema
from api.v1.security import api_jwt_bearer
from api.v1.serializers.profile import serialize_profile
from bio.models import Activity, DailyMetric, Profile
from bio.services.activity_commands import serialize_activity
from bio.services.daily_metric_commands import serialize_daily_metric
from fitness.models import WorkoutSession, WorkoutSessionExercise, WorkoutSet
from fitness.services.sync import serialize_workout_session_tree_sync

SYNC_CONTRACT_VERSION = "1"
router = Router(tags=["sync"])


def _parse_since(value: str):
    if not value:
        raise ApiError(
            code="validation_error",
            message="Sync validation failed.",
            status=400,
            details={"since": "Query parameter 'since' is required."},
        )

    parsed = parse_datetime(value)
    if parsed is None:
        raise ApiError(
            code="validation_error",
            message="Sync validation failed.",
            status=400,
            details={"since": "Use ISO datetime with timezone, e.g. 2026-05-01T10:00:00+00:00."},
        )

    if timezone.is_naive(parsed):
        raise ApiError(
            code="validation_error",
            message="Sync validation failed.",
            status=400,
            details={"since": "Timezone-aware datetime is required."},
        )

    return parsed.astimezone(dt_timezone.utc)


def _split_created_updated(items, serializer, since):
    created = []
    updated = []

    for item in items:
        payload = serializer(item)
        if item.created_at > since:
            created.append(payload)
        else:
            updated.append(payload)

    return created, updated


def _serialize_deleted_ref(obj):
    client_uuid = getattr(obj, "client_uuid", None)
    return {
        "id": obj.id,
        "client_uuid": str(client_uuid) if client_uuid else None,
        "deleted_at": obj.deleted_at.isoformat(),
    }


@router.get(
    "/changes/",
    response={
        200: SyncChangesResponseSchema,
        400: ApiErrorResponseSchema,
        401: ApiErrorResponseSchema,
        403: ApiErrorResponseSchema,
    },
    auth=api_jwt_bearer,
    summary="Delta sync changes",
    description=(
        "Return server-side changes since the provided timestamp. "
        "Workout sessions are returned as full nested trees so child exercise/set "
        "changes are represented via parent session updates."
    ),
)
def sync_changes(request, since: str):
    parsed_since = _parse_since(since)
    synced_at = timezone.now()

    profile_obj = Profile.objects.select_related("user").filter(user=request.user).first()
    profile_created = []
    profile_updated = []
    if profile_obj and profile_obj.updated_at > parsed_since:
        payload = serialize_profile(request, profile_obj)
        if profile_obj.created_at > parsed_since:
            profile_created.append(payload)
        else:
            profile_updated.append(payload)

    daily_metric_qs = DailyMetric.objects.filter(
        user=request.user,
        updated_at__gt=parsed_since,
    ).order_by("updated_at", "id")
    daily_metric_created, daily_metric_updated = _split_created_updated(
        daily_metric_qs,
        serialize_daily_metric,
        parsed_since,
    )

    activity_active_qs = Activity.objects.filter(
        user=request.user,
        deleted_at__isnull=True,
        updated_at__gt=parsed_since,
    ).order_by("updated_at", "id")
    activity_created, activity_updated = _split_created_updated(
        activity_active_qs,
        serialize_activity,
        parsed_since,
    )
    activity_deleted = [
        _serialize_deleted_ref(obj)
        for obj in Activity.objects.filter(
            user=request.user,
            deleted_at__gt=parsed_since,
        ).order_by("deleted_at", "id")
    ]

    session_qs = (
        WorkoutSession.objects.filter(
            user=request.user,
            deleted_at__isnull=True,
            updated_at__gt=parsed_since,
        )
        .select_related("source_pool")
        .prefetch_related(
            Prefetch(
                "session_exercises",
                queryset=WorkoutSessionExercise.objects.select_related(
                    "exercise",
                    "source_pool_item",
                )
                .prefetch_related(
                    Prefetch(
                        "sets",
                        queryset=WorkoutSet.objects.order_by("set_order", "id"),
                    )
                )
                .order_by("sequence", "id"),
            )
        )
        .order_by("updated_at", "id")
    )
    session_created, session_updated = _split_created_updated(
        session_qs,
        serialize_workout_session_tree_sync,
        parsed_since,
    )
    session_deleted = [
        _serialize_deleted_ref(obj)
        for obj in WorkoutSession.objects.filter(
            user=request.user,
            deleted_at__gt=parsed_since,
        ).order_by("deleted_at", "id")
    ]

    return {
        "ok": True,
        "data": {
            "sync_contract_version": SYNC_CONTRACT_VERSION,
            "since": parsed_since.isoformat(),
            "synced_at": synced_at.isoformat(),
            "profile": {
                "created": profile_created,
                "updated": profile_updated,
                "deleted": [],
                "deletion_mode": "not_applicable",
            },
            "daily_metrics": {
                "created": daily_metric_created,
                "updated": daily_metric_updated,
                "deleted": [],
                "deletion_mode": "not_supported_yet",
            },
            "activities": {
                "created": activity_created,
                "updated": activity_updated,
                "deleted": activity_deleted,
                "deletion_mode": "soft_delete",
            },
            "workout_sessions": {
                "created": session_created,
                "updated": session_updated,
                "deleted": session_deleted,
                "deletion_mode": "soft_delete_full_tree",
                "payload_mode": "full_tree",
            },
        },
    }