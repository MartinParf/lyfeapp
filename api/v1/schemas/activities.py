from ninja import Field, Schema
from uuid import UUID


class ActivityCreateInputSchema(Schema):
    client_uuid: UUID = Field(..., description="Client-generated idempotency UUID.")
    date: str = Field(..., description="Activity date in ISO format YYYY-MM-DD.")
    activity_type: str = Field(..., description="Activity type enum value.")
    duration_minutes: int = Field(..., description="Duration in whole minutes.")
    calories_burned_est: int | None = Field(
        None,
        description="Optional estimated calories burned.",
    )
    distance_km: str | None = Field(
        None,
        description="Optional distance in kilometers as decimal string.",
    )
    notes: str | None = Field(
        None,
        description="Optional free-text notes.",
    )


class ActivityDataSchema(Schema):
    id: int
    client_uuid: str
    date: str
    activity_type: str
    duration_minutes: int
    calories_burned_est: int | None
    distance_km: str | None
    notes: str
    version: int
    deleted_at: str | None
    created_at: str
    updated_at: str


class ActivityCreateResponseSchema(Schema):
    ok: bool
    data: ActivityDataSchema
    created: bool