from ninja import Schema


class ApiErrorDetailSchema(Schema):
    code: str
    message: str
    details: dict | list | None = None


class ApiErrorResponseSchema(Schema):
    ok: bool
    error: ApiErrorDetailSchema