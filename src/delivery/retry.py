"""
Module: delivery/retry.py
Description: Retry logic for event delivery.

Implements intelligent retry strategies with exponential backoff
and jitter for handling transient delivery failures.
"""

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_log,
    after_log
)
import httpx
import logging

from utils.logger import get_logger

logger = get_logger(__name__)

# Configure retry decorator for delivery attempts
delivery_retry = retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    retry=retry_if_exception_type((
        httpx.TimeoutException,
        httpx.NetworkError,
        httpx.HTTPStatusError
    )),
    before=before_log(logger, logging.INFO),
    after=after_log(logger, logging.INFO),
    reraise=True
)

async def retry_delivery(delivery_fn, event):
    """
    Retry event delivery with exponential backoff.

    Args:
        delivery_fn: Async function to attempt delivery
        event: Event to deliver

    Returns:
        True if delivery succeeds (after retries), False otherwise
    """
    try:
        @delivery_retry
        async def attempt_delivery():
            success = await delivery_fn(event)
            if not success:
                # Raise exception to trigger retry
                raise httpx.HTTPStatusError(
                    "Delivery failed",
                    request=None,
                    response=None
                )
            return success

        return await attempt_delivery()

    except Exception as e:
        logger.error(f"Delivery failed after all retries for event {event.event_id}: {str(e)}")
        return False
