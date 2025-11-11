# Phase 4: Event Replay & Polish

## Overview

**Goal:** Implement event replay functionality and polish the application for production readiness with performance optimization and comprehensive documentation.

**Duration:** 2-3 days

**Success Criteria:**
- POST /events/{id}/replay endpoint functional
- Event correlation IDs for tracing
- Performance optimization (<100ms warm latency)
- OpenAPI documentation complete
- Production deployment guide
- 99.9% reliability achieved

**Deliverable:** Production-ready Triggers API with all P0 and P1 features complete.

---

## Prerequisites

- Phase 3 completed (delivery and retry working)
- All core endpoints operational
- Monitoring and alerting configured

---

## Features & Tasks

### Feature 1: Event Replay Endpoint

**Description:** Implement POST /events/{id}/replay to re-deliver existing events.

**Steps:**
1. Create `src/handlers/replay.py` with router
2. Add POST /events/{id}/replay endpoint
3. Retrieve original event from DynamoDB
4. Create replay record (same event_id, new attempt)
5. Attempt delivery with replay flag in metadata

**Validation:**
- Replay endpoint accepts valid event IDs
- Original event is preserved
- Replay attempts are logged separately

**Code Template:**
```python
"""
Module: handlers/replay.py
Description: Event replay endpoint for testing and recovery.

Allows re-delivery of existing events while preserving original
event identity and context for idempotent handling.
"""

from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel

from src.models.response import EventResponse
from src.models.event import Event
from src.storage.dynamodb import DynamoDBClient
from src.delivery.push import PushDeliveryClient
from src.queue.sqs import SQSClient
from src.config.settings import settings
from src.utils.logger import get_logger

router = APIRouter(prefix="/events", tags=["replay"])
logger = get_logger(__name__)

class ReplayRequest(BaseModel):
    """Request model for event replay."""
    workflow_id: Optional[str] = None
    reason: Optional[str] = "manual_replay"

def get_db_client() -> DynamoDBClient:
    """Dependency to get DynamoDB client."""
    return DynamoDBClient(table_name=settings.events_table_name)

def get_delivery_client() -> PushDeliveryClient:
    """Dependency to get delivery client."""
    return PushDeliveryClient(webhook_url=settings.zapier_webhook_url)

def get_sqs_client() -> SQSClient:
    """Dependency to get SQS client."""
    return SQSClient(queue_url=settings.inbox_queue_url)

@router.post("/{event_id}/replay", response_model=EventResponse)
async def replay_event(
    event_id: str,
    request: ReplayRequest,
    db_client: DynamoDBClient = Depends(get_db_client),
    delivery_client: PushDeliveryClient = Depends(get_delivery_client),
    sqs_client: SQSClient = Depends(get_sqs_client)
) -> EventResponse:
    """
    Replay an existing event.
    
    Re-delivers an event while preserving its original identity
    and timestamp. Adds replay metadata for tracking.
    
    Args:
        event_id: ID of event to replay
        request: Optional replay parameters
        db_client: DynamoDB client
        delivery_client: Push delivery client
        sqs_client: SQS client
        
    Returns:
        EventResponse with replay status
        
    Raises:
        HTTPException: 404 if event not found
        HTTPException: 400 if event not replayable
        HTTPException: 500 if replay fails
    """
    # Retrieve original event
    try:
        event = await db_client.get_event(event_id)
    except Exception as e:
        logger.error("Failed to retrieve event for replay", event_id=event_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve event"
        )
    
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event {event_id} not found"
        )
    
    # Check if event is replayable
    if event.delivery_attempts >= 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Event has exceeded maximum replay attempts"
        )
    
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
    
    # Attempt immediate delivery
    try:
        delivery_success = await delivery_client.deliver_event(event)
        
        if delivery_success:
            # Update replay status
            event.status = "replayed"
            event.delivery_attempts += 1
            await db_client.update_event(event)
            
            logger.info(
                "Event replayed successfully",
                event_id=event_id,
                reason=request.reason,
                workflow_id=request.workflow_id
            )
            
            return EventResponse(
                event_id=event.event_id,
                status="replayed",
                created_at=event.created_at,
                delivered_at=datetime.now(timezone.utc),
                delivery_attempts=event.delivery_attempts,
                message="Event replayed successfully"
            )
        else:
            # Queue for retry
            await sqs_client.send_message(
                event_id=event_id,
                event_data=event.model_dump(mode='json')
            )
            
            logger.info("Event replay queued for retry", event_id=event_id)
            
            return EventResponse(
                event_id=event.event_id,
                status="pending",
                created_at=event.created_at,
                delivery_attempts=event.delivery_attempts,
                message="Event replay queued"
            )
            
    except Exception as e:
        logger.error("Event replay failed", event_id=event_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Event replay failed"
        )
```

