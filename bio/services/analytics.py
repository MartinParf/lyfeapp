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


def _panel_class(tone: str) -> str:
    if tone == "good":
        return "panel-success"
    if tone == "warn":
        return "panel-warning"
    if tone == "danger":
        return "panel-danger"
    return "panel-soft"


def _build_card(
    *,
    kicker: str,
    title: str,
    body: str,
    badge: str | None = None,
    tone: str = "neutral",
    supporting: str | None = None,
    meta_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "kicker": kicker,
        "title": title,
        "body": body,
        "badge": badge,
        "tone": tone,
        "panel_class": _panel_class(tone),
        "supporting": supporting,
        "meta_rows": meta_rows or [],
    }


def _build_main_insight(
    *,
    consistency_score: int,
    sleep_signal: str,
    alcohol_signal: str,
    activity_signal: str,
    total_activity_minutes: int,
) -> dict[str, Any]:
    if consistency_score < 45:
        return _build_card(
            kicker="Main insight",
            title="Tracking baseline is still thin",
            body="The current window still has visible gaps, so interpretation confidence is limited.",
            badge="LIMITED",
            tone="warn",
        )

    if sleep_signal == "worsening" and alcohol_signal == "worsening":
        return _build_card(
            kicker="Main insight",
            title="Recovery pressure is building",
            body="Sleep quality and alcohol trend are both moving in the wrong direction versus the previous window.",
            badge="DEGRADED",
            tone="warn",
        )

    if activity_signal == "decreasing" and total_activity_minutes < 150:
        return _build_card(
            kicker="Main insight",
            title="Movement rhythm is fading",
            body="The recent window shows lower movement volume, so momentum looks weaker than before.",
            badge="SOFTER",
            tone="warn",
        )

    if sleep_signal == "improving" and alcohol_signal == "improving":
        return _build_card(
            kicker="Main insight",
            title="Recovery signals are improving",
            body="Sleep and alcohol direction both support a cleaner recent window than the previous one.",
            badge="IMPROVING",
            tone="good",
        )

    return _build_card(
        kicker="Main insight",
        title="Signals are mostly stable",
        body="No dominant shift stands out in the current window, so the baseline looks relatively steady.",
        badge="NEUTRAL",
        tone="neutral",
    )


def _build_next_action(
    *,
    period_days: int,
    metric_days: int,
    active_days: int,
    sleep_signal: str,
    avg_alcohol: float | None,
    activity_signal: str,
) -> dict[str, Any]:
    minimum_metric_days = max(4, round(period_days * 0.6))
    minimum_active_days = max(2, round(period_days * 0.3))

    if metric_days < minimum_metric_days:
        return _build_card(
            kicker="Next action",
            title="Increase daily metric coverage",
            body="Add more daily metric entries first. Better coverage will improve every downstream signal.",
            badge="TRACKING",
            tone="warn",
        )

    if active_days < minimum_active_days:
        return _build_card(
            kicker="Next action",
            title="Add another movement day",
            body="Movement frequency is still light for the selected window, so add one more active day before reading too much into trends.",
            badge="ACTIVITY",
            tone="warn",
        )

    if sleep_signal == "worsening" and (avg_alcohol is not None and avg_alcohol >= 4):
        return _build_card(
            kicker="Next action",
            title="Protect sleep first",
            body="Reduce alcohol exposure and stabilize evening routine before pushing volume or adding more variables.",
            badge="RECOVERY",
            tone="warn",
        )

    if activity_signal == "decreasing":
        return _build_card(
            kicker="Next action",
            title="Rebuild movement rhythm",
            body="Keep the baseline simple and bring movement minutes back up before changing anything more advanced.",
            badge="RHYTHM",
            tone="neutral",
        )

    return _build_card(
        kicker="Next action",
        title="Stabilize the routine",
        body="The current baseline is usable, but more consistent tracking and movement rhythm will improve signal quality.",
        badge="BASELINE",
        tone="neutral",
    )


