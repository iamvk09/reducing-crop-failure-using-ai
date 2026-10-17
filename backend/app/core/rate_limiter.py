"""In-memory rate limiter with sliding window / token bucket algorithm.

Designed for defense-in-depth protection on FastAPI backend instances.
Enforces per-authenticated-user and per-client-IP rate limits with custom Retry-After headers.
Thread-safe and async-compatible.
"""

import time
import threading
from typing import Dict, List, Optional, Tuple
from fastapi import Request, HTTPException, status
from backend.app.core.config import settings
from backend.app.core.logging import logger


class SlidingWindowRateLimiter:
    """Sliding window counter rate limiter.
    
    Maintains timestamp records for request keys and prunes expired records.
    Provides atomic thread-safe rate limit checking and consumption.
    """

    def __init__(self, default_limit: int = 60, window_seconds: int = 60, max_keys: int = 10000):
        self.default_limit = default_limit
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._history: Dict[str, List[float]] = {}
        self._lock = threading.Lock()
        self._last_cleanup = time.time()

    def _cleanup_expired_keys(self, now: float, window: int):
        """Periodic garbage collection of keys with no active requests in window."""
        if now - self._last_cleanup < 60 and len(self._history) < self.max_keys:
            return
        self._last_cleanup = now
        window_start = now - window
        keys_to_delete = [
            k for k, timestamps in self._history.items()
            if not timestamps or timestamps[-1] <= window_start
        ]
        for k in keys_to_delete:
            del self._history[k]

        # Hard emergency cap to protect process memory
        if len(self._history) >= self.max_keys:
            # Evict oldest 20%
            sorted_keys = sorted(self._history.keys(), key=lambda k: self._history[k][-1] if self._history[k] else 0)
            for k in sorted_keys[:int(self.max_keys * 0.2)]:
                del self._history[k]

    def is_allowed(self, key: str, limit: Optional[int] = None, window_seconds: Optional[int] = None) -> Tuple[bool, int, int]:
        """Check if request is allowed for given key.
        
        Returns:
            Tuple[is_allowed: bool, remaining: int, retry_after: int]
        """
        max_requests = limit if limit is not None else self.default_limit
        window = window_seconds if window_seconds is not None else self.window_seconds
        now = time.time()
        window_start = now - window

        with self._lock:
            self._cleanup_expired_keys(now, window)
            timestamps = self._history.get(key, [])
            # Prune timestamps older than window_start
            valid_timestamps = [ts for ts in timestamps if ts > window_start]

            if len(valid_timestamps) >= max_requests:
                # Exceeded
                oldest_timestamp = valid_timestamps[0]
                retry_after = max(1, int(oldest_timestamp + window - now))
                self._history[key] = valid_timestamps
                return False, 0, retry_after

            # Allowed - record timestamp
            valid_timestamps.append(now)
            self._history[key] = valid_timestamps
            remaining = max_requests - len(valid_timestamps)
            return True, remaining, 0

    def reset(self):
        """Clear all stored rate limit history (useful for tests)."""
        with self._lock:
            self._history.clear()


# Global rate limiter instances with categorized limits (requests per 60 seconds)
# 1. Predictions: 10 req / min
# 2. SHAP / Heavy Diagnostics / Simulations: 5 req / min
# 3. General Authenticated: 60 req / min
# 4. Unauthenticated / Auth Sensitive: 20 req / min

prediction_limiter = SlidingWindowRateLimiter(default_limit=10, window_seconds=60)
diagnostics_limiter = SlidingWindowRateLimiter(default_limit=5, window_seconds=60)
general_limiter = SlidingWindowRateLimiter(default_limit=60, window_seconds=60)
unauthenticated_limiter = SlidingWindowRateLimiter(default_limit=20, window_seconds=60)


def check_rate_limit(
    key: str,
    limiter: SlidingWindowRateLimiter,
    limit: Optional[int] = None,
    window_seconds: Optional[int] = None,
    error_message: str = "Rate limit exceeded. Please slow down.",
):
    """Utility function to check limiter and raise HTTP 429 if exceeded."""
    # Allow bypassing rate limits in explicit testing mode if configured
    if getattr(settings, "DISABLE_RATE_LIMITS_FOR_TESTS", False):
        return

    allowed, remaining, retry_after = limiter.is_allowed(key, limit=limit, window_seconds=window_seconds)
    if not allowed:
        logger.warning(f"Rate limit exceeded for key={key}: retry_after={retry_after}s")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=error_message,
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(limit or limiter.default_limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(retry_after),
            },
        )
