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


def _metric_signal(label: str, metric: str) -> str:
    if label in {"no_data", "insufficient_data"}:
        return "insufficient data"

    if metric == "weight":
        if label == "up":
            return "increasing"
        if label == "down":
            return "decreasing"
        return "stable"

    if metric == "sleep":
        if label == "up":
            return "improving"
        if label == "down":
            return "worsening"
        return "stable"

    if metric == "alcohol":
        if label == "down":
            return "improving"
        if label == "up":
            return "worsening"
        return "stable"

    if metric == "activity":
        if label == "up":
            return "increasing"
        if label == "down":
            return "decreasing"
        return "stable"

    if metric == "kcal":
        if label == "up":
            return "increasing"
        if label == "down":
            return "decreasing"
        return "stable"

    return "stable"


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


def _has_metric_baseline(recent_metric_days: int, previous_metric_days: int) -> bool:
    return recent_metric_days >= 2 and previous_metric_days >= 2


def _has_activity_baseline(recent_active_days: int, previous_active_days: int) -> bool:
    return recent_active_days >= 1 and previous_active_days >= 1


def _build_trend(
    *,
    metric: str,
    recent_value: float | None,
    previous_value: float | None,
    tolerance: float,
    sufficient: bool,
) -> dict[str, Any]:
    if not sufficient:
        state = "insufficient_data"
        signal = "insufficient data"
        symbol = "–"
        delta = None
    else:
        state = _trend_label(recent_value, previous_value, tolerance=tolerance)
        signal = _metric_signal(state, metric)
        symbol = _signal_symbol(signal)
        delta = _safe_delta(recent_value, previous_value, 2)

    return {
        "metric": metric,
        "recent": recent_value,
        "previous": previous_value,
        "delta": delta,
        "state": state,
        "signal": signal,
        "symbol": symbol,
        "sufficient": sufficient,
    }


def _fmt(value: float | None, digits: int = 1, suffix: str = "") -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}{suffix}"


def _main_insight(
    *,
    consistency_score: int,
    weight_trend: dict[str, Any],
    sleep_trend: dict[str, Any],
    alcohol_trend: dict[str, Any],
    activity_trend: dict[str, Any],
    kcal_trend: dict[str, Any],
    metric_days: int,
) -> dict[str, str]:
    if consistency_score < 50 or metric_days <= 2:
        return {
            "title": "Baseline is still thin",
            "body": "Current tracking is not dense enough yet for confident interpretation. Keep logging daily metrics first.",
            "tone": "neutral",
        }

    if sleep_trend["signal"] == "worsening" and alcohol_trend["signal"] == "worsening":
        return {
            "title": "Recovery signal weakened",
            "body": "Sleep quality worsened while alcohol trend also moved in the wrong direction versus the previous window.",
            "tone": "warning",
        }

    if kcal_trend["signal"] == "increasing" and weight_trend["signal"] == "increasing":
        return {
            "title": "Intake and bodyweight both moved up",
            "body": "Average calorie intake is rising and bodyweight is moving up in the same window.",
            "tone": "warning",
        }

    if activity_trend["signal"] == "decreasing" and consistency_score < 70:
        return {
            "title": "Routine momentum softened",
            "body": "Movement volume dropped and tracking consistency is not yet strong enough to call this stable.",
            "tone": "warning",
        }

    if sleep_trend["signal"] == "improving" and alcohol_trend["signal"] == "improving":
        return {
            "title": "Recovery trend improved",
            "body": "Sleep improved while alcohol moved in the right direction compared with the previous window.",
            "tone": "positive",
        }

    if activity_trend["signal"] == "increasing" and sleep_trend["signal"] in {"stable", "improving"}:
        return {
            "title": "Movement rhythm looks stronger",
            "body": "Activity minutes increased without a visible negative recovery signal in sleep.",
            "tone": "positive",
        }

    return {
        "title": "Signals are mostly stable",
        "body": "No dominant shift stands out in the current window, so the baseline looks relatively steady.",
        "tone": "neutral",
    }