---

### Feature 2: Correlation IDs

**Description:** Add correlation ID tracking for distributed tracing.

**Steps:**
1. Generate correlation ID on event creation
2. Pass correlation ID through all operations
3. Include in logs and metrics
4. Add to X-Ray trace annotations
5. Return in response headers

**Validation:**
- Correlation IDs in all logs
- X-Ray traces show correlation IDs
- Response headers include correlation ID

**Code Addition:**
```python
from uuid import uuid4

def generate_correlation_id() -> str:
    """Generate unique correlation ID."""
    return f"corr_{uuid4().hex[:16]}"

# In FastAPI middleware
@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    """Add correlation ID to request context."""
    correlation_id = request.headers.get('X-Correlation-ID') or generate_correlation_id()
    
    # Add to request state
    request.state.correlation_id = correlation_id
    
    # Process request
    response = await call_next(request)
    
    # Add to response headers
    response.headers['X-Correlation-ID'] = correlation_id
    
    return response
```

---

### Feature 3: Rate Limiting Enhancement

**Description:** Implement API Gateway usage plans for tiered rate limiting.

**Steps:**
1. Create usage plans in SAM template (Free, Pro, Enterprise)
2. Associate API keys with usage plans
3. Configure rate and burst limits per tier
4. Add throttling metrics to CloudWatch
5. Document rate limits in API documentation

**Validation:**
- Rate limiting enforces correctly
- Different tiers have different limits
- Throttled requests return 429

**Template Addition:**
```yaml
Resources:
  FreeUsagePlan:
    Type: AWS::ApiGateway::UsagePlan
    Properties:
      UsagePlanName: !Sub '${AWS::StackName}-free-tier'
      ApiStages:
        - ApiId: !Ref TriggersApi
          Stage: !Ref TriggersApi.Stage
      Throttle:
        RateLimit: 100
        BurstLimit: 200
      Quota:
        Limit: 10000
        Period: DAY

  ProUsagePlan:
    Type: AWS::ApiGateway::UsagePlan
    Properties:
      UsagePlanName: !Sub '${AWS::StackName}-pro-tier'
      ApiStages:
        - ApiId: !Ref TriggersApi
          Stage: !Ref TriggersApi.Stage
      Throttle:
        RateLimit: 1000
        BurstLimit: 2000
      Quota:
        Limit: 1000000
        Period: MONTH
```

---

### Feature 4: Performance Optimization

**Description:** Optimize Lambda functions to achieve <100ms warm latency.

**Steps:**
1. Optimize cold starts (reduce dependencies, lazy imports)
2. Implement connection pooling for DynamoDB and httpx
3. Enable Lambda SnapStart for Python 3.11
4. Cache frequently accessed data (settings, schemas)
5. Profile and optimize hot paths

**Validation:**
- Warm latency <100ms (P95)
- Cold start <3 seconds
- Memory usage optimized

**Optimization Techniques:**
```python
# Lazy imports for cold start reduction
def get_expensive_dependency():
    """Lazy import expensive dependencies."""
    global _expensive_dependency
    if '_expensive_dependency' not in globals():
        import expensive_module
        _expensive_dependency = expensive_module.SomeClass()
    return _expensive_dependency

# Connection pooling
class ConnectionPool:
    """Reuse database connections across Lambda invocations."""
    _client = None
    
    @classmethod
    def get_client(cls):
        if cls._client is None:
            cls._client = boto3.client('dynamodb')
        return cls._client
```

---

### Feature 5: OpenAPI Documentation

**Description:** Complete and polish OpenAPI/Swagger documentation.

**Steps:**
1. Add detailed descriptions to all endpoints
2. Include request/response examples
3. Document all error codes and responses
4. Add authentication documentation
5. Generate and host Swagger UI

**Validation:**
- Swagger UI accessible at /docs
- All endpoints documented
- Examples are accurate

**Code Enhancement:**
```python
@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=EventResponse,
    summary="Create new event",
    description="Ingest a new event into the Triggers API with automatic delivery attempt.",
    responses={
        202: {
            "description": "Event accepted and delivery attempted",
            "content": {
                "application/json": {
                    "example": {
                        "event_id": "evt_abc123xyz456",
                        "status": "delivered",
                        "created_at": "2024-01-15T10:30:00Z",
                        "delivered_at": "2024-01-15T10:30:01Z",
                        "message": "Event delivered"
                    }
                }
            }
        },
        400: {"description": "Invalid request payload"},
        401: {"description": "Invalid or missing API key"},
        500: {"description": "Internal server error"}
    }
)
async def create_event(...):
    """Create and ingest a new event..."""
```

---

### Feature 6: Health Check Enhancement

**Description:** Improve health check to verify dependencies.

