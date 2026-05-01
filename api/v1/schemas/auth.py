from ninja import Schema, Field


class AuthLoginInputSchema(Schema):
    identity: str = Field(..., description="Username or email.")
    password: str = Field(..., description="Plain-text password for login.")


class AuthRefreshInputSchema(Schema):
    refresh: str = Field(..., description="Refresh token previously issued by login or refresh.")


class AuthLogoutInputSchema(Schema):
    refresh: str = Field(..., description="Refresh token to blacklist.")


class AuthUserSchema(Schema):
    id: int = Field(..., description="Internal user ID.")
    username: str = Field(..., description="Username.")
    email: str = Field(..., description="Primary account email.")
    is_staff: bool = Field(..., description="Whether the user is staff.")
    is_superuser: bool = Field(..., description="Whether the user is superuser.")
    email_verified: bool = Field(..., description="Whether the user's email has been verified.")


class AuthTokenDataSchema(Schema):
    access: str = Field(..., description="Short-lived JWT access token.")
    refresh: str = Field(..., description="Long-lived JWT refresh token.")
    token_type: str = Field(..., description="Authorization header token type.")
    access_expires_in_seconds: int = Field(..., description="Access token lifetime in seconds.")
    refresh_expires_in_seconds: int = Field(..., description="Refresh token lifetime in seconds.")


class AuthLoginDataSchema(Schema):
    user: AuthUserSchema
    tokens: AuthTokenDataSchema


class AuthLoginResponseSchema(Schema):
    ok: bool
    data: AuthLoginDataSchema


class AuthRefreshDataSchema(Schema):
    access: str = Field(..., description="New access token.")
    refresh: str = Field(..., description="New refresh token if rotation is enabled.")
    token_type: str = Field(..., description="Authorization header token type.")
    access_expires_in_seconds: int = Field(..., description="Access token lifetime in seconds.")
    refresh_expires_in_seconds: int = Field(..., description="Refresh token lifetime in seconds.")


class AuthRefreshResponseSchema(Schema):
    ok: bool
    data: AuthRefreshDataSchema


class AuthLogoutDataSchema(Schema):
    logged_out: bool = Field(..., description="Whether logout completed successfully.")


class AuthLogoutResponseSchema(Schema):
    ok: bool
    data: AuthLogoutDataSchema


class AuthMeResponseSchema(Schema):
    ok: bool
    data: AuthUserSchema