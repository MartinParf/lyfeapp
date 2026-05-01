from django.contrib.auth import get_user_model
from django.db.models import Q
from ninja import Router
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer,
    TokenRefreshSerializer,
)
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from api.exceptions import ApiError
from api.v1.schemas.auth import (
    AuthLoginInputSchema,
    AuthLoginResponseSchema,
    AuthLogoutInputSchema,
    AuthLogoutResponseSchema,
    AuthMeResponseSchema,
    AuthRefreshInputSchema,
    AuthRefreshResponseSchema,
)
from api.v1.security import api_jwt_bearer
from bio.models import Profile


router = Router(tags=["auth"])


def _resolve_login_identity(identity: str) -> str:
    User = get_user_model()
    candidate = (
        User.objects.filter(
            Q(username__iexact=identity.strip()) | Q(email__iexact=identity.strip())
        )
        .order_by("id")
        .first()
    )
    return candidate.username if candidate else identity.strip()


def _serialize_user(user):
    profile, _ = Profile.objects.get_or_create(user=user)
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email or "",
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "email_verified": bool(profile.email_verified_at),
    }


def _token_lifetimes():
    return {
        "access_expires_in_seconds": int(api_settings.ACCESS_TOKEN_LIFETIME.total_seconds()),
        "refresh_expires_in_seconds": int(api_settings.REFRESH_TOKEN_LIFETIME.total_seconds()),
    }


@router.post("/login/", response=AuthLoginResponseSchema, auth=None)
def auth_login(request, payload: AuthLoginInputSchema):
    serializer = TokenObtainPairSerializer(
        data={
            "username": _resolve_login_identity(payload.identity),
            "password": payload.password,
        }
    )

    try:
        serializer.is_valid(raise_exception=True)
    except Exception:
        raise ApiError(
            code="invalid_credentials",
            message="Invalid credentials.",
            status=401,
        )

    User = get_user_model()
    username = _resolve_login_identity(payload.identity)
    user = User.objects.filter(username=username).first()
    if not user:
        raise ApiError(
            code="invalid_credentials",
            message="Invalid credentials.",
            status=401,
        )

    lifetimes = _token_lifetimes()

    return {
        "ok": True,
        "data": {
            "user": _serialize_user(user),
            "tokens": {
                "access": serializer.validated_data["access"],
                "refresh": serializer.validated_data["refresh"],
                "token_type": "Bearer",
                **lifetimes,
            },
        },
    }


@router.post("/refresh/", response=AuthRefreshResponseSchema, auth=None)
def auth_refresh(request, payload: AuthRefreshInputSchema):
    serializer = TokenRefreshSerializer(data={"refresh": payload.refresh})

    try:
        serializer.is_valid(raise_exception=True)
    except Exception:
        raise ApiError(
            code="invalid_refresh_token",
            message="Invalid or expired refresh token.",
            status=401,
        )

    lifetimes = _token_lifetimes()

    return {
        "ok": True,
        "data": {
            "access": serializer.validated_data["access"],
            "refresh": serializer.validated_data.get("refresh", payload.refresh),
            "token_type": "Bearer",
            **lifetimes,
        },
    }


@router.post("/logout/", response=AuthLogoutResponseSchema, auth=None)
def auth_logout(request, payload: AuthLogoutInputSchema):
    try:
        token = RefreshToken(payload.refresh)
        token.blacklist()
    except TokenError:
        raise ApiError(
            code="invalid_refresh_token",
            message="Invalid or expired refresh token.",
            status=401,
        )

    return {
        "ok": True,
        "data": {
            "logged_out": True,
        },
    }


@router.get("/me/", response=AuthMeResponseSchema, auth=api_jwt_bearer)
def auth_me(request):
    return {
        "ok": True,
        "data": _serialize_user(request.user),
    }