**Steps:**
1. Add dependency checks (DynamoDB, SQS availability)
2. Return detailed health status JSON
3. Include version and uptime information
4. Add separate /readiness and /liveness endpoints
5. Document health check format

**Validation:**
- Health check verifies all dependencies
- Returns detailed status information
- Can be used by load balancers

**Code Enhancement:**
```python
from datetime import datetime
import boto3

@app.get("/health")
async def health_check():
    """
    Comprehensive health check.
    
    Verifies API is running and can connect to dependencies.
    """
    health_status = {
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dependencies": {}
    }
    
    # Check DynamoDB
    try:
        dynamodb = boto3.client('dynamodb')
        dynamodb.describe_table(TableName=settings.events_table_name)
        health_status["dependencies"]["dynamodb"] = "healthy"
    except Exception as e:
        health_status["dependencies"]["dynamodb"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"
    
    # Check SQS
    try:
        sqs = boto3.client('sqs')
        sqs.get_queue_attributes(
            QueueUrl=settings.inbox_queue_url,
            AttributeNames=['ApproximateNumberOfMessages']
        )
        health_status["dependencies"]["sqs"] = "healthy"
    except Exception as e:
        health_status["dependencies"]["sqs"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"
    
    status_code = 200 if health_status["status"] == "healthy" else 503
    return JSONResponse(content=health_status, status_code=status_code)
```

---

### Feature 7: Comprehensive Error Handling

**Description:** Standardize error handling across all endpoints.

**Steps:**
1. Create global exception handler in FastAPI
2. Map all exceptions to appropriate HTTP status codes
3. Return consistent error response format
4. Log all errors with full context
5. Don't expose internal details in error messages

**Validation:**
- All errors return consistent format
- Appropriate status codes used
- No sensitive information leaked

**Code Template:**
```python
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler for unhandled errors.
    
    Logs error details and returns user-friendly error response.
    """
    logger.error(
        "Unhandled exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        error_type=type(exc).__name__,
        correlation_id=getattr(request.state, 'correlation_id', None)
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "InternalServerError",
            "message": "An unexpected error occurred",
            "correlation_id": getattr(request.state, 'correlation_id', None)
        }
    )
```

---

### Feature 8: Production Deployment Guide

**Description:** Create comprehensive deployment documentation.

**Steps:**
1. Document AWS account setup requirements
2. Create deployment checklist
3. Document environment variables and secrets
4. Create rollback procedures
5. Document monitoring and alerting setup

**Validation:**
- Guide enables independent deployment
- All prerequisites documented
- Rollback procedures tested

**Document Structure:**
```markdown
# Production Deployment Guide

## Prerequisites
- AWS account with admin access
- Domain name for custom API endpoint
- Email for alarm notifications
- Zapier account for webhook testing

## Deployment Steps
1. Configure AWS credentials
2. Set environment variables
3. Run sam deploy with production parameters
4. Configure Route53 for custom domain
5. Generate and store API keys
6. Test all endpoints
7. Configure monitoring alerts

## Post-Deployment
- Verify health check
- Test event creation and delivery
- Check CloudWatch dashboard
- Test rollback procedure
```

---

### Feature 9: Load Testing

**Description:** Perform load testing to validate 99.9% reliability target.

**Steps:**
1. Create load test script with locust or k6
2. Test sustained load (100 req/s for 10 minutes)
3. Test burst load (1000 req/s for 1 minute)
4. Measure error rate, latency, and throughput
5. Identify and fix bottlenecks

**Validation:**
- 99.9% success rate under load
- P95 latency <500ms
- No throttling errors

**Load Test Example:**
```python
"""
Load test script using locust.

Run with: locust -f load_test.py --host https://api-url
"""

from locust import HttpUser, task, between

class TriggersAPIUser(HttpUser):
    wait_time = between(1, 3)
    
    def on_start(self):
        """Setup API key header."""
        self.client.headers['Authorization'] = 'Bearer YOUR_API_KEY'
    
    @task(10)
    def create_event(self):
        """Create event (primary operation)."""
        self.client.post("/events", json={
            "event_type": "load.test",
            "payload": {"test_id": 123},
            "metadata": {"source": "load-test"}
        })
    
    @task(3)
    def get_events(self):
        """List events."""
        self.client.get("/events?limit=10")
    
    @task(2)
    def get_inbox(self):
        """Check inbox."""
        self.client.get("/inbox?limit=10")
```

---

### Feature 10: Final Integration Testing

**Description:** Comprehensive end-to-end testing of all features.

**Steps:**
1. Test complete event lifecycle (create → deliver → acknowledge)
2. Test replay functionality
3. Test failure scenarios and recovery
4. Test rate limiting and authentication
5. Verify all monitoring and alerts

