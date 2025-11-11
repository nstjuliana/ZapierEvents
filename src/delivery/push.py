"""
Module: push.py
Description: Push event delivery to Zapier webhook.

Implements HTTP push delivery with timeout handling and
error recovery for transient failures.
"""

import httpx
from typing import Optional
from datetime import datetime, timezone

from models.event import Event
from utils.logger import get_logger

logger = get_logger(__name__)


class PushDeliveryClient:
    """
    HTTP client for pushing events to Zapier.

    Handles delivery attempts with proper timeout and
    error handling for network issues.
    """

    def __init__(self, webhook_url: str, timeout_seconds: int = 10):
        """
        Initialize push delivery client.

        Args:
            webhook_url: Zapier webhook URL for delivery
            timeout_seconds: HTTP timeout in seconds

        Raises:
            ValueError: If webhook_url is invalid
        """
        if not webhook_url or not isinstance(webhook_url, str):
            raise ValueError("webhook_url must be a non-empty string")
        if not webhook_url.startswith(('http://', 'https://')):
            raise ValueError("webhook_url must be a valid HTTP/HTTPS URL")

        self.webhook_url = webhook_url
        self.timeout = httpx.Timeout(timeout_seconds, connect=timeout_seconds)

        logger.info(
            "Push delivery client initialized",
            webhook_url=webhook_url,
            timeout_seconds=timeout_seconds
        )

    async def deliver_event(self, event: Event) -> bool:
        """
        Deliver event to Zapier via HTTP POST.

        Args:
            event: Event to deliver

        Returns:
            True if delivery successful, False otherwise
        """
        if not isinstance(event, Event):
            raise ValueError("event must be an Event instance")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                payload = {
                    'event_id': event.event_id,
                    'event_type': event.event_type,
                    'payload': event.payload,
                    'metadata': event.metadata,
                    'created_at': event.created_at.isoformat() + 'Z'
                }

                logger.debug(
                    "Attempting event delivery",
                    event_id=event.event_id,
                    webhook_url=self.webhook_url
                )

                response = await client.post(
                    self.webhook_url,
                    json=payload,
                    headers={'Content-Type': 'application/json'}
                )

                response.raise_for_status()

                logger.info(
                    "Event delivered successfully",
                    event_id=event.event_id,
                    status_code=response.status_code,
                    response_time_ms=response.elapsed.total_seconds() * 1000
                )

                return True

            except httpx.TimeoutException:
                logger.warning(
                    "Event delivery timeout",
                    event_id=event.event_id,
                    webhook_url=self.webhook_url
                )
                return False

            except httpx.HTTPStatusError as e:
                logger.warning(
                    "Event delivery HTTP error",
                    event_id=event.event_id,
                    status_code=e.response.status_code,
                    response=e.response.text[:500]  # Truncate large responses
                )
                return False

            except httpx.NetworkError as e:
                logger.warning(
                    "Event delivery network error",
                    event_id=event.event_id,
                    error=str(e)
                )
                return False

            except Exception as e:
                logger.error(
                    "Event delivery failed",
                    event_id=event.event_id,
                    error=str(e),
                    error_type=type(e).__name__
                )
                return False
