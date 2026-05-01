from django.db import transaction
from django.shortcuts import get_object_or_404
from ninja import Router

from api.v1.schemas.common import ApiErrorResponseSchema
from api.v1.schemas.workout_session_lifecycle import (
    WorkoutSessionLifecycleResponseSchema,
)
from api.v1.schemas.workout_sessions import (
    WorkoutSessionCreateInputSchema,
    WorkoutSessionCreateResponseSchema,
)
from api.v1.security import api_jwt_bearer
from fitness.models import WorkoutSession
from fitness.services.session_commands import (
    create_workout_session_idempotent,
    serialize_workout_session,
)
from fitness.services.session_lifecycle import (
    cancel_session,
    complete_session,
    start_session,
)

router = Router(tags=["workout-sessions"])

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
def workout_session_create(request, payload: WorkoutSessionCreateInputSchema):
    session, created, imported_exercise_count = create_workout_session_idempotent(
        user=request.user,
        payload=payload,
    )
    return (201 if created else 200), {
        "ok": True,
        "data": serialize_workout_session(
            session,
            imported_exercise_count=imported_exercise_count,
        ),
        "created": created,
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