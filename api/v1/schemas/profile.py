from ninja import Schema


class ProfileMeSchema(Schema):
    user_id: int
    email: str
    display_name: str
    resolved_display_name: str
    bio: str
    avatar_url: str | None
    date_of_birth: str | None
    height_cm: int | None
    target_weight_kg: str | None
    goal_mode: str
    goal_mode_label: str
    email_verified_at: str | None
    onboarding_completed_at: str | None
    created_at: str
    updated_at: str
    profile_version: str


class ProfileMeResponseSchema(Schema):
    ok: bool
    data: ProfileMeSchema


class ProfileMePatchInputSchema(Schema):
    display_name: str | None = None
    bio: str | None = None
    date_of_birth: str | None = None
    height_cm: int | None = None
    target_weight_kg: str | None = None
    goal_mode: str | None = None