# Phase 2: Event Retrieval & Monitoring

## Overview

**Goal:** Implement event retrieval endpoints (GET /events, GET /events/{id}, GET /inbox) and enhance monitoring capabilities.

**Duration:** 2-3 days

**Success Criteria:**
- GET /events/{id} retrieves specific events
- GET /events lists events with filtering
- GET /inbox shows undelivered events
- CloudWatch dashboard for key metrics
- Comprehensive error handling

**Deliverable:** Full CRUD API with monitoring and observability for event lifecycle tracking.

---

## Prerequisites

- Phase 1 completed (POST /events working)
- Events stored in DynamoDB
- API key authentication functional

---

## Features & Tasks

### Feature 1: GET /events/{id} Endpoint

**Description:** Retrieve a specific event by its unique ID.

**Steps:**
1. Add GET route to `src/handlers/events.py`
2. Query DynamoDB by event_id
3. Return 404 if event not found
4. Return EventResponse with full event details
5. Add authorization check (user can only access their events)

**Validation:**
- Endpoint returns 200 OK for valid event_id
- Returns 404 for non-existent events
- Returns correct event data

**Code Addition:**
```python
@router.get("/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: str,
    db_client: DynamoDBClient = Depends(get_db_client)
) -> EventResponse:
    """
    Retrieve a specific event by ID.
    
    Args:
        event_id: Unique event identifier
        db_client: DynamoDB client
        
    Returns:
        EventResponse with event details
        
    Raises:
        HTTPException: 404 if event not found
        HTTPException: 500 if database error
    """
    try:
        event = await db_client.get_event(event_id)
    except Exception as e:
        logger.error("Database error retrieving event", event_id=event_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve event"
        )
    
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
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
        delivery_attempts=event.delivery_attempts
    )
```

---

### Feature 2: GET /events List Endpoint

**Description:** List events with pagination and optional status filtering.

**Steps:**
1. Add GET /events route for listing
2. Implement pagination with limit and cursor parameters
3. Add optional status filter query parameter
4. Query DynamoDB using GSI for status filtering
5. Return list of EventResponse objects

**Validation:**
- Returns paginated list of events
- Status filter works correctly
- Pagination handles large result sets

**Code Addition:**
```python
from typing import List, Optional

@router.get("", response_model=List[EventResponse])
async def list_events(
    status: Optional[str] = None,
    limit: int = 50,
    cursor: Optional[str] = None,
    db_client: DynamoDBClient = Depends(get_db_client)
) -> List[EventResponse]:
    """
    List events with optional filtering and pagination.
    
    Args:
        status: Optional status filter (pending, delivered, failed)
        limit: Maximum number of events to return (default 50, max 100)
        cursor: Pagination cursor from previous response
        db_client: DynamoDB client
        
    Returns:
        List of EventResponse objects
        
    Raises:
        HTTPException: 400 if invalid parameters
        HTTPException: 500 if database error
    """
    if limit > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
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
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list events"
        )
    
    return [
        EventResponse(
            event_id=event.event_id,
            event_type=event.event_type,
            status=event.status,
            created_at=event.created_at,
            delivered_at=event.delivered_at
        )
        for event in events
    ]
```

---

### Feature 3: DynamoDB Query Methods

**Description:** Extend DynamoDB client with list and query capabilities.

**Steps:**
1. Add `list_events()` method to DynamoDBClient
2. Implement query using StatusIndex GSI
3. Handle pagination with LastEvaluatedKey
4. Add scan fallback if no status filter
5. Add proper error handling and logging

**Validation:**
- Query method returns correct events
- Pagination works for large datasets
- GSI queries are efficient

