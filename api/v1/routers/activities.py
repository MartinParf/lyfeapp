from ninja import Router

from bio.services.activity_commands import (
    create_activity_idempotent,
    serialize_activity,
)
from api.v1.schemas.activities import (
    ActivityCreateInputSchema,
    ActivityCreateResponseSchema,
)
from api.v1.schemas.common import ApiErrorResponseSchema
from api.v1.security import api_jwt_bearer


router = Router(tags=["activities"])

@router.post(
    "/",
    response={
        201: ActivityCreateResponseSchema,
        200: ActivityCreateResponseSchema,
        400: ApiErrorResponseSchema,
        401: ApiErrorResponseSchema,
        403: ApiErrorResponseSchema,
    },
    auth=api_jwt_bearer,
    summary="Create activity",
    description="Create a new activity using client_uuid idempotency. Replays return the existing object.",
)
def activity_create(request, payload: ActivityCreateInputSchema):
    activity, created = create_activity_idempotent(
        user=request.user,
        payload=payload,
    )
    return (201 if created else 200), {
        "ok": True,
        "data": serialize_activity(activity),
        "created": created,
    }