# Project Rules & Conventions

## Overview

This document defines the coding standards, file organization, and best practices for the Zapier Triggers API project. These rules are designed to create an AI-first codebase that is modular, scalable, and easy to understand for both humans and AI tools.

**Core Principles:**
- **Modularity**: Small, focused modules with clear responsibilities
- **Navigability**: Intuitive file structure and descriptive naming
- **Clarity**: Self-documenting code with comprehensive comments
- **AI-Compatibility**: Files under 500 lines for optimal AI tool processing
- **Consistency**: Uniform patterns and conventions throughout the codebase

---

## Directory Structure

### Root Directory Organization

```
zapier-triggers-api/
├── template.yaml              # AWS SAM infrastructure definition
├── requirements.txt           # Production Python dependencies
├── requirements-dev.txt       # Development and testing dependencies
├── .env.example              # Environment variable template (never commit .env)
├── .gitignore                # Git ignore rules
├── README.md                 # Project overview and setup instructions
├── src/                      # Application source code
├── tests/                    # Test suite
└── _docs/                    # Project documentation
```

### Source Code Structure (`src/`)

```
src/
├── main.py                   # FastAPI application entry point and initialization
├── handlers/                 # API endpoint handlers (route implementations)
│   ├── __init__.py          # Package initialization
│   ├── events.py            # Event ingestion endpoints (POST /events, GET /events)
│   ├── inbox.py             # Inbox polling endpoints (GET /inbox)
│   └── replay.py            # Event replay endpoints (POST /events/{id}/replay)
├── models/                   # Pydantic data models
│   ├── __init__.py          # Package initialization, export all models
│   ├── event.py             # Event domain models
│   ├── request.py           # API request models
│   └── response.py          # API response models
├── auth/                     # Authentication and authorization
│   ├── __init__.py          # Package initialization
│   ├── authorizer.py        # Lambda authorizer function
│   └── api_key.py           # API key validation and hashing
├── storage/                  # Data persistence layer
│   ├── __init__.py          # Package initialization
│   └── dynamodb.py          # DynamoDB operations and queries
├── queue/                    # Message queue operations
│   ├── __init__.py          # Package initialization
│   └── sqs.py               # SQS send/receive/delete operations
├── delivery/                 # Event delivery logic
│   ├── __init__.py          # Package initialization
│   ├── push.py              # Push events to Zapier workflow engine
│   └── retry.py             # Retry logic for failed deliveries
├── config/                   # Configuration management
│   ├── __init__.py          # Package initialization
│   └── settings.py          # Pydantic settings and environment config
└── utils/                    # Utility functions and helpers
    ├── __init__.py          # Package initialization
    ├── logger.py            # Structured logging configuration
    └── helpers.py           # Common helper functions
```

### Test Structure (`tests/`)

```
tests/
├── __init__.py              # Test package initialization
├── conftest.py              # Shared pytest fixtures
├── unit/                    # Unit tests (isolated, mocked dependencies)
│   ├── __init__.py
│   ├── handlers/
│   │   ├── test_events.py
│   │   ├── test_inbox.py
│   │   └── test_replay.py
│   ├── models/
│   │   └── test_event.py
│   ├── auth/
│   │   └── test_api_key.py
│   └── storage/
│       └── test_dynamodb.py
└── integration/             # Integration tests (multiple components)
    ├── __init__.py
    ├── test_api.py          # End-to-end API tests
    └── test_delivery.py     # Event delivery flow tests
```

---

## File Naming Conventions

### Python Files

**Format:** `lowercase_with_underscores.py`

**Rules:**
- Use descriptive, noun-based names for modules: `events.py`, `api_key.py`, `dynamodb.py`
- Use verb-noun format for test files: `test_events.py`, `test_api_key.py`
- Avoid abbreviations unless universally understood: `sqs.py` (OK), `db.py` (use `database.py`)
- Keep names concise but meaningful: `settings.py` not `configuration_management.py`

**Examples:**
- ✅ `events.py` - Event handler module
- ✅ `api_key.py` - API key validation
- ✅ `test_events.py` - Event tests
- ❌ `ev.py` - Too abbreviated
- ❌ `EventHandlerModule.py` - Use snake_case, not PascalCase
- ❌ `events-handler.py` - Use underscores, not hyphens

### Configuration Files

**Format:** `lowercase-with-hyphens.yaml` or `lowercase.txt`

