from django.utils import timezone
from ninja import Router, Schema


router = Router(tags=["system"])


class SystemPingDataSchema(Schema):
    api_version: str
    server_time: str


class SystemPingResponseSchema(Schema):
    ok: bool
    data: SystemPingDataSchema


@router.get("/ping/", response=SystemPingResponseSchema, auth=None)
def system_ping(request):
    return {
        "ok": True,
        "data": {
            "api_version": "v1",
            "server_time": timezone.now().isoformat(),
        },
    }