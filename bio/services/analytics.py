from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.db.models import Avg, Sum
from django.utils import timezone

from bio.models import (
    Activity,
    AnalyticsSnapshot,
    AnalyticsSnapshotStatus,
    AnalyticsSnapshotType,
    DailyMetric,
)
from bio.services.dataframes import (
    build_bio_correlation_foundation,
    build_bio_dataframe_foundation,
    build_bio_rolling_foundation,
)

User = get_user_model()

def _safe_state(value):
    return (value or "").strip().lower()


def _badge_label_for_state(state, *, kind="secondary"):
    state = _safe_state(state)

    if kind == "main":
        mapping = {
            "neutral": "STABLE",
            "stable": "STABLE",
            "mixed": "MIXED",
            "improving": "IMPROVING",
            "worsening": "WORSENING",
            "insufficient_data": "LIMITED",
            "limited": "LIMITED",
        }
        return mapping.get(state, state.replace("_", " ").upper() if state else "STABLE")

    if kind == "action":
        return "PRIORITY"

    if kind == "consistency":
        mapping = {
            "strong": "STRONG",
            "moderate": "MODERATE",
            "limited": "LIMITED",
        }
        return mapping.get(state, "MODERATE")

    mapping = {
        "increasing": "HIGHER",
        "decreasing": "LOWER",
        "improving": "IMPROVING",
        "worsening": "WORSENING",
        "stable": "STABLE",
        "neutral": "STABLE",
        "mixed": "MIXED",
        "insufficient_data": "LIMITED",
        "limited": "LIMITED",
        "strong": "STRONG",
        "moderate": "MODERATE",
        "lower": "LOWER",
        "higher": "HIGHER",
    }
    return mapping.get(state, state.replace("_", " ").upper() if state else "STABLE")


def _badge_tone_for_state(state, *, kind="secondary"):
    state = _safe_state(state)

    if kind == "action":
        return "info"

    if kind == "consistency":
        if state == "strong":
            return "success"
        if state == "limited":
            return "warning"
        return "neutral"

    if state in {"improving", "strong"}:
        return "success"
    if state in {"worsening"}:
        return "danger"
    if state in {"decreasing", "lower"}:
        return "warning"
    if state in {"increasing", "higher"}:
        return "info"
    if state in {"insufficient_data", "limited"}:
        return "muted"

    return "neutral"


def _consistency_state_from_score(score):
    if score >= 75:
        return "strong"
    if score >= 45:
        return "moderate"
    return "limited"


def _apply_analytics_polish(analytics, window_days):
    analytics["comparison_label"] = f"vs previous {window_days}d"

    main_insight = analytics.get("main_insight")
    if main_insight:
        raw_state = (
            main_insight.get("state")
            or main_insight.get("status")
            or main_insight.get("badge")
            or "neutral"
        )
        main_insight["badge_label"] = _badge_label_for_state(raw_state, kind="main")
        main_insight["badge_tone"] = _badge_tone_for_state(raw_state, kind="main")

    next_action = analytics.get("next_action")
    if next_action:
        next_action["badge_label"] = _badge_label_for_state("priority", kind="action")
        next_action["badge_tone"] = _badge_tone_for_state("priority", kind="action")

    consistency = analytics.get("consistency")
    if consistency:
        overall_score = consistency.get("overall_score", 0)
        consistency_state = _consistency_state_from_score(overall_score)
        consistency["badge_label"] = _badge_label_for_state(consistency_state, kind="consistency")
        consistency["badge_tone"] = _badge_tone_for_state(consistency_state, kind="consistency")

    for item in analytics.get("secondary_insights", []):
        raw_state = (
            item.get("state")
            or item.get("status")
            or item.get("badge")
            or "stable"
        )
        item["badge_label"] = _badge_label_for_state(raw_state, kind="secondary")
        item["badge_tone"] = _badge_tone_for_state(raw_state, kind="secondary")

    return analytics

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

def _build_pandas_foundation_payload(
    *,
    user: User,
    recent_start: date,
    recent_end: date,
    previous_start: date,
    previous_end: date,
) -> dict[str, Any]:
    return {
        "enabled": True,
        "granularity": "day",
        "recent": build_bio_dataframe_foundation(
            user=user,
            start_date=recent_start,
            end_date=recent_end,
        ),
        "previous": build_bio_dataframe_foundation(
            user=user,
            start_date=previous_start,
            end_date=previous_end,
        ),
    }

def _build_pandas_rolling_payload(
    *,
    user: User,
    recent_start: date,
    recent_end: date,
    previous_start: date,
    previous_end: date,
) -> dict[str, Any]:
    return {
        "enabled": True,
        "recent": build_bio_rolling_foundation(
            user=user,
            start_date=recent_start,
            end_date=recent_end,
        ),
        "previous": build_bio_rolling_foundation(
            user=user,
            start_date=previous_start,
            end_date=previous_end,
        ),
    }

