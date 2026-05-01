from django.conf import settings
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
from api.v1.schemas.common import ApiErrorResponseSchema
from api.v1.rate_limit import auth_window_seconds, client_ip, rate_limit_or_raise
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


@router.post(
    "/login/",
    response={
        200: AuthLoginResponseSchema,
        401: ApiErrorResponseSchema,
        429: ApiErrorResponseSchema,
    },
    auth=None,
    summary="Login",
    description="Authenticate user with username or email and return access/refresh JWT pair.",
)
def auth_login(request, payload: AuthLoginInputSchema):
    normalized_identity = payload.identity.strip()
    resolved_username = _resolve_login_identity(normalized_identity)
    ip = client_ip(request)
    window = auth_window_seconds()

    rate_limit_or_raise(
        scope="auth_login_ip",
        identifier=ip,
        limit=settings.API_LOGIN_IP_LIMIT,
        window_seconds=window,
    )
    rate_limit_or_raise(
        scope="auth_login_identity_ip",
        identifier=f"{resolved_username.lower()}::{ip}",
        limit=settings.API_LOGIN_IDENTITY_IP_LIMIT,
        window_seconds=window,
    )

    serializer = TokenObtainPairSerializer(
        data={
            "username": resolved_username,
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
    user = User.objects.filter(username=resolved_username).first()
    if not user:
        raise ApiError(
            code="invalid_credentials",
            message="Invalid credentials.",
            status=401,
        )

    if not user.is_active:
        raise ApiError(
            code="inactive_user",
            message="User account is inactive.",
            status=403,
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


@router.post(
    "/refresh/",
    response={
        200: AuthRefreshResponseSchema,
        401: ApiErrorResponseSchema,
        429: ApiErrorResponseSchema,
    },
    auth=None,
    summary="Refresh token pair",
    description="Refresh access token and optionally rotate refresh token.",
)
def auth_refresh(request, payload: AuthRefreshInputSchema):
    ip = client_ip(request)

    rate_limit_or_raise(
        scope="auth_refresh_ip",
        identifier=ip,
        limit=settings.API_REFRESH_IP_LIMIT,
        window_seconds=auth_window_seconds(),
    )

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


@router.post(
    "/logout/",
    response={
        200: AuthLogoutResponseSchema,
        401: ApiErrorResponseSchema,
        429: ApiErrorResponseSchema,
    },
    auth=None,
    summary="Logout",
    description="Blacklist the provided refresh token.",
)
def auth_logout(request, payload: AuthLogoutInputSchema):
    ip = client_ip(request)

    rate_limit_or_raise(
        scope="auth_logout_ip",
        identifier=ip,
        limit=settings.API_LOGOUT_IP_LIMIT,
        window_seconds=auth_window_seconds(),
    )

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


@router.get(
    "/me/",
    response={
        200: AuthMeResponseSchema,
        401: ApiErrorResponseSchema,
        403: ApiErrorResponseSchema,
    },
    auth=api_jwt_bearer,
    summary="Current authenticated user",
    description="Return the currently authenticated user derived from Bearer access token.",
)
def auth_me(request):
    return {
        "ok": True,
        "data": _serialize_user(request.user),
    }