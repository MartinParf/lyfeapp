from bio.models import Profile


def profile_avatar_url(request, profile: Profile) -> str | None:
    if not profile.avatar:
        return None
    return request.build_absolute_uri(profile.avatar.url)


def serialize_profile(request, profile: Profile) -> dict:
    return {
        "user_id": profile.user_id,
        "email": profile.user.email or "",
        "display_name": profile.display_name,
        "resolved_display_name": profile.resolved_display_name,
        "bio": profile.bio,
        "avatar_url": profile_avatar_url(request, profile),
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