def _build_fitness_bridge_summary(
    *,
    pandas_foundation: dict[str, Any],
    pandas_rolling: dict[str, Any],
) -> dict[str, Any]:
    recent_foundation = pandas_foundation.get("recent", {})
    previous_foundation = pandas_foundation.get("previous", {})

    recent_strength = recent_foundation.get("strength_summary", {})
    previous_strength = previous_foundation.get("strength_summary", {})

    recent_rolling = pandas_rolling.get("recent", {}).get("latest", {})
    previous_rolling = pandas_rolling.get("previous", {}).get("latest", {})

    return {
        "enabled": True,
        "recent": {
            "training_days": recent_strength.get("training_days", 0),
            "sessions": recent_strength.get("sessions", 0),
            "set_count": recent_strength.get("set_count", 0),
            "exercise_count": recent_strength.get("exercise_count", 0),
            "volume_load": recent_strength.get("volume_load", 0),
            "avg_training_load_score": recent_strength.get("avg_training_load_score", 0),
            "rolling_training_load_ma_7d": recent_rolling.get("strength_training_load_ma_7d"),
            "rolling_strength_sessions_7d": recent_rolling.get("strength_sessions_7d"),
        },
        "previous": {
            "training_days": previous_strength.get("training_days", 0),
            "sessions": previous_strength.get("sessions", 0),
            "set_count": previous_strength.get("set_count", 0),
            "exercise_count": previous_strength.get("exercise_count", 0),
            "volume_load": previous_strength.get("volume_load", 0),
            "avg_training_load_score": previous_strength.get("avg_training_load_score", 0),
            "rolling_training_load_ma_7d": previous_rolling.get("strength_training_load_ma_7d"),
            "rolling_strength_sessions_7d": previous_rolling.get("strength_sessions_7d"),
        },
    }

def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _confidence_from_non_null_counts(recent_count: int, previous_count: int, *, high: int = 5, medium: int = 3) -> str:
    baseline = min(recent_count, previous_count)

    if baseline >= high:
        return "HIGH"
    if baseline >= medium:
        return "MEDIUM"
    return "LOW"


def _compare_directional_metric(
    *,
    recent_value: float | None,
    previous_value: float | None,
    tolerance: float,
    higher_is_better: bool,
    stable_label: str = "stable",
) -> tuple[str, float | None]:
    if recent_value is None or previous_value is None:
        return ("insufficient", None)

    delta = recent_value - previous_value
    if abs(delta) <= tolerance:
        return (stable_label, delta)

    if higher_is_better:
        return ("improving", delta) if delta > 0 else ("worsening", delta)

    return ("improving", delta) if delta < 0 else ("worsening", delta)


def _compare_weight_metric(
    *,
    recent_value: float | None,
    previous_value: float | None,
    tolerance: float,
) -> tuple[str, float | None]:
    if recent_value is None or previous_value is None:
        return ("insufficient", None)

    delta = recent_value - previous_value
    if abs(delta) <= tolerance:
        return ("stable", delta)
    return ("increasing", delta) if delta > 0 else ("decreasing", delta)


def _compare_balance_metric(
    *,
    recent_value: float | None,
    previous_value: float | None,
    tolerance: float,
) -> tuple[str, float | None]:
    if recent_value is None or previous_value is None:
        return ("insufficient", None)

    recent_abs = abs(recent_value)
    previous_abs = abs(previous_value)
    delta = recent_abs - previous_abs

    if abs(delta) <= tolerance:
        return ("stable", recent_value - previous_value)

    if recent_abs < previous_abs:
        return ("closer_to_target", recent_value - previous_value)
    return ("farther_from_target", recent_value - previous_value)


def _trend_card(
    *,
    name: str,
    signal: str,
    recent_value: float | None,
    previous_value: float | None,
    delta: float | None,
    confidence: str,
    basis: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "signal": signal,
        "recent_value": recent_value,
        "previous_value": previous_value,
        "delta": delta,
        "confidence": confidence,
        "basis": basis,
    }


def _pick_dominant_trend(trend_cards: list[dict[str, Any]]) -> dict[str, Any] | None:
    priority = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    neutral_signals = {"stable", "insufficient"}

    candidates = [
        card for card in trend_cards
        if card["signal"] not in neutral_signals
    ]
    if not candidates:
        return None

    candidates.sort(
        key=lambda card: (
            priority.get(card["confidence"], 0),
            abs(card["delta"]) if card["delta"] is not None else 0,
        ),
        reverse=True,
    )
    return candidates[0]


