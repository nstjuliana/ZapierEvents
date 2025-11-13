# Explain Zapier triggers API documentation
_Exported on 11/10/2025 at 11:08:17 CST from Cursor (2.0.69)_

---

**User**

Explain @PRD_Zapier_Zapier_Triggers_API.md 

---

**Cursor**

## Overview

A unified REST API for sending real-time events into Zapier. It enables event-driven automation, allowing systems to react to events in real time instead of relying on scheduled polling or manual triggers.

## The Problem

Current Zapier triggers are defined within individual integrations, which limits flexibility and scalability. There’s no centralized way to accept events from diverse sources, restricting real-time, event-driven workflows.

## Goals

- Build a working prototype that can ingest, store, and deliver events
- Achieve 99.9% reliability for event ingestion
- Reduce event processing latency by 50%
- Get positive developer feedback
- Achieve 10% adoption by existing Zapier integrations within 6 months

## Target Users

1. Developers: Need a simple API to integrate their systems
2. Automation Specialists: Build workflows that react to external events
3. Business Analysts: Access real-time data for insights

## Core Features (Prioritized)

**P0 (Must-have):**
- `/events` endpoint: Accept POST requests with JSON payloads, store events with metadata, return acknowledgments
- Event persistence: Store events durably, provide `/inbox` endpoint to retrieve undelivered events, support acknowledgment/deletion after consumption

**P1 (Should-have):**
- Clear API design with predictable routes/responses
- Basic retry logic and status tracking

**P2 (Nice-to-have):**
- Documentation and example client code

## Technical Approach

- RESTful API built with Python
- Deployed on AWS with horizontal scalability
- JSON-based event payloads
- Target: < 100ms response time for event ingestion

## Out of Scope (MVP)

- Advanced event filtering/transformation
- Comprehensive analytics/reporting
- Long-term data retention beyond MVP needs

This PRD outlines a foundational API to enable real-time, event-driven automation on Zapier, positioning it for agent frameworks and next-generation automation.

---

**User**

How is this different/better than a webhook trigger?

---

**Cursor**

## Key differences

### 1. Centralized vs. integration-specific
- Webhook triggers: Each Zapier integration defines its own webhook endpoint. You need different URLs/configurations per integration.
- Triggers API: Single, unified endpoint (`/events`) that any system can use, regardless of which Zapier integration or workflow will consume it.

### 2. Event persistence and reliability
- Webhook triggers: Typically fire-and-forget. If a Zap isn’t active or there’s a temporary issue, the event may be lost.
- Triggers API: Events are stored durably. The `/inbox` endpoint lets you retrieve undelivered events, and there’s an acknowledgment/deletion flow after consumption. This supports retry and at-least-once delivery.

### 3. Decoupling
- Webhook triggers: Tightly coupled to specific Zaps/workflows. You need to know which Zap’s webhook URL to call.
- Triggers API: Decouples event production from consumption. You send events to a central system, and multiple workflows can react to the same events without the sender needing to know about them.

### 4. Scalability and flexibility
- Webhook triggers: Each integration manages its own webhook infrastructure, which can be harder to scale and maintain.
- Triggers API: Centralized architecture that can scale horizontally on AWS, making it easier to handle high volumes and add features like filtering, routing, and analytics.

### 5. Developer experience
- Webhook triggers: Different endpoints, authentication methods, and payload formats per integration.
- Triggers API: Single, consistent REST API with standardized JSON payloads, making integration simpler.

## Use case example

**With webhook triggers:**
- Your app needs to notify 3 different Zaps → you call 3 different webhook URLs
- If a Zap is paused → event is lost
- Each integration has different auth/format requirements

**With Triggers API:**
- Your app sends one event to `/events`
- Multiple Zaps can react to that same event
- Events are stored and can be retried if delivery fails
- Consistent API regardless of which workflows consume it

In short, the Triggers API acts as a centralized event bus, while webhook triggers are point-to-point connections. This supports more reliable, scalable, and flexible event-driven automation.

---

**User**

What AWS service is best for hosting this

---

**Cursor**

Given the PRD requirements, here are the best AWS options:

