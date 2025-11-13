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
from fastapi.responses import JSONResponse, Response
from typing import Dict, List, Optional, Union

from models.request import CreateEventRequest, UpdateEventRequest, BatchCreateEventRequest, BatchUpdateEventRequest, BatchDeleteEventRequest, ReplayEventRequest, BatchReplayEventRequest, GetEventsByListRequest
from models.response import EventResponse, BatchCreateResponse, BatchUpdateResponse, BatchDeleteResponse, BatchCreateItemResult, BatchUpdateItemResult, BatchDeleteItemResult, BatchItemError, BatchOperationSummary, ReplayResponse, BatchReplayItemResult, BatchReplayResponse
from models.event import Event
from storage.dynamodb import DynamoDBClient
from sqs_queue.sqs import SQSClient
from delivery.push import PushDeliveryClient
from config.settings import settings
from utils.logger import get_logger
from utils.metrics import MetricsClient
from utils.filters import parse_filter_params

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
                    message="Event already exists with this user_id and idempotency key"
                )
                return JSONResponse(
                    content=response_data.model_dump(mode='json'),
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


@router.post("/batch", status_code=status_codes.HTTP_201_CREATED, response_model=BatchCreateResponse)
async def batch_create_events(
    request: BatchCreateEventRequest,
    http_request: Request,
    db_client: DynamoDBClient = Depends(get_db_client),
    sqs_client: SQSClient = Depends(get_sqs_client),
    delivery_client: PushDeliveryClient = Depends(get_delivery_client),
    metrics_client: MetricsClient = Depends(get_metrics_client)
) -> BatchCreateResponse:
    """
    Create and ingest multiple events in a single batch operation.

    Processes events with best-effort semantics - continues processing even if
    some events fail. Supports idempotency via per-event idempotency keys.
    Attempts immediate push delivery for successful events.

    Args:
        request: BatchCreateEventRequest containing list of events to create
        http_request: FastAPI Request object for authorization context
        db_client: DynamoDB client (injected via dependency)
        sqs_client: SQS client for queuing failed deliveries
        delivery_client: Push delivery client for Zapier webhook
        metrics_client: Metrics client for publishing statistics

    Returns:
        BatchCreateResponse with detailed per-item results and summary

    Raises:
        HTTPException: 400 if batch validation fails
        HTTPException: 500 if critical system error occurs

    Example:
        POST /events/batch
        {
          "events": [
            {
              "event_type": "order.created",
              "payload": {"order_id": "12345", "amount": 99.99},
              "metadata": {"source": "ecommerce-platform"},
              "idempotency_key": "order-12345-2024-01-15"
            },
            {
              "event_type": "order.updated",
              "payload": {"order_id": "12345", "status": "shipped"},
              "metadata": {"source": "ecommerce-platform"}
            }
          ]
        }

        Response (201 Created):
        {
          "results": [
            {
              "index": 0,
              "success": true,
              "event": {
                "event_id": "evt_abc123xyz456",
                "status": "delivered",
                "created_at": "2024-01-15T10:30:01Z",
                "message": "Event created and delivered"
              }
            },
            {
              "index": 1,
              "success": false,
              "error": {
                "code": "VALIDATION_ERROR",
                "message": "payload is required"
              }
            }
          ],
          "summary": {
            "total": 2,
            "successful": 1,
            "failed": 1
          }
        }
    """
    try:
        # Get user_id from auth context
        user_id = get_user_id_from_request(http_request)

        # Validate batch size
        from utils.batch_helpers import validate_batch_size
        validate_batch_size(request.events, 100)

        logger.info(
            "Starting batch create",
            batch_size=len(request.events),
            user_id=user_id
        )

        results: List[BatchCreateItemResult] = []
        events_to_store: List[Event] = []
        events_to_deliver: List[Event] = []
        index_map: Dict[str, int] = {}  # event_id -> original index
        idempotent_indices: set[int] = set()  # Track which indices are idempotent matches

        # Process each event in the batch
        for idx, item in enumerate(request.events):
            try:
                # Get user_id for this event: from request body, or fallback to auth context
                event_user_id = item.user_id or user_id

                # Check for idempotency key duplicate (per event, since user_id may vary)
                if item.idempotency_key and event_user_id:
                    existing_event = await db_client.get_event_by_idempotency_key(
                        user_id=event_user_id,
                        idempotency_key=item.idempotency_key
                    )

                    if existing_event:
                        logger.info(
                            "Duplicate event creation prevented by idempotency key",
                            idempotency_key=item.idempotency_key,
                            user_id=event_user_id,
                            existing_event_id=existing_event.event_id,
                            index=idx
                        )

                        # Return existing event as successful result (but mark as idempotent)
                        event_response = EventResponse(
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

                        results.append(BatchCreateItemResult(
                            index=idx,
                            success=True,
                            event=event_response
                        ))
                        idempotent_indices.add(idx)
                        continue

                # Generate unique event ID
                event_id = f"evt_{uuid4().hex[:12]}"

                # Create event model
                event = Event(
                    event_id=event_id,
                    event_type=item.event_type,
                    payload=item.payload,
                    metadata=item.metadata,
                    status="pending",
                    created_at=datetime.now(timezone.utc),
                    delivered_at=None,
                    delivery_attempts=0,
                    user_id=event_user_id,
                    idempotency_key=item.idempotency_key
                )

                # Add to lists for batch operations
                events_to_store.append(event)
                events_to_deliver.append(event)
                index_map[event_id] = idx

                logger.info(
                    "Prepared event for batch processing",
                    event_id=event_id,
                    event_type=item.event_type,
                    index=idx,
                    has_idempotency_key=bool(item.idempotency_key)
                )

            except Exception as e:
                # Validation or other error for this item
                logger.warning(
                    "Failed to prepare event for batch creation",
                    index=idx,
                    error=str(e),
                    event_type=getattr(item, 'event_type', 'unknown')
                )

                results.append(BatchCreateItemResult(
                    index=idx,
                    success=False,
                    error=BatchItemError(
                        code="VALIDATION_ERROR",
                        message=str(e)
                    )
                ))

        # Batch store events in DynamoDB
        successful_event_ids = []
        if events_to_store:
            batch_result = await db_client.batch_put_events(events_to_store)
            successful_event_ids = batch_result["successful_event_ids"]

            # Process failed events from batch storage
            for failed_item in batch_result["failed_items"]:
                failed_event_id = failed_item["event_id"]
                original_idx = index_map.get(failed_event_id)

                if original_idx is not None:
                    results.append(BatchCreateItemResult(
                        index=original_idx,
                        success=False,
                        error=BatchItemError(
                            code="STORAGE_ERROR",
                            message=failed_item["reason"]
                        )
                    ))

                    # Remove from delivery list
                    events_to_deliver = [e for e in events_to_deliver if e.event_id != failed_event_id]

        # Attempt delivery for successful events
        delivered_event_ids = []
        if events_to_deliver:
            for event in events_to_deliver:
                try:
                    delivery_success = await delivery_client.deliver_event(event)

                    if delivery_success:
                        event.status = "delivered"
                        event.delivered_at = datetime.now(timezone.utc)
                        event.delivery_attempts = 1
                        delivered_event_ids.append(event.event_id)

                        # Publish delivery metrics
                        try:
                            metrics_client.put_metric(
                                metric_name="EventDelivered",
                                value=1.0,
                                dimensions={"EventType": event.event_type}
                            )
                        except Exception:
                            pass

                        logger.info("Event delivered immediately in batch", event_id=event.event_id)
                    else:
                        # Queue to SQS for retry
                        await sqs_client.send_message(
                            event_id=event.event_id,
                            event_data=event.model_dump(mode='json')
                        )
                        logger.info("Event queued for retry in batch", event_id=event.event_id)

                except Exception as e:
                    logger.warning(
                        "Push delivery failed in batch, queueing to SQS",
                        event_id=event.event_id,
                        error=str(e)
                    )
                    try:
                        await sqs_client.send_message(
                            event_id=event.event_id,
                            event_data=event.model_dump(mode='json')
                        )
                    except Exception as queue_error:
                        logger.error(
                            "Failed to queue event to SQS in batch",
                            event_id=event.event_id,
                            error=str(queue_error)
                        )

        # Update delivered events in DynamoDB
        if delivered_event_ids:
            delivered_events = [e for e in events_to_deliver if e.event_id in delivered_event_ids]
            if delivered_events:
                # Note: We could batch update these, but for simplicity we'll update individually
                # In a production system, you might want to add a batch_update_events method
                for event in delivered_events:
                    try:
                        await db_client.update_event(event)
                    except Exception as e:
                        logger.error(
                            "Failed to update delivered event status in batch",
                            event_id=event.event_id,
                            error=str(e)
                        )

        # Build final results for successful events
        for event in events_to_store:
            if event.event_id in successful_event_ids:
                original_idx = index_map[event.event_id]
                event_response = EventResponse(
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

                results.append(BatchCreateItemResult(
                    index=original_idx,
                    success=True,
                    event=event_response
                ))

        # Sort results by original index
        results.sort(key=lambda r: r.index)

        # Calculate summary
        # Successful = newly created events (not idempotent)
        successful_count = sum(1 for r in results if r.success and r.index not in idempotent_indices)
        idempotent_count = len(idempotent_indices)
        failed_count = sum(1 for r in results if not r.success)

        summary = BatchOperationSummary(
            total=len(results),
            successful=successful_count,
            idempotent=idempotent_count,
            failed=failed_count
        )

        # Publish batch metrics
        try:
            metrics_client.put_metric(
                metric_name="BatchCreateEvents",
                value=1.0,
                dimensions={"BatchSize": str(len(request.events))}
            )
        except Exception:
            pass

        logger.info(
            "Batch create completed",
            total=len(results),
            successful=successful_count,
            idempotent=idempotent_count,
            failed=failed_count,
            user_id=user_id
        )

        return BatchCreateResponse(
            results=results,
            summary=summary
        )

    except ValueError as e:
        # Batch validation error
        logger.warning(
            "Batch create validation failed",
            error=str(e),
            batch_size=len(getattr(request, 'events', []))
        )
        raise HTTPException(
            status_code=status_codes.HTTP_400_BAD_REQUEST,
            detail=f"Invalid batch request: {str(e)}"
        )

    except Exception as e:
        # Critical system error
        logger.error(
            "Critical error in batch create",
            error=str(e),
            batch_size=len(getattr(request, 'events', []))
        )
        raise HTTPException(
            status_code=status_codes.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process batch create request"
        )


@router.patch("/batch", response_model=BatchUpdateResponse)
async def batch_update_events(
    request: BatchUpdateEventRequest,
    http_request: Request,
    db_client: DynamoDBClient = Depends(get_db_client),
    sqs_client: SQSClient = Depends(get_sqs_client),
    metrics_client: MetricsClient = Depends(get_metrics_client)
) -> BatchUpdateResponse:
    """
    Update multiple events in a single batch operation.

    Processes event updates with best-effort semantics - continues processing
    even if some updates fail. Enforces ownership checks for security.
    Events with status "delivered" or "replayed" are reset to "pending" and
    queued for redelivery.

    Args:
        request: BatchUpdateEventRequest containing list of event updates
        http_request: FastAPI Request object for authorization context
        db_client: DynamoDB client (injected via dependency)
        sqs_client: SQS client for queuing redelivery

    Returns:
        BatchUpdateResponse with detailed per-item results and summary

    Raises:
        HTTPException: 400 if batch validation fails
        HTTPException: 500 if critical system error occurs

    Example:
        PATCH /events/batch
        {
          "events": [
            {
              "event_id": "evt_abc123xyz456",
              "payload": {"order_id": "12345", "amount": 150.00},
              "metadata": {"updated": true}
            },
            {
              "event_id": "evt_def789uvw012",
              "idempotency_key": "order-67890-2024-01-15"
            }
          ]
        }

        Response (200 OK):
        {
          "results": [
            {
              "index": 0,
              "success": true,
              "event": {
                "event_id": "evt_abc123xyz456",
                "status": "pending",
                "created_at": "2024-01-15T10:30:01Z",
                "message": "Event updated and queued for redelivery"
              }
            },
            {
              "index": 1,
              "success": false,
              "error": {
                "code": "FORBIDDEN",
                "message": "You can only update your own events"
              }
            }
          ],
          "summary": {
            "total": 2,
            "successful": 1,
            "failed": 1
          }
        }
    """
    try:
        # Get user_id from auth context
        user_id = get_user_id_from_request(http_request)

        # Check if this is filter mode or list mode
        is_filter_mode = request.events is None
        
        if is_filter_mode:
            # Filter mode: Parse query parameters and get matching events
            query_params = dict(http_request.query_params)
            filters = parse_filter_params(query_params)
            
            if not filters and 'status' not in query_params:
                raise ValueError(
                    "Filter mode requires at least one query parameter filter "
                    "(e.g., ?payload.field=value or ?status=pending)"
                )
            
            logger.info(
                "Starting filtered batch update",
                filters=bool(filters),
                status_filter=query_params.get('status'),
                user_id=user_id
            )
            
            # Get matching events (up to 100)
            matching_events = await db_client.list_events(
                status=query_params.get('status'),
                limit=100,
                cursor=None,
                filters=filters
            )
            
            # Build batch update items from filter results, filtering by user_id for ownership
            from models.request import BatchUpdateEventItem
            batch_items = []
            for event in matching_events:
                # Skip events that don't belong to this user (if auth is enabled)
                if user_id is not None and event.user_id != user_id:
                    continue
                item = BatchUpdateEventItem(
                    event_id=event.event_id,
                    payload=request.payload,
                    metadata=request.metadata,
                    idempotency_key=request.idempotency_key
                )
                batch_items.append(item)
            
            if not batch_items:
                # No events matched the filter (after user filtering)
                logger.info("No events matched the filter criteria for this user")
                return BatchUpdateResponse(
                    results=[],
                    summary=BatchOperationSummary(
                        total=0,
                        successful=0,
                        idempotent=0,
                        failed=0
                    )
                )
            
            logger.info(
                "Filtered batch update found matching events",
                matched_count=len(batch_items)
            )
        else:
            # List mode: Use provided events list
            batch_items = request.events
            
            # Validate batch size
            from utils.batch_helpers import validate_batch_size
            validate_batch_size(batch_items, 100)
            
            logger.info(
                "Starting batch update",
                batch_size=len(batch_items),
                user_id=user_id
            )

        results: List[BatchUpdateItemResult] = []

        # Extract all event_ids for batch retrieval
        event_ids = [item.event_id for item in batch_items]

        # Batch get existing events from DynamoDB
        existing_events = await db_client.batch_get_events(event_ids)
        events_by_id = {event.event_id: event for event in existing_events}

        # Process each update in the batch
        events_to_update: List[Event] = []
        index_map: Dict[str, int] = {}  # event_id -> original index

        for idx, item in enumerate(batch_items):
            try:
                # Check if event exists
                event = events_by_id.get(item.event_id)
                if not event:
                    results.append(BatchUpdateItemResult(
                        index=idx,
                        success=False,
                        error=BatchItemError(
                            code="NOT_FOUND",
                            message=f"Event {item.event_id} not found"
                        )
                    ))
                    continue

                # Verify ownership (only check if auth is enabled and user_id is set)
                if user_id is not None and event.user_id != user_id:
                    logger.warning(
                        "Unauthorized batch event update attempt",
                        event_id=item.event_id,
                        requested_by=user_id,
                        event_owner=event.user_id,
                        index=idx
                    )
                    results.append(BatchUpdateItemResult(
                        index=idx,
                        success=False,
                        error=BatchItemError(
                            code="FORBIDDEN",
                            message="You can only update your own events"
                        )
                    ))
                    continue

                # Check which fields were explicitly provided
                provided_fields = item.model_dump(exclude_unset=True)

                # Validate at least one field is provided
                update_fields = []
                if 'payload' in provided_fields:
                    if item.payload is not None:
                        event.payload = item.payload
                        update_fields.append("payload")
                    else:
                        results.append(BatchUpdateItemResult(
                            index=idx,
                            success=False,
                            error=BatchItemError(
                                code="VALIDATION_ERROR",
                                message="payload cannot be null"
                            )
                        ))
                        continue

                if 'metadata' in provided_fields:
                    # metadata can be set to None to remove it
                    event.metadata = item.metadata
                    update_fields.append("metadata")

                if 'idempotency_key' in provided_fields:
                    # idempotency_key can be set to None to remove it
                    event.idempotency_key = item.idempotency_key
                    if item.idempotency_key is None:
                        update_fields.append("idempotency_key (removed)")
                    else:
                        update_fields.append("idempotency_key")

                # Validate that at least one field was provided
                if not update_fields:
                    results.append(BatchUpdateItemResult(
                        index=idx,
                        success=False,
                        error=BatchItemError(
                            code="VALIDATION_ERROR",
                            message="At least one of payload, metadata, or idempotency_key must be provided"
                        )
                    ))
                    continue

                # Smart status handling for redelivery
                previous_status = event.status
                should_redeliver = event.status in ["delivered", "replayed"]
                if should_redeliver:
                    # Reset to pending for redelivery
                    event.status = "pending"
                    event.delivered_at = None

                    logger.info(
                        "Event updated and reset for redelivery",
                        event_id=event.event_id,
                        previous_status=previous_status,
                        updated_fields=update_fields,
                        index=idx
                    )

                    # Queue to SQS for immediate redelivery
                    try:
                        await sqs_client.send_message(
                            event_id=event.event_id,
                            event_data=event.model_dump(mode='json')
                        )
                        logger.info("Updated event queued for redelivery", event_id=event.event_id)
                    except Exception as queue_error:
                        logger.error(
                            "Failed to queue updated event for redelivery",
                            event_id=event.event_id,
                            error=str(queue_error)
                        )
                        # Don't fail the update, just log the error
                else:
                    logger.info(
                        "Event updated without status change",
                        event_id=event.event_id,
                        status=event.status,
                        updated_fields=update_fields,
                        index=idx
                    )

                # Add to batch update list
                events_to_update.append(event)
                index_map[event.event_id] = idx

            except Exception as e:
                # Unexpected error for this item
                logger.warning(
                    "Failed to process event update in batch",
                    event_id=item.event_id,
                    index=idx,
                    error=str(e)
                )

                results.append(BatchUpdateItemResult(
                    index=idx,
                    success=False,
                    error=BatchItemError(
                        code="VALIDATION_ERROR",
                        message=str(e)
                    )
                ))

        # Batch update events in DynamoDB (using individual put_item for now)
        # Note: In a production system, you might want to add a batch_update_events method
        successful_event_ids = []
        for event in events_to_update:
            try:
                await db_client.update_event(event)
                successful_event_ids.append(event.event_id)
                logger.info(
                    "Event updated in batch",
                    event_id=event.event_id,
                    status=event.status
                )
            except Exception as e:
                logger.error(
                    "Failed to update event in DynamoDB batch",
                    event_id=event.event_id,
                    error=str(e)
                )
                # Mark as failed
                original_idx = index_map[event.event_id]
                results.append(BatchUpdateItemResult(
                    index=original_idx,
                    success=False,
                    error=BatchItemError(
                        code="STORAGE_ERROR",
                        message=f"Failed to update event: {str(e)}"
                    )
                ))

        # Build final results for successful updates
        for event in events_to_update:
            if event.event_id in successful_event_ids:
                original_idx = index_map[event.event_id]

                message = "Event updated"
                if event.status == "pending":
                    message += " and queued for redelivery"
                else:
                    message += " successfully"

                event_response = EventResponse(
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
                    message=message
                )

                results.append(BatchUpdateItemResult(
                    index=original_idx,
                    success=True,
                    event=event_response
                ))

        # Sort results by original index
        results.sort(key=lambda r: r.index)

        # Calculate summary
        successful_count = sum(1 for r in results if r.success)
        failed_count = len(results) - successful_count

        summary = BatchOperationSummary(
            total=len(results),
            successful=successful_count,
            idempotent=0,  # Not applicable for updates
            failed=failed_count
        )

        # Publish batch metrics
        try:
            metrics_client.put_metric(
                metric_name="BatchUpdateEvents",
                value=1.0,
                dimensions={"BatchSize": str(len(batch_items))}
            )
        except Exception:
            pass

        logger.info(
            "Batch update completed",
            total=len(results),
            successful=successful_count,
            failed=failed_count,
            user_id=user_id,
            filter_mode=is_filter_mode
        )

        return BatchUpdateResponse(
            results=results,
            summary=summary
        )

    except ValueError as e:
        # Batch validation error
        logger.warning(
            "Batch update validation failed",
            error=str(e),
            batch_size=len(getattr(request, 'events', []))
        )
        raise HTTPException(
            status_code=status_codes.HTTP_400_BAD_REQUEST,
            detail=f"Invalid batch request: {str(e)}"
        )

    except Exception as e:
        # Critical system error
        logger.error(
            "Critical error in batch update",
            error=str(e),
            batch_size=len(getattr(request, 'events', []))
        )
        raise HTTPException(
            status_code=status_codes.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process batch update request"
        )


@router.delete("/batch", response_model=BatchDeleteResponse)
async def batch_delete_events(
    request: BatchDeleteEventRequest,
    http_request: Request,
    db_client: DynamoDBClient = Depends(get_db_client),
    metrics_client: MetricsClient = Depends(get_metrics_client)
) -> BatchDeleteResponse:
    """
    Delete multiple events in a single batch operation.

    Processes event deletions with best-effort semantics - continues processing
    even if some deletions fail. Enforces ownership checks for security.
    Missing events are treated as successful (idempotent delete).

    Args:
        request: BatchDeleteEventRequest containing list of event IDs to delete
        http_request: FastAPI Request object for authorization context
        db_client: DynamoDB client (injected via dependency)

    Returns:
        BatchDeleteResponse with detailed per-item results and summary

    Raises:
        HTTPException: 400 if batch validation fails
        HTTPException: 500 if critical system error occurs

    Example:
        DELETE /events/batch
        {
          "event_ids": [
            "evt_abc123xyz456",
            "evt_def789uvw012"
          ]
        }

        Response (200 OK):
        {
          "results": [
            {
              "index": 0,
              "success": true,
              "event_id": "evt_abc123xyz456",
              "message": "Event deleted"
            },
            {
              "index": 1,
              "success": false,
              "event_id": "evt_def789uvw012",
              "error": {
                "code": "FORBIDDEN",
                "message": "You can only delete your own events"
              }
            }
          ],
          "summary": {
            "total": 2,
            "successful": 1,
            "failed": 1
          }
        }
    """
    try:
        # Get user_id from auth context
        user_id = get_user_id_from_request(http_request)

        # Parse query parameters for filter mode
        query_params = dict(http_request.query_params)
        filters = parse_filter_params(query_params)
        has_filters = bool(filters) or 'status' in query_params
        
        # Collect event IDs from both filters and request body
        event_ids_set = set()
        
        if has_filters:
            # Filter mode: Get matching events
            logger.info(
                "Starting filtered batch delete",
                filters=bool(filters),
                status_filter=query_params.get('status'),
                has_body_event_ids=request.event_ids is not None,
                user_id=user_id
            )
            
            # Get matching events (up to 100)
            matching_events = await db_client.list_events(
                status=query_params.get('status'),
                limit=100,
                cursor=None,
                filters=filters
            )
            
            logger.info(
                "list_events returned results for filtered batch delete",
                count=len(matching_events),
                event_ids=[e.event_id for e in matching_events] if matching_events else []
            )
            
            # Add filtered event IDs to the set, filtering by user_id for ownership
            for event in matching_events:
                # Skip events that don't belong to this user (if auth is enabled)
                if user_id is not None and event.user_id != user_id:
                    logger.debug(
                        "Skipping event from different user in filtered batch delete",
                        event_id=event.event_id,
                        event_user=event.user_id,
                        requested_by=user_id
                    )
                    continue
                
                # Defensive check: skip events with missing critical fields
                if not event.event_id or not hasattr(event, 'payload'):
                    logger.warning(
                        "Skipping malformed event in filtered batch delete",
                        event_id=getattr(event, 'event_id', 'UNKNOWN'),
                        has_payload=hasattr(event, 'payload')
                    )
                    continue
                    
                event_ids_set.add(event.event_id)
                logger.debug(
                    "Added event to filtered batch delete",
                    event_id=event.event_id,
                    event_type=getattr(event, 'event_type', 'UNKNOWN')
                )
            
            logger.info(
                "Filtered batch delete found matching events",
                matched_count=len(event_ids_set)
            )
        
        # Add event IDs from request body if provided (union with filtered results)
        if request.event_ids:
            event_ids_set.update(request.event_ids)
            logger.info(
                "Combined filter results with body event_ids",
                total_count=len(event_ids_set)
            )
        
        # Check if we have any event IDs to delete
        if not event_ids_set:
            if has_filters:
                # No events matched the filter
                logger.info("No events matched the filter criteria")
                return BatchDeleteResponse(
                    results=[],
                    summary=BatchOperationSummary(
                        total=0,
                        successful=0,
                        idempotent=0,
                        failed=0
                    )
                )
            else:
                # No filters and no event_ids in body
                raise ValueError(
                    "Either provide event_ids in the request body or use query parameter filters "
                    "(e.g., ?payload.field=value or ?status=pending)"
                )
        
        # Convert to list and enforce batch size limit
        event_ids_list = list(event_ids_set)[:100]  # Cap at 100 events
        
        if len(event_ids_set) > 100:
            logger.warning(
                "Batch delete exceeded 100 events, capping at 100",
                requested_count=len(event_ids_set)
            )
        
        logger.info(
            "Starting batch delete",
            batch_size=len(event_ids_list),
            user_id=user_id,
            filter_mode=has_filters
        )

        results: List[BatchDeleteItemResult] = []

        # Batch get existing events from DynamoDB to check ownership
        existing_events = await db_client.batch_get_events(event_ids_list)
        events_by_id = {event.event_id: event for event in existing_events}
        
        # Check for events that were in list_events but not in batch_get_events (stale index)
        missing_event_ids = set(event_ids_list) - set(events_by_id.keys())
        if missing_event_ids:
            logger.warning(
                "Events from list_events not found in batch_get_events (stale index or concurrent deletion)",
                count=len(missing_event_ids),
                event_ids=list(missing_event_ids),
                note="These will be treated as idempotent deletes"
            )

        # Process each deletion in the batch
        event_ids_to_delete = []

        for idx, event_id in enumerate(event_ids_list):
            try:
                # Check if event exists
                event = events_by_id.get(event_id)
                if not event:
                    # Event doesn't exist - idempotent delete (already deleted)
                    logger.info(
                        "Delete requested for non-existent event (idempotent)",
                        event_id=event_id,
                        index=idx,
                        requested_by=user_id
                    )
                    results.append(BatchDeleteItemResult(
                        index=idx,
                        success=True,
                        event_id=event_id,
                        message="Event already deleted (idempotent)"
                    ))
                    continue

                # Verify ownership (only check if auth is enabled and user_id is set)
                if user_id is not None and event.user_id != user_id:
                    logger.warning(
                        "Unauthorized batch event delete attempt",
                        event_id=event_id,
                        requested_by=user_id,
                        event_owner=event.user_id,
                        index=idx
                    )
                    results.append(BatchDeleteItemResult(
                        index=idx,
                        success=False,
                        event_id=event_id,
                        error=BatchItemError(
                            code="FORBIDDEN",
                            message="You can only delete your own events"
                        )
                    ))
                    continue

                # Add to deletion list
                event_ids_to_delete.append(event_id)
                logger.info(
                    "Event marked for batch deletion",
                    event_id=event_id,
                    event_type=event.event_type,
                    index=idx
                )

            except Exception as e:
                # Unexpected error for this item
                logger.warning(
                    "Failed to process event deletion in batch",
                    event_id=event_id,
                    index=idx,
                    error=str(e)
                )

                results.append(BatchDeleteItemResult(
                    index=idx,
                    success=False,
                    event_id=event_id,
                    error=BatchItemError(
                        code="VALIDATION_ERROR",
                        message=str(e)
                    )
                ))

        # Batch delete events from DynamoDB
        successful_event_ids = []
        if event_ids_to_delete:
            batch_result = await db_client.batch_delete_events(event_ids_to_delete)
            successful_event_ids = batch_result["successful_event_ids"]

            # Process failed deletions
            failed_event_ids = batch_result["failed_event_ids"]
            for failed_event_id in failed_event_ids:
                # Find original index for this event_id
                original_idx = None
                for idx, event_id in enumerate(event_ids_list):
                    if event_id == failed_event_id:
                        original_idx = idx
                        break

                if original_idx is not None:
                    results.append(BatchDeleteItemResult(
                        index=original_idx,
                        success=False,
                        event_id=failed_event_id,
                        error=BatchItemError(
                            code="STORAGE_ERROR",
                            message="Failed to delete event from database"
                        )
                    ))

        # Build final results for successful deletions
        for event_id in event_ids_to_delete:
            if event_id in successful_event_ids:
                # Find original index for this event_id
                original_idx = None
                for idx, req_event_id in enumerate(event_ids_list):
                    if req_event_id == event_id:
                        original_idx = idx
                        break

                if original_idx is not None:
                    results.append(BatchDeleteItemResult(
                        index=original_idx,
                        success=True,
                        event_id=event_id,
                        message="Event deleted"
                    ))

                    logger.info(
                        "Event deleted successfully in batch",
                        event_id=event_id,
                        index=original_idx
                    )

        # Sort results by original index
        results.sort(key=lambda r: r.index)

        # Calculate summary
        successful_count = sum(1 for r in results if r.success)
        failed_count = len(results) - successful_count
        # Count idempotent deletions (events that were already deleted)
        idempotent_count = sum(1 for r in results if r.success and r.message == "Event already deleted (idempotent)")

        summary = BatchOperationSummary(
            total=len(results),
            successful=successful_count,
            idempotent=idempotent_count,
            failed=failed_count
        )

        # Publish batch metrics
        try:
            metrics_client.put_metric(
                metric_name="BatchDeleteEvents",
                value=1.0,
                dimensions={"BatchSize": str(len(event_ids_list))}
            )
        except Exception:
            pass

        logger.info(
            "Batch delete completed",
            total=len(results),
            successful=successful_count,
            idempotent=idempotent_count,
            failed=failed_count,
            user_id=user_id,
            filter_mode=has_filters
        )

        return BatchDeleteResponse(
            results=results,
            summary=summary
        )

    except ValueError as e:
        # Batch validation error
        logger.warning(
            "Batch delete validation failed",
            error=str(e),
            batch_size=len(getattr(request, 'event_ids', []))
        )
        raise HTTPException(
            status_code=status_codes.HTTP_400_BAD_REQUEST,
            detail=f"Invalid batch request: {str(e)}"
        )

    except Exception as e:
        # Critical system error
        logger.error(
            "Critical error in batch delete",
            error=str(e),
            batch_size=len(getattr(request, 'event_ids', []))
        )
        raise HTTPException(
            status_code=status_codes.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process batch delete request"
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


@router.post("/list", response_model=List[EventResponse])
async def get_events_by_list(
    request_body: GetEventsByListRequest,
    db_client: DynamoDBClient = Depends(get_db_client)
) -> List[EventResponse]:
    """
    Retrieve multiple events by providing a list of event IDs.

    Fetches multiple events from DynamoDB in a single batch request.
    Events that don't exist are silently omitted from the results.

    Args:
        request_body: Request containing list of event_ids to retrieve
        db_client: DynamoDB client (injected via dependency)

    Returns:
        List of EventResponse objects for found events

    Raises:
        HTTPException: 400 if invalid request parameters
        HTTPException: 500 if database error

    Example:
        POST /events/list
        Body: {"event_ids": ["evt_abc123xyz456", "evt_def789ghi012"]}

        Response (200):
        [
            {
                "event_id": "evt_abc123xyz456",
                "status": "delivered",
                "created_at": "2024-01-15T10:30:01Z",
                "delivered_at": "2024-01-15T10:30:02Z",
                "message": "Event retrieved successfully"
            },
            {
                "event_id": "evt_def789ghi012",
                "status": "pending",
                "created_at": "2024-01-15T10:31:00Z",
                "message": "Event retrieved successfully"
            }
        ]
    """
    try:
        # Use the existing batch_get_events method which handles chunking
        events = await db_client.batch_get_events(request_body.event_ids)
        
        logger.info(
            "Retrieved events by list",
            requested_count=len(request_body.event_ids),
            found_count=len(events)
        )
        
        # Convert Event objects to EventResponse objects
        response_events = [
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
        
        return response_events
        
    except ValueError as e:
        logger.warning("Invalid request for get_events_by_list", error=str(e))
        raise HTTPException(
            status_code=status_codes.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Database error retrieving events by list", error=str(e))
        raise HTTPException(
            status_code=status_codes.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve events"
        )


@router.get("", response_model=List[EventResponse])
async def list_events(
    request: Request,
    status: Optional[str] = None,
    limit: int = 50,
    cursor: Optional[str] = None,
    db_client: DynamoDBClient = Depends(get_db_client)
) -> List[EventResponse]:
    """
    List events with advanced filtering and pagination.

    Returns a paginated list of events with support for complex filtering by
    payload fields, metadata, dates, and various comparison operators.

    Supports filtering operators: eq (default), gt, gte, lt, lte, ne, contains, startswith
    Special date filters: created_after, created_before, delivered_after, delivered_before

    Args:
        request: FastAPI Request object for accessing all query parameters
        status: Optional status filter (pending, delivered, failed, replayed)
        limit: Maximum number of events to return (default 50, max 100)
        cursor: Pagination cursor from previous response (not supported with custom filters)
        db_client: DynamoDB client (injected via dependency)

    Returns:
        List of EventResponse objects

    Raises:
        HTTPException: 400 if invalid parameters
        HTTPException: 500 if database error

    Examples:
        GET /events?status=pending&limit=10

        GET /events?payload.order_id=12345

        GET /events?metadata.source=ecommerce&payload.amount[gte]=100

        GET /events?created_after=2024-01-15T00:00:00Z&payload.customer.email[contains]=gmail

        Response (200):
        [
            {
                "event_id": "evt_abc123xyz456",
                "status": "delivered",
                "created_at": "2024-01-15T10:30:01Z",
                "delivered_at": "2024-01-15T10:30:02Z",
                "message": "Event retrieved successfully"
            }
        ]
    """
    if limit > 100:
        raise HTTPException(
            status_code=status_codes.HTTP_400_BAD_REQUEST,
            detail="Limit cannot exceed 100"
        )

    # Parse filter parameters from query string
    query_params = dict(request.query_params)
    filters = parse_filter_params(query_params)

    try:
        events = await db_client.list_events(
            status=status,
            limit=limit,
            cursor=cursor,
            filters=filters
        )
    except Exception as e:
        logger.error("Database error listing events", error=str(e), filters=bool(filters))
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


@router.patch("/{event_id}", response_model=EventResponse)
async def update_event(
    event_id: str,
    request: UpdateEventRequest,
    http_request: Request,
    db_client: DynamoDBClient = Depends(get_db_client),
    sqs_client: SQSClient = Depends(get_sqs_client)
) -> EventResponse:
    """
    Update an event's payload, metadata, and/or idempotency_key.

    Updates only the provided fields (payload, metadata, and/or idempotency_key).
    For delivered/replayed events, resets status to "pending" and queues for redelivery.
    
    To remove idempotency_key, set it to null in the request.

    Args:
        event_id: Unique event identifier
        request: UpdateEventRequest containing fields to update
        http_request: FastAPI Request object for authorization context
        db_client: DynamoDB client (injected via dependency)
        sqs_client: SQS client for queuing redelivery

    Returns:
        EventResponse with updated event details

    Raises:
        HTTPException: 400 if no fields provided or invalid data, 403 if user not authorized, 
                       404 if event not found, 500 if database error

    Example:
        # Update payload and metadata
        PATCH /events/evt_abc123xyz456
        {
            "payload": {"order_id": "12345", "amount": 150.00},
            "metadata": {"updated": true}
        }

        # Add or update idempotency_key
        PATCH /events/evt_abc123xyz456
        {
            "idempotency_key": "order-12345-2024-01-15"
        }

        # Remove idempotency_key
        PATCH /events/evt_abc123xyz456
        {
            "idempotency_key": null
        }

        Response (200):
        {
            "event_id": "evt_abc123xyz456",
            "status": "pending",
            "created_at": "2024-01-15T10:30:01Z",
            "idempotency_key": "order-12345-2024-01-15",
            "message": "Event updated and queued for redelivery"
        }
    """
    try:
        # Get user_id from authorizer context
        user_id = get_user_id_from_request(http_request)

        # Fetch existing event
        event = await db_client.get_event(event_id)
        if not event:
            raise HTTPException(
                status_code=status_codes.HTTP_404_NOT_FOUND,
                detail=f"Event {event_id} not found"
            )

        # Verify ownership (only check if auth is enabled and user_id is set)
        if user_id is not None and event.user_id != user_id:
            logger.warning(
                "Unauthorized event update attempt",
                event_id=event_id,
                requested_by=user_id,
                event_owner=event.user_id
            )
            raise HTTPException(
                status_code=status_codes.HTTP_403_FORBIDDEN,
                detail="You can only update your own events"
            )

        # Check which fields were explicitly provided in the request
        # This allows us to distinguish between "not provided" and "explicitly set to None"
        provided_fields = request.model_dump(exclude_unset=True)
        
        # Validate that at least one field was provided
        if not provided_fields:
            raise HTTPException(
                status_code=status_codes.HTTP_400_BAD_REQUEST,
                detail="At least one of payload, metadata, or idempotency_key must be provided"
            )

        # Update the provided fields
        updated_fields = []
        if 'payload' in provided_fields:
            if request.payload is not None:
                event.payload = request.payload
                updated_fields.append("payload")
            else:
                raise HTTPException(
                    status_code=status_codes.HTTP_400_BAD_REQUEST,
                    detail="payload cannot be null"
                )
        
        if 'metadata' in provided_fields:
            # metadata can be set to None to remove it
            event.metadata = request.metadata
            updated_fields.append("metadata")
        
        if 'idempotency_key' in provided_fields:
            # idempotency_key can be set to None to remove it
            event.idempotency_key = request.idempotency_key
            if request.idempotency_key is None:
                updated_fields.append("idempotency_key (removed)")
            else:
                updated_fields.append("idempotency_key")

        # Smart status handling for redelivery
        previous_status = event.status
        should_redeliver = event.status in ["delivered", "replayed"]
        if should_redeliver:
            # Reset to pending for redelivery
            event.status = "pending"
            event.delivered_at = None

            logger.info(
                "Event updated and reset for redelivery",
                event_id=event_id,
                previous_status=previous_status,
                updated_fields=updated_fields
            )

            # Queue to SQS for immediate redelivery
            try:
                await sqs_client.send_message(
                    event_id=event_id,
                    event_data=event.model_dump(mode='json')
                )
                logger.info("Updated event queued for redelivery", event_id=event_id)
            except Exception as queue_error:
                logger.error(
                    "Failed to queue updated event for redelivery",
                    event_id=event_id,
                    error=str(queue_error)
                )
                # Don't fail the update, just log the error
        else:
            logger.info(
                "Event updated without status change",
                event_id=event_id,
                status=event.status,
                updated_fields=updated_fields
            )

        # Save updated event
        await db_client.update_event(event)

        message = "Event updated"
        if should_redeliver:
            message += " and queued for redelivery"
        else:
            message += " successfully"

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
            message=message
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to update event",
            event_id=event_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status_codes.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update event"
        )


@router.delete("/{event_id}")
async def delete_event(
    event_id: str,
    http_request: Request,
    db_client: DynamoDBClient = Depends(get_db_client)
) -> Response:
    """
    Delete an event.

    Permanently removes an event from the system.
    Only the event owner can delete their events.
    Idempotent: returns 204 if event already deleted.

    Args:
        event_id: Unique event identifier to delete
        http_request: FastAPI Request object for authorization context
        db_client: DynamoDB client (injected via dependency)

    Returns:
        Response: 200 OK if deleted, 204 No Content if already deleted (idempotent)

    Raises:
        HTTPException: 403 if user not authorized, 500 if database error

    Example:
        DELETE /events/evt_abc123xyz456

        Response (200): Event deleted successfully
        Response (204): Event already deleted (idempotent)
    """
    try:
        # Get user_id from authorizer context
        user_id = get_user_id_from_request(http_request)

        # Fetch existing event
        event = await db_client.get_event(event_id)
        if not event:
            # Event doesn't exist - idempotent delete (already deleted)
            logger.info(
                "Delete requested for non-existent event (idempotent)",
                event_id=event_id,
                requested_by=user_id
            )
            return Response(status_code=status_codes.HTTP_204_NO_CONTENT)

        # Verify ownership (only check if auth is enabled and user_id is set)
        if user_id is not None and event.user_id != user_id:
            logger.warning(
                "Unauthorized event delete attempt",
                event_id=event_id,
                requested_by=user_id,
                event_owner=event.user_id
            )
            raise HTTPException(
                status_code=status_codes.HTTP_403_FORBIDDEN,
                detail="You can only delete your own events"
            )

        # Delete the event
        await db_client.delete_event(event_id)

        logger.info(
            "Event deleted successfully",
            event_id=event_id,
            event_type=event.event_type,
            deleted_by=user_id
        )

        # Return 200 OK for successful deletion
        return Response(status_code=status_codes.HTTP_200_OK)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to delete event",
            event_id=event_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status_codes.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete event"
        )


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


# Create a separate router for replay endpoints
replay_router = APIRouter(prefix="/replay", tags=["replay"])

@replay_router.post("/batch", response_model=BatchReplayResponse)
async def batch_replay_events(
    http_request: Request,
    request: BatchReplayEventRequest = BatchReplayEventRequest(),
    db_client: DynamoDBClient = Depends(get_db_client),
    delivery_client: PushDeliveryClient = Depends(get_delivery_client),
    sqs_client: SQSClient = Depends(get_sqs_client)
) -> BatchReplayResponse:
    """
    Replay multiple events in a single batch operation.
    
    Supports two modes:
    1. List mode: Provide event_ids in request body
    2. Filter mode: Use query parameters to filter events
    
    Processes event replays with best-effort semantics - continues processing
    even if some replays fail. Enforces ownership checks for security.
    
    Args:
        request: BatchReplayEventRequest containing list of event IDs and replay params
        http_request: FastAPI Request object for query params and authorization context
        db_client: DynamoDB client (injected via dependency)
        delivery_client: Push delivery client (injected via dependency)
        sqs_client: SQS client (injected via dependency)
        
    Returns:
        BatchReplayResponse with detailed per-item results and summary
        
    Raises:
        HTTPException: 400 if batch validation fails
        HTTPException: 500 if critical system error occurs
        
    Example (List Mode):
        POST /replay/batch
        {
          "event_ids": ["evt_abc123xyz456", "evt_def789uvw012"]
        }
        
    Example (Filter Mode):
        POST /replay/batch?status=failed&payload.error_type=timeout
        
    Example (Combined Mode - union of filters and body):
        POST /replay/batch?status=failed
        {
          "event_ids": ["evt_abc123xyz456"]
        }
    """
    try:
        # Get user_id from auth context
        user_id = get_user_id_from_request(http_request)
        
        # Parse query parameters for filter mode
        query_params = dict(http_request.query_params)
        filters = parse_filter_params(query_params)
        has_filters = bool(filters) or 'status' in query_params
        
        # Collect event IDs from both filters and request body
        event_ids_set = set()
        
        if has_filters:
            # Filter mode: Get matching events
            logger.info(
                "Starting filtered batch replay",
                filters=bool(filters),
                status_filter=query_params.get('status'),
                has_body_event_ids=request.event_ids is not None,
                user_id=user_id
            )
            
            # Get matching events (up to 100)
            matching_events = await db_client.list_events(
                status=query_params.get('status'),
                limit=100,
                cursor=None,
                filters=filters
            )
            
            logger.info(
                "list_events returned results for filtered batch replay",
                count=len(matching_events),
                event_ids=[e.event_id for e in matching_events] if matching_events else []
            )
            
            # Add filtered event IDs to the set, filtering by user_id for ownership
            for event in matching_events:
                # Skip events that don't belong to this user (if auth is enabled)
                if user_id is not None and event.user_id != user_id:
                    logger.debug(
                        "Skipping event from different user in filtered batch replay",
                        event_id=event.event_id,
                        event_user=event.user_id,
                        requested_by=user_id
                    )
                    continue
                
                # Defensive check: skip events with missing critical fields
                if not event.event_id or not hasattr(event, 'payload'):
                    logger.warning(
                        "Skipping malformed event in filtered batch replay",
                        event_id=getattr(event, 'event_id', 'UNKNOWN'),
                        has_payload=hasattr(event, 'payload')
                    )
                    continue
                    
                event_ids_set.add(event.event_id)
                logger.debug(
                    "Added event to filtered batch replay",
                    event_id=event.event_id,
                    event_type=getattr(event, 'event_type', 'UNKNOWN')
                )
            
            logger.info(
                "Filtered batch replay found matching events",
                matched_count=len(event_ids_set)
            )
        
        # Add event IDs from request body if provided (union with filtered results)
        if request.event_ids:
            event_ids_set.update(request.event_ids)
            logger.info(
                "Combined filter results with body event_ids",
                total_count=len(event_ids_set)
            )
        
        # Check if we have any event IDs to replay
        if not event_ids_set:
            if has_filters:
                # No events matched the filter
                logger.info("No events matched the filter criteria for replay")
                return BatchReplayResponse(
                    results=[],
                    summary=BatchOperationSummary(
                        total=0,
                        successful=0,
                        idempotent=0,
                        failed=0
                    )
                )
            else:
                # No event IDs provided and no filters
                raise HTTPException(
                    status_code=status_codes.HTTP_400_BAD_REQUEST,
                    detail="Either provide event_ids or use query parameters to filter events"
                )
        
        # Convert to list and cap at 100
        event_ids = list(event_ids_set)[:100]
        
        if len(event_ids_set) > 100:
            logger.warning(
                "Batch replay size exceeded 100, capped",
                requested=len(event_ids_set),
                processed=100
            )
        
        logger.info(
            "Starting batch replay",
            batch_size=len(event_ids),
            user_id=user_id
        )
        
        results: List[BatchReplayItemResult] = []
        
        # Batch get existing events from DynamoDB
        existing_events = await db_client.batch_get_events(event_ids)
        events_by_id = {event.event_id: event for event in existing_events}
        
        # Process each replay in the batch
        successful = 0
        failed = 0
        
        for idx, event_id in enumerate(event_ids):
            try:
                # Check if event exists
                event = events_by_id.get(event_id)
                if not event:
                    results.append(BatchReplayItemResult(
                        index=idx,
                        success=False,
                        event_id=event_id,
                        status="failed",
                        message="Event not found",
                        error=BatchItemError(
                            code="NOT_FOUND",
                            message="Event not found"
                        )
                    ))
                    failed += 1
                    continue
                
                # Check ownership
                if user_id is not None and event.user_id != user_id:
                    results.append(BatchReplayItemResult(
                        index=idx,
                        success=False,
                        event_id=event_id,
                        status="failed",
                        message="You can only replay your own events",
                        error=BatchItemError(
                            code="FORBIDDEN",
                            message="You can only replay your own events"
                        )
                    ))
                    failed += 1
                    continue
                
                # Check replay limits
                if event.delivery_attempts >= 10:
                    results.append(BatchReplayItemResult(
                        index=idx,
                        success=False,
                        event_id=event_id,
                        status="failed",
                        message="Event has exceeded maximum replay attempts (10)",
                        error=BatchItemError(
                            code="MAX_ATTEMPTS_EXCEEDED",
                            message="Event has exceeded maximum replay attempts (10)"
                        )
                    ))
                    failed += 1
                    continue
                
                # Add replay metadata
                replay_metadata = {
                    'is_replay': True,
                    'replayed_at': datetime.now(timezone.utc).isoformat(),
                    'replay_reason': 'batch_replay',
                    'original_created_at': event.created_at.isoformat(),
                    'original_status': event.status
                }
                
                # Merge with existing metadata
                if event.metadata:
                    event.metadata.update(replay_metadata)
                else:
                    event.metadata = replay_metadata
                
                # Attempt immediate delivery
                delivery_success = await delivery_client.deliver_event(event)
                
                if delivery_success:
                    # Update replay status
                    event.status = "replayed"
                    event.delivery_attempts += 1
                    event.delivered_at = datetime.now(timezone.utc)
                    await db_client.update_event(event)
                    
                    results.append(BatchReplayItemResult(
                        index=idx,
                        success=True,
                        event_id=event_id,
                        status="replayed",
                        message="Event replayed successfully"
                    ))
                    successful += 1
                else:
                    # Queue for retry
                    event.status = "pending"
                    event.delivery_attempts += 1
                    await db_client.update_event(event)
                    
                    await sqs_client.send_message(
                        event_id=event_id,
                        event_data=event.model_dump(mode='json')
                    )
                    
                    results.append(BatchReplayItemResult(
                        index=idx,
                        success=True,
                        event_id=event_id,
                        status="pending",
                        message="Event replay queued for retry"
                    ))
                    successful += 1
                    
            except Exception as e:
                logger.error(
                    "Failed to replay event in batch",
                    event_id=event_id,
                    index=idx,
                    error=str(e)
                )
                results.append(BatchReplayItemResult(
                    index=idx,
                    success=False,
                    event_id=event_id,
                    status="failed",
                    message=f"Replay failed: {str(e)}",
                    error=BatchItemError(
                        code="REPLAY_FAILED",
                        message=str(e)
                    )
                ))
                failed += 1
        
        logger.info(
            "Batch replay completed",
            total=len(event_ids),
            successful=successful,
            failed=failed,
            filter_mode=has_filters
        )
        
        return BatchReplayResponse(
            results=results,
            summary=BatchOperationSummary(
                total=len(event_ids),
                successful=successful,
                idempotent=0,  # Replays are not idempotent in the same way as creates
                failed=failed
            )
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Batch replay operation failed", error=str(e))
        raise HTTPException(
            status_code=status_codes.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Batch replay operation failed"
        )



@replay_router.post("/{event_id}", response_model=ReplayResponse)
async def replay_event(
    event_id: str,
    request: Optional[ReplayEventRequest] = None,
    db_client: DynamoDBClient = Depends(get_db_client),
    delivery_client: PushDeliveryClient = Depends(get_delivery_client),
    sqs_client: SQSClient = Depends(get_sqs_client)
) -> ReplayResponse:
    """
    Replay an existing event.
    
    Re-delivers an event while preserving its original identity
    and timestamp. Adds replay metadata for tracking.
    
    Args:
        event_id: ID of event to replay
        request: Optional request body with replay parameters (reason, workflow_id)
        db_client: DynamoDB client
        delivery_client: Push delivery client
        sqs_client: SQS client
        
    Returns:
        ReplayResponse with replay status
        
    Raises:
        HTTPException: 404 if event not found
        HTTPException: 400 if event not replayable
        HTTPException: 500 if replay fails
    """
    try:
        # Retrieve original event
        event = await db_client.get_event(event_id)
        
        if not event:
            raise HTTPException(
                status_code=status_codes.HTTP_404_NOT_FOUND,
                detail=f"Event {event_id} not found"
            )
        
        # Check if event is replayable (max 10 attempts)
        if event.delivery_attempts >= 10:
            raise HTTPException(
                status_code=status_codes.HTTP_400_BAD_REQUEST,
                detail="Event has exceeded maximum replay attempts (10)"
            )
        
        # Use defaults if no request body provided
        if request is None:
            request = ReplayEventRequest()
        
        # Add replay metadata
        replay_metadata = {
            'is_replay': True,
            'replayed_at': datetime.now(timezone.utc).isoformat(),
            'replay_reason': request.reason,
            'original_created_at': event.created_at.isoformat(),
            'original_status': event.status
        }
        
        if request.workflow_id:
            replay_metadata['target_workflow_id'] = request.workflow_id
        
        # Merge with existing metadata
        if event.metadata:
            event.metadata.update(replay_metadata)
        else:
            event.metadata = replay_metadata
        
        logger.info(
            "Attempting event replay",
            event_id=event_id,
            reason=request.reason,
            workflow_id=request.workflow_id,
            current_attempts=event.delivery_attempts
        )
        
        # Attempt immediate delivery
        delivery_success = await delivery_client.deliver_event(event)
        
        if delivery_success:
            # Update replay status
            event.status = "replayed"
            event.delivery_attempts += 1
            event.delivered_at = datetime.now(timezone.utc)
            await db_client.update_event(event)
            
            logger.info(
                "Event replayed successfully",
                event_id=event_id,
                reason=request.reason,
                workflow_id=request.workflow_id,
                delivery_attempts=event.delivery_attempts
            )
            
            return ReplayResponse(
                event_id=event.event_id,
                status="replayed",
                created_at=event.created_at,
                delivered_at=event.delivered_at,
                delivery_attempts=event.delivery_attempts,
                message="Event replayed successfully"
            )
        else:
            # Queue for retry
            event.status = "pending"
            event.delivery_attempts += 1
            await db_client.update_event(event)
            
            await sqs_client.send_message(
                event_id=event_id,
                event_data=event.model_dump(mode='json')
            )
            
            logger.info(
                "Event replay queued for retry",
                event_id=event_id,
                reason=request.reason,
                delivery_attempts=event.delivery_attempts
            )
            
            return ReplayResponse(
                event_id=event.event_id,
                status="pending",
                created_at=event.created_at,
                delivered_at=None,
                delivery_attempts=event.delivery_attempts,
                message="Event replay queued for retry"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Event replay failed", event_id=event_id, error=str(e))
        raise HTTPException(
            status_code=status_codes.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Event replay failed"
        )