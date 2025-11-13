# Phase 1: MVP - Core Event Ingestion

## Overview

**Goal:** Implement core event ingestion functionality with POST /events endpoint, DynamoDB storage, and API key authentication.

**Duration:** 3-5 days

**Success Criteria:**
- POST /events accepts and validates event payloads
- Events stored in DynamoDB with unique IDs
- API key authentication protects endpoints
- Basic error handling and validation
- Unit tests for core functionality

**Deliverable:** Functional API that can ingest and store events securely.

---

## Prerequisites

- Phase 0 completed (AWS infrastructure deployed)
- API Gateway and Lambda function operational
- CloudWatch logs accessible

---

## Features & Tasks

### Feature 1: Pydantic Data Models

**Description:** Define data models for events, requests, and responses using Pydantic v2.

**Steps:**
1. Create `src/models/event.py` with Event model
2. Create `src/models/request.py` with CreateEventRequest model
3. Create `src/models/response.py` with EventResponse model
4. Add validation rules (required fields, types, constraints)
5. Add JSON schema generation for OpenAPI docs

**Validation:**
- Models validate correctly with valid data
- Models reject invalid data with clear error messages
- JSON schemas generated properly

**Code Template:**
```python
"""
Module: models/event.py
Description: Event data models for the Triggers API.

Defines the core Event model with validation rules.
"""

from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict

class Event(BaseModel):
    """
    Event model representing an ingested event.
    
    Attributes:
        event_id: Unique event identifier (generated)
        event_type: Type of event (e.g., 'order.created')
        payload: Event data payload (flexible JSON)
        metadata: Optional metadata (source, custom fields)
        status: Delivery status (pending, delivered, failed)
        created_at: Timestamp when event was created
        delivered_at: Timestamp when event was delivered (nullable)
        delivery_attempts: Number of delivery attempts made
    """
    
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True
    )
    
    event_id: str = Field(
        ...,
        description="Unique event identifier",
        pattern=r"^evt_[a-z0-9]{12}$"
    )
    event_type: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Event type identifier"
    )
    payload: Dict[str, Any] = Field(
        ...,
        description="Event payload data"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional event metadata"
    )
    status: str = Field(
        default="pending",
        pattern=r"^(pending|delivered|failed|replayed)$",
        description="Event delivery status"
    )
    created_at: datetime = Field(
        ...,
        description="Event creation timestamp"
    )
    delivered_at: Optional[datetime] = Field(
        default=None,
        description="Event delivery timestamp"
    )
    delivery_attempts: int = Field(
        default=0,
        ge=0,
        description="Number of delivery attempts"
    )
```

---

### Feature 2: DynamoDB Table Infrastructure

**Description:** Add DynamoDB table to SAM template for event storage.

**Steps:**
1. Update `template.yaml` to include EventsTable resource
2. Define partition key: `event_id` (String)
3. Add Global Secondary Index for status queries
4. Configure on-demand billing mode
5. Add table name to Lambda environment variables

**Validation:**
- SAM template validates successfully
- Table creates on deployment
- GSI for status queries available

**Template Addition:**
```yaml
Resources:
  EventsTable:
    Type: AWS::DynamoDB::Table
    Properties:
      TableName: !Sub '${AWS::StackName}-events'
      BillingMode: PAY_PER_REQUEST
      AttributeDefinitions:
        - AttributeName: event_id
          AttributeType: S
        - AttributeName: status
          AttributeType: S
        - AttributeName: created_at
          AttributeType: S
      KeySchema:
        - AttributeName: event_id
          KeyType: HASH
      GlobalSecondaryIndexes:
        - IndexName: StatusIndex
          KeySchema:
            - AttributeName: status
              KeyType: HASH
            - AttributeName: created_at
              KeyType: RANGE
          Projection:
            ProjectionType: ALL
      TimeToLiveSpecification:
        AttributeName: ttl
        Enabled: true
      PointInTimeRecoverySpecification:
        PointInTimeRecoveryEnabled: true
      Tags:
        - Key: Environment
          Value: dev
        - Key: Service
          Value: triggers-api

  # Update EventsFunction with table permissions
  EventsFunction:
    Type: AWS::Serverless::Function
    Properties:
      # ... existing properties ...
      Environment:
        Variables:
          EVENTS_TABLE_NAME: !Ref EventsTable
      Policies:
        - DynamoDBCrudPolicy:
            TableName: !Ref EventsTable
```

