from ninja import Schema, Field
from api.v1.schemas.profile import ProfileMeSchema


class BootstrapServerSchema(Schema):
    api_version: str = Field(..., description="API version identifier.")
    server_time: str = Field(..., description="Current server time in ISO format.")


class BootstrapConfigSchema(Schema):
    bootstrap_version: str = Field(..., description="Bootstrap payload version marker.")
    profile_api_enabled: bool = Field(..., description="Whether profile API is enabled.")
    fitness_api_enabled: bool = Field(..., description="Whether fitness API is enabled.")


class BootstrapFeatureFlagsSchema(Schema):
    profile_edit_enabled: bool = Field(..., description="Whether profile editing is enabled.")
    fitness_sessions_enabled: bool = Field(..., description="Whether fitness sessions flow is enabled.")
    analytics_enabled: bool = Field(..., description="Whether analytics API is enabled.")


class BootstrapExerciseSchema(Schema):
    id: int = Field(..., description="Exercise ID.")
    name: str = Field(..., description="Exercise name.")
    slug: str = Field(..., description="Stable slug for exercise.")
    primary_pattern: str | None = Field(None, description="Primary training pattern classification.")
    is_custom: bool = Field(..., description="Whether the exercise is user-defined.")
    is_active: bool = Field(..., description="Whether the exercise is active.")


class BootstrapPoolSummarySchema(Schema):
    id: int = Field(..., description="Exercise pool ID.")
    name: str = Field(..., description="Exercise pool name.")
    focus: str = Field(..., description="Pool focus classification.")
    description: str = Field(..., description="Pool description.")
    exercise_count: int = Field(..., description="Number of exercises in the pool.")


class BootstrapFitnessSchema(Schema):
    exercises: list[BootstrapExerciseSchema]
    pool_summaries: list[BootstrapPoolSummarySchema]


class BootstrapDataSchema(Schema):
    profile: ProfileMeSchema
    server: BootstrapServerSchema
    config: BootstrapConfigSchema
    feature_flags: BootstrapFeatureFlagsSchema
    fitness: BootstrapFitnessSchema


class BootstrapResponseSchema(Schema):
    ok: bool
    data: BootstrapDataSchema