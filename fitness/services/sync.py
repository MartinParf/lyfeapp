from django.utils import timezone

from fitness.models import WorkoutSession, WorkoutSessionExercise, WorkoutSet
from fitness.services.session_commands import serialize_workout_session


def touch_session_for_sync(session: WorkoutSession) -> WorkoutSession:
    session.updated_at = timezone.now()
    session.save(update_fields=["updated_at"])
    return session


def serialize_workout_set_sync(workout_set: WorkoutSet) -> dict:
    return {
        "id": workout_set.id,
        "client_uuid": str(workout_set.client_uuid) if workout_set.client_uuid else "",
        "set_order": workout_set.set_order,
        "set_type": workout_set.set_type,
        "weight_kg": str(workout_set.weight_kg) if workout_set.weight_kg is not None else None,
        "reps": workout_set.reps,
        "rpe": str(workout_set.rpe) if workout_set.rpe is not None else None,
        "notes": workout_set.notes,
        "version": workout_set.version,
        "created_at": workout_set.created_at.isoformat(),
        "updated_at": workout_set.updated_at.isoformat(),
    }


def serialize_workout_session_exercise_sync(entry: WorkoutSessionExercise) -> dict:
    return {
        "id": entry.id,
        "client_uuid": str(entry.client_uuid) if entry.client_uuid else "",
        "sequence": entry.sequence,
        "exercise_id": entry.exercise_id,
        "exercise_name": entry.exercise.name,
        "source_pool_item_id": entry.source_pool_item_id,
        "notes": entry.notes,
        "version": entry.version,
        "created_at": entry.created_at.isoformat(),
        "updated_at": entry.updated_at.isoformat(),
        "sets": [
            serialize_workout_set_sync(workout_set)
            for workout_set in entry.sets.all()
        ],
    }


def serialize_workout_session_tree_sync(session: WorkoutSession) -> dict:
    payload = serialize_workout_session(
        session,
        imported_exercise_count=session.session_exercises.count(),
    )
    payload["exercises"] = [
        serialize_workout_session_exercise_sync(entry)
        for entry in session.session_exercises.all()
    ]
    return payload