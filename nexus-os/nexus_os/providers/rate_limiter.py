"""Per-provider rate limit tracking.

Tracks request and token usage within sliding windows.
Used by the ProviderRouter to skip providers that are at capacity.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass
class RateWindow:
    """A sliding window counter."""
    timestamps: deque  # of (time.monotonic(), tokens_used)
    max_per_minute: int
    tokens_per_minute: int

    def prune(self, now: float) -> None:
        cutoff = now - 60.0
        while self.timestamps and self.timestamps[0][0] < cutoff:
            self.timestamps.popleft()

    def current_requests(self) -> int:
        return len(self.timestamps)

    def current_tokens(self) -> int:
        return sum(t for _, t in self.timestamps)

    def can_proceed(self, tokens_needed: int = 0) -> bool:
        now = time.monotonic()
        self.prune(now)
        if self.current_requests() >= self.max_per_minute:
            return False
        if self.current_tokens() + tokens_needed > self.tokens_per_minute:
            return False
        return True

    def record(self, tokens_used: int = 0) -> None:
        now = time.monotonic()
        self.prune(now)
        self.timestamps.append((now, tokens_used))


class RateLimiter:
    """Thread-safe rate limiter keyed by provider name."""

    def __init__(self) -> None:
        self._windows: dict[str, RateWindow] = {}
        self._lock = threading.Lock()

    def register(self, provider_name: str, rpm: int, tpm: int) -> None:
        with self._lock:
            self._windows[provider_name] = RateWindow(
                timestamps=deque(),
                max_per_minute=rpm,
                tokens_per_minute=tpm,
            )

    def can_proceed(self, provider_name: str, tokens_needed: int = 0) -> bool:
        with self._lock:
            window = self._windows.get(provider_name)
            if not window:
                return True  # unregistered = no limit
            return window.can_proceed(tokens_needed)

    def record(self, provider_name: str, tokens_used: int = 0) -> None:
        with self._lock:
            window = self._windows.get(provider_name)
            if window:
                window.record(tokens_used)

    def snapshot(self) -> dict[str, dict]:
        """Return current usage for all providers."""
        with self._lock:
            result = {}
            for name, w in self._windows.items():
                w.prune(time.monotonic())
                result[name] = {
                    "requests": w.current_requests(),
                    "tokens": w.current_tokens(),
                    "rpm_limit": w.max_per_minute,
                    "tpm_limit": w.tokens_per_minute,
                }
            return result