def _secondary_insights(
    *,
    weight_trend: dict[str, Any],
    sleep_trend: dict[str, Any],
    alcohol_trend: dict[str, Any],
    activity_trend: dict[str, Any],
    kcal_trend: dict[str, Any],
    avg_weight: float | None,
    prev_avg_weight: float | None,
    avg_sleep: float | None,
    prev_avg_sleep: float | None,
    avg_alcohol: float | None,
    prev_avg_alcohol: float | None,
    total_activity_minutes: int,
    prev_total_activity_minutes: int,
    avg_calories_actual: float | None,
    prev_avg_calories_actual: float | None,
) -> list[dict[str, str]]:
    recovery_value = "mixed"
    recovery_tone = "neutral"

    if sleep_trend["signal"] == "improving" and alcohol_trend["signal"] == "improving":
        recovery_value = "improving"
        recovery_tone = "positive"
    elif sleep_trend["signal"] == "worsening" or alcohol_trend["signal"] == "worsening":
        recovery_value = "attention"
        recovery_tone = "warning"
    elif sleep_trend["signal"] == "stable" and alcohol_trend["signal"] == "stable":
        recovery_value = "stable"
        recovery_tone = "neutral"

    return [
        {
            "label": "Weight",
            "value": weight_trend["signal"],
            "note": f"{_fmt(avg_weight, 2, ' kg')} vs {_fmt(prev_avg_weight, 2, ' kg')}",
            "tone": "neutral",
        },
        {
            "label": "Recovery",
            "value": recovery_value,
            "note": f"Sleep {_fmt(avg_sleep, 1)} / Alcohol {_fmt(avg_alcohol, 1)} vs {_fmt(prev_avg_sleep, 1)} / {_fmt(prev_avg_alcohol, 1)}",
            "tone": recovery_tone,
        },
        {
            "label": "Activity",
            "value": activity_trend["signal"],
            "note": f"{total_activity_minutes} min vs {prev_total_activity_minutes} min",
            "tone": "positive" if activity_trend["signal"] == "increasing" else "warning" if activity_trend["signal"] == "decreasing" else "neutral",
        },
        {
            "label": "Intake",
            "value": kcal_trend["signal"],
            "note": f"{_fmt(avg_calories_actual, 0, ' kcal')} vs {_fmt(prev_avg_calories_actual, 0, ' kcal')}",
            "tone": "neutral",
        },
    ]


