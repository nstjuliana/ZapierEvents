"""
Module: inbox.py
Description: Inbox endpoint for polling undelivered events.

Allows Zapier system to poll for events that need delivery,
implementing the pull portion of the hybrid push/pull model.

Key Components:
- get_inbox(): Main inbox endpoint for retrieving pending events
- get_db_client(): Dependency injection for DynamoDB client
- Event filtering by status and sorting by creation time

Dependencies: FastAPI, typing, models, storage, config, utils
Author: Triggers API Team
"""

from typing import List
from fastapi import APIRouter, HTTPException, Depends
from fastapi import status as status_codes

from models.response import EventResponse
from storage.dynamodb import DynamoDBClient
from config.settings import settings
from utils.logger import get_logger
from utils.metrics import MetricsClient

router = APIRouter(prefix="/inbox", tags=["inbox"])
logger = get_logger(__name__)


def get_db_client() -> DynamoDBClient:
    """Dependency to get DynamoDB client."""
    return DynamoDBClient(table_name=settings.events_table_name)


def get_metrics_client() -> MetricsClient:
    """
    Dependency to get CloudWatch metrics client.

    Creates and returns a configured MetricsClient instance
    for publishing custom metrics.
    """
    return MetricsClient()


@router.get("", response_model=List[EventResponse])
async def get_inbox(
    limit: int = 100,
    db_client: DynamoDBClient = Depends(get_db_client),
    metrics_client: MetricsClient = Depends(get_metrics_client)
) -> List[EventResponse]:
    """
    Retrieve undelivered events from inbox.

    Returns events with status 'pending' or 'undelivered',
    sorted by creation time (oldest first) for FIFO processing.

    Args:
        limit: Maximum number of events to return (default 100)
        db_client: DynamoDB client

    Returns:
        List of undelivered events

    Raises:
        HTTPException: 400 if invalid limit
        HTTPException: 500 if database error

    Example:
        GET /inbox?limit=50

        Response (200):
        [
            {
                "event_id": "evt_abc123xyz456",
                "status": "pending",
                "created_at": "2024-01-15T10:30:01Z",
                "delivered_at": null,
                "message": "Event retrieved successfully"
            }
        ]
    """
    if limit > 100:
        raise HTTPException(
            status_code=status_codes.HTTP_400_BAD_REQUEST,
            detail="Limit cannot exceed 100"
        )

    try:
        # Get pending events
        pending_events = await db_client.list_events(
            status="pending",
            limit=limit
        )

        logger.info(
            "Inbox retrieved",
            count=len(pending_events),
            limit=limit
        )

        # Publish metrics
        try:
            metrics_client.put_metric(
                metric_name="InboxDepth",
                value=float(len(pending_events))
            )
        except Exception:
            # Metrics failure shouldn't break inbox retrieval
            pass

        return [
            EventResponse(
                event_id=event.event_id,
                event_type=event.event_type,
                payload=event.payload,
                metadata=event.metadata,
                status=event.status,
                created_at=event.created_at,
                delivered_at=event.delivered_at,
                delivery_attempts=event.delivery_attempts,
                message="Event retrieved successfully"
            )
            for event in pending_events
        ]

    except Exception as e:
        logger.error("Failed to retrieve inbox", error=str(e))
        raise HTTPException(
            status_code=status_codes.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve inbox"
        )
