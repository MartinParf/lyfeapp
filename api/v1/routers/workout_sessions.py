from datetime import date
from django.shortcuts import get_object_or_404

from django.db import transaction
from ninja import Router

from api.exceptions import ApiError
from api.v1.schemas.common import ApiErrorResponseSchema
from api.v1.schemas.workout_sessions import (
    WorkoutSessionCreateInputSchema,
    WorkoutSessionCreateResponseSchema,
)
from api.v1.schemas.workout_session_lifecycle import (
    WorkoutSessionLifecycleResponseSchema,
)
from fitness.services.session_lifecycle import (
    cancel_session,
    complete_session,
    start_session,
)
from api.v1.security import api_jwt_bearer
from fitness.models import (
    ExercisePool,
    PoolFocus,
    WorkoutSession,
    WorkoutSessionExercise,
    WorkoutSessionStatus,
)


router = Router(tags=["workout-sessions"])


def _serialize_workout_session(session: WorkoutSession, *, imported_exercise_count: int = 0) -> dict:
    return {
        "id": session.id,
        "client_uuid": str(session.client_uuid) if session.client_uuid else "",
        "focus": session.focus,
        "source_pool_id": session.source_pool_id,
        "status": session.status,
        "scheduled_date": session.scheduled_date.isoformat() if session.scheduled_date else None,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "notes": session.notes,
        "version": session.version,
        "deleted_at": session.deleted_at.isoformat() if session.deleted_at else None,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "imported_exercise_count": imported_exercise_count,
    }

def _serialize_session_lifecycle(session, *, changed: bool) -> dict:
    return {
        "id": session.id,
        "status": session.status,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "version": session.version,
        "updated_at": session.updated_at.isoformat(),
        "changed": changed,
    }


@router.post(
    "/",
    response={
        201: WorkoutSessionCreateResponseSchema,
        200: WorkoutSessionCreateResponseSchema,
        400: ApiErrorResponseSchema,
        401: ApiErrorResponseSchema,
        403: ApiErrorResponseSchema,
    },
    auth=api_jwt_bearer,
    summary="Create workout session",
    description="Create a new workout session using client_uuid idempotency. Replays return the existing session.",
)
@transaction.atomic
def workout_session_create(request, payload: WorkoutSessionCreateInputSchema):
    existing = WorkoutSession.objects.filter(
        user=request.user,
        client_uuid=payload.client_uuid,
    ).first()
    if existing:
        imported_exercise_count = existing.session_exercises.count()
        return 200, {
            "ok": True,
            "data": _serialize_workout_session(
                existing,
                imported_exercise_count=imported_exercise_count,
            ),
            "created": False,
        }

    allowed_focus = {choice for choice, _label in PoolFocus.choices}
    if payload.focus not in allowed_focus:
        raise ApiError(
            code="validation_error",
            message="Workout session create validation failed.",
            status=400,
            details={
                "focus": f"Invalid focus. Allowed: {', '.join(sorted(allowed_focus))}."
            },
        )

    parsed_scheduled_date = None
    if payload.scheduled_date not in (None, ""):
        try:
            parsed_scheduled_date = date.fromisoformat(payload.scheduled_date)
        except ValueError:
            raise ApiError(
                code="validation_error",
                message="Workout session create validation failed.",
                status=400,
                details={"scheduled_date": "Use ISO format YYYY-MM-DD."},
            )

    source_pool = None
    if payload.source_pool_id is not None:
        source_pool = ExercisePool.objects.filter(
            id=payload.source_pool_id,
            user=request.user,
            is_active=True,
        ).first()
        if not source_pool:
            raise ApiError(
                code="validation_error",
                message="Workout session create validation failed.",
                status=400,
                details={"source_pool_id": "Source pool was not found or is inactive."},
            )

    session = WorkoutSession(
        user=request.user,
        client_uuid=payload.client_uuid,
        focus=payload.focus,
        source_pool=source_pool,
        status=WorkoutSessionStatus.PLANNED,
        scheduled_date=parsed_scheduled_date,
        notes=(payload.notes or "").strip(),
    )

    try:
        session.full_clean()
    except Exception as exc:
        if hasattr(exc, "message_dict"):
            details = {k: "; ".join(v) for k, v in exc.message_dict.items()}
        else:
            details = {"non_field_errors": getattr(exc, "messages", ["Validation failed."])}
        raise ApiError(
            code="validation_error",
            message="Workout session create validation failed.",
            status=400,
            details=details,
        )

    session.save()

    imported_exercise_count = 0
    if source_pool:
        pool_items = source_pool.items.filter(is_active=True).select_related("exercise").order_by("sequence", "id")
        session_exercises = [
            WorkoutSessionExercise(
                session=session,
                exercise=item.exercise,
                sequence=item.sequence,
                source_pool_item=item,
            )
            for item in pool_items
        ]
        if session_exercises:
            WorkoutSessionExercise.objects.bulk_create(session_exercises)
            imported_exercise_count = len(session_exercises)

    return 201, {
        "ok": True,
        "data": _serialize_workout_session(
            session,
            imported_exercise_count=imported_exercise_count,
        ),
        "created": True,
    }

@router.post(
    "/{session_id}/start/",
    response={
        200: WorkoutSessionLifecycleResponseSchema,
        409: ApiErrorResponseSchema,
        400: ApiErrorResponseSchema,
        401: ApiErrorResponseSchema,
        403: ApiErrorResponseSchema,
    },
    auth=api_jwt_bearer,
    summary="Start workout session",
    description="Transition a planned session into in-progress state.",
)
@transaction.atomic
def workout_session_start(request, session_id: int):
    session = get_object_or_404(WorkoutSession, id=session_id, user=request.user)
    session, changed = start_session(session)
    return {
        "ok": True,
        "data": _serialize_session_lifecycle(session, changed=changed),
    }


@router.post(
    "/{session_id}/complete/",
    response={
        200: WorkoutSessionLifecycleResponseSchema,
        409: ApiErrorResponseSchema,
        400: ApiErrorResponseSchema,
        401: ApiErrorResponseSchema,
        403: ApiErrorResponseSchema,
    },
    auth=api_jwt_bearer,
    summary="Complete workout session",
    description="Transition an in-progress session into completed state.",
)
@transaction.atomic
def workout_session_complete(request, session_id: int):
    session = get_object_or_404(WorkoutSession, id=session_id, user=request.user)
    session, changed = complete_session(session)
    return {
        "ok": True,
        "data": _serialize_session_lifecycle(session, changed=changed),
    }


@router.post(
    "/{session_id}/cancel/",
    response={
        200: WorkoutSessionLifecycleResponseSchema,
        409: ApiErrorResponseSchema,
        400: ApiErrorResponseSchema,
        401: ApiErrorResponseSchema,
        403: ApiErrorResponseSchema,
    },
    auth=api_jwt_bearer,
    summary="Cancel workout session",
    description="Transition a planned or in-progress session into cancelled state.",
)
@transaction.atomic
def workout_session_cancel(request, session_id: int):
    session = get_object_or_404(WorkoutSession, id=session_id, user=request.user)
    session, changed = cancel_session(session)
    return {
        "ok": True,
        "data": _serialize_session_lifecycle(session, changed=changed),
    }