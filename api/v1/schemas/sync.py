from ninja import Field, Schema

from api.v1.schemas.daily_metrics import DailyMetricDataSchema
from api.v1.schemas.profile import ProfileMeSchema
from api.v1.schemas.activities import ActivityDataSchema


class SyncDeletedRefSchema(Schema):
    id: int
    client_uuid: str | None = None
    deleted_at: str


class SyncWorkoutSetSchema(Schema):
    id: int
    client_uuid: str
    set_order: int
    set_type: str | None
    weight_kg: str | None
    reps: int | None
    rpe: str | None
    notes: str
    version: int
    created_at: str
    updated_at: str


class SyncWorkoutSessionExerciseSchema(Schema):
    id: int
    client_uuid: str
    sequence: int
    exercise_id: int
    exercise_name: str
    source_pool_item_id: int | None
    notes: str
    version: int
    created_at: str
    updated_at: str
    sets: list[SyncWorkoutSetSchema] = Field(default_factory=list)


class SyncWorkoutSessionTreeSchema(Schema):
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
    exercises: list[SyncWorkoutSessionExerciseSchema] = Field(default_factory=list)


class SyncProfileBucketSchema(Schema):
    created: list[ProfileMeSchema] = Field(default_factory=list)
    updated: list[ProfileMeSchema] = Field(default_factory=list)
    deleted: list[SyncDeletedRefSchema] = Field(default_factory=list)
    deletion_mode: str


class SyncDailyMetricBucketSchema(Schema):
    created: list[DailyMetricDataSchema] = Field(default_factory=list)
    updated: list[DailyMetricDataSchema] = Field(default_factory=list)
    deleted: list[SyncDeletedRefSchema] = Field(default_factory=list)
    deletion_mode: str


class SyncActivityBucketSchema(Schema):
    created: list[ActivityDataSchema] = Field(default_factory=list)
    updated: list[ActivityDataSchema] = Field(default_factory=list)
    deleted: list[SyncDeletedRefSchema] = Field(default_factory=list)
    deletion_mode: str


class SyncWorkoutSessionBucketSchema(Schema):
    created: list[SyncWorkoutSessionTreeSchema] = Field(default_factory=list)
    updated: list[SyncWorkoutSessionTreeSchema] = Field(default_factory=list)
    deleted: list[SyncDeletedRefSchema] = Field(default_factory=list)
    deletion_mode: str
    payload_mode: str


class SyncChangesDataSchema(Schema):
    sync_contract_version: str
    since: str
    synced_at: str
    profile: SyncProfileBucketSchema
    daily_metrics: SyncDailyMetricBucketSchema
    activities: SyncActivityBucketSchema
    workout_sessions: SyncWorkoutSessionBucketSchema


class SyncChangesResponseSchema(Schema):
    ok: bool
    data: SyncChangesDataSchema