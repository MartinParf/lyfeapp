from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction

from api.exceptions import ApiError
from fitness.models import (
    ExercisePool,
    PoolFocus,
    WorkoutSession,
    WorkoutSessionExercise,
    WorkoutSessionStatus,
)


def serialize_workout_session(session: WorkoutSession, *, imported_exercise_count: int = 0) -> dict:
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


@transaction.atomic
def create_workout_session_idempotent(*, user, payload) -> tuple[WorkoutSession, bool, int]:
    existing = WorkoutSession.objects.filter(
        user=user,
        client_uuid=payload.client_uuid,
    ).first()
    if existing:
        return existing, False, existing.session_exercises.count()

    allowed_focus = {choice for choice, _label in PoolFocus.choices}
    if payload.focus not in allowed_focus:
        raise ApiError(
            code="validation_error",
            message="Workout session create validation failed.",
            status=400,
            details={"focus": f"Invalid focus. Allowed: {', '.join(sorted(allowed_focus))}."},
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
            user=user,
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
        user=user,
        client_uuid=payload.client_uuid,
        focus=payload.focus,
        source_pool=source_pool,
        status=WorkoutSessionStatus.PLANNED,
        scheduled_date=parsed_scheduled_date,
        notes=(payload.notes or "").strip(),
    )

    try:
        session.full_clean()
    except ValidationError as exc:
        details = (
            {k: "; ".join(v) for k, v in exc.message_dict.items()}
            if hasattr(exc, "message_dict")
            else {"non_field_errors": exc.messages}
        )
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

    return session, True, imported_exercise_count