def _next_action(
    *,
    metric_days: int,
    active_days: int,
    avg_calories_actual: float | None,
    sleep_trend: dict[str, Any],
    alcohol_trend: dict[str, Any],
    activity_trend: dict[str, Any],
    kcal_trend: dict[str, Any],
    weight_trend: dict[str, Any],
    consistency_score: int,
) -> dict[str, str]:
    if metric_days < 4:
        return {
            "label": "Log more daily metrics",
            "reason": "This week still needs more body and recovery entries before deeper trend interpretation becomes reliable.",
        }

    if avg_calories_actual is None:
        return {
            "label": "Track actual calorie intake more often",
            "reason": "Calories are missing too often to connect intake with bodyweight, sleep, and recovery patterns.",
        }

    if sleep_trend["signal"] == "worsening" and alcohol_trend["signal"] == "worsening":
        return {
            "label": "Prioritize recovery this week",
            "reason": "Sleep is worsening and alcohol trend also moved in the wrong direction.",
        }

    if weight_trend["signal"] == "increasing" and kcal_trend["signal"] == "increasing":
        return {
            "label": "Review intake trend",
            "reason": "Average calorie intake and bodyweight are both moving up in the same window.",
        }

    if activity_trend["signal"] == "decreasing" and active_days < 3:
        return {
            "label": "Add one more activity day",
            "reason": "Movement volume dropped and the current week would benefit from one more simple activity block.",
        }

    if consistency_score < 70:
        return {
            "label": "Stabilize the routine",
            "reason": "The current baseline is usable, but more consistent tracking and movement rhythm will improve signal quality.",
        }

    return {
        "label": "Stay consistent",
        "reason": "Current signals do not show a major problem, so the best move is to maintain the routine for another week.",
    }


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
    previous_metric_days = previous_metrics.count()

    activity_entries = recent_activities.count()
    active_days = recent_activities.values("date").distinct().count()
    previous_active_days = previous_activities.values("date").distinct().count()

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

    metric_baseline_ok = _has_metric_baseline(metric_days, previous_metric_days)
    activity_baseline_ok = _has_activity_baseline(active_days, previous_active_days)

    weight_trend = _build_trend(
        metric="weight",
        recent_value=avg_weight,
        previous_value=prev_avg_weight,
        tolerance=0.25,
        sufficient=metric_baseline_ok,
    )
    sleep_trend = _build_trend(
        metric="sleep",
        recent_value=avg_sleep,
        previous_value=prev_avg_sleep,
        tolerance=0.30,
        sufficient=metric_baseline_ok,
    )
    alcohol_trend = _build_trend(
        metric="alcohol",
        recent_value=avg_alcohol,
        previous_value=prev_avg_alcohol,
        tolerance=0.50,
        sufficient=metric_baseline_ok,
    )
    activity_trend = _build_trend(
        metric="activity",
        recent_value=float(total_activity_minutes),
        previous_value=float(prev_total_activity_minutes),
        tolerance=45.0,
        sufficient=activity_baseline_ok,
    )
    kcal_trend = _build_trend(
        metric="kcal",
        recent_value=avg_calories_actual,
        previous_value=prev_avg_calories_actual,
        tolerance=150.0,
        sufficient=metric_baseline_ok,
    )

    consistency = _consistency_breakdown(metric_days, active_days, period_days)

    main_insight = _main_insight(
        consistency_score=consistency["overall_score"],
        weight_trend=weight_trend,
        sleep_trend=sleep_trend,
        alcohol_trend=alcohol_trend,
        activity_trend=activity_trend,
        kcal_trend=kcal_trend,
        metric_days=metric_days,
    )

    secondary_insights = _secondary_insights(
        weight_trend=weight_trend,
        sleep_trend=sleep_trend,
        alcohol_trend=alcohol_trend,
        activity_trend=activity_trend,
        kcal_trend=kcal_trend,
        avg_weight=avg_weight,
        prev_avg_weight=prev_avg_weight,
        avg_sleep=avg_sleep,
        prev_avg_sleep=prev_avg_sleep,
        avg_alcohol=avg_alcohol,
        prev_avg_alcohol=prev_avg_alcohol,
        total_activity_minutes=total_activity_minutes,
        prev_total_activity_minutes=prev_total_activity_minutes,
        avg_calories_actual=avg_calories_actual,
        prev_avg_calories_actual=prev_avg_calories_actual,
    )

    next_action = _next_action(
        metric_days=metric_days,
        active_days=active_days,
        avg_calories_actual=avg_calories_actual,
        sleep_trend=sleep_trend,
        alcohol_trend=alcohol_trend,
        activity_trend=activity_trend,
        kcal_trend=kcal_trend,
        weight_trend=weight_trend,
        consistency_score=consistency["overall_score"],
    )

    weekly_summary = {
        "title": f"{period_days}-day summary",
        "body": (
            f"{metric_days}/{period_days} metric days, "
            f"{active_days} active days, "
            f"{total_activity_minutes} movement min, "
            f"avg intake {_fmt(avg_calories_actual, 0, ' kcal')}."
        ),
    }

    insights = [main_insight["body"]] + [item["note"] for item in secondary_insights]

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
            "metric_days": previous_metric_days,
            "active_days": previous_active_days,
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
        "trend_logic": {
            "weight": weight_trend,
            "sleep": sleep_trend,
            "alcohol": alcohol_trend,
            "activity": activity_trend,
            "kcal": kcal_trend,
        },
        "trends": {
            "weight": weight_trend["signal"],
            "sleep": sleep_trend["signal"],
            "alcohol": alcohol_trend["signal"],
            "activity": activity_trend["signal"],
            "kcal": kcal_trend["signal"],
        },
        "signal_symbols": {
            "weight": weight_trend["symbol"],
            "sleep": sleep_trend["symbol"],
            "alcohol": alcohol_trend["symbol"],
            "kcal": kcal_trend["symbol"],
        },
        "consistency": consistency,
        "weekly_summary": weekly_summary,
        "main_insight": main_insight,
        "secondary_insights": secondary_insights,
        "next_action": next_action,
        "insights": insights,
    }