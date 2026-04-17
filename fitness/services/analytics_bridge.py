from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.db.models import Prefetch

from fitness.models import (
    WorkoutSession,
    WorkoutSessionExercise,
    WorkoutSessionStatus,
    WorkoutSet,
)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _safe_duration_minutes(session: WorkoutSession) -> int | None:
    if not session.started_at or not session.ended_at:
        return None

    delta_seconds = (session.ended_at - session.started_at).total_seconds()
    if delta_seconds <= 0:
        return None

    return max(1, round(delta_seconds / 60))


def _session_volume_load(session: WorkoutSession) -> float:
    total = 0.0

    for entry in session.session_exercises.all():
        for workout_set in entry.sets.all():
            weight = _to_float(workout_set.weight_kg)
            reps = workout_set.reps
            if weight is None or reps is None:
                continue
            total += weight * reps

    return round(total, 2)


def _session_set_count(session: WorkoutSession) -> int:
    return sum(entry.sets.count() for entry in session.session_exercises.all())


def _session_exercise_count(session: WorkoutSession) -> int:
    return session.session_exercises.count()


def _training_load_score(*, duration_minutes: int | None, exercise_count: int, set_count: int, volume_load: float) -> int:
    score = 0

    if duration_minutes is not None:
        if duration_minutes >= 90:
            score += 35
        elif duration_minutes >= 60:
            score += 25
        elif duration_minutes >= 30:
            score += 15
        else:
            score += 5

    if set_count >= 20:
        score += 30
    elif set_count >= 12:
        score += 20
    elif set_count >= 6:
        score += 10
    elif set_count > 0:
        score += 5

    if exercise_count >= 8:
        score += 15
    elif exercise_count >= 5:
        score += 10
    elif exercise_count >= 3:
        score += 5

    if volume_load >= 10000:
        score += 20
    elif volume_load >= 5000:
        score += 12
    elif volume_load >= 1500:
        score += 6

    return min(score, 100)


def _training_load_band(score: int) -> str:
    if score >= 70:
        return "HIGH"
    if score >= 35:
        return "MODERATE"
    return "LOW"


def build_completed_session_activity_rows(*, user, start_date: date, end_date: date) -> list[dict[str, Any]]:
    sessions = (
        WorkoutSession.objects.filter(
            user=user,
            status=WorkoutSessionStatus.COMPLETED,
            started_at__isnull=False,
            ended_at__isnull=False,
            started_at__date__gte=start_date,
            started_at__date__lte=end_date,
        )
        .prefetch_related(
            Prefetch(
                "session_exercises",
                queryset=WorkoutSessionExercise.objects.prefetch_related(
                    Prefetch("sets", queryset=WorkoutSet.objects.order_by("set_order", "id"))
                ).order_by("sequence", "id"),
            )
        )
        .order_by("started_at", "id")
    )

    rows: list[dict[str, Any]] = []

    for session in sessions:
        duration_minutes = _safe_duration_minutes(session)
        exercise_count = _session_exercise_count(session)
        set_count = _session_set_count(session)
        volume_load = _session_volume_load(session)
        training_load_score = _training_load_score(
            duration_minutes=duration_minutes,
            exercise_count=exercise_count,
            set_count=set_count,
            volume_load=volume_load,
        )

        rows.append(
            {
                "date": session.started_at.date(),
                "activity_type": "LYFE_FIT",
                "duration_minutes": duration_minutes,
                "calories_burned_est": None,  # intentionally conservative for strength training v1
                "distance_km": None,
                "source": "FITNESS_SESSION",
                "is_strength_training": True,
                "session_count": 1,
                "exercise_count": exercise_count,
                "set_count": set_count,
                "volume_load": volume_load,
                "training_load_score": training_load_score,
                "training_load_band": _training_load_band(training_load_score),
                "session_focus": session.focus,
            }
        )

    return rows