## Recommended architecture

### Option 1: Serverless (best fit for MVP)
- API Gateway + Lambda (Python)
  - Auto-scales, pay-per-use
  - Low latency (API Gateway + Lambda can meet < 100ms)
  - No server management
  - Built-in authentication/authorization
- DynamoDB for event storage
  - Fast, serverless, scales automatically
  - Good for event metadata and inbox queries
- SQS or EventBridge for event delivery
  - Reliable delivery, retries, dead-letter queues

### Option 2: Containerized (more control)
- ECS (Fargate) or App Runner
  - More control over runtime
  - Still auto-scales
  - Better for long-running processes
- Application Load Balancer for routing
- DynamoDB for storage (same as above)

## Why serverless fits best
1. Horizontal scalability: Lambda scales automatically
2. Low latency: API Gateway + Lambda can meet < 100ms
3. High availability: Built-in redundancy across AZs
4. Cost: Pay only for requests (good for MVP)
5. Event storage: DynamoDB handles high throughput
6. Event delivery: SQS/EventBridge provides retries and DLQs

## Complete stack recommendation

```
API Gateway → Lambda (Python) → DynamoDB (events)
                              → SQS/EventBridge (delivery queue)
```

This aligns with the PRD’s goals: scalable, low-latency, and developer-friendly. Should I draft a technical architecture document with specific AWS service configurations?

```plaintext
API Gateway → Lambda (Python) → DynamoDB (events)
                              → SQS/EventBridge (delivery queue)
```

---

**User**

So the primary upside is:

1. 1 event can serve as a trigger for multiple zaps/workflows

2. events can be persisted and replayed/retried in the future

---

**Cursor**

Yes. Those are the two primary advantages:

## 1. One event → multiple workflows
- Decouples event production from consumption
- One API call can trigger multiple Zaps without the sender knowing about them
- Enables fan-out patterns (e.g., one "order created" event triggers shipping, notifications, analytics, etc.)

## 2. Event persistence and replay/retry
- Events are stored durably (not fire-and-forget)
- `/inbox` endpoint allows retrieval of undelivered events
- Supports retry logic and acknowledgment flows
- Enables replay for debugging, testing, or recovery

## Additional benefit
- Unified developer experience: one consistent API instead of managing multiple webhook endpoints per integration

These two features enable more reliable, scalable, and flexible event-driven automation compared to traditional webhook triggers.

---

**User**

What other features not in the PRD would you recommend that would make my solution for this stand out

---

**Cursor**

Here are features that would differentiate the solution:

## Developer experience

1. Event schema validation
   - Accept JSON schemas on registration
   - Validate incoming events against schemas
   - Return clear validation errors

2. Event replay API
   - Replay specific events or time ranges
   - Useful for testing, debugging, and recovery

3. Webhook-style callback URLs
   - Let developers register callback URLs for delivery confirmations
   - Support retry callbacks for failed deliveries

## Observability and debugging

4. Event tracing/correlation IDs
   - Generate correlation IDs for each event
   - Track event flow through multiple workflows
   - Dashboard showing event journey

5. Event search and filtering
   - Search by payload content, metadata, time range
   - Filter by status (delivered, pending, failed)
   - Useful for debugging and auditing

6. Delivery status webhooks
   - Notify when events are delivered/failed
   - Real-time visibility into delivery health

## Advanced routing and transformation

7. Event routing rules
   - Route events to specific workflows based on payload content
   - Conditional routing (e.g., route high-priority events to premium workflows)

8. Event transformation pipeline
   - Transform payloads before delivery
   - Map fields, enrich data, filter sensitive information

## Performance and scale

9. Event batching API
   - Accept multiple events in a single request
   - Reduce API calls for high-volume scenarios

10. Rate limiting and quotas
    - Per-developer rate limits
    - Quota management for fair usage
    - Clear rate limit headers in responses

## Security and compliance

11. Event encryption at rest
    - Encrypt sensitive event data
    - Support customer-managed keys (CMK)

12. Event retention policies
    - Configurable retention periods
    - Automatic cleanup of old events
    - Compliance-friendly data lifecycle

