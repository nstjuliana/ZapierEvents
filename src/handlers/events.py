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
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi import status as status_codes
from fastapi.responses import JSONResponse
from typing import List, Optional, Union

from models.request import CreateEventRequest
from models.response import EventResponse
from models.event import Event
from storage.dynamodb import DynamoDBClient
from sqs_queue.sqs import SQSClient
from delivery.push import PushDeliveryClient
from config.settings import settings
from utils.logger import get_logger
from utils.metrics import MetricsClient

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


def get_metrics_client() -> MetricsClient:
    """
    Dependency to get CloudWatch metrics client.

    Creates and returns a configured MetricsClient instance
    for publishing custom metrics.

    Returns:
        Configured MetricsClient instance
    """
    return MetricsClient()


def get_sqs_client() -> SQSClient:
    """
    Dependency to get SQS client.

    Creates and returns a configured SQSClient instance
    for queueing failed deliveries.

    Returns:
        Configured SQSClient instance
    """
    return SQSClient(queue_url=settings.inbox_queue_url)


def get_delivery_client() -> PushDeliveryClient:
    """
    Dependency to get push delivery client.

    Creates and returns a configured PushDeliveryClient instance
    for delivering events to Zapier webhooks.

    Returns:
        Configured PushDeliveryClient instance
    """
    return PushDeliveryClient(
        webhook_url=settings.zapier_webhook_url,
        timeout_seconds=settings.delivery_timeout
    )


def get_user_id_from_request(request: Request) -> Optional[str]:
    """
    Extract user_id from API Gateway authorizer context.

    When auth is enabled, the authorizer sets user_id in the context.
    This function extracts it from the request scope.

    Args:
        request: FastAPI Request object

    Returns:
        user_id if available from authorizer, None otherwise
    """
    try:
        # Access the raw Lambda event from Mangum
        # The event is stored in request.scope by Mangum
        event = request.scope.get('aws.event', {})
        request_context = event.get('requestContext', {})
        authorizer = request_context.get('authorizer', {})
        context = authorizer.get('context', {})
        user_id = context.get('userId')
        
        # Only return user_id if it's not the default 'authenticated-user'
        if user_id and user_id != 'authenticated-user':
            return user_id
        
        return None
    except Exception:
        # If auth is disabled or context not available, return None
        return None