**Code Addition:**
```python
async def list_events(
    self,
    status: Optional[str] = None,
    limit: int = 50,
    cursor: Optional[str] = None
) -> List[Event]:
    """
    List events with optional status filter and pagination.
    
    Args:
        status: Optional status to filter by
        limit: Maximum number of events to return
        cursor: Pagination cursor (base64-encoded last key)
        
    Returns:
        List of Event objects
        
    Raises:
        ClientError: If DynamoDB operation fails
    """
    try:
        kwargs = {'Limit': limit}
        
        # Add pagination cursor if provided
        if cursor:
            import base64
            import json
            kwargs['ExclusiveStartKey'] = json.loads(base64.b64decode(cursor))
        
        # Query by status using GSI or scan all
        if status:
            response = self.table.query(
                IndexName='StatusIndex',
                KeyConditionExpression='#status = :status',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={':status': status},
                ScanIndexForward=False,  # Most recent first
                **kwargs
            )
        else:
            response = self.table.scan(**kwargs)
        
        # Convert items to Event objects
        events = []
        for item in response.get('Items', []):
            item['created_at'] = datetime.fromisoformat(item['created_at'])
            if item.get('delivered_at'):
                item['delivered_at'] = datetime.fromisoformat(item['delivered_at'])
            events.append(Event(**item))
        
        logger.info(
            "Events listed",
            count=len(events),
            status_filter=status,
            has_more=('LastEvaluatedKey' in response)
        )
        
        return events
        
    except ClientError as e:
        logger.error("Failed to list events", error=str(e))
        raise
```

---

### Feature 4: GET /inbox Endpoint

**Description:** Implement inbox endpoint for polling undelivered events.

**Steps:**
1. Create `src/handlers/inbox.py` with router
2. Add GET /inbox route
3. Query events with status="pending" or "undelivered"
4. Return list sorted by created_at (oldest first)
5. Add limit parameter for batch retrieval

**Validation:**
- Returns only undelivered events
- Events sorted correctly (oldest first)
- Limit parameter works

**Code Template:**
```python
"""
Module: handlers/inbox.py
Description: Inbox endpoint for polling undelivered events.

Allows Zapier system to poll for events that need delivery,
implementing the pull portion of the hybrid push/pull model.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, status, Depends

from src.models.response import EventResponse
from src.storage.dynamodb import DynamoDBClient
from src.config.settings import settings
from src.utils.logger import get_logger

router = APIRouter(prefix="/inbox", tags=["inbox"])
logger = get_logger(__name__)

def get_db_client() -> DynamoDBClient:
    """Dependency to get DynamoDB client."""
    return DynamoDBClient(table_name=settings.events_table_name)

@router.get("", response_model=List[EventResponse])
async def get_inbox(
    limit: int = 100,
    db_client: DynamoDBClient = Depends(get_db_client)
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
    """
    if limit > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
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
        
        return [
            EventResponse(
                event_id=event.event_id,
                event_type=event.event_type,
                payload=event.payload,
                metadata=event.metadata,
                status=event.status,
                created_at=event.created_at,
                delivery_attempts=event.delivery_attempts
            )
            for event in pending_events
        ]
        
    except Exception as e:
        logger.error("Failed to retrieve inbox", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve inbox"
        )
```

---

### Feature 5: Event Acknowledgment Endpoint

**Description:** Allow Zapier to acknowledge successful event delivery.

**Steps:**
1. Add DELETE /events/{id} or POST /events/{id}/acknowledge endpoint
2. Update event status to "delivered"
3. Set delivered_at timestamp
4. Return 204 No Content on success
5. Log acknowledgment for audit trail

**Validation:**
- Acknowledged events update in DynamoDB
- Status changes from pending to delivered
- Endpoint returns correct status code

**Code Addition:**
```python
@router.post("/{event_id}/acknowledge", status_code=status.HTTP_204_NO_CONTENT)
async def acknowledge_event(
    event_id: str,
    db_client: DynamoDBClient = Depends(get_db_client)
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
    """
    try:
        # Get event
        event = await db_client.get_event(event_id)
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
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
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to acknowledge event", event_id=event_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to acknowledge event"
        )
```

