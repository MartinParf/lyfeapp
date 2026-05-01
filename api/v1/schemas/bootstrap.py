from ninja import Schema

from api.v1.schemas.profile import ProfileMeSchema


class BootstrapServerSchema(Schema):
    api_version: str
    server_time: str


class BootstrapConfigSchema(Schema):
    bootstrap_version: str
    profile_api_enabled: bool
    fitness_api_enabled: bool


class BootstrapFeatureFlagsSchema(Schema):
    profile_edit_enabled: bool
    fitness_sessions_enabled: bool
    analytics_enabled: bool


class BootstrapExerciseSchema(Schema):
    id: int
    name: str
    slug: str
    primary_pattern: str | None
    is_custom: bool
    is_active: bool


class BootstrapPoolSummarySchema(Schema):
    id: int
    name: str
    focus: str
    description: str
    exercise_count: int


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