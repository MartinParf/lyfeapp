from ninja import Schema


class AuthLoginInputSchema(Schema):
    identity: str
    password: str


class AuthRefreshInputSchema(Schema):
    refresh: str


class AuthLogoutInputSchema(Schema):
    refresh: str


class AuthUserSchema(Schema):
    id: int
    username: str
    email: str
    is_staff: bool
    is_superuser: bool
    email_verified: bool


class AuthTokenDataSchema(Schema):
    access: str
    refresh: str
    token_type: str
    access_expires_in_seconds: int
    refresh_expires_in_seconds: int


class AuthLoginDataSchema(Schema):
    user: AuthUserSchema
    tokens: AuthTokenDataSchema


class AuthLoginResponseSchema(Schema):
    ok: bool
    data: AuthLoginDataSchema


class AuthRefreshDataSchema(Schema):
    access: str
    refresh: str
    token_type: str
    access_expires_in_seconds: int
    refresh_expires_in_seconds: int


class AuthRefreshResponseSchema(Schema):
    ok: bool
    data: AuthRefreshDataSchema


class AuthLogoutResponseSchema(Schema):
    ok: bool
    data: dict


class AuthMeResponseSchema(Schema):
    ok: bool
    data: AuthUserSchema