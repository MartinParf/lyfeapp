from django.utils import timezone
from ninja import Router, Schema
from api.v1.schemas.common import ApiErrorResponseSchema


router = Router(tags=["system"])


class SystemPingDataSchema(Schema):
    api_version: str
    server_time: str


class SystemPingResponseSchema(Schema):
    ok: bool
    data: SystemPingDataSchema


@router.get(
    "/ping/",
    response={
        200: SystemPingResponseSchema,
    },
    auth=None,
    summary="System ping",
    description="Simple unauthenticated health-style API ping for client connectivity checks.",
)
def system_ping(request):
    return {
        "ok": True,
        "data": {
            "api_version": "v1",
            "server_time": timezone.now().isoformat(),
        },
    }