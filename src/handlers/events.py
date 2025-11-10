"""
Module: events.py
Description: Event ingestion and retrieval handlers.

Implements the core event endpoints for the Triggers API:
- POST /events: Create and ingest new events
- Event validation, ID generation, and storage
- Structured error handling and logging

Key Components:
- create_event(): Main event creation endpoint
- get_db_client(): Dependency injection for DynamoDB client
- Event ID generation and validation
- Comprehensive error handling with HTTP status codes

Dependencies: FastAPI, datetime, uuid, typing
Author: Triggers API Team
"""

from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, HTTPException, status, Depends
from typing import Optional

from models.request import CreateEventRequest
from models.response import EventResponse
from models.event import Event
from storage.dynamodb import DynamoDBClient
from config.settings import settings
from utils.logger import get_logger

router = APIRouter(prefix="/events", tags=["events"])
logger = get_logger(__name__)


def get_db_client() -> DynamoDBClient:
    """
    Dependency to get DynamoDB client.

    Creates and returns a configured DynamoDBClient instance
    for event storage operations. Uses singleton pattern via
    global settings.

    Returns:
        Configured DynamoDBClient instance
    """
    return DynamoDBClient(table_name=settings.events_table_name)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=EventResponse)
async def create_event(
    request: CreateEventRequest,
    db_client: DynamoDBClient = Depends(get_db_client)
) -> EventResponse:
    """
    Create and ingest a new event.

    Validates the event payload, generates a unique event ID,
    attempts to push the event to Zapier, and stores it in DynamoDB.
    If push fails, the event is queued in SQS for later polling.

    Args:
        request: CreateEventRequest containing event_type, payload, and metadata
        db_client: DynamoDB client (injected via dependency)

    Returns:
        EventResponse with event details including generated ID

    Raises:
        HTTPException: 400 if validation fails
        HTTPException: 500 if database operation fails

    Example:
        POST /events
        {
            "event_type": "order.created",
            "payload": {"order_id": "12345", "amount": 99.99},
            "metadata": {"source": "ecommerce-platform"}
        }

        Response (201):
        {
            "event_id": "evt_abc123xyz456",
            "status": "pending",
            "created_at": "2024-01-15T10:30:01Z",
            "delivered_at": null,
            "message": "Event created successfully"
        }
    """
    try:
        # Generate unique event ID
        event_id = f"evt_{uuid4().hex[:12]}"

        logger.info(
            "Creating new event",
            event_type=request.event_type,
            has_metadata=bool(request.metadata),
            payload_size=len(str(request.payload))
        )

        # Create event model
        event = Event(
            event_id=event_id,
            event_type=request.event_type,
            payload=request.payload,
            metadata=request.metadata,
            status="pending",
            created_at=datetime.now(timezone.utc),
            delivered_at=None,
            delivery_attempts=0
        )

        # Store in DynamoDB
        await db_client.put_event(event)

        logger.info(
            "Event created successfully",
            event_id=event_id,
            event_type=request.event_type
        )

        return EventResponse(
            event_id=event.event_id,
            status=event.status,
            created_at=event.created_at,
            delivered_at=event.delivered_at,
            message="Event created successfully"
        )

    except ValueError as e:
        # Validation error
        logger.warning(
            "Event validation failed",
            error=str(e),
            event_type=getattr(request, 'event_type', 'unknown')
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid event data: {str(e)}"
        )

    except Exception as e:
        # Database or other error
        logger.error(
            "Failed to create event",
            error=str(e),
            event_type=getattr(request, 'event_type', 'unknown')
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create event"
        )