def _build_advanced_trends(
    *,
    pandas_rolling: dict[str, Any],
    fitness_bridge: dict[str, Any],
) -> dict[str, Any]:
    recent = pandas_rolling.get("recent", {})
    previous = pandas_rolling.get("previous", {})

    recent_latest = recent.get("latest", {})
    previous_latest = previous.get("latest", {})

    recent_non_null = recent.get("non_null_counts", {})
    previous_non_null = previous.get("non_null_counts", {})

    weight_recent = _safe_float(recent_latest.get("weight_ma_7d"))
    weight_previous = _safe_float(previous_latest.get("weight_ma_7d"))
    weight_signal, weight_delta = _compare_weight_metric(
        recent_value=weight_recent,
        previous_value=weight_previous,
        tolerance=0.2,
    )

    sleep_recent = _safe_float(recent_latest.get("sleep_ma_7d"))
    sleep_previous = _safe_float(previous_latest.get("sleep_ma_7d"))
    sleep_signal, sleep_delta = _compare_directional_metric(
        recent_value=sleep_recent,
        previous_value=sleep_previous,
        tolerance=0.2,
        higher_is_better=True,
    )

    alcohol_recent = _safe_float(recent_latest.get("alcohol_ma_7d"))
    alcohol_previous = _safe_float(previous_latest.get("alcohol_ma_7d"))
    alcohol_signal, alcohol_delta = _compare_directional_metric(
        recent_value=alcohol_recent,
        previous_value=alcohol_previous,
        tolerance=0.25,
        higher_is_better=False,
    )

    activity_recent = _safe_float(recent_latest.get("activity_minutes_7d"))
    activity_previous = _safe_float(previous_latest.get("activity_minutes_7d"))
    activity_signal, activity_delta = _compare_directional_metric(
        recent_value=activity_recent,
        previous_value=activity_previous,
        tolerance=20.0,
        higher_is_better=True,
    )

    calorie_recent = _safe_float(recent_latest.get("calorie_delta_ma_7d"))
    calorie_previous = _safe_float(previous_latest.get("calorie_delta_ma_7d"))
    calorie_signal, calorie_delta = _compare_balance_metric(
        recent_value=calorie_recent,
        previous_value=calorie_previous,
        tolerance=150.0,
    )

    strength_recent = _safe_float(recent_latest.get("strength_training_load_ma_7d"))
    strength_previous = _safe_float(previous_latest.get("strength_training_load_ma_7d"))
    strength_signal, strength_delta = _compare_weight_metric(
        recent_value=strength_recent,
        previous_value=strength_previous,
        tolerance=5.0,
    )

    trend_cards = [
        _trend_card(
            name="weight",
            signal=weight_signal,
            recent_value=weight_recent,
            previous_value=weight_previous,
            delta=weight_delta,
            confidence=_confidence_from_non_null_counts(
                int(recent_non_null.get("weight_ma_7d", 0)),
                int(previous_non_null.get("weight_ma_7d", 0)),
            ),
            basis="weight_ma_7d",
        ),
        _trend_card(
            name="sleep",
            signal=sleep_signal,
            recent_value=sleep_recent,
            previous_value=sleep_previous,
            delta=sleep_delta,
            confidence=_confidence_from_non_null_counts(
                int(recent_non_null.get("sleep_ma_7d", 0)),
                int(previous_non_null.get("sleep_ma_7d", 0)),
            ),
            basis="sleep_ma_7d",
        ),
        _trend_card(
            name="alcohol",
            signal=alcohol_signal,
            recent_value=alcohol_recent,
            previous_value=alcohol_previous,
            delta=alcohol_delta,
            confidence=_confidence_from_non_null_counts(
                int(recent_non_null.get("alcohol_ma_7d", 0)),
                int(previous_non_null.get("alcohol_ma_7d", 0)),
            ),
            basis="alcohol_ma_7d",
        ),
        _trend_card(
            name="activity",
            signal=activity_signal,
            recent_value=activity_recent,
            previous_value=activity_previous,
            delta=activity_delta,
            confidence=_confidence_from_non_null_counts(
                int(recent_non_null.get("activity_minutes_7d", 0)),
                int(previous_non_null.get("activity_minutes_7d", 0)),
                high=7,
                medium=4,
            ),
            basis="activity_minutes_7d",
        ),
        _trend_card(
            name="calorie_balance",
            signal=calorie_signal,
            recent_value=calorie_recent,
            previous_value=calorie_previous,
            delta=calorie_delta,
            confidence=_confidence_from_non_null_counts(
                int(recent_non_null.get("calorie_delta_ma_7d", 0)),
                int(previous_non_null.get("calorie_delta_ma_7d", 0)),
            ),
            basis="calorie_delta_ma_7d",
        ),
        _trend_card(
            name="strength_load",
            signal=strength_signal,
            recent_value=strength_recent,
            previous_value=strength_previous,
            delta=strength_delta,
            confidence=_confidence_from_non_null_counts(
                int(recent_non_null.get("strength_training_load_ma_7d", 0)),
                int(previous_non_null.get("strength_training_load_ma_7d", 0)),
                high=7,
                medium=3,
            ),
            basis="strength_training_load_ma_7d",
        ),
    ]

    dominant = _pick_dominant_trend(trend_cards)

    return {
        "enabled": True,
        "cards": trend_cards,
        "dominant": dominant,
        "fitness_context": fitness_bridge,
    }


def _build_correlation_layer(
    *,
    user: User,
    recent_start: date,
    recent_end: date,
    previous_start: date,
    previous_end: date,
) -> dict[str, Any]:
    return {
        "enabled": True,
        "recent": build_bio_correlation_foundation(
            user=user,
            start_date=recent_start,
            end_date=recent_end,
        ),
        "previous": build_bio_correlation_foundation(
            user=user,
            start_date=previous_start,
            end_date=previous_end,
        ),
    }

def _lookup_trend_card(advanced_trends: dict[str, Any], name: str) -> dict[str, Any] | None:
    for card in advanced_trends.get("cards", []):
        if card.get("name") == name:
            return card
    return None


def _lookup_dominant_correlation(correlation_layer: dict[str, Any]) -> dict[str, Any] | None:
    recent = correlation_layer.get("recent", {}).get("dominant")
    previous = correlation_layer.get("previous", {}).get("dominant")
    return recent or previous


def _card_with_state(card: dict[str, Any], state: str) -> dict[str, Any]:
    enriched = dict(card)
    enriched["state"] = state
    return enriched