## Integration features

13. Event subscriptions
    - Subscribe to event types or patterns
    - Pub/sub model for event distribution

14. Event deduplication
    - Detect and handle duplicate events
    - Idempotency keys to prevent duplicate processing

## Most impactful recommendations

Top 3 to prioritize:
1. Event replay API — enables testing and recovery
2. Event tracing/correlation IDs — improves debugging and observability
3. Event schema validation — catches errors early and improves DX

These align with the PRD’s goals and differentiate the solution from basic webhook triggers. Should I draft a detailed spec for any of these?

---

**User**

Provide a /inbox endpoint to list or retrieve undelivered events.



This seems strange. How often will events be undelivered?

---

**Cursor**

The `/inbox` requirement is a bit vague in the PRD. Here are likely scenarios where events would be undelivered:

## When events might be undelivered

1. Workflows/Zaps are paused or disabled
   - Event arrives but no active workflow to deliver to
   - Event sits in inbox until workflows are reactivated

2. Temporary system failures
   - Zapier's delivery system is down
   - Network issues between Triggers API and Zapier's workflow engine
   - Events queue up until service is restored

3. Rate limiting or throttling
   - Too many events for a workflow to process
   - Events back up in the inbox

4. Validation/processing errors
   - Event format doesn't match workflow expectations
   - Delivery attempt fails, event remains in inbox

## The real question: delivery model

The PRD doesn't specify the delivery mechanism. Possible models:

- Push model: Triggers API immediately pushes events to Zapier's workflow engine
  - Inbox would only contain events that failed to push
- Pull model: Zapier's workflow engine polls `/inbox` for new events
  - Inbox acts as a queue of undelivered events
- Hybrid: Push with fallback to inbox if push fails

## Recommendation

Clarify in the PRD:
1. How delivery works (push vs pull vs hybrid)
2. What "undelivered" means (never attempted, attempted but failed, etc.)
3. Expected frequency of undelivered events (rare vs common)

If delivery is reliable, the inbox might be mostly empty and used for edge cases. If it's a polling model, the inbox is the primary queue. This affects architecture decisions (SQS vs direct API calls, etc.).

Should I suggest PRD updates to clarify the delivery mechanism?

---

**User**

Event replay API — enables testing and recovery



What's the difference between replay, and just calling the event api again?

---

**Cursor**

Here are the differences:

## Calling the Event API Again (New Event)
- Creates a new event with a new ID and new timestamp
- Loses original context (original timestamp, original metadata, original event ID)
- May cause duplicate processing if workflows aren't idempotent
- No audit trail linking it to the original event
- Workflows can't distinguish it from a new event

## Event Replay API (Re-deliver Existing Event)
- Preserves the original event identity (same event ID, same original timestamp)
- Maintains original metadata and context
- Can be marked as a replay in delivery metadata
- Supports selective replay (e.g., only to specific workflows that failed)
- Maintains audit trail (e.g., "replayed event X at time Y")
- Enables idempotent handling (workflows can detect and skip already-processed events)

## Example Scenario

**Scenario:** An event was delivered to 3 workflows, but workflow #2 failed.

**Calling Event API again:**
```
POST /events
→ Creates NEW event (ID: event-456, timestamp: now)
→ All 3 workflows process it again (including #1 and #3 that already succeeded)
→ Duplicate processing, lost original context
```

**Replay API:**
```
POST /events/event-123/replay?workflow=workflow-2
→ Re-delivers ORIGINAL event (ID: event-123, original timestamp: 2 hours ago)
→ Only workflow #2 processes it
→ Workflows #1 and #3 can detect it's a replay and skip
→ Audit log: "Replayed event-123 to workflow-2 at 3pm"
```

## Key Benefits of Replay
1. Preserves event identity and original timestamp
2. Selective replay (only failed workflows)
3. Idempotency support (workflows can detect replays)
4. Better audit trail and debugging

Without a replay API, you'd need to manually reconstruct the original event payload and call the API again, losing the original event's identity and context.

