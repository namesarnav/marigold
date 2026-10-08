"""Per-run accounting of Gemini calls: tokens and latency.

The eval script needs tokens per upload and generation latency for both modes,
and the numbers must be the API's own, not estimates. Threading a tracker
through every function between the route and the SDK call would touch every
signature, so the active tracker lives in a context variable instead:
`track_usage()` opens one, and the Gemini wrappers record into whichever is
active. Outside a `track_usage()` block recording is a no-op, which is the
normal case in the app.

Context variables are copied into threads by anyio.to_thread, so calls made
from worker threads land in the right tracker.
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator, List, Optional


@dataclass
class CallRecord:
    kind: str  # "generate" | "embed"
    model: str
    latency_seconds: float
    # From the API's usage metadata. None when the API did not report it —
    # never filled in with a guess.
    prompt_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    thinking_tokens: Optional[int] = None
    # Embedding calls on the Gemini API return no usage metadata, so their
    # input size can only be estimated (chunking.estimate_tokens). Kept apart
    # from prompt_tokens so a report can never mistake one for the other.
    estimated_input_tokens: Optional[int] = None
    label: str = ""


@dataclass
class UsageTracker:
    calls: List[CallRecord] = field(default_factory=list)

    def record(self, rec: CallRecord) -> None:
        self.calls.append(rec)


_active: contextvars.ContextVar[Optional[UsageTracker]] = contextvars.ContextVar(
    "marigold_usage_tracker", default=None
)


def record(rec: CallRecord) -> None:
    tracker = _active.get()
    if tracker is not None:
        tracker.record(rec)


@contextmanager
def track_usage() -> Iterator[UsageTracker]:
    tracker = UsageTracker()
    token = _active.set(tracker)
    try:
        yield tracker
    finally:
        _active.reset(token)
