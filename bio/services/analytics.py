from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.db.models import Avg, Sum
from django.utils import timezone

from bio.models import Activity, DailyMetric

User = get_user_model()


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _round_or_none(value: Any, digits: int = 2) -> float | None:
    numeric = _to_float(value)
    if numeric is None:
        return None
    return round(numeric, digits)


def _safe_delta(current: float | None, previous: float | None, digits: int = 2) -> float | None:
    if current is None or previous is None:
        return None
    return round(current - previous, digits)


def _trend_label(current: float | None, previous: float | None, tolerance: float) -> str:
    if current is None or previous is None:
        return "no_data"

    delta = current - previous
    if abs(delta) <= tolerance:
        return "stable"
    return "up" if delta > 0 else "down"


def _weight_signal(label: str) -> str:
    if label == "down":
        return "decreasing"
    if label == "up":
        return "increasing"
    if label == "stable":
        return "stable"
    return "no data"


def _sleep_signal(label: str) -> str:
    if label == "up":
        return "improving"
    if label == "down":
        return "worsening"
    if label == "stable":
        return "stable"
    return "no data"


def _alcohol_signal(label: str) -> str:
    if label == "down":
        return "improving"
    if label == "up":
        return "worsening"
    if label == "stable":
        return "stable"
    return "no data"


def _activity_signal(label: str) -> str:
    if label == "up":
        return "increasing"
    if label == "down":
        return "decreasing"
    if label == "stable":
        return "stable"
    return "no data"


def _signal_symbol(signal: str) -> str:
    if signal in {"increasing", "improving"}:
        return "↑"
    if signal in {"decreasing", "worsening"}:
        return "↓"
    if signal == "stable":
        return "•"
    return "–"


def _consistency_breakdown(metric_days: int, active_days: int, period_days: int) -> dict[str, int]:
    if period_days <= 0:
        return {
            "metric_score": 0,
            "activity_score": 0,
            "overall_score": 0,
        }

    metric_score = round(min(metric_days / period_days, 1.0) * 100)
    activity_score = round(min(active_days / period_days, 1.0) * 100)
    overall_score = round(metric_score * 0.65 + activity_score * 0.35)

    return {
        "metric_score": metric_score,
        "activity_score": activity_score,
        "overall_score": overall_score,
    }


def _build_insights(
    *,
    metric_days: int,
    activity_entries: int,
    active_days: int,
    avg_sleep: float | None,
    avg_alcohol: float | None,
    weight_trend: str,
    sleep_trend: str,
    alcohol_trend: str,
    activity_trend: str,
    consistency_score: int,
    total_activity_minutes: int,
) -> list[str]:
    insights: list[str] = []

    if consistency_score >= 85:
        insights.append("Tracking consistency is strong across the selected window.")
    elif consistency_score >= 60:
        insights.append("Tracking baseline is usable, but still has visible gaps.")
    else:
        insights.append("Tracking is still sparse, so trend confidence is limited.")

    if metric_days <= 2:
        insights.append("Add more daily metrics to improve signal quality.")
    if active_days <= 1 and activity_entries <= 1:
        insights.append("Movement logging is light in the current window.")

    if avg_sleep is not None and avg_alcohol is not None:
        if avg_alcohol >= 4 and avg_sleep <= 2.5:
            insights.append("Higher alcohol intake may be dragging sleep quality down.")
        elif avg_alcohol <= 1 and avg_sleep >= 4:
            insights.append("Low alcohol and strong sleep look aligned.")

    if sleep_trend == "up":
        insights.append("Sleep quality is improving versus the previous window.")
    elif sleep_trend == "down":
        insights.append("Sleep quality is worse than in the previous window.")

    if alcohol_trend == "down":
        insights.append("Alcohol trend is improving versus the previous window.")
    elif alcohol_trend == "up":
        insights.append("Alcohol trend is worsening versus the previous window.")

    if weight_trend == "down":
        insights.append("Bodyweight is trending down in the recent window.")
    elif weight_trend == "up":
        insights.append("Bodyweight is trending up in the recent window.")

    if total_activity_minutes >= 180:
        insights.append("Weekly movement volume looks strong.")
    elif total_activity_minutes == 0:
        insights.append("No movement minutes were logged in the selected window.")

    if activity_trend == "up":
        insights.append("Movement volume is increasing versus the previous window.")
    elif activity_trend == "down":
        insights.append("Movement volume is lower than in the previous window.")

    return insights[:5]


