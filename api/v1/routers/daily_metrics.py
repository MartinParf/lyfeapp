from ninja import Router

from api.v1.schemas.common import ApiErrorResponseSchema
from api.v1.schemas.daily_metrics import (
    DailyMetricUpsertInputSchema,
    DailyMetricUpsertResponseSchema,
)
from api.v1.security import api_jwt_bearer
from bio.services.daily_metric_commands import (
    serialize_daily_metric,
    upsert_daily_metric_by_date,
)


router = Router(tags=["daily-metrics"])

@router.put(
    "/by-date/{entry_date}/",
    response={
        201: DailyMetricUpsertResponseSchema,
        200: DailyMetricUpsertResponseSchema,
        400: ApiErrorResponseSchema,
        401: ApiErrorResponseSchema,
        403: ApiErrorResponseSchema,
    },
    auth=api_jwt_bearer,
    summary="Upsert daily metric by date",
    description="Create or replace the authenticated user's daily metric for a given date.",
)
def daily_metric_upsert(request, entry_date: str, payload: DailyMetricUpsertInputSchema):
    metric, created = upsert_daily_metric_by_date(
        user=request.user,
        entry_date=entry_date,
        payload=payload,
    )
    return (201 if created else 200), {
        "ok": True,
        "data": serialize_daily_metric(metric),
        "created": created,
    }