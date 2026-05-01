from ninja import Schema, Field


class ProfileMeSchema(Schema):
    user_id: int = Field(..., description="Internal user ID.")
    email: str = Field(..., description="Primary account email.")
    display_name: str = Field(..., description="User-facing display name.")
    resolved_display_name: str = Field(..., description="Resolved display name fallback used by the app.")
    bio: str = Field(..., description="Short user bio.")
    avatar_url: str | None = Field(None, description="Absolute avatar URL.")
    date_of_birth: str | None = Field(None, description="Date of birth in ISO format YYYY-MM-DD.")
    height_cm: int | None = Field(None, description="Height in centimeters.")
    target_weight_kg: str | None = Field(None, description="Target weight in kilograms as decimal string.")
    goal_mode: str = Field(..., description="Primary goal mode.")
    goal_mode_label: str = Field(..., description="Human-readable goal mode label.")
    email_verified_at: str | None = Field(None, description="Email verification timestamp in ISO format.")
    onboarding_completed_at: str | None = Field(None, description="Onboarding completion timestamp in ISO format.")
    created_at: str = Field(..., description="Profile creation timestamp in ISO format.")
    updated_at: str = Field(..., description="Profile update timestamp in ISO format.")
    profile_version: str = Field(..., description="Profile cache/version marker derived from updated_at.")


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