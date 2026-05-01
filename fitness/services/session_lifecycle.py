from django.core.exceptions import ValidationError
from django.utils import timezone

from api.exceptions import ApiError
from fitness.models import WorkoutSession, WorkoutSessionStatus


def ensure_session_structure_mutable(session: WorkoutSession):
    if not session.can_edit_structure:
        raise ApiError(
            code="session_locked",
            message="Completed or cancelled sessions are read-only.",
            status=409,
            details={"status": session.status},
        )


def ensure_session_deletable(session: WorkoutSession):
    if not session.can_delete_session:
        raise ApiError(
            code="session_delete_forbidden",
            message="Only planned sessions can be deleted.",
            status=409,
            details={"status": session.status},
        )


def start_session(session: WorkoutSession, *, when=None) -> tuple[WorkoutSession, bool]:
    if session.status == WorkoutSessionStatus.IN_PROGRESS:
        return session, False

    if not session.can_start:
        raise ApiError(
            code="invalid_state_transition",
            message="Session cannot be started from its current status.",
            status=409,
            details={"status": session.status, "target_status": WorkoutSessionStatus.IN_PROGRESS},
        )

    when = when or timezone.now()
    session.status = WorkoutSessionStatus.IN_PROGRESS
    session.started_at = session.started_at or when
    session.ended_at = None

    try:
        session.full_clean()
    except ValidationError as exc:
        if hasattr(exc, "message_dict"):
            details = {k: "; ".join(v) for k, v in exc.message_dict.items()}
        else:
            details = {"non_field_errors": exc.messages}
        raise ApiError(
            code="validation_error",
            message="Session start validation failed.",
            status=400,
            details=details,
        )

    session.save()
    return session, True


def complete_session(session: WorkoutSession, *, when=None) -> tuple[WorkoutSession, bool]:
    if session.status == WorkoutSessionStatus.COMPLETED:
        return session, False

    if not session.can_complete:
        raise ApiError(
            code="invalid_state_transition",
            message="Session cannot be completed from its current status.",
            status=409,
            details={"status": session.status, "target_status": WorkoutSessionStatus.COMPLETED},
        )

    when = when or timezone.now()
    session.ended_at = when
    session.status = WorkoutSessionStatus.COMPLETED

    try:
        session.full_clean()
    except ValidationError as exc:
        if hasattr(exc, "message_dict"):
            details = {k: "; ".join(v) for k, v in exc.message_dict.items()}
        else:
            details = {"non_field_errors": exc.messages}
        raise ApiError(
            code="validation_error",
            message="Session completion validation failed.",
            status=400,
            details=details,
        )

    session.save()
    return session, True


def cancel_session(session: WorkoutSession) -> tuple[WorkoutSession, bool]:
    if session.status == WorkoutSessionStatus.CANCELLED:
        return session, False

    if not session.can_cancel:
        raise ApiError(
            code="invalid_state_transition",
            message="Session cannot be cancelled from its current status.",
            status=409,
            details={"status": session.status, "target_status": WorkoutSessionStatus.CANCELLED},
        )

    session.status = WorkoutSessionStatus.CANCELLED
    session.ended_at = None

    try:
        session.full_clean()
    except ValidationError as exc:
        if hasattr(exc, "message_dict"):
            details = {k: "; ".join(v) for k, v in exc.message_dict.items()}
        else:
            details = {"non_field_errors": exc.messages}
        raise ApiError(
            code="validation_error",
            message="Session cancellation validation failed.",
            status=400,
            details=details,
        )

    session.save()
    return session, True