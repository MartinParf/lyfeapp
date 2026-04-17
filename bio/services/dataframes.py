from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd

from bio.models import Activity, DailyMetric
from fitness.services.analytics_bridge import build_completed_session_activity_rows


METRIC_COLUMNS = [
    "date",
    "weight_kg",
    "sleep_quality",
    "alcohol_units",
    "calories_planned",
    "calories_actual",
    "diet_mode",
]

ACTIVITY_ENTRY_COLUMNS = [
    "date",
    "activity_type",
    "duration_minutes",
    "calories_burned_est",
    "distance_km",
    "source",
    "is_strength_training",
    "session_count",
    "exercise_count",
    "set_count",
    "volume_load",
    "training_load_score",
    "training_load_band",
    "session_focus",
]

ACTIVITY_DAILY_COLUMNS = [
    "date",
    "activity_entries",
    "activity_minutes_raw",
    "activity_minutes",
    "activity_calories_raw",
    "activity_calories",
    "activity_distance_km_raw",
    "activity_distance_km",
    "activity_duration_outlier_count",
    "activity_distance_outlier_count",
    "activity_calories_outlier_count",
    "activity_type_count",
    "activity_types",
    "activity_logged",
    "strength_sessions",
    "strength_exercise_count",
    "strength_set_count",
    "strength_volume_load",
    "strength_training_load_score",
    "strength_training_day",
]

DAILY_COLUMNS = [
    "date",
    "metric_logged",
    "has_metric",
    "weight_kg",
    "sleep_quality",
    "alcohol_units",
    "calories_planned",
    "calories_actual",
    "diet_mode",
    "activity_logged",
    "has_activity",
    "activity_entries",
    "activity_minutes_raw",
    "activity_minutes",
    "activity_calories_raw",
    "activity_calories",
    "activity_distance_km_raw",
    "activity_distance_km",
    "activity_duration_outlier_count",
    "activity_distance_outlier_count",
    "activity_calories_outlier_count",
    "activity_type_count",
    "activity_types",
    "strength_sessions",
    "strength_exercise_count",
    "strength_set_count",
    "strength_volume_load",
    "strength_training_load_score",
    "strength_training_day",
    "calorie_delta",
    "calorie_target_hit",
    "weight_change_1d",
    "sleep_low_flag",
    "alcohol_high_flag",
]

ROLLING_COLUMNS = [
    "date",
    "weight_ma_3d",
    "weight_ma_7d",
    "sleep_ma_3d",
    "sleep_ma_7d",
    "alcohol_ma_7d",
    "calories_actual_ma_7d",
    "calorie_delta_ma_7d",
    "activity_minutes_7d",
    "activity_entries_7d",
    "activity_distance_km_7d",
    "active_days_7d",
    "metric_days_7d",
    "strength_sessions_7d",
    "strength_set_count_7d",
    "strength_volume_load_7d",
    "strength_training_load_ma_7d",
]

MAX_ACTIVITY_DURATION_MINUTES = 720
MAX_ACTIVITY_DISTANCE_KM = 200.0
MAX_ACTIVITY_CALORIES_BURNED = 5000


@dataclass(frozen=True)
class BioDataFrameBundle:
    daily: pd.DataFrame
    metrics: pd.DataFrame
    activities: pd.DataFrame


def _decimal_to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _round_float(value: Any, digits: int = 2) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def _empty_metrics_df() -> pd.DataFrame:
    return pd.DataFrame(columns=METRIC_COLUMNS + ["metric_logged"])


def _empty_activity_entries_df() -> pd.DataFrame:
    return pd.DataFrame(columns=ACTIVITY_ENTRY_COLUMNS)


def _empty_activity_daily_df() -> pd.DataFrame:
    return pd.DataFrame(columns=ACTIVITY_DAILY_COLUMNS)


def _empty_rolling_df() -> pd.DataFrame:
    return pd.DataFrame(columns=ROLLING_COLUMNS)


def _ensure_datetime_date_column(df: pd.DataFrame) -> pd.DataFrame:
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    return df