```plaintext
POST /events
→ Creates NEW event (ID: event-456, timestamp: now)
→ All 3 workflows process it again (including #1 and #3 that already succeeded)
→ Duplicate processing, lost original context
```

```plaintext
POST /events/event-123/replay?workflow=workflow-2
→ Re-delivers ORIGINAL event (ID: event-123, original timestamp: 2 hours ago)
→ Only workflow #2 processes it
→ Workflows #1 and #3 can detect it's a replay and skip
→ Audit log: "Replayed event-123 to workflow-2 at 3pm"
```

---

**User**

Successful ingestion of events from external sources with a 99.9% reliability rate.



How will we accomplish this?

---

**Cursor**

To achieve 99.9% reliability for event ingestion, use these strategies:

## 1. High availability architecture

**Multi-AZ deployment:**
- Deploy across multiple Availability Zones
- Use Application Load Balancer or API Gateway (multi-AZ by default)
- Lambda functions run across all AZs automatically
- DynamoDB with multi-region replication for critical data

**Target:** Eliminates single points of failure

## 2. Redundancy and failover

**API Gateway + Lambda:**
- API Gateway provides automatic failover
- Lambda has built-in redundancy across AZs
- If one AZ fails, traffic routes to others

**Database redundancy:**
- DynamoDB Global Tables for multi-region replication
- Or DynamoDB with point-in-time recovery enabled

## 3. Retry mechanisms

**Client-side retries:**
- Exponential backoff for transient failures
- Document recommended retry strategies in API docs

**Server-side resilience:**
- Use SQS as a buffer (events go to SQS first, then processed)
- SQS provides automatic retries for failed processing
- Dead Letter Queue (DLQ) for events that fail after max retries

## 4. Monitoring and alerting

**CloudWatch metrics:**
- Track success/failure rates
- Monitor latency, error rates, throttling
- Set alarms for reliability thresholds

**Health checks:**
- Route53 health checks for API endpoints
- Automatic failover if primary region fails

## 5. Rate limiting and throttling

**API Gateway throttling:**
- Prevent overload that causes failures
- Graceful degradation under load
- Return 429 (Too Many Requests) instead of 500 errors

## 6. Data validation and error handling