---

### Feature 3: DynamoDB Client Module

**Description:** Create DynamoDB client wrapper for event operations.

**Steps:**
1. Create `src/storage/dynamodb.py` with DynamoDBClient class
2. Implement `put_event()` method to store events
3. Implement `get_event()` method to retrieve by ID
4. Add error handling for DynamoDB exceptions
5. Add structured logging for operations

**Validation:**
- Client successfully stores events
- Client retrieves events by ID
- Errors are handled gracefully

**Code Template:**
```python
"""
Module: storage/dynamodb.py
Description: DynamoDB client for event storage and retrieval.

Provides async operations for storing, retrieving, and querying events
in DynamoDB with proper error handling and logging.
"""

import boto3
from botocore.exceptions import ClientError
from typing import Optional
from datetime import datetime, timezone

from src.models.event import Event
from src.utils.logger import get_logger

logger = get_logger(__name__)

class DynamoDBClient:
    """
    DynamoDB client for event operations.
    
    Handles all DynamoDB operations including storing events,
    retrieving events, and querying by status.
    """
    
    def __init__(self, table_name: str):
        """
        Initialize DynamoDB client.
        
        Args:
            table_name: Name of the DynamoDB events table
        """
        self.table_name = table_name
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table(table_name)
    
    async def put_event(self, event: Event) -> None:
        """
        Store an event in DynamoDB.
        
        Args:
            event: Event model to store
            
        Raises:
            ClientError: If DynamoDB operation fails
        """
        try:
            item = event.model_dump()
            # Convert datetime objects to ISO strings
            item['created_at'] = item['created_at'].isoformat()
            if item.get('delivered_at'):
                item['delivered_at'] = item['delivered_at'].isoformat()
            
            self.table.put_item(Item=item)
            
            logger.info(
                "Event stored in DynamoDB",
                event_id=event.event_id,
                event_type=event.event_type,
                status=event.status
            )
        except ClientError as e:
            logger.error(
                "Failed to store event in DynamoDB",
                event_id=event.event_id,
                error=str(e)
            )
            raise
    
    async def get_event(self, event_id: str) -> Optional[Event]:
        """
        Retrieve an event by ID.
        
        Args:
            event_id: Unique event identifier
            
        Returns:
            Event model if found, None otherwise
            
        Raises:
            ClientError: If DynamoDB operation fails
        """
        try:
            response = self.table.get_item(Key={'event_id': event_id})
            
            if 'Item' not in response:
                logger.warning("Event not found", event_id=event_id)
                return None
            
            item = response['Item']
            # Convert ISO strings back to datetime
            item['created_at'] = datetime.fromisoformat(item['created_at'])
            if item.get('delivered_at'):
                item['delivered_at'] = datetime.fromisoformat(item['delivered_at'])
            
            return Event(**item)
        except ClientError as e:
            logger.error(
                "Failed to retrieve event from DynamoDB",
                event_id=event_id,
                error=str(e)
            )
            raise
```

---

### Feature 4: POST /events Endpoint Handler

**Description:** Implement the core event ingestion endpoint.

**Steps:**
1. Create `src/handlers/events.py` with router
2. Implement POST /events handler function
3. Generate unique event ID (evt_ prefix + 12 char random)
4. Store event in DynamoDB
5. Return EventResponse with 201 Created status

**Validation:**
- Endpoint accepts valid POST requests
- Returns 201 with event details
- Event is stored in DynamoDB

