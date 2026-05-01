from ninja import Field, Schema
from uuid import UUID


class WorkoutSessionCreateInputSchema(Schema):
    client_uuid: UUID = Field(..., description="Client-generated idempotency UUID.")
    focus: str = Field(..., description="Workout focus enum value.")
    source_pool_id: int | None = Field(
        None,
        description="Optional source exercise pool ID owned by the user.",
    )
    scheduled_date: str | None = Field(
        None,
        description="Optional scheduled date in ISO format YYYY-MM-DD.",
    )
    notes: str | None = Field(
        None,
        description="Optional session notes.",
    )


class WorkoutSessionDataSchema(Schema):
    id: int
    client_uuid: str
    focus: str
    source_pool_id: int | None
    status: str
    scheduled_date: str | None
    started_at: str | None
    ended_at: str | None
    notes: str
    version: int
    deleted_at: str | None
    created_at: str
    updated_at: str
    imported_exercise_count: int


class WorkoutSessionCreateResponseSchema(Schema):
    ok: bool
    data: WorkoutSessionDataSchema
    created: bool