from django.utils import timezone
from ninja import Router

from api.v1.schemas.bootstrap import BootstrapResponseSchema
from api.v1.security import api_jwt_bearer
from bio.models import Profile
from fitness.models import Exercise, ExercisePool


router = Router(tags=["bootstrap"])
BOOTSTRAP_VERSION = "2026.05.01-bootstrap-v1"


def _profile_avatar_url(request, profile: Profile) -> str | None:
    if not profile.avatar:
        return None
    return request.build_absolute_uri(profile.avatar.url)


def _serialize_profile(request, profile: Profile) -> dict:
    return {
        "user_id": profile.user_id,
        "email": profile.user.email or "",
        "display_name": profile.display_name,
        "resolved_display_name": profile.resolved_display_name,
        "bio": profile.bio,
        "avatar_url": _profile_avatar_url(request, profile),
        "date_of_birth": profile.date_of_birth.isoformat() if profile.date_of_birth else None,
        "height_cm": profile.height_cm,
        "target_weight_kg": (
            str(profile.target_weight_kg)
            if profile.target_weight_kg is not None
            else None
        ),
        "goal_mode": profile.goal_mode,
        "goal_mode_label": profile.get_goal_mode_display(),
        "email_verified_at": (
            profile.email_verified_at.isoformat()
            if profile.email_verified_at
            else None
        ),
        "onboarding_completed_at": (
            profile.onboarding_completed_at.isoformat()
            if profile.onboarding_completed_at
            else None
        ),
        "created_at": profile.created_at.isoformat(),
        "updated_at": profile.updated_at.isoformat(),
        "profile_version": profile.updated_at.isoformat(),
    }


def _get_profile(user):
    profile, _ = Profile.objects.get_or_create(user=user)
    return profile


@router.get("/", response=BootstrapResponseSchema, auth=api_jwt_bearer)
def bootstrap(request):
    profile = _get_profile(request.user)

    exercises = (
        Exercise.objects.filter(is_active=True)
        .order_by("name", "id")
    )
    pools = (
        ExercisePool.objects.filter(user=request.user, is_active=True)
        .prefetch_related("items")
        .order_by("name", "id")
    )

    return {
        "ok": True,
        "data": {
            "profile": _serialize_profile(request, profile),
            "server": {
                "api_version": "v1",
                "server_time": timezone.now().isoformat(),
            },
            "config": {
                "bootstrap_version": BOOTSTRAP_VERSION,
                "profile_api_enabled": True,
                "fitness_api_enabled": True,
            },
            "feature_flags": {
                "profile_edit_enabled": True,
                "fitness_sessions_enabled": True,
                "analytics_enabled": False,
            },
            "fitness": {
                "exercises": [
                    {
                        "id": exercise.id,
                        "name": exercise.name,
                        "slug": exercise.slug,
                        "primary_pattern": exercise.primary_pattern,
                        "is_custom": exercise.is_custom,
                        "is_active": exercise.is_active,
                    }
                    for exercise in exercises
                ],
                "pool_summaries": [
                    {
                        "id": pool.id,
                        "name": pool.name,
                        "focus": pool.focus,
                        "description": pool.description,
                        "exercise_count": pool.items.count(),
                    }
                    for pool in pools
                ],
            },
        },
    }