---

### Feature 6: CloudWatch Custom Metrics

**Description:** Publish custom metrics for event ingestion and delivery.

**Steps:**
1. Create `src/utils/metrics.py` for CloudWatch metrics
2. Publish metric for event created (count)
3. Publish metric for event delivered (count)
4. Track inbox depth (gauge)
5. Track API latency (histogram)

**Validation:**
- Metrics appear in CloudWatch console
- Metrics update in real-time
- Metrics namespace is correct

**Code Template:**
```python
"""
Module: utils/metrics.py
Description: CloudWatch custom metrics publishing.

Publishes application metrics to CloudWatch for monitoring
event ingestion rates, delivery success, and API performance.
"""

import boto3
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)

class MetricsClient:
    """CloudWatch metrics client."""
    
    def __init__(self, namespace: str = "TriggersAPI"):
        """
        Initialize metrics client.
        
        Args:
            namespace: CloudWatch metrics namespace
        """
        self.namespace = namespace
        self.cloudwatch = boto3.client('cloudwatch')
    
    def put_metric(
        self,
        metric_name: str,
        value: float,
        unit: str = 'Count',
        dimensions: Optional[dict] = None
    ) -> None:
        """
        Publish a metric to CloudWatch.
        
        Args:
            metric_name: Name of the metric
            value: Metric value
            unit: Metric unit (Count, Seconds, etc.)
            dimensions: Optional metric dimensions
        """
        try:
            metric_data = {
                'MetricName': metric_name,
                'Value': value,
                'Unit': unit
            }
            
            if dimensions:
                metric_data['Dimensions'] = [
                    {'Name': k, 'Value': v}
                    for k, v in dimensions.items()
                ]
            
            self.cloudwatch.put_metric_data(
                Namespace=self.namespace,
                MetricData=[metric_data]
            )
            
        except Exception as e:
            # Don't fail request if metrics fail
            logger.warning("Failed to publish metric", metric_name=metric_name, error=str(e))
```

---

### Feature 7: CloudWatch Dashboard

**Description:** Create CloudWatch dashboard for monitoring key metrics.

**Steps:**
1. Add CloudWatch dashboard to SAM template
2. Add widgets for event ingestion rate
3. Add widgets for inbox depth over time
4. Add widgets for API latency (p50, p95, p99)
5. Add widgets for error rates

**Validation:**
- Dashboard visible in CloudWatch console
- Widgets show real-time data
- Dashboard updates automatically

**Template Addition:**
```yaml
Resources:
  MonitoringDashboard:
    Type: AWS::CloudWatch::Dashboard
    Properties:
      DashboardName: !Sub '${AWS::StackName}-monitoring'
      DashboardBody: !Sub |
        {
          "widgets": [
            {
              "type": "metric",
              "properties": {
                "metrics": [
                  ["TriggersAPI", "EventCreated", {"stat": "Sum"}],
                  [".", "EventDelivered", {"stat": "Sum"}]
                ],
                "period": 300,
                "stat": "Sum",
                "region": "${AWS::Region}",
                "title": "Event Throughput",
                "yAxis": {"left": {"min": 0}}
              }
            },
            {
              "type": "metric",
              "properties": {
                "metrics": [
                  ["AWS/Lambda", "Duration", {"stat": "Average"}],
                  ["...", {"stat": "p95"}],
                  ["...", {"stat": "p99"}]
                ],
                "period": 300,
                "stat": "Average",
                "region": "${AWS::Region}",
                "title": "API Latency"
              }
            }
          ]
        }
```

---

### Feature 8: X-Ray Tracing Integration

**Description:** Enable AWS X-Ray for distributed tracing.

**Steps:**
1. Add X-Ray tracing to Lambda functions in SAM template
2. Install aws-xray-sdk for Python
3. Patch boto3 and httpx clients for tracing
4. Add subsegments for DynamoDB operations
5. View traces in X-Ray console