**Early validation:**
- Validate payloads before storage
- Return clear 4xx errors (client errors don't count against reliability)
- Only count 5xx errors (server failures) against reliability

**Graceful error responses:**
- Always return structured error responses
- Never crash or timeout without response

## 7. Recommended architecture for 99.9% reliability

```
Client → API Gateway → Lambda (validation) → SQS → Lambda (storage) → DynamoDB
                                                      ↓ (on failure)
                                                   DLQ
```

**Why this works:**
- API Gateway: 99.99% SLA
- Lambda: Highly available, auto-scaling
- SQS: 99.5%+ availability, handles retries
- DynamoDB: 99.99% availability SLA

## 8. Additional strategies

**Circuit breakers:**
- Prevent cascading failures
- Fail fast when downstream services are down

**Async processing:**
- Accept events quickly (return 202 Accepted)
- Process asynchronously (improves perceived reliability)

**Idempotency:**
- Accept idempotency keys
- Prevent duplicate processing from retries

## Measuring 99.9% reliability

**Track:**
- Uptime: API is available 99.9% of the time
- Success rate: 99.9% of valid requests are successfully ingested and stored

**Exclude from reliability metric:**
- Client errors (4xx) - these are client issues
- Invalid payloads - these are expected failures

**Count as failures:**
- 5xx server errors
- Timeouts
- Service unavailability

## Realistic target breakdown

- API Gateway: 99.99% uptime
- Lambda: 99.95%+ uptime
- DynamoDB: 99.99% uptime
- Combined: ~99.9% end-to-end (accounting for network, retries, etc.)

This architecture should meet the 99.9% reliability target. Should I draft a detailed technical design document with specific AWS configurations?

```plaintext
Client → API Gateway → Lambda (validation) → SQS → Lambda (storage) → DynamoDB
                                                      ↓ (on failure)
                                                   DLQ
```

---

**User**

**Security:** Ensure secure data transmission and storage, including authentication and authorization mechanisms.



How do we do this? 

---

**Cursor**

Here’s how to implement security for the Triggers API:

## 1. Secure data transmission

**HTTPS/TLS:**
- API Gateway enforces HTTPS (TLS 1.2+)
- Terminate TLS at API Gateway
- Use AWS Certificate Manager (ACM) for SSL certificates
- Redirect HTTP to HTTPS

**Additional transmission security:**
- Require TLS 1.2+ minimum
- Use strong cipher suites
- Consider mTLS for high-security use cases (optional)

## 2. Authentication mechanisms

**API key authentication (recommended for MVP):**
```
Authorization: Bearer <api_key>
```
- Generate API keys per developer/application
- Store hashed keys in DynamoDB (never store plaintext)
- Use AWS Secrets Manager or Parameter Store for key management
- Rotate keys periodically

**OAuth 2.0 (for production scale):**
- Client credentials flow for server-to-server
- Issue short-lived access tokens (JWT)
- Use AWS Cognito or custom OAuth server
- Refresh tokens for long-lived access

**Implementation in API Gateway:**
- Use API Gateway authorizers (Lambda authorizer or API key authorizer)
- Validate tokens/keys before request reaches Lambda
- Return 401 Unauthorized for invalid credentials

## 3. Authorization mechanisms

**Role-based access control (RBAC):**
- Roles: `admin`, `developer`, `readonly`
- Permissions:
  - `events:create` - POST /events
  - `events:read` - GET /inbox, GET /events/:id
  - `events:delete` - DELETE /events/:id
  - `events:replay` - POST /events/:id/replay

**Resource-level authorization:**
- Developers can only access their own events
- Use API keys/claims to scope access
- Validate ownership before operations

**Implementation:**
```python
# In Lambda authorizer or handler
def authorize(event, required_permission):
    api_key = extract_api_key(event)
    user = get_user_from_api_key(api_key)
    
    if required_permission not in user.permissions:
        raise UnauthorizedError()
    
    return user
```

## 4. Secure data storage

**Encryption at rest:**
- DynamoDB: Enable encryption at rest (AWS managed keys or customer-managed KMS)
- S3 (if used): Enable server-side encryption (SSE-S3 or SSE-KMS)
- Lambda environment variables: Encrypt with KMS

**AWS KMS (Key Management Service):**
- Use KMS keys for encryption
- Control key access via IAM policies
- Enable key rotation
- Audit key usage via CloudTrail

**Data classification:**
- Identify sensitive fields (PII, credentials)
- Encrypt sensitive fields before storage
- Consider field-level encryption for highly sensitive data

## 5. API security best practices

**Input validation:**
- Validate all inputs (JSON schema validation)
- Sanitize payloads to prevent injection attacks
- Rate limiting per API key to prevent abuse

**CORS configuration:**
- Configure CORS in API Gateway
- Whitelist specific origins
- Don't use wildcard (`*`) in production

**Request signing (optional, advanced):**
- HMAC signature for request authenticity
- Prevents replay attacks
- Useful for high-security scenarios

## 6. Recommended architecture

```
Client Request
    ↓
API Gateway (HTTPS enforced)
    ↓
Lambda Authorizer (validates API key/token)
    ↓
Lambda Handler (checks permissions, processes request)
    ↓
DynamoDB (encrypted at rest with KMS)
```

## 7. Implementation details

**API Key management:**
```python
# Store in DynamoDB
{
    "api_key_hash": "bcrypt_hash_of_key",
    "user_id": "user_123",
    "permissions": ["events:create", "events:read"],
    "created_at": "2024-01-01",
    "expires_at": "2025-01-01",
    "rate_limit": 1000  # requests per hour
}
```

**Lambda authorizer:**
```python
def lambda_authorizer(event):
    # Extract API key from header
    api_key = event['headers'].get('Authorization', '').replace('Bearer ', '')
    
    # Validate and get user
    user = validate_api_key(api_key)
    
    # Return IAM policy
    return generate_policy(user, 'Allow', event['methodArn'])
```

**DynamoDB encryption:**
- Enable encryption at rest in table settings
- Use AWS managed keys (default) or customer-managed KMS keys
- Encrypt sensitive fields before storing

## 8. Security monitoring and auditing

**CloudTrail:**
- Log all API calls
- Track authentication attempts
- Monitor for suspicious activity

**CloudWatch:**
- Alert on failed authentication attempts
- Monitor rate limit violations
- Track unusual patterns

**AWS WAF (optional):**
- Protect against common attacks (SQL injection, XSS)
- Rate limiting rules
- IP whitelisting/blacklisting

## 9. Compliance considerations

**GDPR/CCPA:**
- Encrypt PII
- Support data deletion requests
- Audit data access

**SOC 2:**
- Encryption at rest and in transit
- Access controls and audit logs
- Regular security reviews

## 10. MVP vs production

**MVP (P0):**
- API key authentication
- HTTPS/TLS
- DynamoDB encryption at rest (AWS managed keys)
- Basic rate limiting

**Production (P1+):**
- OAuth 2.0
- Customer-managed KMS keys
- Advanced rate limiting per key
- Request signing
- WAF protection
- Security audit logs

## Quick implementation checklist

- [ ] Enable HTTPS only in API Gateway
- [ ] Implement API key authentication
- [ ] Store API keys hashed in DynamoDB
- [ ] Enable DynamoDB encryption at rest
- [ ] Add Lambda authorizer for token validation
- [ ] Implement permission checks in handlers
- [ ] Add rate limiting per API key
- [ ] Enable CloudTrail logging
- [ ] Set up CloudWatch alarms for security events

This provides a solid security foundation. Should I draft detailed implementation code for any of these components?

```plaintext
Authorization: Bearer <api_key>
```

```python
# In Lambda authorizer or handler
def authorize(event, required_permission):
    api_key = extract_api_key(event)
    user = get_user_from_api_key(api_key)
    
    if required_permission not in user.permissions:
        raise UnauthorizedError()
    
    return user
```

```plaintext
Client Request
    ↓
API Gateway (HTTPS enforced)
    ↓
Lambda Authorizer (validates API key/token)
    ↓
Lambda Handler (checks permissions, processes request)
    ↓
DynamoDB (encrypted at rest with KMS)
```

```python
# Store in DynamoDB
{
    "api_key_hash": "bcrypt_hash_of_key",
    "user_id": "user_123",
    "permissions": ["events:create", "events:read"],
    "created_at": "2024-01-01",
    "expires_at": "2025-01-01",
    "rate_limit": 1000  # requests per hour
}
```

```python
def lambda_authorizer(event):
    # Extract API key from header
    api_key = event['headers'].get('Authorization', '').replace('Bearer ', '')
    
    # Validate and get user
    user = validate_api_key(api_key)
    
    # Return IAM policy
    return generate_policy(user, 'Allow', event['methodArn'])
```

---

**User**

Which python libraries will we use

---

**Cursor**

Recommended Python libraries for the Zapier Triggers API:

## Core API framework

**FastAPI (recommended):**
- Fast, async support
- Automatic OpenAPI/Swagger docs
- Built-in request validation
- Type hints
- Works well with Lambda

**Alternative: Flask**
- Simpler, synchronous
- More mature ecosystem
- Requires more manual setup

## AWS integration

**boto3:**
- AWS SDK for Python
- DynamoDB, SQS, S3, KMS, Secrets Manager
- Essential for AWS services

**mangum (if using FastAPI):**
- ASGI adapter for Lambda
- Converts FastAPI app to Lambda handler

## Database and storage

**boto3 (DynamoDB):**
- Native DynamoDB operations
- Or use a DynamoDB wrapper

**pydantic:**
- Data validation and serialization
- Type-safe models
- Works well with FastAPI

## Authentication and security

**python-jose:**
- JWT encoding/decoding (if using OAuth)
- Token validation

**passlib:**
- Password/API key hashing
- bcrypt for secure hashing

**cryptography:**
- Encryption/decryption
- KMS integration helpers

## Validation and serialization

**pydantic:**
- Request/response validation
- JSON schema generation
- Type coercion

**jsonschema:**
- JSON schema validation (if needed beyond pydantic)

## HTTP and requests

**httpx or requests:**
- Outbound HTTP calls (if needed)
- httpx supports async

## Environment and configuration

**python-dotenv:**
- Load environment variables from .env
- Useful for local development

**pydantic-settings:**
- Type-safe settings management
- Environment variable parsing

## Logging and monitoring

**structlog:**
- Structured logging
- Better for CloudWatch

**python-json-logger:**
- JSON-formatted logs for CloudWatch

## Testing

**pytest:**
- Testing framework

**pytest-asyncio:**
- Async test support (if using FastAPI)

**moto:**
- Mock AWS services (DynamoDB, SQS, etc.)
- Local testing without AWS

**responses:**
- Mock HTTP requests

## Utilities

**python-dateutil:**
- Date/time parsing and manipulation

**uuid:**
- Event ID generation (built-in)

**tenacity:**
- Retry logic with exponential backoff

## Recommended stack

**Minimum viable (P0):**
```python
# requirements.txt
fastapi>=0.104.0
mangum>=0.17.0
boto3>=1.29.0
pydantic>=2.5.0
python-dotenv>=1.0.0
structlog>=23.2.0
pytest>=7.4.0
moto>=5.0.0
```

**Production-ready (P1+):**
```python
# requirements.txt
fastapi>=0.104.0
mangum>=0.17.0
boto3>=1.29.0
pydantic>=2.5.0
pydantic-settings>=2.1.0
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
cryptography>=41.0.0
structlog>=23.2.0
tenacity>=8.2.0
httpx>=0.25.0
pytest>=7.4.0
pytest-asyncio>=0.21.0
moto>=5.0.0
```

## Example project structure

```
project/
├── requirements.txt
├── src/
│   ├── main.py              # FastAPI app
│   ├── handlers/
│   │   ├── events.py        # /events endpoint
│   │   └── inbox.py         # /inbox endpoint
│   ├── models/
│   │   └── event.py         # Pydantic models
│   ├── auth/
│   │   └── api_key.py       # API key validation
│   ├── storage/
│   │   └── dynamodb.py      # DynamoDB operations
│   └── utils/
│       └── logger.py         # Logging setup
└── tests/
    └── test_events.py
```

## Key library choices explained

**FastAPI over Flask:**
- Better async support (important for Lambda)
- Automatic API documentation
- Built-in validation
- Better type safety

**mangum:**
- Required to run FastAPI in Lambda
- Handles ASGI to Lambda event conversion

**boto3:**
- Official AWS SDK
- Required for all AWS service interactions

**pydantic:**
- Type-safe data models
- Automatic validation
- Works seamlessly with FastAPI

**structlog:**
- Better CloudWatch integration
- Structured logs are easier to query

This stack provides a solid foundation for the API. Should I create a sample `requirements.txt` and basic project structure?

```python
# requirements.txt
fastapi>=0.104.0
mangum>=0.17.0
boto3>=1.29.0
pydantic>=2.5.0
python-dotenv>=1.0.0
structlog>=23.2.0
pytest>=7.4.0
moto>=5.0.0
```

```python
# requirements.txt
fastapi>=0.104.0
mangum>=0.17.0
boto3>=1.29.0
pydantic>=2.5.0
pydantic-settings>=2.1.0
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
cryptography>=41.0.0
structlog>=23.2.0
tenacity>=8.2.0
httpx>=0.25.0
pytest>=7.4.0
pytest-asyncio>=0.21.0
moto>=5.0.0
```

```plaintext
project/
├── requirements.txt
├── src/
│   ├── main.py              # FastAPI app
│   ├── handlers/
│   │   ├── events.py        # /events endpoint
│   │   └── inbox.py         # /inbox endpoint
│   ├── models/
│   │   └── event.py         # Pydantic models
│   ├── auth/
│   │   └── api_key.py       # API key validation
│   ├── storage/
│   │   └── dynamodb.py      # DynamoDB operations
│   └── utils/
│       └── logger.py         # Logging setup
└── tests/
    └── test_events.py
```

