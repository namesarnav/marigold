"""Fixed-window rate limiting, Redis-backed with an in-process fallback.

The brief called for Redis, and `redis_url` is the production path. It is not
required to run the app, though: with no URL configured the limiter falls back
to a dict in this process so local dev and the test suite work unchanged. That
fallback is per-worker — two uvicorn workers would each get their own budget —
so it is a development convenience, not a production mode. `backend_name` on
the active limiter says which one is live.

The window is fixed rather than sliding. For login throttling that is the right
trade: it is one round trip, it cannot drift, and the worst case (an attacker
straddling a window boundary to get 2x the budget briefly) is well inside the
margin these limits are chosen with.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from .config import get_settings

settings = get_settings()


@dataclass(frozen=True)
class RateLimitStatus:
    """Outcome of one `hit()`."""

    allowed: bool
    remaining: int
    retry_after_seconds: int


class _MemoryBackend:
    """Per-process fixed-window counters. Not shared between workers."""

    name = "memory"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._windows: Dict[str, Tuple[int, float]] = {}

    def incr(self, key: str, window_seconds: int) -> Tuple[int, float]:
        now = time.monotonic()
        with self._lock:
            count, expires_at = self._windows.get(key, (0, 0.0))
            if expires_at <= now:
                count, expires_at = 0, now + window_seconds
            count += 1
            self._windows[key] = (count, expires_at)
            return count, expires_at - now

    def reset(self, key: str) -> None:
        with self._lock:
            self._windows.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._windows.clear()


class _RedisBackend:
    """Fixed window via INCR + EXPIRE, applied atomically in one pipeline."""

    name = "redis"

    def __init__(self, client) -> None:
        self._client = client

    def incr(self, key: str, window_seconds: int) -> Tuple[int, float]:
        pipe = self._client.pipeline()
        pipe.incr(key)
        # Only set the TTL when the key is new, so a burst cannot keep pushing
        # the window's end further out and extend a lockout indefinitely.
        pipe.expire(key, window_seconds, nx=True)
        pipe.ttl(key)
        count, _, ttl = pipe.execute()
        if ttl is None or ttl < 0:
            self._client.expire(key, window_seconds)
            ttl = window_seconds
        return int(count), float(ttl)

    def reset(self, key: str) -> None:
        self._client.delete(key)

    def clear(self) -> None:  # pragma: no cover - never used against real Redis
        raise NotImplementedError("Refusing to flush a shared Redis instance.")


class RateLimiter:
    def __init__(self, backend) -> None:
        self._backend = backend

    @property
    def backend_name(self) -> str:
        return self._backend.name

    def hit(self, key: str, *, limit: int, window_seconds: int) -> RateLimitStatus:
        """Count one attempt against `key` and report whether it is allowed."""
        count, ttl = self._backend.incr(key, window_seconds)
        allowed = count <= limit
        return RateLimitStatus(
            allowed=allowed,
            remaining=max(0, limit - count),
            retry_after_seconds=max(1, int(round(ttl))),
        )

    def peek_blocked(self, key: str, *, limit: int) -> bool:
        """True if `key` is already over budget, without spending an attempt."""
        raw = getattr(self._backend, "_client", None)
        if raw is not None:
            value = raw.get(key)
            return value is not None and int(value) >= limit
        count, _ = self._backend._windows.get(key, (0, 0.0))  # type: ignore[attr-defined]
        return count >= limit

    def reset(self, key: str) -> None:
        self._backend.reset(key)

    def clear(self) -> None:
        self._backend.clear()


def _build_limiter() -> RateLimiter:
    url = settings.redis_url.strip()
    if not url:
        return RateLimiter(_MemoryBackend())
    try:
        import redis  # imported lazily: optional dependency

        client = redis.Redis.from_url(url, decode_responses=True)
        client.ping()
        return RateLimiter(_RedisBackend(client))
    except Exception as exc:  # noqa: BLE001 - any failure means "no Redis"
        # Falling back is deliberate: an unreachable Redis must not take the
        # whole API down. It does silently weaken the limit across workers, so
        # it is logged loudly rather than swallowed.
        import logging

        logging.getLogger(__name__).error(
            "Redis rate-limit backend unavailable (%s); falling back to "
            "in-process counters. Limits are now per-worker.",
            exc,
        )
        return RateLimiter(_MemoryBackend())


_limiter: Optional[RateLimiter] = None


def get_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = _build_limiter()
    return _limiter


# --- Key builders ----------------------------------------------------------
#
# Emails are lowercased so that casing variants share one budget; an attacker
# must not get a fresh allowance by posting "User@x.com" instead of "user@x.com".


def login_account_key(email: str) -> str:
    return f"rl:login:account:{email.strip().casefold()}"


def login_ip_key(ip: str) -> str:
    return f"rl:login:ip:{ip}"


def resend_verification_key(email: str) -> str:
    return f"rl:resend-verification:{email.strip().casefold()}"


def password_reset_key(email: str) -> str:
    return f"rl:password-reset:{email.strip().casefold()}"


def client_ip(request) -> str:
    """Best-effort client IP.

    Trusts X-Forwarded-For's first hop, which is correct behind the k3s Traefik
    ingress this deploys behind. If the app is ever exposed directly, that
    header becomes spoofable and the per-IP limit degrades to per-attacker —
    the per-account limit is the one that still holds in that case.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