def build_bio_analytics(*, user: User, period_days: int = 7) -> dict[str, Any]:
    today = timezone.localdate()

    recent_start = today - timedelta(days=period_days - 1)
    previous_start = recent_start - timedelta(days=period_days)
    previous_end = recent_start - timedelta(days=1)

    recent_metrics = DailyMetric.objects.filter(
        user=user,
        date__gte=recent_start,
        date__lte=today,
    )
    previous_metrics = DailyMetric.objects.filter(
        user=user,
        date__gte=previous_start,
        date__lte=previous_end,
    )

    recent_activities = Activity.objects.filter(
        user=user,
        date__gte=recent_start,
        date__lte=today,
    )
    previous_activities = Activity.objects.filter(
        user=user,
        date__gte=previous_start,
        date__lte=previous_end,
    )

    metric_days = recent_metrics.count()
    activity_entries = recent_activities.count()
    active_days = recent_activities.values("date").distinct().count()

    avg_weight = _round_or_none(recent_metrics.aggregate(value=Avg("weight_kg"))["value"])
    avg_sleep = _round_or_none(recent_metrics.aggregate(value=Avg("sleep_quality"))["value"], 1)
    avg_alcohol = _round_or_none(recent_metrics.aggregate(value=Avg("alcohol_units"))["value"], 1)
    avg_calories_actual = _round_or_none(
        recent_metrics.exclude(calories_actual__isnull=True).aggregate(value=Avg("calories_actual"))["value"],
        0,
    )

    prev_avg_weight = _round_or_none(previous_metrics.aggregate(value=Avg("weight_kg"))["value"])
    prev_avg_sleep = _round_or_none(previous_metrics.aggregate(value=Avg("sleep_quality"))["value"], 1)
    prev_avg_alcohol = _round_or_none(previous_metrics.aggregate(value=Avg("alcohol_units"))["value"], 1)
    prev_avg_calories_actual = _round_or_none(
        previous_metrics.exclude(calories_actual__isnull=True).aggregate(value=Avg("calories_actual"))["value"],
        0,
    )

    total_activity_minutes = recent_activities.aggregate(value=Sum("duration_minutes"))["value"] or 0
    total_activity_calories = recent_activities.aggregate(value=Sum("calories_burned_est"))["value"] or 0
    total_distance = _round_or_none(recent_activities.aggregate(value=Sum("distance_km"))["value"])

    prev_total_activity_minutes = previous_activities.aggregate(value=Sum("duration_minutes"))["value"] or 0
    prev_total_activity_calories = previous_activities.aggregate(value=Sum("calories_burned_est"))["value"] or 0
    prev_total_distance = _round_or_none(previous_activities.aggregate(value=Sum("distance_km"))["value"])

    weight_trend_raw = _trend_label(avg_weight, prev_avg_weight, tolerance=0.15)
    sleep_trend_raw = _trend_label(avg_sleep, prev_avg_sleep, tolerance=0.2)
    alcohol_trend_raw = _trend_label(avg_alcohol, prev_avg_alcohol, tolerance=0.25)
    activity_trend_raw = _trend_label(float(total_activity_minutes), float(prev_total_activity_minutes), tolerance=20.0)

    consistency = _consistency_breakdown(metric_days, active_days, period_days)

    weight_signal = _weight_signal(weight_trend_raw)
    sleep_signal = _sleep_signal(sleep_trend_raw)
    alcohol_signal = _alcohol_signal(alcohol_trend_raw)
    activity_signal = _activity_signal(activity_trend_raw)

    insights = _build_insights(
        metric_days=metric_days,
        activity_entries=activity_entries,
        active_days=active_days,
        avg_sleep=avg_sleep,
        avg_alcohol=avg_alcohol,
        weight_trend=weight_trend_raw,
        sleep_trend=sleep_trend_raw,
        alcohol_trend=alcohol_trend_raw,
        activity_trend=activity_trend_raw,
        consistency_score=consistency["overall_score"],
        total_activity_minutes=total_activity_minutes,
    )

    return {
        "period_days": period_days,
        "window": {
            "recent_start": recent_start,
            "recent_end": today,
            "previous_start": previous_start,
            "previous_end": previous_end,
        },
        "summary": {
            "metric_days": metric_days,
            "activity_entries": activity_entries,
            "active_days": active_days,
            "avg_weight": avg_weight,
            "avg_sleep": avg_sleep,
            "avg_alcohol": avg_alcohol,
            "avg_calories_actual": avg_calories_actual,
            "total_activity_minutes": total_activity_minutes,
            "total_activity_calories": total_activity_calories,
            "total_distance": total_distance,
        },
        "previous_summary": {
            "avg_weight": prev_avg_weight,
            "avg_sleep": prev_avg_sleep,
            "avg_alcohol": prev_avg_alcohol,
            "avg_calories_actual": prev_avg_calories_actual,
            "total_activity_minutes": prev_total_activity_minutes,
            "total_activity_calories": prev_total_activity_calories,
            "total_distance": prev_total_distance,
        },
        "deltas": {
            "avg_weight": _safe_delta(avg_weight, prev_avg_weight, 2),
            "avg_sleep": _safe_delta(avg_sleep, prev_avg_sleep, 1),
            "avg_alcohol": _safe_delta(avg_alcohol, prev_avg_alcohol, 1),
            "avg_calories_actual": _safe_delta(avg_calories_actual, prev_avg_calories_actual, 0),
            "activity_minutes": _safe_delta(float(total_activity_minutes), float(prev_total_activity_minutes), 0),
            "activity_calories": _safe_delta(float(total_activity_calories), float(prev_total_activity_calories), 0),
            "distance": _safe_delta(total_distance, prev_total_distance, 2),
        },
        "trends": {
            "weight": weight_signal,
            "sleep": sleep_signal,
            "alcohol": alcohol_signal,
            "activity": activity_signal,
        },
        "signal_symbols": {
            "weight": _signal_symbol(weight_signal),
            "sleep": _signal_symbol(sleep_signal),
            "alcohol": _signal_symbol(alcohol_signal),
        },
        "consistency": consistency,
        "insights": insights,
    }