**Validation:**
- All user flows work end-to-end
- No critical bugs remain
- System meets all success criteria

---

## Phase 4 Completion Checklist

- [ ] Event replay endpoint implemented
- [ ] Correlation IDs added for tracing
- [ ] Rate limiting configured with usage plans
- [ ] Performance optimized (<100ms warm latency)
- [ ] OpenAPI documentation complete
- [ ] Enhanced health checks
- [ ] Global error handling
- [ ] Production deployment guide written
- [ ] Load testing completed successfully
- [ ] Final integration testing passed
- [ ] All documentation updated
- [ ] Application deployed to production

---

## Production Readiness Checklist

### Functionality
- [ ] All P0 endpoints operational (POST /events, GET /inbox, acknowledgment)
- [ ] P1 features complete (retry logic, status tracking, replay)
- [ ] Error handling comprehensive
- [ ] Input validation robust

### Performance
- [ ] <100ms warm latency (P95)
- [ ] <5s cold start latency
- [ ] 99.9% availability under load
- [ ] Handles 100+ concurrent requests

### Security
- [ ] API key authentication enforced
- [ ] Secrets in Secrets Manager (not environment)
- [ ] HTTPS/TLS encryption
- [ ] IAM roles follow least privilege
- [ ] No secrets in logs

### Monitoring
- [ ] CloudWatch dashboard configured
- [ ] X-Ray tracing enabled
- [ ] Custom metrics publishing
- [ ] Alarms configured (errors, DLQ, latency)
- [ ] Email notifications set up

### Documentation
- [ ] API documentation (OpenAPI/Swagger)
- [ ] Deployment guide
- [ ] Runbook for common operations
- [ ] Troubleshooting guide
- [ ] Architecture diagrams

### Testing
- [ ] Unit tests >80% coverage
- [ ] Integration tests passing
- [ ] Load tests successful
- [ ] Manual testing complete

---

## Final Testing

### End-to-End Test Script

```bash
#!/bin/bash
# comprehensive-test.sh - Test all features

API_URL="https://your-api-url.amazonaws.com"
API_KEY="your-api-key"

echo "1. Testing health check..."
curl -s "$API_URL/health" | jq .

echo "\n2. Creating event..."
EVENT_RESPONSE=$(curl -s -X POST "$API_URL/events" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"event_type": "test.complete", "payload": {"test": true}}')
echo $EVENT_RESPONSE | jq .
EVENT_ID=$(echo $EVENT_RESPONSE | jq -r .event_id)

echo "\n3. Getting event by ID..."
curl -s "$API_URL/events/$EVENT_ID" \
  -H "Authorization: Bearer $API_KEY" | jq .

echo "\n4. Listing events..."
curl -s "$API_URL/events?limit=5" \
  -H "Authorization: Bearer $API_KEY" | jq .

echo "\n5. Checking inbox..."
curl -s "$API_URL/inbox" \
  -H "Authorization: Bearer $API_KEY" | jq .

echo "\n6. Replaying event..."
curl -s -X POST "$API_URL/events/$EVENT_ID/replay" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"reason": "final-test"}' | jq .

echo "\n✅ All tests complete!"
```

---

## Success Metrics

After Phase 4 completion, verify these metrics:

- [ ] **Reliability**: 99.9% success rate over 7 days
- [ ] **Latency**: P95 <100ms warm, <5s cold
- [ ] **Throughput**: Handles 100+ events/second
- [ ] **Availability**: 99.9% uptime over 30 days
- [ ] **Error Rate**: <0.1% server errors
- [ ] **Recovery Time**: <5 minutes for incidents

---

## Congratulations!

Upon completing Phase 4, you have:

✅ **Fully functional Triggers API** with all core features  
✅ **Production-ready infrastructure** on AWS  
✅ **Comprehensive monitoring** and alerting  
✅ **Complete documentation** for users and operators  
✅ **Tested and validated** system meeting all requirements  

**The Zapier Triggers API is ready for production use!**

---

## Future Enhancements (Post-MVP)

Consider these features for future iterations:

1. **Event Schema Validation** - Validate payloads against JSON schemas
2. **Event Filtering** - Route events based on type or content
3. **Webhook Callbacks** - Notify on delivery success/failure
4. **Multi-Region Deployment** - Deploy across multiple AWS regions
5. **Event Transformation** - Transform payloads before delivery
6. **Advanced Analytics** - Detailed event analytics and reporting
7. **GraphQL API** - Alternative API interface
8. **WebSocket Support** - Real-time event streaming

---

## Resources

- [FastAPI Performance](https://fastapi.tiangolo.com/deployment/concepts/)
- [AWS Lambda SnapStart](https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html)
- [Load Testing with Locust](https://docs.locust.io/)
- [OpenAPI Specification](https://swagger.io/specification/)