def build_daily_metrics_df(*, user, start_date: date, end_date: date) -> pd.DataFrame:
    rows = list(
        DailyMetric.objects
        .filter(user=user, date__gte=start_date, date__lte=end_date)
        .order_by("date")
        .values(*METRIC_COLUMNS)
    )

    if not rows:
        return _empty_metrics_df()

    df = pd.DataFrame.from_records(rows)
    df = _ensure_datetime_date_column(df)

    numeric_columns = [
        "weight_kg",
        "sleep_quality",
        "alcohol_units",
        "calories_planned",
        "calories_actual",
    ]
    for column in numeric_columns:
        if column in df.columns:
            if column == "weight_kg":
                df[column] = df[column].map(_decimal_to_float)
            df[column] = pd.to_numeric(df[column], errors="coerce")

    df["metric_logged"] = True
    df = df.sort_values("date").reset_index(drop=True)
    return df


def build_activity_entries_df(*, user, start_date: date, end_date: date) -> pd.DataFrame:
    bio_rows = list(
        Activity.objects
        .filter(user=user, date__gte=start_date, date__lte=end_date)
        .order_by("date", "id")
        .values(
            "date",
            "activity_type",
            "duration_minutes",
            "calories_burned_est",
            "distance_km",
        )
    )

    normalized_bio_rows = [
        {
            "date": row["date"],
            "activity_type": row["activity_type"],
            "duration_minutes": row["duration_minutes"],
            "calories_burned_est": row["calories_burned_est"],
            "distance_km": row["distance_km"],
            "source": "BIO_ACTIVITY",
            "is_strength_training": False,
            "session_count": 0,
            "exercise_count": 0,
            "set_count": 0,
            "volume_load": 0.0,
            "training_load_score": 0,
            "training_load_band": None,
            "session_focus": None,
        }
        for row in bio_rows
    ]

    session_rows = build_completed_session_activity_rows(
        user=user,
        start_date=start_date,
        end_date=end_date,
    )

    rows = normalized_bio_rows + session_rows

    if not rows:
        return _empty_activity_entries_df()

    df = pd.DataFrame.from_records(rows)
    df = _ensure_datetime_date_column(df)

    numeric_columns = [
        "duration_minutes",
        "calories_burned_est",
        "distance_km",
        "session_count",
        "exercise_count",
        "set_count",
        "volume_load",
        "training_load_score",
    ]
    for column in numeric_columns:
        if column in df.columns:
            if column == "distance_km":
                df[column] = df[column].map(_decimal_to_float)
            df[column] = pd.to_numeric(df[column], errors="coerce")

    df["activity_duration_outlier"] = (
        df["duration_minutes"].notna()
        & (
            (df["duration_minutes"] < 1)
            | (df["duration_minutes"] > MAX_ACTIVITY_DURATION_MINUTES)
        )
    )
    df["activity_distance_outlier"] = (
        df["distance_km"].notna()
        & (
            (df["distance_km"] < 0)
            | (df["distance_km"] > MAX_ACTIVITY_DISTANCE_KM)
        )
    )
    df["activity_calories_outlier"] = (
        df["calories_burned_est"].notna()
        & (
            (df["calories_burned_est"] < 0)
            | (df["calories_burned_est"] > MAX_ACTIVITY_CALORIES_BURNED)
        )
    )

    df["duration_minutes_clean"] = df["duration_minutes"].where(~df["activity_duration_outlier"])
    df["distance_km_clean"] = df["distance_km"].where(~df["activity_distance_outlier"])
    df["calories_burned_est_clean"] = df["calories_burned_est"].where(~df["activity_calories_outlier"])

    df["is_strength_training"] = df["is_strength_training"].fillna(False).astype(bool)
    df = df.sort_values(["date", "source", "activity_type"]).reset_index(drop=True)
    return df