**Examples:**
- ✅ `template.yaml` - SAM template
- ✅ `requirements.txt` - Dependencies
- ✅ `.env.example` - Environment template
- ✅ `pytest.ini` - Test configuration

### Documentation Files

**Format:** `PascalCase.md` or `kebab-case.md`

**Examples:**
- ✅ `README.md` - Standard convention
- ✅ `Project Overview.md` - Multi-word with spaces
- ✅ `project-rules.md` - Alternative kebab-case style
- ✅ `user-flow.md` - User journey documentation

---

## Code Organization Rules

### File Size Limit

**Maximum: 500 lines per file**

**Rationale:** Optimizes AI tool processing and improves code navigability.

**Enforcement:**
- Break large files into smaller, focused modules
- Split handlers by endpoint or feature
- Extract complex logic into separate utility functions
- Use multiple model files instead of one large models.py

**Example Split:**
```python
# Instead of one large handlers.py (800 lines)
# Split into:
handlers/
├── events.py      # 250 lines - Event CRUD operations
├── inbox.py       # 150 lines - Inbox polling
└── replay.py      # 200 lines - Event replay
```

### Module Organization

**Every Python file should contain:**

1. **File Header Comment** (Lines 1-10)
2. **Imports** (Standard library → Third-party → Local)
3. **Constants/Configuration** (If any)
4. **Functions/Classes** (Grouped by functionality)
5. **Main Block** (If executable)

**Example Structure:**

```python
"""
Module: events.py
Description: Event ingestion and retrieval handlers for the Triggers API.

This module implements the core event endpoints:
- POST /events: Create and ingest new events
- GET /events: List events with filtering
- GET /events/{id}: Retrieve specific event details

Dependencies: FastAPI, DynamoDB, SQS
Author: Triggers API Team
"""

# Standard library imports
from datetime import datetime, timezone
from typing import Optional, List
from uuid import uuid4

# Third-party imports
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import ValidationError

# Local imports
from src.models.event import Event, EventResponse
from src.models.request import CreateEventRequest
from src.storage.dynamodb import DynamoDBClient
from src.config.settings import settings
from src.utils.logger import get_logger

# Module-level constants
ROUTER = APIRouter(prefix="/events", tags=["events"])
logger = get_logger(__name__)
MAX_EVENTS_PER_PAGE = 100

# Handler functions below...
```

---

## Documentation Standards

### File-Level Documentation

**Every Python file must start with a docstring:**

```python
"""
Module: <filename>
Description: <Brief description of module purpose>

<Detailed explanation of what this module does, key components,
and how it fits into the larger system>

Key Components:
- <Component 1>: <Description>
- <Component 2>: <Description>

Dependencies: <Key external dependencies>
Author: <Team or person>
Last Updated: <Date or omit for auto>
"""
```

### Function Documentation

**Use Google-style docstrings for all functions:**

```python
async def create_event(
    request: CreateEventRequest,
    db_client: DynamoDBClient = Depends(get_db_client)
) -> EventResponse:
    """
    Create and ingest a new event into the Triggers API.
    
    This function validates the event payload, generates a unique event ID,
    attempts to push the event to Zapier, and stores it in DynamoDB.
    If push fails, the event is queued in SQS for later polling.
    
    Args:
        request: CreateEventRequest containing event_type, payload, and metadata
        db_client: DynamoDB client instance (injected via dependency)
        
    Returns:
        EventResponse: Created event with ID, status, and timestamps
        
    Raises:
        HTTPException: 400 if validation fails
        HTTPException: 500 if database operation fails
        
    Example:
        >>> request = CreateEventRequest(
        ...     event_type="order.created",
        ...     payload={"order_id": "123"}
        ... )
        >>> response = await create_event(request)
        >>> print(response.event_id)
        'evt_abc123xyz'
    """
    # Function implementation...
```

### Class Documentation

**Use docstrings for classes and all public methods:**

```python
class DynamoDBClient:
    """
    DynamoDB client for event storage and retrieval.
    
    This class handles all DynamoDB operations for the Triggers API,
    including event CRUD operations, querying by status, and TTL management.
    
    Attributes:
        table_name: Name of the DynamoDB table
        client: boto3 DynamoDB client instance
        table: boto3 DynamoDB table resource
        
    Example:
        >>> client = DynamoDBClient(table_name="triggers-api-events")
        >>> event = await client.get_event("evt_123")
        >>> print(event.status)
        'delivered'
    """
    
    def __init__(self, table_name: str):
        """
        Initialize DynamoDB client with table name.
        
        Args:
            table_name: Name of the DynamoDB table to connect to
            
        Raises:
            ValueError: If table_name is empty or invalid
        """
        # Implementation...
```

