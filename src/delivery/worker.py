"""
Module: delivery/worker.py
Description: SQS worker Lambda for event delivery.

Processes events from SQS inbox queue and retries delivery
to Zapier with status updates in DynamoDB.
"""

import json
import httpx
from datetime import datetime, timezone
from typing import Dict, Any

from models.event import Event
from storage.dynamodb import DynamoDBClient
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class SyncPushDeliveryClient:
    """
    Synchronous HTTP client for pushing events to Zapier.

    Handles delivery attempts with proper timeout and
    error handling for network issues. Synchronous version
    for Lambda SQS worker.
    """

    def __init__(self, webhook_url: str):
        """
        Initialize push delivery client.

        Args:
            webhook_url: Zapier webhook URL for delivery
        """
        if not webhook_url or not isinstance(webhook_url, str):
            raise ValueError("webhook_url must be a non-empty string")
        if not webhook_url.startswith(('http://', 'https://')):
            raise ValueError("webhook_url must be a valid HTTP/HTTPS URL")

        self.webhook_url = webhook_url
        self.timeout = httpx.Timeout(10.0, connect=5.0)

        logger.info(
            "Sync push delivery client initialized",
            webhook_url=webhook_url,
            timeout_seconds=10.0
        )

    def deliver_event(self, event: Event) -> bool:
        """
        Deliver event to Zapier via HTTP POST.

        Args:
            event: Event to deliver

        Returns:
            True if delivery successful, False otherwise
        """
        if not isinstance(event, Event):
            raise ValueError("event must be an Event instance")

        with httpx.Client(timeout=self.timeout) as client:
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

                response = client.post(
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


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for SQS event processing.

    Args:
        event: SQS event with batch of messages
        context: Lambda context

    Returns:
        Response with batch item failures (if any)
    """
    db_client = DynamoDBClient(settings.events_table_name)
    delivery_client = SyncPushDeliveryClient(settings.zapier_webhook_url)

    batch_failures = []

    for record in event['Records']:
        try:
            # Parse event from SQS message
            event_data = json.loads(record['body'])
            event_obj = Event(**event_data)

            logger.info("Processing event from SQS", event_id=event_obj.event_id)

            # Check if event still exists in DynamoDB (may have been deleted)
            db_event = db_client.get_event(event_obj.event_id)
            if not db_event:
                logger.info(
                    "Event no longer exists in DynamoDB, skipping delivery",
                    event_id=event_obj.event_id,
                    reason="event_deleted"
                )
                # Don't report as failure - orphaned messages are acceptable
                continue

            # Use the current event data from DynamoDB for delivery
            event_obj = db_event

            # Attempt delivery
            success = delivery_client.deliver_event(event_obj)

            if success:
                # Update status to delivered
                event_obj.status = "delivered"
                event_obj.delivered_at = datetime.now(timezone.utc)
                event_obj.delivery_attempts += 1
                db_client.update_event(event_obj)

                logger.info("Event delivered from queue", event_id=event_obj.event_id)
            else:
                # Increment attempt count and return to queue
                event_obj.delivery_attempts += 1
                db_client.update_event(event_obj)

                # Report failure to retry (message returns to queue)
                batch_failures.append({
                    'itemIdentifier': record['messageId']
                })

                logger.warning(
                    "Event delivery failed, will retry",
                    event_id=event_obj.event_id,
                    attempts=event_obj.delivery_attempts
                )

        except Exception as e:
            logger.error(
                "Error processing SQS message",
                message_id=record['messageId'],
                error=str(e)
            )
            batch_failures.append({
                'itemIdentifier': record['messageId']
            })

    return {'batchItemFailures': batch_failures}
