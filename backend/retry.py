"""Retry with backoff for Gemini API calls (generation and embeddings alike)."""

from __future__ import annotations

import logging
import random
import time
from typing import Callable, TypeVar

import httpx
from google.genai import errors as genai_errors

logger = logging.getLogger(__name__)

T = TypeVar("T")

# 429 is the rate limit; the 5xx codes are the transient server failures Google
# documents as safe to retry. Any other 4xx is a request the API will reject
# again, so retrying it only burns quota and delays the failure.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 6
BASE_DELAY_SECONDS = 1.0
MAX_DELAY_SECONDS = 30.0


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, genai_errors.APIError):
        return exc.code in RETRYABLE_STATUS
    # Connection resets, DNS hiccups and timeouts never reached the model.
    return isinstance(exc, (httpx.TransportError, TimeoutError, ConnectionError))


def backoff_delay(attempt: int) -> float:
    """Full-jitter exponential backoff: uniform in [0, min(cap, base * 2^n)].

    Jitter matters because a rate limit hits every worker at once; without it
    they all retry in lockstep and collide again.
    """
    return random.uniform(0, min(MAX_DELAY_SECONDS, BASE_DELAY_SECONDS * (2 ** attempt)))


def with_retry(call: Callable[[], T], sleep: Callable[[float], None] = time.sleep,
               what: str = "Gemini request") -> T:
    for attempt in range(MAX_ATTEMPTS):
        try:
            return call()
        except Exception as exc:
            if not is_retryable(exc) or attempt == MAX_ATTEMPTS - 1:
                raise
            delay = backoff_delay(attempt)
            logger.warning(
                "%s failed (%s); retry %d/%d in %.1fs",
                what, exc, attempt + 1, MAX_ATTEMPTS - 1, delay,
            )
            sleep(delay)
    raise AssertionError("unreachable")