### Inline Comments

**Guidelines:**
- Comment complex logic or non-obvious decisions
- Explain "why" not "what" (code shows what)
- Use TODO, FIXME, NOTE, HACK prefixes for special comments
- Keep comments concise and up-to-date with code changes

```python
# Good: Explains why
# Use exponential backoff to prevent thundering herd during retries
await retry_with_backoff(delivery_fn, max_attempts=3)

# Bad: States the obvious
# Call the retry function
await retry_with_backoff(delivery_fn, max_attempts=3)

# Special comment types
# TODO: Add support for batch event ingestion
# FIXME: Handle edge case where event_id contains special characters
# NOTE: DynamoDB requires ISO 8601 format for timestamp queries
# HACK: Workaround for boto3 pagination bug, remove when fixed
```

---

## Python Code Conventions

### Naming Conventions

**Variables and Functions:**
- Format: `snake_case`
- Descriptive, not abbreviated
- Boolean variables: use `is_`, `has_`, `can_` prefixes

```python
# Good
event_id = "evt_123"
is_delivered = True
has_expired = check_expiration(event)
user_count = len(users)

# Bad
evtId = "evt_123"  # camelCase
del_status = True  # Abbreviated
x = len(users)     # Not descriptive
```

**Classes:**
- Format: `PascalCase`
- Noun-based names
- Descriptive of the entity or service

```python
# Good
class EventResponse:
class DynamoDBClient:
class APIKeyValidator:

# Bad
class event_response:  # snake_case
class DB:              # Too abbreviated
class HandleEvents:    # Verb-based (use EventHandler)
```

**Constants:**
- Format: `UPPER_CASE_WITH_UNDERSCORES`
- Module-level only
- Group related constants

```python
# Good
MAX_RETRY_ATTEMPTS = 3
DEFAULT_TIMEOUT_SECONDS = 30
EVENT_STATUS_DELIVERED = "delivered"

# Bad
maxRetryAttempts = 3  # camelCase
max_retry = 3         # snake_case
MRTA = 3              # Too abbreviated
```

**Private Methods:**
- Prefix with single underscore: `_method_name`
- Use for internal methods not meant to be called externally

```python
class EventHandler:
    def process_event(self, event):
        """Public method."""
        return self._validate_and_store(event)
    
    def _validate_and_store(self, event):
        """Private method for internal use only."""
        # Implementation...
```

### Import Organization

**Order:** Standard library → Third-party → Local (alphabetical within each group)

```python
# Standard library
import json
import os
from datetime import datetime, timezone
from typing import Optional, List, Dict
from uuid import uuid4

# Third-party packages
import boto3
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

# Local imports (relative to project root)
from src.config.settings import settings
from src.models.event import Event, EventResponse
from src.storage.dynamodb import DynamoDBClient
from src.utils.logger import get_logger
```

### Type Hints

**Required for:**
- All function parameters
- All function return values
- Class attributes
- Module-level variables (when not obvious)

```python
from typing import Optional, List, Dict, Any

# Good: Full type hints
async def get_events(
    status: Optional[str] = None,
    limit: int = 100
) -> List[EventResponse]:
    """Retrieve events with optional status filter."""
    # Implementation...

# Good: Class with type hints
class Event(BaseModel):
    event_id: str
    event_type: str
    payload: Dict[str, Any]
    created_at: datetime
    status: str
    
# Bad: Missing type hints
async def get_events(status=None, limit=100):
    # Implementation...
```

### Async/Await

**Rules:**
- Use `async def` for functions that perform I/O operations
- Always `await` async function calls
- Use `async with` for async context managers
- Regular `def` for pure computation functions

```python
# Good: Async for I/O operations
async def store_event(event: Event) -> None:
    """Store event in DynamoDB (I/O operation)."""
    async with get_db_client() as client:
        await client.put_item(event.dict())

# Good: Sync for pure computation
def generate_event_id() -> str:
    """Generate unique event ID (no I/O)."""
    return f"evt_{uuid4().hex[:12]}"

# Bad: Async without I/O (unnecessary overhead)
async def calculate_checksum(data: str) -> str:
    return hashlib.md5(data.encode()).hexdigest()
```

