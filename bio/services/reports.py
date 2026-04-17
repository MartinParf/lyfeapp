from __future__ import annotations

from datetime import date
from typing import Any

from bio.services.analytics import build_bio_analytics
from bio.services.dataframes import build_bio_daily_df


def build_bio_analytics_report(*, user, period_days: int) -> dict[str, Any]:
    analytics = build_bio_analytics(user=user, period_days=period_days)

    return {
        "report_type": "bio_analytics_report",
        "period_days": period_days,
        "generated_for_user_id": user.id,
        "generated_for_username": getattr(user, "username", "") or "",
        "analytics": analytics,
    }


def build_bio_daily_csv_rows(*, user, start_date: date, end_date: date) -> list[dict[str, Any]]:
    bundle = build_bio_daily_df(user=user, start_date=start_date, end_date=end_date)
    daily_df = bundle.daily.copy()

    if daily_df.empty:
        return []

    export_df = daily_df.copy()
    export_df["date"] = export_df["date"].dt.date.astype(str)
    export_df["activity_types"] = export_df["activity_types"].apply(
        lambda values: ", ".join(values) if isinstance(values, list) else ""
    )

    rows: list[dict[str, Any]] = export_df.to_dict(orient="records")
    return rows