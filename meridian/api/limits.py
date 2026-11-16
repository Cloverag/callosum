"""In-process rate limits for public surfaces.

Not a substitute for an edge limiter. One process, one dict, enough to stop a
browser from hammering `POST /auth/demo/select` on the 2-core demo host.

Authenticated domain routes are not limited here by default: the gated suite
issues hundreds of writes from one IP, and a default cap would make CI the
first victim. Set `MERIDIAN_RATE_LIMIT_PER_MINUTE` to apply a process-wide
POST cap in deployment.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

#: Public impersonation is the one unauthenticated write that must not be free.
_DEMO_SELECT = "/auth/demo/select"
_DEMO_PER_MINUTE = 30

_hits: dict[str, deque[float]] = defaultdict(deque)


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"true", "1", "yes"}


def limiter_disabled() -> bool:
    return _truthy("MERIDIAN_RATE_LIMIT_OFF")


def allow(key: str, *, limit: int, window_s: float, now: float | None = None) -> bool:
    """True when `key` is still inside `limit` events in the trailing window."""
    clock = time.monotonic() if now is None else now
    bucket = _hits[key]
    cutoff = clock - window_s
    while bucket and bucket[0] <= cutoff:
        bucket.popleft()
    if len(bucket) >= limit:
        return False
    bucket.append(clock)
    return True


def reset() -> None:
    """Test helper — the buckets are process-global."""
    _hits.clear()


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if limiter_disabled() or request.method not in {"POST", "PATCH", "DELETE", "PUT"}:
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        path = request.url.path

        if path == _DEMO_SELECT or path.rstrip("/") == _DEMO_SELECT:
            if not allow(f"demo:{ip}", limit=_DEMO_PER_MINUTE, window_s=60.0):
                return _too_many()

        raw = os.environ.get("MERIDIAN_RATE_LIMIT_PER_MINUTE", "").strip()
        if raw:
            try:
                cap = int(raw)
            except ValueError:
                cap = 0
            if cap > 0 and not allow(f"post:{ip}", limit=cap, window_s=60.0):
                return _too_many()

        return await call_next(request)


def _too_many() -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"error": {"code": "rate_limited", "detail": "Too many requests."}},
        headers={"Retry-After": "60"},
    )