def _build_weekly_summary_card(
    *,
    period_days: int,
    metric_days: int,
    active_days: int,
    total_activity_minutes: int,
    avg_calories_actual: float | None,
) -> dict[str, Any]:
    summary = (
        f"{metric_days}/{period_days} metric days, "
        f"{active_days} active days, "
        f"{total_activity_minutes} movement min"
    )
    if avg_calories_actual is not None:
        summary += f", avg intake {int(avg_calories_actual)} kcal."

    return _build_card(
        kicker="Weekly summary",
        title=f"{period_days}-day summary",
        body=summary,
        tone="neutral",
    )


def _build_consistency_card(
    *,
    consistency: dict[str, int],
    active_days: int,
) -> dict[str, Any]:
    overall = consistency["overall_score"]
    tone = "good" if overall >= 75 else "neutral" if overall >= 50 else "warn"
    badge = "STRONG" if overall >= 75 else "USABLE" if overall >= 50 else "SPARSE"

    return _build_card(
        kicker="Consistency",
        title="Score breakdown",
        body="How reliable the current window is for interpretation.",
        badge=badge,
        tone=tone,
        meta_rows=[
            {"label": "Metric score", "value": consistency["metric_score"]},
            {"label": "Activity score", "value": consistency["activity_score"]},
            {"label": "Overall score", "value": consistency["overall_score"]},
            {"label": "Active days", "value": active_days},
        ],
    )


def _build_weight_card(
    *,
    avg_weight: float | None,
    prev_avg_weight: float | None,
    weight_signal: str,
) -> dict[str, Any]:
    if avg_weight is None or prev_avg_weight is None:
        return _build_card(
            kicker="Secondary insight",
            title="Weight",
            body="Not enough paired windows yet for a reliable weight comparison.",
            badge="INSUFFICIENT DATA",
            tone="warn",
        )

    badge_map = {
        "increasing": "INCREASING",
        "decreasing": "DECREASING",
        "stable": "STABLE",
    }

    return _build_card(
        kicker="Secondary insight",
        title="Weight",
        body=f"{avg_weight:.2f} kg vs {prev_avg_weight:.2f} kg",
        badge=badge_map.get(weight_signal, "INSUFFICIENT DATA"),
        tone="neutral" if weight_signal != "stable" else "good",
    )


def _build_recovery_card(
    *,
    avg_sleep: float | None,
    prev_avg_sleep: float | None,
    avg_alcohol: float | None,
    prev_avg_alcohol: float | None,
    sleep_signal: str,
    alcohol_signal: str,
) -> dict[str, Any]:
    if (
        avg_sleep is None
        or prev_avg_sleep is None
        or avg_alcohol is None
        or prev_avg_alcohol is None
    ):
        return _build_card(
            kicker="Secondary insight",
            title="Recovery",
            body="Not enough paired sleep and alcohol windows yet for a recovery comparison.",
            badge="INSUFFICIENT DATA",
            tone="warn",
        )

    if sleep_signal == "improving" and alcohol_signal == "improving":
        badge = "IMPROVING"
        tone = "good"
    elif sleep_signal == "worsening" and alcohol_signal == "worsening":
        badge = "DEGRADED"
        tone = "warn"
    elif sleep_signal == "stable" and alcohol_signal == "stable":
        badge = "STABLE"
        tone = "neutral"
    else:
        badge = "MIXED"
        tone = "neutral"

    return _build_card(
        kicker="Secondary insight",
        title="Recovery",
        body=(
            f"Sleep {avg_sleep:.1f} / Alcohol {avg_alcohol:.1f} "
            f"vs {prev_avg_sleep:.1f} / {prev_avg_alcohol:.1f}"
        ),
        badge=badge,
        tone=tone,
    )


def _build_activity_card(
    *,
    total_activity_minutes: int,
    prev_total_activity_minutes: int,
    activity_signal: str,
) -> dict[str, Any]:
    badge_map = {
        "increasing": "INCREASING",
        "decreasing": "DECREASING",
        "stable": "STABLE",
    }

    tone = "good" if activity_signal == "increasing" else "warn" if activity_signal == "decreasing" else "neutral"

    return _build_card(
        kicker="Secondary insight",
        title="Activity",
        body=f"{total_activity_minutes} min vs {prev_total_activity_minutes} min",
        badge=badge_map.get(activity_signal, "NO DATA"),
        tone=tone,
    )


