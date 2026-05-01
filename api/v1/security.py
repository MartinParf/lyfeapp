from django.contrib.auth.models import AnonymousUser
from ninja.security import HttpBearer
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.settings import api_settings

from api.exceptions import ApiError


class ApiJWTBearer(HttpBearer):
    def __call__(self, request):
        header = request.headers.get("Authorization", "").strip()

        if not header:
            raise ApiError(
                code="authentication_required",
                message="Authentication credentials were not provided.",
                status=401,
            )

        parts = header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise ApiError(
                code="invalid_authorization_header",
                message="Authorization header must be in the format: Bearer <token>.",
                status=401,
            )

        return self.authenticate(request, parts[1])

    def authenticate(self, request, token: str):
        jwt_auth = JWTAuthentication()

        try:
            validated_token = jwt_auth.get_validated_token(token)
            user = jwt_auth.get_user(validated_token)
        except (InvalidToken, TokenError):
            raise ApiError(
                code="invalid_token",
                message="Invalid or expired access token.",
                status=401,
            )

        if not user or isinstance(user, AnonymousUser):
            raise ApiError(
                code="authentication_failed",
                message="Authentication failed.",
                status=401,
            )

        if not user.is_active:
            raise ApiError(
                code="inactive_user",
                message="User account is inactive.",
                status=403,
            )

        request.user = user
        request.auth = validated_token
        return user


api_jwt_bearer = ApiJWTBearer()