def _format_metric(value: float | None, *, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    rounded = round(float(value), digits)
    if digits == 0:
        rounded = int(round(float(value), 0))
    return f"{rounded}{suffix}"


def _build_richer_main_insight(
    *,
    legacy_main_insight: dict[str, Any],
    advanced_trends: dict[str, Any],
    correlation_layer: dict[str, Any],
    fitness_bridge: dict[str, Any],
    pandas_foundation: dict[str, Any],
) -> dict[str, Any]:
    dominant = advanced_trends.get("dominant")
    dominant_correlation = _lookup_dominant_correlation(correlation_layer)

    recent_foundation = pandas_foundation.get("recent", {})
    metric_coverage_pct = recent_foundation.get("metric_coverage_pct", 0)
    activity_coverage_pct = recent_foundation.get("activity_coverage_pct", 0)

    recent_strength = fitness_bridge.get("recent", {})
    strength_sessions = recent_strength.get("sessions", 0)
    training_days = recent_strength.get("training_days", 0)

    if metric_coverage_pct < 50:
        return _card_with_state(
            _build_card(
                kicker="Main insight",
                title="Tracking coverage is limiting interpretation",
                body=(
                    f"Metric coverage is only {metric_coverage_pct}% in the recent window, "
                    "so the smarter trend layer is active but confidence is still limited."
                ),
                badge="LIMITED",
                tone="warn",
            ),
            "limited",
        )

    if dominant and dominant.get("name") == "activity" and dominant.get("signal") == "worsening":
        recent_value = dominant.get("recent_value")
        previous_value = dominant.get("previous_value")
        extra = ""
        if strength_sessions == 0:
            extra = " No completed strength sessions were captured in the recent window either."
        return _card_with_state(
            _build_card(
                kicker="Main insight",
                title="Movement baseline dropped in the recent window",
                body=(
                    f"Rolling activity volume fell from {_format_metric(previous_value, digits=0, suffix=' min')} "
                    f"to {_format_metric(recent_value, digits=0, suffix=' min')}.{extra}"
                ),
                badge="WORSENING",
                tone="warn",
            ),
            "worsening",
        )

    if dominant and dominant.get("name") == "sleep" and dominant.get("signal") == "worsening":
        return _card_with_state(
            _build_card(
                kicker="Main insight",
                title="Recovery trend weakened",
                body=(
                    f"Rolling sleep quality moved from {_format_metric(dominant.get('previous_value'))} "
                    f"to {_format_metric(dominant.get('recent_value'))}, so the recent window looks less recovered."
                ),
                badge="WORSENING",
                tone="warn",
            ),
            "worsening",
        )

    if dominant and dominant.get("name") == "calorie_balance" and dominant.get("signal") == "closer_to_target":
        return _card_with_state(
            _build_card(
                kicker="Main insight",
                title="Intake alignment improved",
                body=(
                    "The rolling calorie balance moved closer to target than in the previous window, "
                    "which makes intake interpretation cleaner."
                ),
                badge="IMPROVING",
                tone="good",
            ),
            "improving",
        )

    if dominant and dominant.get("name") == "strength_load" and dominant.get("signal") == "increasing" and training_days > 0:
        return _card_with_state(
            _build_card(
                kicker="Main insight",
                title="Training load stepped up",
                body=(
                    f"The recent window includes {strength_sessions} completed strength sessions "
                    "with a higher rolling training load than before."
                ),
                badge="HIGHER LOAD",
                tone="info",
            ),
            "increasing",
        )

    if dominant_correlation and dominant_correlation.get("status") == "OK":
        return _card_with_state(
            _build_card(
                kicker="Main insight",
                title="A relationship signal is starting to emerge",
                body=(
                    f"{dominant_correlation['label']} is currently the clearest association in the available data "
                    f"({dominant_correlation['direction'].lower()}, {dominant_correlation['strength'].lower()})."
                ),
                badge="ASSOCIATION",
                tone="neutral",
            ),
            "mixed",
        )

    return legacy_main_insight


def _build_richer_next_action(
    *,
    legacy_next_action: dict[str, Any],
    advanced_trends: dict[str, Any],
    correlation_layer: dict[str, Any],
    fitness_bridge: dict[str, Any],
    pandas_foundation: dict[str, Any],
) -> dict[str, Any]:
    recent_foundation = pandas_foundation.get("recent", {})
    metric_coverage_pct = recent_foundation.get("metric_coverage_pct", 0)

    activity_card = _lookup_trend_card(advanced_trends, "activity")
    sleep_card = _lookup_trend_card(advanced_trends, "sleep")
    alcohol_card = _lookup_trend_card(advanced_trends, "alcohol")
    strength_card = _lookup_trend_card(advanced_trends, "strength_load")

    dominant_correlation = _lookup_dominant_correlation(correlation_layer)
    recent_strength = fitness_bridge.get("recent", {})
    training_days = recent_strength.get("training_days", 0)
    strength_sessions = recent_strength.get("sessions", 0)

    if metric_coverage_pct < 60:
        return _card_with_state(
            _build_card(
                kicker="Next action",
                title="Raise metric coverage first",
                body=(
                    f"Recent metric coverage is only {metric_coverage_pct}%, so add more daily BIO entries "
                    "before trusting the stronger analytics too much."
                ),
                badge="TRACKING",
                tone="warn",
            ),
            "limited",
        )

    if activity_card and activity_card.get("signal") == "worsening" and strength_sessions == 0:
        return _card_with_state(
            _build_card(
                kicker="Next action",
                title="Add one real movement or training day",
                body=(
                    "The rolling activity baseline faded and no completed strength session was captured recently, "
                    "so the cleanest next step is to add one genuine activity day."
                ),
                badge="MOVEMENT",
                tone="warn",
            ),
            "worsening",
        )

    if (
        sleep_card and sleep_card.get("signal") == "worsening"
        and alcohol_card and alcohol_card.get("signal") == "worsening"
    ):
        return _card_with_state(
            _build_card(
                kicker="Next action",
                title="Reduce evening recovery drag",
                body=(
                    "Sleep and alcohol both moved the wrong way. Protect the next few evenings first, "
                    "then reassess trend direction."
                ),
                badge="RECOVERY",
                tone="warn",
            ),
            "worsening",
        )

    if training_days > 0 and (sleep_card is None or sleep_card.get("signal") == "insufficient"):
        return _card_with_state(
            _build_card(
                kicker="Next action",
                title="Track sleep around training days",
                body=(
                    f"You already have {strength_sessions} completed strength session(s) in the window, "
                    "so add sleep data consistently to unlock better recovery correlations."
                ),
                badge="SLEEP DATA",
                tone="neutral",
            ),
            "neutral",
        )

    if dominant_correlation and dominant_correlation.get("name") == "alcohol_vs_next_sleep":
        return _card_with_state(
            _build_card(
                kicker="Next action",
                title="Test alcohol reduction against sleep",
                body=(
                    "The clearest relationship signal currently points at alcohol and next-day sleep, "
                    "so the next useful experiment is reducing alcohol exposure for a few days."
                ),
                badge="EXPERIMENT",
                tone="neutral",
            ),
            "mixed",
        )

    if strength_card and strength_card.get("signal") == "increasing" and training_days > 0:
        return _card_with_state(
            _build_card(
                kicker="Next action",
                title="Support the higher training load",
                body=(
                    "Training load is trending upward. Keep recovery inputs tighter before increasing complexity further."
                ),
                badge="LOAD",
                tone="neutral",
            ),
            "increasing",
        )

    return legacy_next_action


def _build_richer_weekly_summary_card(
    *,
    legacy_weekly_summary_card: dict[str, Any],
    pandas_foundation: dict[str, Any],
    fitness_bridge: dict[str, Any],
) -> dict[str, Any]:
    recent_foundation = pandas_foundation.get("recent", {})
    recent_strength = fitness_bridge.get("recent", {})

    rows = recent_foundation.get("rows", 0)
    metric_days = recent_foundation.get("metric_days", 0)
    activity_days = recent_foundation.get("activity_days", 0)
    activity_totals = recent_foundation.get("activity_totals", {})
    strength_sessions = recent_strength.get("sessions", 0)
    training_days = recent_strength.get("training_days", 0)
    avg_training_load_score = recent_strength.get("avg_training_load_score", 0)

    if rows == 0:
        return legacy_weekly_summary_card

    return _card_with_state(
        _build_card(
            kicker="Weekly summary",
            title=f"{rows}-day enriched summary",
            body=(
                f"{metric_days}/{rows} metric days, {activity_days} active days, "
                f"{activity_totals.get('minutes', 0)} clean movement min, "
                f"{strength_sessions} strength session(s) across {training_days} training day(s)."
            ),
            tone="neutral",
            supporting=(
                f"Average training load score: {avg_training_load_score}"
                if strength_sessions
                else "No completed strength sessions were captured in this window."
            ),
        ),
        "neutral",
    )


def _build_richer_secondary_insights(
    *,
    legacy_secondary_insights: list[dict[str, Any]],
    advanced_trends: dict[str, Any],
    correlation_layer: dict[str, Any],
    fitness_bridge: dict[str, Any],
) -> list[dict[str, Any]]:
    recent_strength = fitness_bridge.get("recent", {})
    dominant_correlation = _lookup_dominant_correlation(correlation_layer)

    weight_card = _lookup_trend_card(advanced_trends, "weight")
    sleep_card = _lookup_trend_card(advanced_trends, "sleep")
    alcohol_card = _lookup_trend_card(advanced_trends, "alcohol")
    activity_card = _lookup_trend_card(advanced_trends, "activity")
    calorie_card = _lookup_trend_card(advanced_trends, "calorie_balance")

    cards: list[dict[str, Any]] = []

    if weight_card and weight_card.get("signal") != "insufficient":
        cards.append(_card_with_state(
            _build_card(
                kicker="Secondary insight",
                title="Weight trend",
                body=(
                    f"Rolling weight moved from {_format_metric(weight_card.get('previous_value'))} kg "
                    f"to {_format_metric(weight_card.get('recent_value'))} kg."
                ),
                badge=str(weight_card.get("signal", "stable")).upper(),
                tone="neutral",
                supporting=f"Confidence: {weight_card.get('confidence', 'LOW')}",
            ),
            str(weight_card.get("signal", "stable")),
        ))
    else:
        cards.append(legacy_secondary_insights[0])

    if sleep_card and alcohol_card and (
        sleep_card.get("signal") != "insufficient" or alcohol_card.get("signal") != "insufficient"
    ):
        cards.append(_card_with_state(
            _build_card(
                kicker="Secondary insight",
                title="Recovery pattern",
                body=(
                    f"Sleep: {sleep_card.get('signal')} / Alcohol: {alcohol_card.get('signal')} "
                    "on rolling 7d signals."
                ),
                badge="RECOVERY",
                tone="neutral" if sleep_card.get("signal") != "worsening" else "warn",
                supporting=(
                    f"Correlation lead: {dominant_correlation['label']}"
                    if dominant_correlation and dominant_correlation.get("status") == "OK"
                    else None
                ),
            ),
            "mixed",
        ))
    else:
        cards.append(legacy_secondary_insights[1])

    cards.append(_card_with_state(
        _build_card(
            kicker="Secondary insight",
            title="Activity + training",
            body=(
                f"Rolling movement signal is {activity_card.get('signal') if activity_card else 'insufficient'} "
                f"with {recent_strength.get('sessions', 0)} completed strength session(s)."
            ),
            badge="TRAINING" if recent_strength.get("sessions", 0) else "ACTIVITY",
            tone="neutral" if recent_strength.get("sessions", 0) else "warn",
            supporting=(
                f"Avg training load score {recent_strength.get('avg_training_load_score', 0)}"
                if recent_strength.get("sessions", 0)
                else "No completed strength session in the recent window."
            ),
        ),
        "neutral",
    ))

    if calorie_card and calorie_card.get("signal") != "insufficient":
        cards.append(_card_with_state(
            _build_card(
                kicker="Secondary insight",
                title="Calorie balance",
                body=(
                    "Rolling intake balance is "
                    f"{str(calorie_card.get('signal', 'stable')).replace('_', ' ')} versus the previous window."
                ),
                badge=str(calorie_card.get("signal", "stable")).upper(),
                tone="neutral",
                supporting=f"Confidence: {calorie_card.get('confidence', 'LOW')}",
            ),
            str(calorie_card.get("signal", "stable")),
        ))
    else:
        cards.append(legacy_secondary_insights[3])

    return cards[:4]


def _build_richer_summary_generation(
    *,
    legacy_main_insight: dict[str, Any],
    legacy_next_action: dict[str, Any],
    legacy_weekly_summary_card: dict[str, Any],
    legacy_secondary_insights: list[dict[str, Any]],
    advanced_trends: dict[str, Any],
    correlation_layer: dict[str, Any],
    fitness_bridge: dict[str, Any],
    pandas_foundation: dict[str, Any],
) -> dict[str, Any]:
    main_insight = _build_richer_main_insight(
        legacy_main_insight=legacy_main_insight,
        advanced_trends=advanced_trends,
        correlation_layer=correlation_layer,
        fitness_bridge=fitness_bridge,
        pandas_foundation=pandas_foundation,
    )
    next_action = _build_richer_next_action(
        legacy_next_action=legacy_next_action,
        advanced_trends=advanced_trends,
        correlation_layer=correlation_layer,
        fitness_bridge=fitness_bridge,
        pandas_foundation=pandas_foundation,
    )
    weekly_summary_card = _build_richer_weekly_summary_card(
        legacy_weekly_summary_card=legacy_weekly_summary_card,
        pandas_foundation=pandas_foundation,
        fitness_bridge=fitness_bridge,
    )
    secondary_insights = _build_richer_secondary_insights(
        legacy_secondary_insights=legacy_secondary_insights,
        advanced_trends=advanced_trends,
        correlation_layer=correlation_layer,
        fitness_bridge=fitness_bridge,
    )

    insights = _build_legacy_insights(
        main_insight=main_insight,
        next_action=next_action,
        weekly_summary_card=weekly_summary_card,
        secondary_insights=secondary_insights,
    )

    return {
        "engine_version": "pandas_summary_v1",
        "main_insight": main_insight,
        "next_action": next_action,
        "weekly_summary_card": weekly_summary_card,
        "secondary_insights": secondary_insights,
        "insights": insights,
    }


def _secondary_guard_card(
    *,
    title: str,
    body: str,
    badge: str = "LIMITED",
    tone: str = "warn",
    supporting: str | None = None,
    state: str = "limited",
) -> dict[str, Any]:
    return _card_with_state(
        _build_card(
            kicker="Secondary insight",
            title=title,
            body=body,
            badge=badge,
            tone=tone,
            supporting=supporting,
        ),
        state,
    )


def _build_guarded_secondary_insights(
    *,
    richer_summary: dict[str, Any],
    pandas_foundation: dict[str, Any],
    advanced_trends: dict[str, Any],
    correlation_layer: dict[str, Any],
    fitness_bridge: dict[str, Any],
) -> list[dict[str, Any]]:
    recent_foundation = pandas_foundation.get("recent", {})
    rows = int(recent_foundation.get("rows", 0) or 0)
    metric_days = int(recent_foundation.get("metric_days", 0) or 0)
    activity_days = int(recent_foundation.get("activity_days", 0) or 0)
    coverage = int(recent_foundation.get("metric_coverage_pct", 0) or 0)

    recent_strength = fitness_bridge.get("recent", {})
    dominant_trend = advanced_trends.get("dominant")
    dominant_correlation = _lookup_dominant_correlation(correlation_layer)

    richer_cards = richer_summary.get("secondary_insights", [])

    cards: list[dict[str, Any]] = []

    cards.append(
        _secondary_guard_card(
            title="Coverage",
            body=f"{metric_days}/{rows} metric days and {activity_days} active days in the recent window.",
            badge="LIMITED" if coverage < 60 else "USABLE",
            tone="warn" if coverage < 60 else "neutral",
            supporting=(
                "Interpretation is still thin; treat comparisons cautiously."
                if coverage < 60
                else "Coverage is usable enough for trend interpretation."
            ),
            state="limited" if coverage < 60 else "neutral",
        )
    )

    if len(richer_cards) >= 3:
        cards.append(richer_cards[2])
    else:
        cards.append(
            _secondary_guard_card(
                title="Activity + training",
                body=(
                    f"{activity_days} active days and {recent_strength.get('sessions', 0)} completed strength session(s) "
                    "were captured in the recent window."
                ),
                badge="ACTIVITY",
                tone="neutral",
                supporting=(
                    f"Avg training load score {recent_strength.get('avg_training_load_score', 0)}"
                    if recent_strength.get("sessions", 0)
                    else "No completed strength session in the recent window."
                ),
                state="neutral",
            )
        )

    if dominant_trend:
        cards.append(
            _secondary_guard_card(
                title="Trend confidence",
                body=(
                    f"The clearest current trend is {dominant_trend['name']} = {dominant_trend['signal']} "
                    f"with {dominant_trend.get('confidence', 'LOW')} confidence."
                ),
                badge="TREND",
                tone="neutral",
                supporting=f"Basis: {dominant_trend.get('basis', 'n/a')}",
                state="neutral",
            )
        )
    else:
        cards.append(
            _secondary_guard_card(
                title="Trend confidence",
                body="The trend engine is active, but the recent window still lacks enough paired data for confident secondary trend calls.",
                badge="LIMITED",
                tone="warn",
                supporting="Add more consecutive metric days to unlock better secondary signals.",
                state="limited",
            )
        )

    if dominant_correlation and dominant_correlation.get("status") == "OK":
        cards.append(
            _secondary_guard_card(
                title="Association signal",
                body=(
                    f"{dominant_correlation['label']} is the clearest current relationship signal "
                    f"({dominant_correlation['direction'].lower()}, {dominant_correlation['strength'].lower()})."
                ),
                badge="ASSOCIATION",
                tone="neutral",
                supporting="Associative only — not a causal claim.",
                state="neutral",
            )
        )
    else:
        cards.append(
            _secondary_guard_card(
                title="Associations",
                body="There is not enough paired data yet for reliable correlation-style insight cards.",
                badge="INSUFFICIENT",
                tone="warn",
                supporting="Keep logging consecutive days, especially around sleep, alcohol, activity and training.",
                state="limited",
            )
        )

    return cards[:4]


def _select_insight_model(
    *,
    legacy_summary: dict[str, Any],
    richer_summary: dict[str, Any],
    pandas_foundation: dict[str, Any],
    advanced_trends: dict[str, Any],
    correlation_layer: dict[str, Any],
    fitness_bridge: dict[str, Any],
) -> dict[str, Any]:
    recent_foundation = pandas_foundation.get("recent", {})
    metric_days = int(recent_foundation.get("metric_days", 0) or 0)
    coverage = int(recent_foundation.get("metric_coverage_pct", 0) or 0)
    activity_days = int(recent_foundation.get("activity_days", 0) or 0)

    v1 = {
        "model_id": "legacy_v1",
        "summary": legacy_summary,
    }
    v2 = {
        "model_id": "pandas_summary_v1",
        "summary": richer_summary,
    }

    if metric_days < 3 or coverage < 40:
        guarded_secondary = _build_guarded_secondary_insights(
            richer_summary=richer_summary,
            pandas_foundation=pandas_foundation,
            advanced_trends=advanced_trends,
            correlation_layer=correlation_layer,
            fitness_bridge=fitness_bridge,
        )
        selected_summary = {
            "engine_version": "hybrid_guarded_v2",
            "main_insight": richer_summary["main_insight"],
            "next_action": richer_summary["next_action"],
            "weekly_summary_card": richer_summary["weekly_summary_card"],
            "secondary_insights": guarded_secondary,
            "insights": _build_legacy_insights(
                main_insight=richer_summary["main_insight"],
                next_action=richer_summary["next_action"],
                weekly_summary_card=richer_summary["weekly_summary_card"],
                secondary_insights=guarded_secondary,
            ),
        }
        return {
            "selected_model": "hybrid_guarded_v2",
            "selection_reason": (
                f"Recent coverage is thin ({coverage}% / {metric_days} metric days), "
                "so v2 main cards are kept but secondary insights are gated."
            ),
            "v1": v1,
            "v2": v2,
            "selected_summary": selected_summary,
        }

    if coverage < 60 or activity_days < 2:
        guarded_secondary = _build_guarded_secondary_insights(
            richer_summary=richer_summary,
            pandas_foundation=pandas_foundation,
            advanced_trends=advanced_trends,
            correlation_layer=correlation_layer,
            fitness_bridge=fitness_bridge,
        )
        selected_summary = {
            "engine_version": "hybrid_v2_cautious",
            "main_insight": richer_summary["main_insight"],
            "next_action": richer_summary["next_action"],
            "weekly_summary_card": richer_summary["weekly_summary_card"],
            "secondary_insights": guarded_secondary,
            "insights": _build_legacy_insights(
                main_insight=richer_summary["main_insight"],
                next_action=richer_summary["next_action"],
                weekly_summary_card=richer_summary["weekly_summary_card"],
                secondary_insights=guarded_secondary,
            ),
        }
        return {
            "selected_model": "hybrid_v2_cautious",
            "selection_reason": (
                f"Coverage is improving but still not robust enough for full v2 secondary cards "
                f"({coverage}% coverage, {activity_days} active days)."
            ),
            "v1": v1,
            "v2": v2,
            "selected_summary": selected_summary,
        }

    return {
        "selected_model": "pandas_summary_v1",
        "selection_reason": "Coverage and activity depth are sufficient for full pandas-enriched summary output.",
        "v1": v1,
        "v2": v2,
        "selected_summary": richer_summary,
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
    intake_trend_raw = _trend_label(avg_calories_actual, prev_avg_calories_actual, tolerance=75.0)

    weight_signal = _weight_signal(weight_trend_raw)
    sleep_signal = _sleep_signal(sleep_trend_raw)
    alcohol_signal = _alcohol_signal(alcohol_trend_raw)

    pandas_foundation = _build_pandas_foundation_payload(
        user=user,
        recent_start=recent_start,
        recent_end=today,
        previous_start=previous_start,
        previous_end=previous_end,
    )

    pandas_rolling = _build_pandas_rolling_payload(
        user=user,
        recent_start=recent_start,
        recent_end=today,
        previous_start=previous_start,
        previous_end=previous_end,
    )

    recent_foundation = pandas_foundation.get("recent", {})
    previous_foundation = pandas_foundation.get("previous", {})

    recent_activity_totals = recent_foundation.get("activity_totals", {})
    previous_activity_totals = previous_foundation.get("activity_totals", {})

    activity_entries = int(recent_activity_totals.get("entries", activity_entries) or 0)
    active_days = int(recent_foundation.get("activity_days", active_days) or 0)

    total_activity_minutes = int(recent_activity_totals.get("minutes", total_activity_minutes) or 0)
    prev_total_activity_minutes = int(
        previous_activity_totals.get("minutes", prev_total_activity_minutes) or 0
    )

    recent_distance = _safe_float(recent_activity_totals.get("distance_km"))
    previous_distance = _safe_float(previous_activity_totals.get("distance_km"))

    if recent_distance is not None:
        total_distance = round(recent_distance, 2)
    if previous_distance is not None:
        prev_total_distance = round(previous_distance, 2)

    activity_trend_raw = _trend_label(
        float(total_activity_minutes),
        float(prev_total_activity_minutes),
        tolerance=20.0,
    )
    activity_signal = _activity_signal(activity_trend_raw)

    consistency = _consistency_breakdown(metric_days, active_days, period_days)
    consistency["active_days"] = active_days

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

    fitness_bridge = _build_fitness_bridge_summary(
        pandas_foundation=pandas_foundation,
        pandas_rolling=pandas_rolling,
    )

    advanced_trends = _build_advanced_trends(
        pandas_rolling=pandas_rolling,
        fitness_bridge=fitness_bridge,
    )

    correlation_layer = _build_correlation_layer(
        user=user,
        recent_start=recent_start,
        recent_end=today,
        previous_start=previous_start,
        previous_end=previous_end,
    )

    legacy_main_insight = main_insight
    legacy_next_action = next_action
    legacy_weekly_summary_card = weekly_summary_card
    legacy_secondary_insights = secondary_insights

    richer_summary = _build_richer_summary_generation(
        legacy_main_insight=legacy_main_insight,
        legacy_next_action=legacy_next_action,
        legacy_weekly_summary_card=legacy_weekly_summary_card,
        legacy_secondary_insights=legacy_secondary_insights,
        advanced_trends=advanced_trends,
        correlation_layer=correlation_layer,
        fitness_bridge=fitness_bridge,
        pandas_foundation=pandas_foundation,
    )

    legacy_summary = {
        "main_insight": legacy_main_insight,
        "next_action": legacy_next_action,
        "weekly_summary_card": legacy_weekly_summary_card,
        "secondary_insights": legacy_secondary_insights,
    }

    insight_models = _select_insight_model(
        legacy_summary=legacy_summary,
        richer_summary=richer_summary,
        pandas_foundation=pandas_foundation,
        advanced_trends=advanced_trends,
        correlation_layer=correlation_layer,
        fitness_bridge=fitness_bridge,
    )

    selected_summary = insight_models["selected_summary"]

    main_insight = selected_summary["main_insight"]
    next_action = selected_summary["next_action"]
    weekly_summary_card = selected_summary["weekly_summary_card"]
    secondary_insights = selected_summary["secondary_insights"]
    insights = selected_summary["insights"]

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
        "pandas_foundation": pandas_foundation,
        "pandas_rolling": pandas_rolling,
        "fitness_bridge": fitness_bridge,
        "trend_engine_version": "pandas_v1",
        "advanced_trends": advanced_trends,
        "correlation_engine_version": "pandas_v1",
        "correlation_layer": correlation_layer,
        "summary_engine_version": "pandas_summary_v1",
        "richer_summary": richer_summary,
        "legacy_summary": {
            "main_insight": legacy_main_insight,
            "next_action": legacy_next_action,
            "weekly_summary_card": legacy_weekly_summary_card,
            "secondary_insights": legacy_secondary_insights,
        },
        "insight_model_v1": insight_models["v1"],
        "insight_model_v2": insight_models["v2"],
        "selected_insight_model": insight_models["selected_model"],
        "insight_selection_reason": insight_models["selection_reason"],
        "selected_summary": selected_summary,
    }

def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


SNAPSHOT_REFRESH_COOLDOWN_MINUTES = 5


def get_snapshot_max_age_hours(snapshot_type: str) -> int:
    if snapshot_type == AnalyticsSnapshotType.OVERVIEW:
        return 6
    return 12


def queue_snapshot_refresh(*, user: User, period_days: int, snapshot_type: str) -> AnalyticsSnapshot:
    now = timezone.now()
    today = timezone.localdate()

    snapshot, _ = AnalyticsSnapshot.objects.update_or_create(
        user=user,
        snapshot_type=snapshot_type,
        window_days=period_days,
        defaults={
            "as_of_date": today,
            "status": AnalyticsSnapshotStatus.QUEUED,
            "last_enqueued_at": now,
            "last_error": "",
        },
    )
    return snapshot


def mark_snapshot_error(*, user: User, period_days: int, snapshot_type: str, error: str) -> AnalyticsSnapshot:
    snapshot, _ = AnalyticsSnapshot.objects.update_or_create(
        user=user,
        snapshot_type=snapshot_type,
        window_days=period_days,
        defaults={
            "as_of_date": timezone.localdate(),
        },
    )
    snapshot.status = AnalyticsSnapshotStatus.ERROR
    snapshot.last_error = error[:2000]
    snapshot.save(update_fields=["status", "last_error", "updated_at"])
    return snapshot


def store_bio_analytics_snapshot(*, user: User, period_days: int, snapshot_type: str) -> AnalyticsSnapshot:
    payload = build_bio_analytics(user=user, period_days=period_days)
    now = timezone.now()

    snapshot, _ = AnalyticsSnapshot.objects.update_or_create(
        user=user,
        snapshot_type=snapshot_type,
        window_days=period_days,
        defaults={
            "as_of_date": timezone.localdate(),
            "payload": _json_safe(payload),
            "status": AnalyticsSnapshotStatus.FRESH,
            "last_success_at": now,
            "last_error": "",
        },
    )
    return snapshot


def get_bio_analytics_snapshot(*, user: User, period_days: int, snapshot_type: str) -> AnalyticsSnapshot | None:
    return (
        AnalyticsSnapshot.objects
        .filter(
            user=user,
            snapshot_type=snapshot_type,
            window_days=period_days,
        )
        .first()
    )


def get_bio_analytics_payload(*, user: User, period_days: int, snapshot_type: str) -> dict[str, Any] | None:
    snapshot = get_bio_analytics_snapshot(
        user=user,
        period_days=period_days,
        snapshot_type=snapshot_type,
    )
    return snapshot.payload if snapshot else None


def get_cached_bio_analytics(*, user: User, period_days: int, snapshot_type: str) -> dict[str, Any]:
    cached = get_bio_analytics_payload(
        user=user,
        period_days=period_days,
        snapshot_type=snapshot_type,
    )
    if cached:
        return cached

    return build_bio_analytics(user=user, period_days=period_days)