**Code Template:**
```python
"""
Module: handlers/events.py
Description: Event ingestion and retrieval handlers.

Implements POST /events endpoint for creating new events
and storing them in DynamoDB.
"""

from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, HTTPException, status, Depends

from src.models.request import CreateEventRequest
from src.models.response import EventResponse
from src.models.event import Event
from src.storage.dynamodb import DynamoDBClient
from src.config.settings import settings
from src.utils.logger import get_logger

router = APIRouter(prefix="/events", tags=["events"])
logger = get_logger(__name__)

def get_db_client() -> DynamoDBClient:
    """Dependency to get DynamoDB client."""
    return DynamoDBClient(table_name=settings.events_table_name)

@router.post("", status_code=status.HTTP_201_CREATED, response_model=EventResponse)
async def create_event(
    request: CreateEventRequest,
    db_client: DynamoDBClient = Depends(get_db_client)
) -> EventResponse:
    """
    Create and ingest a new event.
    
    Validates the event payload, generates a unique ID, and stores
    the event in DynamoDB with pending status.
    
    Args:
        request: Event creation request with event_type and payload
        db_client: DynamoDB client (injected dependency)
        
    Returns:
        EventResponse with event details including generated ID
        
    Raises:
        HTTPException: 400 if validation fails
        HTTPException: 500 if storage fails
    """
    # Generate unique event ID
    event_id = f"evt_{uuid4().hex[:12]}"
    
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
    try:
        await db_client.put_event(event)
    except Exception as e:
        logger.error("Failed to store event", event_id=event_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store event"
        )
    
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
```

---

### Feature 5: API Key Storage & Management

**Description:** Implement API key storage in DynamoDB for authentication.

**Steps:**
1. Add APIKeysTable to SAM template
2. Create `src/auth/api_key.py` with hashing functions
3. Create script to generate and hash API keys
4. Store hashed keys in DynamoDB with metadata
5. Document API key generation process

**Validation:**
- API keys hash correctly using bcrypt
- Keys stored securely (hashed, not plaintext)
- Script successfully generates new keys

**Code Template:**
```python
"""
Module: auth/api_key.py
Description: API key hashing and validation.

Provides functions for hashing API keys with bcrypt and
validating keys against stored hashes.
"""

from passlib.context import CryptContext
from typing import Optional
import boto3
from botocore.exceptions import ClientError

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Bcrypt context with work factor 13 for production
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_api_key(api_key: str) -> str:
    """
    Hash an API key using bcrypt.
    
    Args:
        api_key: Plain text API key to hash
        
    Returns:
        Hashed API key string
    """
    return pwd_context.hash(api_key)

def verify_api_key(plain_key: str, hashed_key: str) -> bool:
    """
    Verify an API key against its hash.
    
    Args:
        plain_key: Plain text API key from request
        hashed_key: Stored hashed API key
        
    Returns:
        True if key matches, False otherwise
    """
    return pwd_context.verify(plain_key, hashed_key)
```

---

### Feature 6: Lambda Authorizer

**Description:** Implement Lambda authorizer for API key authentication.

**Steps:**
1. Create `src/auth/authorizer.py` with Lambda handler
2. Extract API key from Authorization header
3. Query DynamoDB for key and validate hash
4. Return IAM policy allowing/denying access
5. Add caching for 5-minute TTL

**Validation:**
- Valid API keys return Allow policy
- Invalid keys return Deny policy
- Authorization caching works correctly

**Code Template:**
```python
"""
Module: auth/authorizer.py
Description: Lambda authorizer for API key authentication.

Validates API keys from Authorization header and returns
IAM policies for API Gateway.
"""

import boto3
import os
from typing import Dict, Any

from src.auth.api_key import verify_api_key
from src.utils.logger import get_logger

logger = get_logger(__name__)

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda authorizer handler for API key validation.
    
    Extracts API key from Authorization header, validates against
    stored hashes in DynamoDB, and returns IAM policy.
    
    Args:
        event: API Gateway authorizer event
        context: Lambda context
        
    Returns:
        IAM policy document allowing or denying access
    """
    # Extract API key from header
    token = event.get('headers', {}).get('authorization', '')
    if token.startswith('Bearer '):
        token = token[7:]
    
    # Validate API key
    table_name = os.environ['API_KEYS_TABLE_NAME']
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(table_name)
    
    try:
        # Query for API key (this is simplified - in production, use a lookup)
        # You'd typically store a key_id in the token and look up by that
        response = table.scan(Limit=1)
        
        if response['Items']:
            stored_hash = response['Items'][0]['api_key_hash']
            if verify_api_key(token, stored_hash):
                return generate_policy('user', 'Allow', event['methodArn'])
        
        # Invalid key
        logger.warning("Invalid API key attempted")
        return generate_policy('user', 'Deny', event['methodArn'])
        
    except Exception as e:
        logger.error("Authorization error", error=str(e))
        return generate_policy('user', 'Deny', event['methodArn'])

def generate_policy(principal_id: str, effect: str, resource: str) -> Dict[str, Any]:
    """Generate IAM policy document."""
    return {
        'principalId': principal_id,
        'policyDocument': {
            'Version': '2012-10-17',
            'Statement': [{
                'Action': 'execute-api:Invoke',
                'Effect': effect,
                'Resource': resource
            }]
        }
    }
```

