"""Retry and fallback wrappers using tenacity for tool resilience.

Wraps Gmail and Calendar tool calls with retry logic and fallback behavior.
"""

import logging
from functools import wraps
from typing import Callable, Any

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

logger = logging.getLogger(__name__)


# Transient errors that are worth retrying
TRANSIENT_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    OSError,
)


def with_retry(max_attempts: int = 3, min_wait: int = 1, max_wait: int = 10):
    """Decorator to retry a function on transient failures with exponential backoff.

    Args:
        max_attempts: Maximum number of retries (including first attempt).
        min_wait: Minimum wait time between retries in seconds.
        max_wait: Maximum wait time between retries in seconds.
    """

    def decorator(func: Callable):
        @wraps(func)
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
            retry=retry_if_exception_type(TRANSIENT_EXCEPTIONS),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper

    return decorator


def fallback_on_failure(fallback_func: Callable):
    """Decorator that calls a fallback function if the primary function fails.

    Unlike @with_retry which retries, this decorator immediately falls back
    to a simpler, more reliable implementation.

    Used for: thread summarization (fallback to rule-based summary).
    """

    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.warning(
                    f"Primary function {func.__name__} failed: {e}. Using fallback."
                )
                return fallback_func(*args, **kwargs)

        return wrapper

    return decorator


def rule_based_summary(thread_content: str) -> str:
    """Simple fallback summarization when the primary summarizer fails.

    Extracts basic information using keyword matching.
    """
    content_lower = thread_content.lower()
    points = []

    if "invoice" in content_lower:
        points.append("Invoice-related thread detected")

    if "payment" in content_lower or "paid" in content_lower:
        points.append("Payment-related content")

    if "overdue" in content_lower or "past due" in content_lower:
        points.append("Overdue or past-due notice")

    if "reminder" in content_lower:
        points.append("Reminder/follow-up communication")

    if not points:
        points.append("No specific invoice details extracted")

    return " | ".join(points)