### Error Handling

**Rules:**
- Catch specific exceptions, not bare `Exception`
- Re-raise with context when appropriate
- Log errors before raising
- Use FastAPI's HTTPException for API errors

```python
from fastapi import HTTPException, status
from botocore.exceptions import ClientError

async def get_event(event_id: str) -> Event:
    """Retrieve event by ID."""
    try:
        response = await db_client.get_item(Key={"event_id": event_id})
    except ClientError as e:
        logger.error(
            "Failed to retrieve event from DynamoDB",
            event_id=event_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve event"
        ) from e
    
    if "Item" not in response:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event {event_id} not found"
        )
    
    return Event(**response["Item"])
```

---

## Testing Conventions

### Test File Organization

**Structure:** Mirror source structure in `tests/` directory

```
src/handlers/events.py → tests/unit/handlers/test_events.py
src/storage/dynamodb.py → tests/unit/storage/test_dynamodb.py
```

### Test Function Naming

**Format:** `test_<function_name>_<scenario>_<expected_result>`

```python
# Good test names
def test_create_event_valid_payload_returns_201():
    """Test successful event creation."""
    
def test_create_event_missing_event_type_returns_400():
    """Test validation error for missing event_type."""
    
def test_get_event_nonexistent_id_returns_404():
    """Test 404 for non-existent event."""

# Bad test names
def test_create_event():  # Not specific
def test_1():             # No description
def testCreateEvent():    # Wrong case
```

### Test Structure

**Use AAA pattern:** Arrange → Act → Assert

```python
@pytest.mark.asyncio
async def test_create_event_valid_payload_returns_201():
    """
    Test that creating an event with valid payload returns 201.
    
    Verifies:
    - Event is stored in DynamoDB
    - Response includes event_id and timestamps
    - Status is set to 'pending' or 'delivered'
    """
    # Arrange: Set up test data and mocks
    request = CreateEventRequest(
        event_type="order.created",
        payload={"order_id": "123"}
    )
    mock_db_client = AsyncMock(spec=DynamoDBClient)
    
    # Act: Execute the function under test
    response = await create_event(request, db_client=mock_db_client)
    
    # Assert: Verify expected behavior
    assert response.status_code == 201
    assert response.event_id.startswith("evt_")
    assert response.status in ["pending", "delivered"]
    mock_db_client.put_item.assert_called_once()
```

### Test Markers

**Use pytest markers for categorization:**

```python
import pytest

@pytest.mark.unit
def test_generate_event_id_returns_valid_format():
    """Unit test: Event ID generation."""
    event_id = generate_event_id()
    assert event_id.startswith("evt_")
    assert len(event_id) == 16

@pytest.mark.integration
@pytest.mark.asyncio
async def test_event_delivery_flow_end_to_end():
    """Integration test: Full event delivery flow."""
    # Test complete flow from ingestion to delivery

@pytest.mark.slow
def test_stress_test_1000_concurrent_events():
    """Slow test: Performance under load."""
    # Performance/stress test
```

### Fixture Usage

**Define shared fixtures in `conftest.py`:**

```python
# tests/conftest.py
"""
Shared pytest fixtures for Triggers API tests.

Provides reusable test fixtures for database clients, mock data,
and common test setup/teardown operations.
"""

import pytest
from moto import mock_dynamodb
from src.config.settings import Settings

@pytest.fixture
def test_settings():
    """Provide test configuration settings."""
    return Settings(
        aws_region="us-east-1",
        dynamodb_table_name="test-events",
        sqs_queue_url="https://sqs.us-east-1.amazonaws.com/test-queue"
    )

@pytest.fixture
def sample_event():
    """Provide sample event for testing."""
    return {
        "event_type": "order.created",
        "payload": {"order_id": "123", "amount": 99.99},
        "metadata": {"source": "test-suite"}
    }

@pytest.fixture
@mock_dynamodb
def dynamodb_table(test_settings):
    """Create mock DynamoDB table for testing."""
    import boto3
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    table = dynamodb.create_table(
        TableName=test_settings.dynamodb_table_name,
        KeySchema=[{"AttributeName": "event_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "event_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST"
    )
    yield table
    table.delete()
```

---

## AWS and Infrastructure Conventions

### SAM Template Organization

**File:** `template.yaml`