def build_activity_daily_df(*, user, start_date: date, end_date: date) -> pd.DataFrame:
    entries_df = build_activity_entries_df(user=user, start_date=start_date, end_date=end_date)
    if entries_df.empty:
        return _empty_activity_daily_df()

    daily_df = (
        entries_df.groupby("date", as_index=False)
        .agg(
            activity_entries=("activity_type", "size"),
            activity_minutes_raw=("duration_minutes", "sum"),
            activity_minutes=("duration_minutes_clean", "sum"),
            activity_calories_raw=("calories_burned_est", "sum"),
            activity_calories=("calories_burned_est_clean", "sum"),
            activity_distance_km_raw=("distance_km", "sum"),
            activity_distance_km=("distance_km_clean", "sum"),
            activity_duration_outlier_count=("activity_duration_outlier", "sum"),
            activity_distance_outlier_count=("activity_distance_outlier", "sum"),
            activity_calories_outlier_count=("activity_calories_outlier", "sum"),
            strength_sessions=("session_count", "sum"),
            strength_exercise_count=("exercise_count", "sum"),
            strength_set_count=("set_count", "sum"),
            strength_volume_load=("volume_load", "sum"),
            strength_training_load_score=("training_load_score", "sum"),
        )
    )

    types_df = (
        entries_df.groupby("date")["activity_type"]
        .apply(lambda s: sorted({str(value) for value in s.dropna().tolist()}))
        .reset_index(name="activity_types")
    )

    daily_df = daily_df.merge(types_df, on="date", how="left")
    daily_df["activity_type_count"] = daily_df["activity_types"].apply(
        lambda values: len(values) if isinstance(values, list) else 0
    )
    daily_df["activity_logged"] = daily_df["activity_entries"] > 0
    daily_df["strength_training_day"] = daily_df["strength_sessions"] > 0

    numeric_columns = [
        "activity_entries",
        "activity_minutes_raw",
        "activity_minutes",
        "activity_calories_raw",
        "activity_calories",
        "activity_distance_km_raw",
        "activity_distance_km",
        "activity_duration_outlier_count",
        "activity_distance_outlier_count",
        "activity_calories_outlier_count",
        "activity_type_count",
        "strength_sessions",
        "strength_exercise_count",
        "strength_set_count",
        "strength_volume_load",
        "strength_training_load_score",
    ]
    for column in numeric_columns:
        daily_df[column] = pd.to_numeric(daily_df[column], errors="coerce").fillna(0)

    daily_df = daily_df.sort_values("date").reset_index(drop=True)
    return daily_df


def build_bio_daily_df(*, user, start_date: date, end_date: date) -> BioDataFrameBundle:
    metrics_df = build_daily_metrics_df(user=user, start_date=start_date, end_date=end_date)
    activities_df = build_activity_daily_df(user=user, start_date=start_date, end_date=end_date)

    spine = pd.DataFrame(
        {"date": pd.date_range(start=start_date, end=end_date, freq="D")}
    )

    daily_df = spine.merge(metrics_df, on="date", how="left")
    daily_df = daily_df.merge(activities_df, on="date", how="left")

    daily_df["metric_logged"] = daily_df["metric_logged"].fillna(False).astype(bool)
    daily_df["activity_logged"] = daily_df["activity_logged"].fillna(False).astype(bool)

    activity_fill_zero = [
        "activity_entries",
        "activity_minutes_raw",
        "activity_minutes",
        "activity_calories_raw",
        "activity_calories",
        "activity_distance_km_raw",
        "activity_distance_km",
        "activity_duration_outlier_count",
        "activity_distance_outlier_count",
        "activity_calories_outlier_count",
        "activity_type_count",
        "strength_sessions",
        "strength_exercise_count",
        "strength_set_count",
        "strength_volume_load",
        "strength_training_load_score",
    ]
    for column in activity_fill_zero:
        if column not in daily_df.columns:
            daily_df[column] = 0
        daily_df[column] = pd.to_numeric(daily_df[column], errors="coerce").fillna(0)

    if "activity_types" not in daily_df.columns:
        daily_df["activity_types"] = [[] for _ in range(len(daily_df))]
    else:
        daily_df["activity_types"] = daily_df["activity_types"].apply(
            lambda value: value if isinstance(value, list) else []
        )

    daily_df["has_metric"] = daily_df["metric_logged"]
    daily_df["has_activity"] = daily_df["activity_entries"] > 0
    daily_df["strength_training_day"] = daily_df["strength_sessions"] > 0

    daily_df["calorie_delta"] = daily_df["calories_actual"] - daily_df["calories_planned"]
    daily_df["calorie_target_hit"] = (
        daily_df["calories_actual"].notna()
        & daily_df["calories_planned"].notna()
        & ((daily_df["calories_actual"] - daily_df["calories_planned"]).abs() <= 150)
    )

    daily_df["weight_change_1d"] = daily_df["weight_kg"].diff()
    daily_df["sleep_low_flag"] = daily_df["sleep_quality"].notna() & (daily_df["sleep_quality"] <= 2)
    daily_df["alcohol_high_flag"] = daily_df["alcohol_units"].notna() & (daily_df["alcohol_units"] >= 5)

    daily_df = daily_df[DAILY_COLUMNS].sort_values("date").reset_index(drop=True)
    return BioDataFrameBundle(
        daily=daily_df,
        metrics=metrics_df,
        activities=activities_df,
    )