def _build_intake_card(
    *,
    avg_calories_actual: float | None,
    prev_avg_calories_actual: float | None,
    intake_trend_raw: str,
) -> dict[str, Any]:
    if avg_calories_actual is None or prev_avg_calories_actual is None:
        return _build_card(
            kicker="Secondary insight",
            title="Intake",
            body="Not enough paired calorie windows yet for an intake comparison.",
            badge="INSUFFICIENT DATA",
            tone="warn",
        )

    badge_map = {
        "up": "HIGHER",
        "down": "LOWER",
        "stable": "STABLE",
    }

    return _build_card(
        kicker="Secondary insight",
        title="Intake",
        body=f"{int(avg_calories_actual)} kcal vs {int(prev_avg_calories_actual)} kcal",
        badge=badge_map.get(intake_trend_raw, "INSUFFICIENT DATA"),
        tone="neutral",
    )


def _build_legacy_insights(
    *,
    main_insight: dict[str, Any],
    next_action: dict[str, Any],
    weekly_summary_card: dict[str, Any],
    secondary_insights: list[dict[str, Any]],
) -> list[str]:
    insights = [
        f"{main_insight['title']}: {main_insight['body']}",
        f"{next_action['title']}: {next_action['body']}",
        f"{weekly_summary_card['title']}: {weekly_summary_card['body']}",
    ]

    for card in secondary_insights:
        insights.append(f"{card['title']}: {card['body']}")

    return insights[:6]


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
    intake_trend_raw = _trend_label(avg_calories_actual, prev_avg_calories_actual, tolerance=75.0)

    consistency = _consistency_breakdown(metric_days, active_days, period_days)

    weight_signal = _weight_signal(weight_trend_raw)
    sleep_signal = _sleep_signal(sleep_trend_raw)
    alcohol_signal = _alcohol_signal(alcohol_trend_raw)
    activity_signal = _activity_signal(activity_trend_raw)

    main_insight = _build_main_insight(
        consistency_score=consistency["overall_score"],
        sleep_signal=sleep_signal,
        alcohol_signal=alcohol_signal,
        activity_signal=activity_signal,
        total_activity_minutes=total_activity_minutes,
    )

    next_action = _build_next_action(
        period_days=period_days,
        metric_days=metric_days,
        active_days=active_days,
        sleep_signal=sleep_signal,
        avg_alcohol=avg_alcohol,
        activity_signal=activity_signal,
    )

    weekly_summary_card = _build_weekly_summary_card(
        period_days=period_days,
        metric_days=metric_days,
        active_days=active_days,
        total_activity_minutes=total_activity_minutes,
        avg_calories_actual=avg_calories_actual,
    )

    consistency_card = _build_consistency_card(
        consistency=consistency,
        active_days=active_days,
    )

    secondary_insights = [
        _build_weight_card(
            avg_weight=avg_weight,
            prev_avg_weight=prev_avg_weight,
            weight_signal=weight_signal,
        ),
        _build_recovery_card(
            avg_sleep=avg_sleep,
            prev_avg_sleep=prev_avg_sleep,
            avg_alcohol=avg_alcohol,
            prev_avg_alcohol=prev_avg_alcohol,
            sleep_signal=sleep_signal,
            alcohol_signal=alcohol_signal,
        ),
        _build_activity_card(
            total_activity_minutes=total_activity_minutes,
            prev_total_activity_minutes=prev_total_activity_minutes,
            activity_signal=activity_signal,
        ),
        _build_intake_card(
            avg_calories_actual=avg_calories_actual,
            prev_avg_calories_actual=prev_avg_calories_actual,
            intake_trend_raw=intake_trend_raw,
        ),
    ]

    insights = _build_legacy_insights(
        main_insight=main_insight,
        next_action=next_action,
        weekly_summary_card=weekly_summary_card,
        secondary_insights=secondary_insights,
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
        "main_insight": main_insight,
        "next_action": next_action,
        "weekly_summary_card": weekly_summary_card,
        "consistency_card": consistency_card,
        "secondary_insights": secondary_insights,
        "insights": insights,
    }