**Structure:**
```yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: Zapier Triggers API - Serverless event ingestion and delivery

# Global settings for all functions
Globals:
  Function:
    Runtime: python3.11
    Timeout: 30
    MemorySize: 512
    Environment:
      Variables:
        LOG_LEVEL: INFO
        AWS_REGION: !Ref AWS::Region

# Parameters (environment-specific values)
Parameters:
  StageName:
    Type: String
    Default: dev
    AllowedValues: [dev, staging, prod]
    Description: Deployment stage name

# Resources (grouped by type)
Resources:
  # API Gateway
  TriggersApi:
    Type: AWS::Serverless::HttpApi
    # ...
  
  # Lambda Functions
  EventsFunction:
    Type: AWS::Serverless::Function
    # ...
  
  # DynamoDB Tables
  EventsTable:
    Type: AWS::DynamoDB::Table
    # ...
  
  # SQS Queues
  InboxQueue:
    Type: AWS::SQS::Queue
    # ...

# Outputs (values needed by other stacks or scripts)
Outputs:
  ApiUrl:
    Description: API Gateway endpoint URL
    Value: !Sub 'https://${TriggersApi}.execute-api.${AWS::Region}.amazonaws.com'
```

**Rules:**
- Group resources by type (API, Lambda, Database, Queue)
- Use descriptive logical IDs in PascalCase: `EventsFunction`, `InboxQueue`
- Add comments explaining non-obvious configurations
- Use `!Ref` and `!Sub` for dynamic values
- Define all outputs that other systems need

### Environment Variables

**File:** `.env.example` (committed) and `.env` (gitignored)

**Format:**
```bash
# AWS Configuration
AWS_REGION=us-east-1
AWS_PROFILE=default

# DynamoDB Configuration
DYNAMODB_TABLE_NAME=triggers-api-events-dev
DYNAMODB_ENDPOINT_URL=http://localhost:8000  # For local testing

# SQS Configuration  
SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789/triggers-api-inbox-dev

# Application Configuration
LOG_LEVEL=DEBUG
API_KEY_WORK_FACTOR=12
MAX_RETRY_ATTEMPTS=3

# Zapier Integration
ZAPIER_WEBHOOK_URL=https://hooks.zapier.com/triggers/webhook
ZAPIER_API_TIMEOUT=10

# Feature Flags
ENABLE_REPLAY_API=true
ENABLE_X_RAY_TRACING=true
```

**Rules:**
- Group related variables with comments
- Use UPPER_SNAKE_CASE for variable names
- Provide example values in `.env.example`
- Never commit actual secrets or API keys
- Document each variable's purpose inline

### Resource Naming

**AWS Resource Naming Pattern:** `<service>-<environment>-<resource-type>-<descriptor>`

**Examples:**
```
# Lambda Functions
triggers-api-prod-function-events-post
triggers-api-prod-function-inbox-get

# DynamoDB Tables
triggers-api-prod-table-events
triggers-api-prod-table-api-keys

# SQS Queues
triggers-api-prod-queue-inbox
triggers-api-prod-queue-inbox-dlq

# S3 Buckets
triggers-api-prod-bucket-deployment
triggers-api-prod-bucket-logs

# CloudWatch Log Groups
/aws/lambda/triggers-api-prod-function-events-post
```

---

## Git and Version Control

### Branch Naming

**Format:** `<type>/<short-description>`

**Types:**
- `feature/` - New features
- `bugfix/` - Bug fixes
- `hotfix/` - Urgent production fixes
- `refactor/` - Code refactoring
- `docs/` - Documentation updates
- `test/` - Test additions or fixes

**Examples:**
```
feature/event-replay-api
bugfix/fix-dynamodb-pagination
hotfix/api-key-validation-error
refactor/extract-retry-logic
docs/update-api-documentation
test/add-integration-tests
```

### Commit Messages

**Format:** `<type>(<scope>): <subject>`

**Types:** feat, fix, docs, style, refactor, test, chore

**Examples:**
```
feat(events): add event replay endpoint
fix(auth): correct API key validation logic
docs(readme): update setup instructions
refactor(storage): extract DynamoDB pagination logic
test(events): add unit tests for event creation
chore(deps): update boto3 to version 1.30.0
```

### .gitignore Rules

**Always ignore:**
```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
.venv/
.pytest_cache/
.coverage
htmlcov/

# IDEs
.vscode/
.idea/
*.swp
*.swo

# Environment
.env
.env.local

# AWS
.aws-sam/
samconfig.toml

# OS
.DS_Store
Thumbs.db
```