def build_bio_rolling_df(bundle: BioDataFrameBundle) -> pd.DataFrame:
    daily_df = bundle.daily.copy()
    if daily_df.empty:
        return _empty_rolling_df()

    rolling_df = pd.DataFrame({"date": daily_df["date"].copy()})

    metric_presence = daily_df["has_metric"].astype(int)
    activity_presence = daily_df["has_activity"].astype(int)

    rolling_df["weight_ma_3d"] = daily_df["weight_kg"].rolling(window=3, min_periods=2).mean()
    rolling_df["weight_ma_7d"] = daily_df["weight_kg"].rolling(window=7, min_periods=3).mean()

    rolling_df["sleep_ma_3d"] = daily_df["sleep_quality"].rolling(window=3, min_periods=2).mean()
    rolling_df["sleep_ma_7d"] = daily_df["sleep_quality"].rolling(window=7, min_periods=3).mean()

    rolling_df["alcohol_ma_7d"] = daily_df["alcohol_units"].rolling(window=7, min_periods=2).mean()
    rolling_df["calories_actual_ma_7d"] = daily_df["calories_actual"].rolling(window=7, min_periods=2).mean()
    rolling_df["calorie_delta_ma_7d"] = daily_df["calorie_delta"].rolling(window=7, min_periods=2).mean()

    rolling_df["activity_minutes_7d"] = daily_df["activity_minutes"].rolling(window=7, min_periods=1).sum()
    rolling_df["activity_entries_7d"] = daily_df["activity_entries"].rolling(window=7, min_periods=1).sum()
    rolling_df["activity_distance_km_7d"] = daily_df["activity_distance_km"].rolling(window=7, min_periods=1).sum()

    rolling_df["active_days_7d"] = activity_presence.rolling(window=7, min_periods=1).sum()
    rolling_df["metric_days_7d"] = metric_presence.rolling(window=7, min_periods=1).sum()

    rolling_df["strength_sessions_7d"] = daily_df["strength_sessions"].rolling(window=7, min_periods=1).sum()
    rolling_df["strength_set_count_7d"] = daily_df["strength_set_count"].rolling(window=7, min_periods=1).sum()
    rolling_df["strength_volume_load_7d"] = daily_df["strength_volume_load"].rolling(window=7, min_periods=1).sum()
    rolling_df["strength_training_load_ma_7d"] = daily_df["strength_training_load_score"].rolling(window=7, min_periods=1).mean()

    return rolling_df[ROLLING_COLUMNS].reset_index(drop=True)


