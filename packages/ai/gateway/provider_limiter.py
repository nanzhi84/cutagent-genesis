"""In-process concurrency limiter for provider invocations.

ProviderProfile.concurrency_key carries the intended backpressure grouping
(vendor account / quota bucket). This module enforces a bounded number of
in-flight provider calls per key so concurrent durable runs cannot fan out
unbounded TTS/ASR/VLM/LipSync/LLM requests at vendor quotas.

Scope: this is a PER-PROCESS limiter. Each worker process keeps its own set of
bounded semaphores. Cluster-wide limiting (across many worker processes/pods)
requires a shared limiter (e.g. Redis token bucket) and is intentionally NOT
implemented here.

Thread-safety: the gateway runs provider calls under the activity
ThreadPoolExecutor, so multiple threads enter concurrently. A module-level lock
guards lazy creation of per-key semaphores; the semaphores themselves are
``threading.BoundedSemaphore`` instances which are individually thread-safe.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager

DEFAULT_MAX_INFLIGHT = 4
_ENV_VAR = "CUTAGENT_PROVIDER_MAX_INFLIGHT"

_registry_lock = threading.Lock()
_semaphores: dict[str, threading.BoundedSemaphore] = {}


def _max_inflight() -> int:
    """Resolve the per-key in-flight cap from the environment.

    Read lazily (not at import time) so tests / deployments can set the env var
    before the first invocation. Invalid or non-positive values fall back to the
    sane default rather than disabling backpressure.
    """

    raw = os.getenv(_ENV_VAR)
    if raw is None:
        return DEFAULT_MAX_INFLIGHT
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_MAX_INFLIGHT
    return value if value > 0 else DEFAULT_MAX_INFLIGHT


def _semaphore_for(key: str) -> threading.BoundedSemaphore:
    sem = _semaphores.get(key)
    if sem is not None:
        return sem
    with _registry_lock:
        sem = _semaphores.get(key)
        if sem is None:
            sem = threading.BoundedSemaphore(_max_inflight())
            _semaphores[key] = sem
        return sem


@contextmanager
def provider_slot(concurrency_key: str | None, provider_id: str) -> Iterator[None]:
    """Acquire one in-flight slot for the given concurrency key.

    Falls back to ``provider_id`` when ``concurrency_key`` is missing/blank so a
    profile without an explicit key is still bounded (rather than unbounded).
    """

    key = (concurrency_key or "").strip() or provider_id
    sem = _semaphore_for(key)
    sem.acquire()
    try:
        yield
    finally:
        sem.release()


def reset_limiter_for_tests() -> None:
    """Clear the per-key semaphore registry (test isolation helper)."""

    with _registry_lock:
        _semaphores.clear()