---

## Code Review Checklist

### Before Submitting PR

- [ ] All files under 500 lines
- [ ] File header docstrings present
- [ ] Function docstrings with Args/Returns/Raises
- [ ] Type hints on all functions
- [ ] No hardcoded secrets or credentials
- [ ] Tests added for new functionality
- [ ] All tests passing locally
- [ ] Code follows naming conventions
- [ ] Imports organized correctly
- [ ] No linter errors (ruff, black, mypy)
- [ ] Updated relevant documentation

### During Review

- [ ] Code is self-explanatory with minimal comments
- [ ] Complex logic has explanatory comments
- [ ] Error handling is appropriate
- [ ] No obvious security vulnerabilities
- [ ] Performance considerations addressed
- [ ] AWS resources properly named and tagged
- [ ] Follows project patterns and conventions

---

## AI Tool Optimization

### Why 500 Lines?

**Benefits:**
- Fits within context windows of most AI tools
- Easier for AI to understand entire file scope
- Faster processing and response times
- More accurate code suggestions
- Better error detection

### File Splitting Strategy

**When a file approaches 500 lines:**

1. **Handlers:** Split by endpoint or feature
   ```
   events.py (800 lines) →
   ├── events_create.py (250 lines)
   ├── events_retrieve.py (200 lines)
   └── events_list.py (250 lines)
   ```

2. **Models:** Split by domain or use case
   ```
   models.py (600 lines) →
   ├── event_models.py (300 lines)
   ├── request_models.py (200 lines)
   └── response_models.py (100 lines)
   ```

3. **Utilities:** Split by function category
   ```
   utils.py (700 lines) →
   ├── date_utils.py (150 lines)
   ├── validation_utils.py (200 lines)
   ├── format_utils.py (150 lines)
   └── crypto_utils.py (200 lines)
   ```

### AI-Friendly Documentation

**Key Practices:**
- Start each file with clear purpose statement
- Use descriptive variable and function names
- Explain "why" in comments, not "what"
- Provide usage examples in docstrings
- Keep functions focused on single responsibility
- Use type hints for clarity

---

## Summary: Quick Reference

### File Naming
- Python files: `snake_case.py`
- Classes: `PascalCase`
- Functions/variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private methods: `_snake_case`

### Documentation
- File header: Module description and purpose
- Functions: Google-style docstrings with Args/Returns/Raises
- Classes: Docstring with Attributes and Example
- Inline: Comment complex logic and "why" decisions

### File Organization
- Maximum 500 lines per file
- Imports: stdlib → third-party → local
- Structure: Header → Imports → Constants → Code

### Testing
- Mirror source structure in tests/
- Name: `test_<function>_<scenario>_<result>`
- Use AAA pattern: Arrange → Act → Assert
- Mark tests: @pytest.mark.unit, @pytest.mark.integration

### AWS Resources
- Naming: `<service>-<env>-<type>-<name>`
- Tags: Environment, Service, Owner, CostCenter
- Secrets in AWS Secrets Manager, not env vars
- Use SAM for infrastructure as code

---

## Enforcement

### Pre-commit Checks

**Tools:**
- `black` - Code formatting (auto-fix)
- `ruff` - Fast Python linter (auto-fix)
- `mypy` - Static type checking
- `pytest` - Run test suite

**Configuration in `pyproject.toml` or `.pre-commit-config.yaml`**

### CI/CD Pipeline

**Automated checks on PR:**
1. Linting (black, ruff)
2. Type checking (mypy)
3. Unit tests (pytest)
4. Code coverage (pytest-cov)
5. File size validation (< 500 lines)
6. Documentation completeness

---

## Questions and Exceptions

### When to Break Rules?

**Rare exceptions allowed for:**
- Generated code (e.g., SAM template outputs)
- Third-party integration code (vendor SDKs)
- Complex mathematical algorithms
- Performance-critical optimized code

**Process:**
1. Document reason in code comments
2. Add `# pylint: disable=<rule>` with justification
3. Discuss in PR review
4. Get team approval

### Getting Help

**For questions about:**
- Conventions: Check this document first
- Best practices: See tech-stack.md
- Architecture: See user-flow.md and Project Overview.md
- Implementation: Consult team in PR discussions

---

**Last Updated:** 2025-11-10  
**Version:** 1.0  
**Maintainers:** Triggers API Team