def summarize_bio_dataframe_bundle(bundle: BioDataFrameBundle) -> dict[str, Any]:
    daily_df = bundle.daily

    if daily_df.empty:
        return {
            "rows": 0,
            "date_start": None,
            "date_end": None,
            "metric_days": 0,
            "activity_days": 0,
            "metric_coverage_pct": 0,
            "activity_coverage_pct": 0,
            "source_rows": {
                "metrics": 0,
                "activity_entries": 0,
            },
            "activity_totals": {
                "minutes": 0,
                "entries": 0,
                "distance_km": 0.0,
                "minutes_raw": 0,
                "distance_km_raw": 0.0,
                "filtered_minutes": 0,
                "filtered_distance_km": 0.0,
                "strength_sessions": int(daily_df["strength_sessions"].sum()),
                "strength_sets": int(daily_df["strength_set_count"].sum()),
                "strength_volume_load": round(float(daily_df["strength_volume_load"].sum()), 2),
            },
                "strength_summary": {
                "training_days": int(daily_df["strength_training_day"].sum()),
                "sessions": int(daily_df["strength_sessions"].sum()),
                "set_count": int(daily_df["strength_set_count"].sum()),
                "exercise_count": int(daily_df["strength_exercise_count"].sum()),
                "volume_load": round(float(daily_df["strength_volume_load"].sum()), 2),
                "avg_training_load_score": round(float(daily_df["strength_training_load_score"].mean()), 2)
                if len(daily_df) else 0,
            },
            "outlier_counts": {
                "duration": 0,
                "distance": 0,
                "calories": 0,
            },
            "null_counts": {},
            "available_columns": DAILY_COLUMNS,
        }

    rows = int(len(daily_df))
    metric_days = int(daily_df["has_metric"].sum())
    activity_days = int(daily_df["has_activity"].sum())

    clean_minutes = float(daily_df["activity_minutes"].sum())
    raw_minutes = float(daily_df["activity_minutes_raw"].sum())
    clean_distance = float(daily_df["activity_distance_km"].sum())
    raw_distance = float(daily_df["activity_distance_km_raw"].sum())

    null_counts = {
        "weight_kg": int(daily_df["weight_kg"].isna().sum()),
        "sleep_quality": int(daily_df["sleep_quality"].isna().sum()),
        "alcohol_units": int(daily_df["alcohol_units"].isna().sum()),
        "calories_planned": int(daily_df["calories_planned"].isna().sum()),
        "calories_actual": int(daily_df["calories_actual"].isna().sum()),
    }

    return {
        "rows": rows,
        "date_start": daily_df["date"].min().date().isoformat(),
        "date_end": daily_df["date"].max().date().isoformat(),
        "metric_days": metric_days,
        "activity_days": activity_days,
        "metric_coverage_pct": round((metric_days / rows) * 100) if rows else 0,
        "activity_coverage_pct": round((activity_days / rows) * 100) if rows else 0,
        "source_rows": {
            "metrics": int(len(bundle.metrics)),
            "activity_entries": int(len(bundle.activities)),
        },
        "activity_totals": {
            "minutes": int(clean_minutes),
            "entries": int(daily_df["activity_entries"].sum()),
            "distance_km": round(clean_distance, 2),
            "minutes_raw": int(raw_minutes),
            "distance_km_raw": round(raw_distance, 2),
            "filtered_minutes": int(raw_minutes - clean_minutes),
            "filtered_distance_km": round(raw_distance - clean_distance, 2),
        },
        "outlier_counts": {
            "duration": int(daily_df["activity_duration_outlier_count"].sum()),
            "distance": int(daily_df["activity_distance_outlier_count"].sum()),
            "calories": int(daily_df["activity_calories_outlier_count"].sum()),
        },
        "null_counts": null_counts,
        "available_columns": DAILY_COLUMNS,
        "strength_summary": {
            "training_days": int(daily_df["strength_training_day"].sum()),
            "sessions": int(daily_df["strength_sessions"].sum()),
            "set_count": int(daily_df["strength_set_count"].sum()),
            "exercise_count": int(daily_df["strength_exercise_count"].sum()),
            "volume_load": round(float(daily_df["strength_volume_load"].sum()), 2),
            "avg_training_load_score": round(float(daily_df["strength_training_load_score"].mean()), 2)
            if len(daily_df) else 0,
        },
    }


