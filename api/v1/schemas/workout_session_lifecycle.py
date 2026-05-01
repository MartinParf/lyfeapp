from ninja import Field, Schema


class WorkoutSessionLifecycleDataSchema(Schema):
    id: int
    status: str
    started_at: str | None
    ended_at: str | None
    version: int
    updated_at: str
    changed: bool = Field(..., description="Whether this request changed the session state.")


class WorkoutSessionLifecycleResponseSchema(Schema):
    ok: bool
    data: WorkoutSessionLifecycleDataSchema