@router.post("", status_code=status_codes.HTTP_201_CREATED, response_model=EventResponse)
async def create_event(
    request: CreateEventRequest,
    http_request: Request,
    db_client: DynamoDBClient = Depends(get_db_client),
    sqs_client: SQSClient = Depends(get_sqs_client),
    delivery_client: PushDeliveryClient = Depends(get_delivery_client),
    metrics_client: MetricsClient = Depends(get_metrics_client)
) -> Union[EventResponse, JSONResponse]:
    """
    Create and ingest a new event with automatic delivery attempt.

    Attempts immediate push delivery to Zapier. If push succeeds,
    marks event as delivered. If push fails, queues to SQS for retry.

    Args:
        request: CreateEventRequest containing event_type, payload, and metadata
        db_client: DynamoDB client (injected via dependency)
        sqs_client: SQS client for queuing failed deliveries
        delivery_client: Push delivery client for Zapier webhook

    Returns:
        EventResponse with delivery status

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

        Response (201 Created - new event):
        {
            "event_id": "evt_abc123xyz456",
            "status": "delivered",
            "created_at": "2024-01-15T10:30:01Z",
            "delivered_at": "2024-01-15T10:30:01Z",
            "message": "Event delivered successfully"
        }

        Response (200 OK - idempotent duplicate):
        {
            "event_id": "evt_abc123xyz456",
            "status": "delivered",
            "created_at": "2024-01-15T10:30:01Z",
            "idempotency_key": "order-12345-2024-01-15",
            "message": "Event already exists with this idempotency key"
        }
    """
    try:
        # Get user_id from authorizer context (if auth enabled) or request body (fallback)
        user_id = get_user_id_from_request(http_request) or request.user_id
        
        # Check for idempotency key before creating new event
        if request.idempotency_key:
            existing_event = await db_client.get_event_by_idempotency_key(
                user_id=user_id,
                idempotency_key=request.idempotency_key
            )

            if existing_event:
                logger.info(
                    "Duplicate event creation prevented by idempotency key",
                    idempotency_key=request.idempotency_key,
                    user_id=user_id,
                    existing_event_id=existing_event.event_id,
                    event_type=request.event_type
                )

                # Return existing event with HTTP 200 (idempotent response)
                response_data = EventResponse(
                    event_id=existing_event.event_id,
                    event_type=existing_event.event_type,
                    payload=existing_event.payload,
                    metadata=existing_event.metadata,
                    status=existing_event.status,
                    created_at=existing_event.created_at,
                    delivered_at=existing_event.delivered_at,
                    delivery_attempts=existing_event.delivery_attempts,
                    user_id=existing_event.user_id,
                    idempotency_key=existing_event.idempotency_key,
                    message="Event already exists with this idempotency key"
                )
                return JSONResponse(
                    content=response_data.model_dump(),
                    status_code=status_codes.HTTP_200_OK
                )

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
            delivery_attempts=0,
            user_id=user_id,
            idempotency_key=request.idempotency_key
        )

        # Store in DynamoDB first
        await db_client.put_event(event)

        logger.info(
            "Event stored in database",
            event_id=event_id,
            event_type=request.event_type
        )

        # Attempt immediate push delivery
        try:
            delivery_success = await delivery_client.deliver_event(event)

            if delivery_success:
                # Update to delivered status
                event.status = "delivered"
                event.delivered_at = datetime.now(timezone.utc)
                event.delivery_attempts = 1
                await db_client.update_event(event)

                logger.info("Event delivered immediately", event_id=event_id)

                # Publish delivery metrics
                try:
                    metrics_client.put_metric(
                        metric_name="EventDelivered",
                        value=1.0,
                        dimensions={"EventType": request.event_type}
                    )
                except Exception:
                    pass

            else:
                # Queue to SQS for retry
                await sqs_client.send_message(
                    event_id=event_id,
                    event_data=event.model_dump(mode='json')
                )

                logger.info("Event queued for retry", event_id=event_id)

        except Exception as e:
            # Queue to SQS as fallback
            logger.warning(
                "Push delivery failed, queueing to SQS",
                event_id=event_id,
                error=str(e)
            )
            try:
                await sqs_client.send_message(
                    event_id=event_id,
                    event_data=event.model_dump(mode='json')
                )
            except Exception as queue_error:
                logger.error(
                    "Failed to queue event to SQS",
                    event_id=event_id,
                    error=str(queue_error)
                )

        # Publish creation metrics
        try:
            metrics_client.put_metric(
                metric_name="EventCreated",
                value=1.0,
                dimensions={"EventType": request.event_type}
            )
        except Exception:
            # Metrics failure shouldn't break event creation
            pass

        return EventResponse(
            event_id=event.event_id,
            event_type=event.event_type,
            payload=event.payload,
            metadata=event.metadata,
            status=event.status,
            created_at=event.created_at,
            delivered_at=event.delivered_at,
            delivery_attempts=event.delivery_attempts,
            user_id=event.user_id,
            idempotency_key=event.idempotency_key,
            message=f"Event {event.status}"
        )

    except ValueError as e:
        # Validation error
        logger.warning(
            "Event validation failed",
            error=str(e),
            event_type=getattr(request, 'event_type', 'unknown')
        )
        raise HTTPException(
            status_code=status_codes.HTTP_400_BAD_REQUEST,
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
            status_code=status_codes.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create event"
        )


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: str,
    db_client: DynamoDBClient = Depends(get_db_client)
) -> EventResponse:
    """
    Retrieve a specific event by ID.

    Fetches an event from DynamoDB and returns its full details
    including payload, metadata, and delivery status.

    Args:
        event_id: Unique event identifier
        db_client: DynamoDB client (injected via dependency)

    Returns:
        EventResponse with complete event details

    Raises:
        HTTPException: 404 if event not found
        HTTPException: 500 if database error

    Example:
        GET /events/evt_abc123xyz456

        Response (200):
        {
            "event_id": "evt_abc123xyz456",
            "status": "delivered",
            "created_at": "2024-01-15T10:30:01Z",
            "delivered_at": "2024-01-15T10:30:02Z",
            "message": "Event retrieved successfully"
        }
    """
    try:
        event = await db_client.get_event(event_id)
    except Exception as e:
        logger.error("Database error retrieving event", event_id=event_id, error=str(e))
        raise HTTPException(
            status_code=status_codes.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve event"
        )

    if not event:
        raise HTTPException(
            status_code=status_codes.HTTP_404_NOT_FOUND,
            detail=f"Event {event_id} not found"
        )

    return EventResponse(
        event_id=event.event_id,
        event_type=event.event_type,
        payload=event.payload,
        metadata=event.metadata,
        status=event.status,
        created_at=event.created_at,
        delivered_at=event.delivered_at,
        delivery_attempts=event.delivery_attempts,
        user_id=event.user_id,
        idempotency_key=event.idempotency_key,
        message="Event retrieved successfully"
    )


