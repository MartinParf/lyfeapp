from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.utils import timezone
from ninja import Router

from api.exceptions import ApiError
from api.v1.schemas.profile import (
    ProfileMePatchInputSchema,
    ProfileMeResponseSchema,
)
from api.v1.security import api_jwt_bearer
from bio.models import GoalMode, Profile
from api.v1.serializers.profile import serialize_profile
from api.v1.schemas.common import ApiErrorResponseSchema


router = Router(tags=["profile"])


def _get_profile(user):
    profile, _ = Profile.objects.get_or_create(user=user)
    return profile


@router.get(
    "/me/",
    response={
        200: ProfileMeResponseSchema,
        401: ApiErrorResponseSchema,
        403: ApiErrorResponseSchema,
    },
    auth=api_jwt_bearer,
    summary="Get current profile",
    description="Return the profile payload for the currently authenticated user.",
)
def profile_me(request):
    profile = _get_profile(request.user)
    return {
        "ok": True,
        "data": serialize_profile(request, profile),
    }


@router.patch(
    "/me/",
    response={
        200: ProfileMeResponseSchema,
        400: ApiErrorResponseSchema,
        401: ApiErrorResponseSchema,
        403: ApiErrorResponseSchema,
    },
    auth=api_jwt_bearer,
    summary="Update current profile",
    description="Partially update editable profile fields for the currently authenticated user.",
)
def profile_me_patch(request, payload: ProfileMePatchInputSchema):
    profile = _get_profile(request.user)

    changed_fields: list[str] = []
    errors: dict[str, str] = {}

    if payload.display_name is not None:
        value = payload.display_name.strip()
        if len(value) < 2:
            errors["display_name"] = "Display name must be at least 2 characters long."
        else:
            profile.display_name = value[:50]
            changed_fields.append("display_name")

    if payload.bio is not None:
        profile.bio = payload.bio.strip()[:280]
        changed_fields.append("bio")

    if payload.date_of_birth is not None:
        if payload.date_of_birth == "":
            profile.date_of_birth = None
            changed_fields.append("date_of_birth")
        else:
            try:
                parsed = date.fromisoformat(payload.date_of_birth)
                if parsed > timezone.localdate():
                    errors["date_of_birth"] = "Date of birth cannot be in the future."
                else:
                    profile.date_of_birth = parsed
                    changed_fields.append("date_of_birth")
            except ValueError:
                errors["date_of_birth"] = "Use ISO format YYYY-MM-DD."

    if payload.height_cm is not None:
        value = payload.height_cm
        if value < 80 or value > 260:
            errors["height_cm"] = "Height must be between 80 and 260 cm."
        else:
            profile.height_cm = value
            changed_fields.append("height_cm")

    if payload.target_weight_kg is not None:
        if payload.target_weight_kg == "":
            profile.target_weight_kg = None
            changed_fields.append("target_weight_kg")
        else:
            try:
                value = Decimal(str(payload.target_weight_kg))
                if value < Decimal("25.0") or value > Decimal("400.0"):
                    errors["target_weight_kg"] = (
                        "Target weight must be between 25.0 and 400.0 kg."
                    )
                else:
                    profile.target_weight_kg = value
                    changed_fields.append("target_weight_kg")
            except (InvalidOperation, TypeError, ValueError):
                errors["target_weight_kg"] = "Target weight must be a decimal number."

    if payload.goal_mode is not None:
        allowed = {choice for choice, _label in GoalMode.choices}
        if payload.goal_mode not in allowed:
            errors["goal_mode"] = (
                f"Invalid goal_mode. Allowed: {', '.join(sorted(allowed))}."
            )
        else:
            profile.goal_mode = payload.goal_mode
            changed_fields.append("goal_mode")

    if errors:
        raise ApiError(
            code="validation_error",
            message="Profile update validation failed.",
            status=400,
            details=errors,
        )

    if not changed_fields:
        return {
            "ok": True,
            "data": serialize_profile(request, profile),
        }

    try:
        profile.full_clean()
    except ValidationError as exc:
        if hasattr(exc, "message_dict"):
            details = {k: "; ".join(v) for k, v in exc.message_dict.items()}
        else:
            details = {"non_field_errors": exc.messages}
        raise ApiError(
            code="validation_error",
            message="Profile update validation failed.",
            status=400,
            details=details,
        )

    profile.save()

    return {
        "ok": True,
        "data": serialize_profile(request, profile),
    }