def summarize_bio_rolling_bundle(bundle: BioDataFrameBundle) -> dict[str, Any]:
    rolling_df = build_bio_rolling_df(bundle)
    daily_df = bundle.daily

    if rolling_df.empty:
        return {
            "enabled": True,
            "rows": 0,
            "date_start": None,
            "date_end": None,
            "outlier_counts": {
                "duration": 0,
                "distance": 0,
                "calories": 0,
            },
            "latest": {},
            "non_null_counts": {},
            "available_columns": ROLLING_COLUMNS,
        }

    latest = rolling_df.iloc[-1]

    return {
        "enabled": True,
        "rows": int(len(rolling_df)),
        "date_start": rolling_df["date"].min().date().isoformat(),
        "date_end": rolling_df["date"].max().date().isoformat(),
        "outlier_counts": {
            "duration": int(daily_df["activity_duration_outlier_count"].sum()),
            "distance": int(daily_df["activity_distance_outlier_count"].sum()),
            "calories": int(daily_df["activity_calories_outlier_count"].sum()),
        },
        "latest": {
            "weight_ma_3d": _round_float(latest["weight_ma_3d"], 2),
            "weight_ma_7d": _round_float(latest["weight_ma_7d"], 2),
            "sleep_ma_3d": _round_float(latest["sleep_ma_3d"], 2),
            "sleep_ma_7d": _round_float(latest["sleep_ma_7d"], 2),
            "alcohol_ma_7d": _round_float(latest["alcohol_ma_7d"], 2),
            "calories_actual_ma_7d": _round_float(latest["calories_actual_ma_7d"], 0),
            "calorie_delta_ma_7d": _round_float(latest["calorie_delta_ma_7d"], 0),
            "activity_minutes_7d": _round_float(latest["activity_minutes_7d"], 0),
            "activity_entries_7d": _round_float(latest["activity_entries_7d"], 0),
            "activity_distance_km_7d": _round_float(latest["activity_distance_km_7d"], 2),
            "active_days_7d": _round_float(latest["active_days_7d"], 0),
            "metric_days_7d": _round_float(latest["metric_days_7d"], 0),
            "strength_sessions_7d": _round_float(latest["strength_sessions_7d"], 0),
            "strength_set_count_7d": _round_float(latest["strength_set_count_7d"], 0),
            "strength_volume_load_7d": _round_float(latest["strength_volume_load_7d"], 2),
            "strength_training_load_ma_7d": _round_float(latest["strength_training_load_ma_7d"], 2),
        },
        "non_null_counts": {
            column: int(rolling_df[column].notna().sum())
            for column in ROLLING_COLUMNS
            if column != "date"
        },
        "available_columns": ROLLING_COLUMNS,
    }


def build_bio_dataframe_foundation(*, user, start_date: date, end_date: date) -> dict[str, Any]:
    bundle = build_bio_daily_df(user=user, start_date=start_date, end_date=end_date)
    return summarize_bio_dataframe_bundle(bundle)


def build_bio_rolling_foundation(*, user, start_date: date, end_date: date) -> dict[str, Any]:
    bundle = build_bio_daily_df(user=user, start_date=start_date, end_date=end_date)
    return summarize_bio_rolling_bundle(bundle)

CORRELATION_MIN_PAIRS = 4


def _correlation_strength_label(value: float) -> str:
    absolute = abs(value)
    if absolute >= 0.6:
        return "STRONG"
    if absolute >= 0.35:
        return "MODERATE"
    return "WEAK"


def _correlation_direction_label(value: float) -> str:
    if value > 0:
        return "POSITIVE"
    if value < 0:
        return "NEGATIVE"
    return "FLAT"


