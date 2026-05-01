from ninja import Field, Schema


class DailyMetricUpsertInputSchema(Schema):
    weight_kg: str | None = Field(
        None,
        description="Optional body weight in kilograms as decimal string.",
    )
    diet_mode: str | None = Field(
        None,
        description="Optional diet mode enum value.",
    )
    sleep_quality: int | None = Field(
        None,
        description="Optional sleep quality on a 1-5 scale.",
    )
    alcohol_units: int | None = Field(
        None,
        description="Alcohol intake on a 0-10 scale. Defaults to 0 when omitted.",
    )
    calories_planned: int | None = Field(
        None,
        description="Optional planned calories.",
    )
    calories_actual: int | None = Field(
        None,
        description="Optional actual calories.",
    )
    notes: str | None = Field(
        None,
        description="Optional notes.",
    )


class DailyMetricDataSchema(Schema):
    id: int
    date: str
    weight_kg: str | None
    diet_mode: str | None
    sleep_quality: int | None
    alcohol_units: int
    calories_planned: int | None
    calories_actual: int | None
    notes: str
    version: int
    created_at: str
    updated_at: str


class DailyMetricUpsertResponseSchema(Schema):
    ok: bool
    data: DailyMetricDataSchema
    created: bool