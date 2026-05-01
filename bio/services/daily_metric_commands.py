from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from api.exceptions import ApiError
from bio.models import DailyMetric, DietMode
from bio.tasks import recompute_recent_snapshots_for_user


def serialize_daily_metric(metric: DailyMetric) -> dict:
    return {
        "id": metric.id,
        "date": metric.date.isoformat(),
        "weight_kg": str(metric.weight_kg) if metric.weight_kg is not None else None,
        "diet_mode": metric.diet_mode,
        "sleep_quality": metric.sleep_quality,
        "alcohol_units": metric.alcohol_units,
        "calories_planned": metric.calories_planned,
        "calories_actual": metric.calories_actual,
        "notes": metric.notes,
        "version": metric.version,
        "created_at": metric.created_at.isoformat(),
        "updated_at": metric.updated_at.isoformat(),
    }


@transaction.atomic
def upsert_daily_metric_by_date(*, user, entry_date: str, payload) -> tuple[DailyMetric, bool]:
    try:
        parsed_date = date.fromisoformat(entry_date)
    except ValueError:
        raise ApiError(
            code="validation_error",
            message="Daily metric upsert validation failed.",
            status=400,
            details={"date": "Use ISO format YYYY-MM-DD."},
        )

    allowed_diet_modes = {choice for choice, _label in DietMode.choices}
    if payload.diet_mode is not None and payload.diet_mode not in allowed_diet_modes:
        raise ApiError(
            code="validation_error",
            message="Daily metric upsert validation failed.",
            status=400,
            details={
                "diet_mode": f"Invalid diet_mode. Allowed: {', '.join(sorted(allowed_diet_modes))}."
            },
        )

    weight_value = None
    if payload.weight_kg not in (None, ""):
        try:
            weight_value = Decimal(str(payload.weight_kg))
        except (InvalidOperation, TypeError, ValueError):
            raise ApiError(
                code="validation_error",
                message="Daily metric upsert validation failed.",
                status=400,
                details={"weight_kg": "Weight must be a decimal number."},
            )

    metric = DailyMetric.objects.filter(user=user, date=parsed_date).first()
    created = metric is None

    if created:
        metric = DailyMetric(user=user, date=parsed_date)

    metric.weight_kg = weight_value
    metric.diet_mode = payload.diet_mode
    metric.sleep_quality = payload.sleep_quality
    metric.alcohol_units = 0 if payload.alcohol_units is None else payload.alcohol_units
    metric.calories_planned = payload.calories_planned
    metric.calories_actual = payload.calories_actual
    metric.notes = (payload.notes or "").strip()

    try:
        metric.full_clean()
    except ValidationError as exc:
        details = (
            {k: "; ".join(v) for k, v in exc.message_dict.items()}
            if hasattr(exc, "message_dict")
            else {"non_field_errors": exc.messages}
        )
        raise ApiError(
            code="validation_error",
            message="Daily metric upsert validation failed.",
            status=400,
            details=details,
        )

    metric.save()
    user_id = user.id
    transaction.on_commit(lambda: recompute_recent_snapshots_for_user(user_id))
    return metric, created