def _build_correlation_pair(
    *,
    df: pd.DataFrame,
    left_key: str,
    right_key: str,
    name: str,
    label: str,
    min_pairs: int = CORRELATION_MIN_PAIRS,
) -> dict[str, Any]:
    pair_df = df[[left_key, right_key]].dropna()

    if len(pair_df) < min_pairs:
        return {
            "name": name,
            "label": label,
            "status": "INSUFFICIENT",
            "pairs": int(len(pair_df)),
            "coefficient": None,
            "strength": None,
            "direction": None,
            "left_key": left_key,
            "right_key": right_key,
        }

    if pair_df[left_key].nunique() < 2 or pair_df[right_key].nunique() < 2:
        return {
            "name": name,
            "label": label,
            "status": "INSUFFICIENT",
            "pairs": int(len(pair_df)),
            "coefficient": None,
            "strength": None,
            "direction": None,
            "left_key": left_key,
            "right_key": right_key,
        }

    coefficient = pair_df[left_key].corr(pair_df[right_key])

    if pd.isna(coefficient):
        return {
            "name": name,
            "label": label,
            "status": "INSUFFICIENT",
            "pairs": int(len(pair_df)),
            "coefficient": None,
            "strength": None,
            "direction": None,
            "left_key": left_key,
            "right_key": right_key,
        }

    coefficient = float(coefficient)

    return {
        "name": name,
        "label": label,
        "status": "OK",
        "pairs": int(len(pair_df)),
        "coefficient": round(coefficient, 3),
        "strength": _correlation_strength_label(coefficient),
        "direction": _correlation_direction_label(coefficient),
        "left_key": left_key,
        "right_key": right_key,
    }


def _pick_dominant_correlation(pairs: list[dict[str, Any]]) -> dict[str, Any] | None:
    valid_pairs = [pair for pair in pairs if pair["status"] == "OK" and pair["coefficient"] is not None]
    if not valid_pairs:
        return None

    strength_rank = {"STRONG": 3, "MODERATE": 2, "WEAK": 1}

    valid_pairs.sort(
        key=lambda pair: (
            strength_rank.get(pair["strength"], 0),
            abs(pair["coefficient"]),
            pair["pairs"],
        ),
        reverse=True,
    )
    return valid_pairs[0]


def build_bio_correlation_foundation(*, user, start_date: date, end_date: date) -> dict[str, Any]:
    bundle = build_bio_daily_df(user=user, start_date=start_date, end_date=end_date)
    daily_df = bundle.daily.copy()

    if daily_df.empty:
        return {
            "enabled": True,
            "rows": 0,
            "pairs": [],
            "dominant": None,
            "min_pairs_required": CORRELATION_MIN_PAIRS,
            "note": "Correlation signals are associative only, not causal.",
        }

    daily_df["next_day_sleep_quality"] = daily_df["sleep_quality"].shift(-1)
    daily_df["next_day_weight_change"] = daily_df["weight_kg"].shift(-1) - daily_df["weight_kg"]
    daily_df["next_day_strength_training_load_score"] = daily_df["strength_training_load_score"].shift(-1)

    pairs = [
        _build_correlation_pair(
            df=daily_df,
            left_key="alcohol_units",
            right_key="next_day_sleep_quality",
            name="alcohol_vs_next_sleep",
            label="Alcohol vs next-day sleep",
        ),
        _build_correlation_pair(
            df=daily_df,
            left_key="activity_minutes",
            right_key="next_day_sleep_quality",
            name="activity_vs_next_sleep",
            label="Activity minutes vs next-day sleep",
        ),
        _build_correlation_pair(
            df=daily_df,
            left_key="strength_training_load_score",
            right_key="next_day_sleep_quality",
            name="strength_load_vs_next_sleep",
            label="Strength load vs next-day sleep",
        ),
        _build_correlation_pair(
            df=daily_df,
            left_key="calorie_delta",
            right_key="next_day_weight_change",
            name="calorie_delta_vs_next_weight_change",
            label="Calorie delta vs next-day weight change",
        ),
        _build_correlation_pair(
            df=daily_df,
            left_key="sleep_quality",
            right_key="next_day_strength_training_load_score",
            name="sleep_vs_next_strength_load",
            label="Sleep vs next-day strength load",
        ),
        _build_correlation_pair(
            df=daily_df,
            left_key="alcohol_units",
            right_key="next_day_strength_training_load_score",
            name="alcohol_vs_next_strength_load",
            label="Alcohol vs next-day strength load",
        ),
    ]

    dominant = _pick_dominant_correlation(pairs)

    return {
        "enabled": True,
        "rows": int(len(daily_df)),
        "pairs": pairs,
        "dominant": dominant,
        "min_pairs_required": CORRELATION_MIN_PAIRS,
        "note": "Correlation signals are associative only, not causal.",
    }