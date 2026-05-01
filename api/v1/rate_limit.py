import hashlib
import math
import time

from django.conf import settings
from django.core.cache import cache

from api.exceptions import ApiError


def client_ip(request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def _cache_key(scope: str, identifier: str) -> str:
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
    return f"api_rate_limit:{scope}:{digest}"


def _load_bucket(key: str, now: float, window_seconds: int) -> dict:
    bucket = cache.get(key)
    if not bucket:
        return {
            "count": 0,
            "until": now + window_seconds,
        }

    until = float(bucket.get("until", 0))
    if until <= now:
        return {
            "count": 0,
            "until": now + window_seconds,
        }

    return bucket


def rate_limit_or_raise(*, scope: str, identifier: str, limit: int, window_seconds: int):
    now = time.time()
    key = _cache_key(scope, identifier)
    bucket = _load_bucket(key, now, window_seconds)

    if int(bucket["count"]) >= limit:
        retry_after = max(1, math.ceil(bucket["until"] - now))
        raise ApiError(
            code="rate_limited",
            message="Too many requests. Please try again later.",
            status=429,
            details={
                "scope": scope,
                "retry_after_seconds": retry_after,
                "limit": limit,
                "window_seconds": window_seconds,
            },
        )

    bucket["count"] = int(bucket["count"]) + 1
    timeout = max(1, math.ceil(bucket["until"] - now))
    cache.set(key, bucket, timeout=timeout)


def auth_window_seconds() -> int:
    return settings.API_AUTH_WINDOW_SECONDS