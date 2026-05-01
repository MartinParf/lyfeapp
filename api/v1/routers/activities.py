from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from ninja import Router

from api.exceptions import ApiError
from api.v1.schemas.activities import (
    ActivityCreateInputSchema,
    ActivityCreateResponseSchema,
)
from api.v1.schemas.common import ApiErrorResponseSchema
from api.v1.security import api_jwt_bearer
from bio.models import Activity, ActivityType
from bio.tasks import recompute_recent_snapshots_for_user


router = Router(tags=["activities"])


def _serialize_activity(activity: Activity) -> dict:
    return {
        "id": activity.id,
        "client_uuid": str(activity.client_uuid) if activity.client_uuid else "",
        "date": activity.date.isoformat(),
        "activity_type": activity.activity_type,
        "duration_minutes": activity.duration_minutes,
        "calories_burned_est": activity.calories_burned_est,
        "distance_km": str(activity.distance_km) if activity.distance_km is not None else None,
        "notes": activity.notes,
        "version": activity.version,
        "deleted_at": activity.deleted_at.isoformat() if activity.deleted_at else None,
        "created_at": activity.created_at.isoformat(),
        "updated_at": activity.updated_at.isoformat(),
    }


@router.post(
    "/",
    response={
        201: ActivityCreateResponseSchema,
        200: ActivityCreateResponseSchema,
        400: ApiErrorResponseSchema,
        401: ApiErrorResponseSchema,
        403: ApiErrorResponseSchema,
    },
    auth=api_jwt_bearer,
    summary="Create activity",
    description="Create a new activity using client_uuid idempotency. Replays return the existing object.",
)
@transaction.atomic
def activity_create(request, payload: ActivityCreateInputSchema):
    existing = Activity.objects.filter(
        user=request.user,
        client_uuid=payload.client_uuid,
    ).first()
    if existing:
        return 200, {
            "ok": True,
            "data": _serialize_activity(existing),
            "created": False,
        }

    allowed_types = {choice for choice, _label in ActivityType.choices}
    if payload.activity_type not in allowed_types:
        raise ApiError(
            code="validation_error",
            message="Activity create validation failed.",
            status=400,
            details={
                "activity_type": f"Invalid activity_type. Allowed: {', '.join(sorted(allowed_types))}."
            },
        )

    try:
        parsed_date = date.fromisoformat(payload.date)
    except ValueError:
        raise ApiError(
            code="validation_error",
            message="Activity create validation failed.",
            status=400,
            details={"date": "Use ISO format YYYY-MM-DD."},
        )

    distance_value = None
    if payload.distance_km not in (None, ""):
        try:
            distance_value = Decimal(str(payload.distance_km))
        except (InvalidOperation, TypeError, ValueError):
            raise ApiError(
                code="validation_error",
                message="Activity create validation failed.",
                status=400,
                details={"distance_km": "Distance must be a decimal number."},
            )

    activity = Activity(
        user=request.user,
        client_uuid=payload.client_uuid,
        date=parsed_date,
        activity_type=payload.activity_type,
        duration_minutes=payload.duration_minutes,
        calories_burned_est=payload.calories_burned_est,
        distance_km=distance_value,
        notes=(payload.notes or "").strip(),
    )

    try:
        activity.full_clean()
    except Exception as exc:
        if hasattr(exc, "message_dict"):
            details = {k: "; ".join(v) for k, v in exc.message_dict.items()}
        else:
            details = {"non_field_errors": getattr(exc, "messages", ["Validation failed."])}
        raise ApiError(
            code="validation_error",
            message="Activity create validation failed.",
            status=400,
            details=details,
        )

    activity.save()

    user_id = request.user.id
    transaction.on_commit(lambda: recompute_recent_snapshots_for_user(user_id))

    return 201, {
        "ok": True,
        "data": _serialize_activity(activity),
        "created": True,
    }