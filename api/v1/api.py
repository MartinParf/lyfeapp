from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from django.http import Http404
from ninja import NinjaAPI
from ninja.errors import ValidationError as NinjaValidationError

from api.exceptions import ApiError
from api.v1.routers.system import router as system_router
from api.v1.routers.auth import router as auth_router
from api.v1.routers.profile import router as profile_router
from api.v1.routers.bootstrap import router as bootstrap_router


def _error_payload(*, code: str, message: str, details=None):
    payload = {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if details is not None:
        payload["error"]["details"] = details
    return payload


api_v1 = NinjaAPI(
    title="LYFE Mobile API",
    version="1.0.0",
    urls_namespace="api_v1",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

api_v1.add_router("/system/", system_router)
api_v1.add_router("/auth/", auth_router)
api_v1.add_router("/profile/", profile_router)
api_v1.add_router("/bootstrap/", bootstrap_router)


@api_v1.exception_handler(ApiError)
def api_error_handler(request, exc: ApiError):
    return api_v1.create_response(
        request,
        _error_payload(
            code=exc.code,
            message=exc.message,
            details=exc.details,
        ),
        status=exc.status,
    )


@api_v1.exception_handler(Http404)
def not_found_handler(request, exc):
    return api_v1.create_response(
        request,
        _error_payload(
            code="not_found",
            message="Resource not found.",
        ),
        status=404,
    )


@api_v1.exception_handler(PermissionDenied)
def permission_denied_handler(request, exc):
    return api_v1.create_response(
        request,
        _error_payload(
            code="permission_denied",
            message="You do not have permission to perform this action.",
        ),
        status=403,
    )


@api_v1.exception_handler(DjangoValidationError)
def django_validation_error_handler(request, exc: DjangoValidationError):
    if hasattr(exc, "message_dict"):
        details = {key: "; ".join(value) for key, value in exc.message_dict.items()}
    else:
        details = {"non_field_errors": exc.messages}

    return api_v1.create_response(
        request,
        _error_payload(
            code="validation_error",
            message="Validation failed.",
            details=details,
        ),
        status=400,
    )


@api_v1.exception_handler(NinjaValidationError)
def ninja_validation_error_handler(request, exc: NinjaValidationError):
    details = getattr(exc, "errors", None)
    if callable(details):
        details = details()

    return api_v1.create_response(
        request,
        _error_payload(
            code="validation_error",
            message="Validation failed.",
            details=details,
        ),
        status=422,
    )