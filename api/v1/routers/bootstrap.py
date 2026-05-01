from django.utils import timezone
from ninja import Router

from api.v1.schemas.bootstrap import BootstrapResponseSchema
from api.v1.security import api_jwt_bearer
from bio.models import Profile
from fitness.models import Exercise, ExercisePool
from api.v1.serializers.profile import serialize_profile


router = Router(tags=["bootstrap"])
BOOTSTRAP_VERSION = "2026.05.01-bootstrap-v1"



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
            "profile": serialize_profile(request, profile),
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