**Validation:**
- Traces appear in X-Ray console
- Service map shows all components
- Subsegments show timing breakdowns

**Template Addition:**
```yaml
Globals:
  Function:
    Runtime: python3.11
    Timeout: 30
    MemorySize: 512
    Tracing: Active  # Enable X-Ray tracing
    Environment:
      Variables:
        LOG_LEVEL: INFO
        AWS_XRAY_TRACING_NAME: triggers-api
```

---

### Feature 9: Enhanced Error Responses

**Description:** Improve error handling with detailed, structured error responses.

**Steps:**
1. Create `src/models/error.py` with ErrorResponse model
2. Create custom exception classes for different error types
3. Add FastAPI exception handler for custom exceptions
4. Return structured JSON errors with error codes
5. Log all errors with full context

**Validation:**
- Error responses are consistent and well-structured
- Error codes help clients handle specific errors
- All errors logged with context

**Code Template:**
```python
"""
Module: models/error.py
Description: Error response models and custom exceptions.
"""

from pydantic import BaseModel
from typing import Optional, List

class ErrorDetail(BaseModel):
    """Detailed error information."""
    field: Optional[str] = None
    message: str
    code: str

class ErrorResponse(BaseModel):
    """Standard error response format."""
    error: str
    message: str
    details: Optional[List[ErrorDetail]] = None
    request_id: Optional[str] = None
```

---

### Feature 10: Comprehensive Integration Tests

**Description:** Add integration tests for all new endpoints.

**Steps:**
1. Create tests for GET /events/{id}
2. Create tests for GET /events with filters
3. Create tests for GET /inbox
4. Create tests for POST /events/{id}/acknowledge
5. Test pagination and error scenarios

**Validation:**
- All integration tests pass
- Tests cover success and failure paths
- Tests validate response formats

---

## Phase 2 Completion Checklist

- [ ] GET /events/{id} endpoint implemented
- [ ] GET /events list endpoint with pagination
- [ ] GET /inbox endpoint for undelivered events
- [ ] POST /events/{id}/acknowledge endpoint
- [ ] DynamoDB query methods for listing
- [ ] CloudWatch custom metrics publishing
- [ ] CloudWatch dashboard created
- [ ] X-Ray tracing enabled
- [ ] Enhanced error handling
- [ ] Integration tests for all endpoints
- [ ] Application deployed to AWS
- [ ] Manual testing completed

---

## Testing

### Manual API Testing

```bash
# Get specific event
curl "$API_URL/events/evt_abc123xyz456" \
  -H "Authorization: Bearer YOUR_API_KEY"

# List all events
curl "$API_URL/events" \
  -H "Authorization: Bearer YOUR_API_KEY"

# List pending events
curl "$API_URL/events?status=pending&limit=10" \
  -H "Authorization: Bearer YOUR_API_KEY"

# Get inbox
curl "$API_URL/inbox?limit=50" \
  -H "Authorization: Bearer ZAPIER_API_KEY"

# Acknowledge event
curl -X POST "$API_URL/events/evt_abc123xyz456/acknowledge" \
  -H "Authorization: Bearer ZAPIER_API_KEY"
```

---

## Next Steps

After completing Phase 2, proceed to:
- **Phase 3: Delivery & Retry Logic** - Implement push delivery, SQS queue, and retry mechanisms

**Phase 2 provides:**
- Complete event retrieval API
- Inbox for pull-based delivery
- Monitoring and observability
- Foundation for automated delivery

---

## Resources

- [DynamoDB Query and Scan](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.html)
- [CloudWatch Custom Metrics](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/publishingMetrics.html)
- [AWS X-Ray for Python](https://docs.aws.amazon.com/xray/latest/devguide/xray-sdk-python.html)
- [FastAPI Error Handling](https://fastapi.tiangolo.com/tutorial/handling-errors/)