---

### Feature 7: Structured Logging Setup

**Description:** Configure structlog for JSON logging to CloudWatch.

**Steps:**
1. Create `src/utils/logger.py` with structlog configuration
2. Configure JSON renderer for CloudWatch compatibility
3. Add timestamp and log level processors
4. Create helper function `get_logger(name)`
5. Update all modules to use structured logger

**Validation:**
- Logs output in JSON format
- CloudWatch Insights can query logs easily
- Log context is preserved across calls

---

### Feature 8: Settings and Configuration

**Description:** Implement pydantic-settings for environment configuration.

**Steps:**
1. Create `src/config/settings.py` with Settings class
2. Define environment variables (table names, region, log level)
3. Add validation for required settings
4. Create singleton settings instance
5. Update `.env.example` with all variables

**Validation:**
- Settings load from environment variables
- Validation catches missing required variables
- Type conversion works correctly

---

### Feature 9: Unit Tests for Core Features

**Description:** Write unit tests for models, handlers, and storage.

**Steps:**
1. Create `tests/conftest.py` with shared fixtures
2. Write tests for Pydantic models in `tests/unit/models/`
3. Write tests for DynamoDB client with moto mocks
4. Write tests for POST /events handler
5. Achieve >80% code coverage for core modules

**Validation:**
- All tests pass: `pytest tests/unit/`
- Code coverage >80%
- Tests use proper mocking (moto for AWS)

---

### Feature 10: Integration Testing

**Description:** Create integration tests for end-to-end event creation flow.

**Steps:**
1. Create `tests/integration/test_api.py`
2. Test full POST /events flow with mocked DynamoDB
3. Test validation error scenarios
4. Test authentication (valid and invalid keys)
5. Run tests with `pytest tests/integration/`

**Validation:**
- Integration tests pass
- All error scenarios covered
- Tests run independently (proper setup/teardown)

---

## Phase 1 Completion Checklist

- [ ] Pydantic models defined for Event, Request, Response
- [ ] DynamoDB table added to SAM template
- [ ] DynamoDB client module implemented
- [ ] POST /events endpoint working
- [ ] API key hashing module implemented
- [ ] Lambda authorizer configured
- [ ] Structured logging configured
- [ ] Settings management with pydantic-settings
- [ ] Unit tests written and passing (>80% coverage)
- [ ] Integration tests written and passing
- [ ] Application deployed to AWS
- [ ] Manual testing completed successfully

---

## Testing

### Manual API Testing

```bash
# Get API URL
API_URL=$(aws cloudformation describe-stacks \
  --stack-name triggers-api-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' \
  --output text)

# Create an event (replace with actual API key)
curl -X POST "$API_URL/events" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "order.created",
    "payload": {
      "order_id": "12345",
      "amount": 99.99
    },
    "metadata": {
      "source": "test-client"
    }
  }'

# Expected response:
# {
#   "event_id": "evt_abc123xyz456",
#   "status": "pending",
#   "created_at": "2024-01-15T10:30:00Z",
#   "delivered_at": null,
#   "message": "Event created successfully"
# }
```

### Validation Criteria

- [ ] POST /events returns 201 Created with valid API key
- [ ] Event stored in DynamoDB with all fields
- [ ] Invalid API key returns 401 Unauthorized
- [ ] Invalid payload returns 400 Bad Request with validation errors
- [ ] CloudWatch logs show structured JSON logs
- [ ] Response time < 1000ms (cold start) and < 200ms (warm)

---

## Next Steps

After completing Phase 1, proceed to:
- **Phase 2: Event Retrieval & Monitoring** - Implement GET endpoints and /inbox

**Phase 1 provides:**
- Functional event ingestion API
- Secure authentication
- Persistent event storage
- Foundation for event retrieval and delivery

---

## Resources

- [Pydantic V2 Documentation](https://docs.pydantic.dev/latest/)
- [DynamoDB with boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [API Gateway Lambda Authorizers](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-lambda-authorizer.html)