@router.get("", response_model=List[EventResponse])
async def list_events(
    status: Optional[str] = None,
    limit: int = 50,
    cursor: Optional[str] = None,
    db_client: DynamoDBClient = Depends(get_db_client)
) -> List[EventResponse]:
    """
    List events with optional filtering and pagination.

    Returns a paginated list of events, optionally filtered by status.
    Uses cursor-based pagination for efficient handling of large datasets.

    Args:
        status: Optional status filter (pending, delivered, failed, replayed)
        limit: Maximum number of events to return (default 50, max 100)
        cursor: Pagination cursor from previous response
        db_client: DynamoDB client (injected via dependency)

    Returns:
        List of EventResponse objects

    Raises:
        HTTPException: 400 if invalid parameters
        HTTPException: 500 if database error

    Example:
        GET /events?status=pending&limit=10

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
        events = await db_client.list_events(
            status=status,
            limit=limit,
            cursor=cursor
        )
    except Exception as e:
        logger.error("Database error listing events", error=str(e))
        raise HTTPException(
            status_code=status_codes.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list events"
        )

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
            user_id=event.user_id,
            idempotency_key=event.idempotency_key,
            message="Event retrieved successfully"
        )
        for event in events
    ]


@router.post("/{event_id}/acknowledge", status_code=status_codes.HTTP_204_NO_CONTENT)
async def acknowledge_event(
    event_id: str,
    db_client: DynamoDBClient = Depends(get_db_client),
    metrics_client: MetricsClient = Depends(get_metrics_client)
) -> None:
    """
    Acknowledge successful event delivery.

    Updates event status to 'delivered' and sets delivery timestamp.
    Called by Zapier after successfully processing an event.

    Args:
        event_id: Unique event identifier to acknowledge
        db_client: DynamoDB client

    Raises:
        HTTPException: 404 if event not found
        HTTPException: 500 if database error

    Example:
        POST /events/evt_abc123xyz456/acknowledge

        Response (204): No Content
    """
    try:
        # Get event
        event = await db_client.get_event(event_id)
        if not event:
            raise HTTPException(
                status_code=status_codes.HTTP_404_NOT_FOUND,
                detail=f"Event {event_id} not found"
            )

        # Update status
        event.status = "delivered"
        event.delivered_at = datetime.now(timezone.utc)

        await db_client.update_event(event)

        logger.info(
            "Event acknowledged",
            event_id=event_id,
            event_type=event.event_type
        )

        # Publish metrics
        try:
            metrics_client.put_metric(
                metric_name="EventDelivered",
                value=1.0,
                dimensions={"EventType": event.event_type}
            )
        except Exception:
            # Metrics failure shouldn't break acknowledgment
            pass

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to acknowledge event", event_id=event_id, error=str(e))
        raise HTTPException(
            status_code=status_codes.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to acknowledge event"
        )