# User Flow Documentation

## Introduction

This document defines the user journeys through the Zapier Triggers API, a unified RESTful interface for sending real-time events into Zapier. The API enables event-driven automation by allowing systems to send events that can trigger multiple workflows simultaneously, with durable storage and delivery guarantees.

**Scope:**
- This document covers P0 (must-have) and P1 (should-have) features
- All interactions are API-based (no UI components)
- Delivery model: Hybrid push/pull (attempt push first, fallback to /inbox for polling)

**Key Features Documented:**
- Event ingestion via POST /events
- Event persistence and delivery tracking
- Inbox endpoint for undelivered events
- Event replay API for testing and recovery
- Event status tracking and retrieval

**Actors:**
- **Developer**: External system developer sending events to the API
- **Zapier System**: Internal Zapier workflow engine that consumes events
- **Triggers API**: The API service that ingests, stores, and delivers events

---

## User Journey 1: First-Time Setup

**Goal:** Developer obtains API credentials and understands how to authenticate with the API.

**Actors:** Developer, Triggers API

### Flow Sequence

1. **Developer Registration**
   - Developer registers for API access (external process, not part of API)
   - Receives API key and base URL for the Triggers API
   - API key format: `Bearer <api_key>` in Authorization header

2. **Initial Authentication Test**
   - Developer makes test request to verify API key
   - **Endpoint:** `GET /health` or `GET /events` (with empty result)
   - **Request Headers:**
     ```
     Authorization: Bearer <api_key>
     Content-Type: application/json
     ```
   - **Success Response:** `200 OK` confirms authentication works
   - **Error Response:** `401 Unauthorized` if API key is invalid

3. **Understanding API Structure**
   - Developer reviews API documentation
   - Learns about:
     - Event payload structure
     - Required vs optional fields
     - Delivery model (push with fallback to inbox)

### State Transitions

- **Unauthenticated** → **Authenticated** (upon successful API key validation)
- Developer's API key is stored in system with associated permissions

### Error Scenarios

- **Invalid API Key:** Returns `401 Unauthorized`
- **Expired API Key:** Returns `401 Unauthorized` with expiration message
- **Rate Limit Exceeded:** Returns `429 Too Many Requests` (if applicable)

### Connections to Other Journeys

- Required prerequisite for all other journeys
- API key must be valid for any subsequent API calls

---

## User Journey 2: Regular Event Sending

**Goal:** Developer successfully sends an event that is immediately delivered to Zapier workflows.

**Actors:** Developer, Triggers API, Zapier System

### Flow Sequence

1. **Event Creation**
   - Developer's application creates an event payload
   - **Endpoint:** `POST /events`
   - **Request Headers:**
     ```
     Authorization: Bearer <api_key>
     Content-Type: application/json
     ```
   - **Request Body:**
     ```json
     {
       "event_type": "order.created",
       "payload": {
         "order_id": "12345",
         "customer_id": "67890",
         "amount": 99.99
       },
       "metadata": {
         "source": "ecommerce-platform",
         "timestamp": "2024-01-15T10:30:00Z"
       }
     }
     ```

2. **Event Ingestion**
   - Triggers API receives and validates the request
   - Validates JSON structure and required fields
   - Generates unique event ID
   - Stores event with metadata (ID, timestamp, payload, status)

3. **Immediate Push Delivery Attempt**
   - Triggers API attempts to push event to Zapier workflow engine
   - Zapier receives event and routes to matching workflows
   - Multiple workflows can consume the same event

4. **Success Response**
   - **Response:** `202 Accepted` or `200 OK`
   - **Response Body:**
     ```json
     {
       "event_id": "evt_abc123xyz",
       "status": "delivered",
       "ingested_at": "2024-01-15T10:30:01Z",
       "delivered_at": "2024-01-15T10:30:01Z",
       "workflows_triggered": 3
     }
     ```

5. **Event Storage**
   - Event is stored in persistent storage (DynamoDB)
   - Status marked as "delivered"
   - Original timestamp and metadata preserved

### State Transitions

- **Event Created** → **Validated** → **Stored** → **Push Attempted** → **Delivered**
- Event status: `pending` → `delivered`

### Error Scenarios

- **Invalid Payload:** Returns `400 Bad Request` with validation errors
- **Authentication Failure:** Returns `401 Unauthorized`
- **Rate Limit Exceeded:** Returns `429 Too Many Requests`
- **Server Error:** Returns `500 Internal Server Error` (triggers Journey 3)

### Connections to Other Journeys

- If push fails → transitions to **Journey 3: Failed Delivery & Recovery**
- Event can be replayed later via **Journey 4: Event Replay**
- Event status can be checked via **Journey 5: Event Monitoring**

---

## User Journey 3: Failed Delivery & Recovery

**Goal:** Handle events that fail to push immediately, storing them in /inbox for Zapier to poll and retrieve.

**Actors:** Developer, Triggers API, Zapier System

### Flow Sequence

1. **Event Ingestion (Same as Journey 2)**
   - Developer sends event via `POST /events`
   - Event is validated and stored
   - Event ID and timestamp are generated

2. **Push Delivery Attempt Fails**
   - Triggers API attempts to push event to Zapier
   - Push fails due to:
     - Zapier workflow engine unavailable
     - Network timeout
     - Workflow paused/disabled
     - Rate limiting on Zapier side
   - **Response:** `202 Accepted` (event accepted, delivery pending)
   - **Response Body:**
     ```json
     {
       "event_id": "evt_abc123xyz",
       "status": "pending",
       "ingested_at": "2024-01-15T10:30:01Z",
       "delivered_at": null,
       "message": "Event stored. Delivery will be retried."
     }
     ```

3. **Event Stored in Inbox**
   - Event is stored with status `pending` or `undelivered`
   - Event is added to inbox queue for polling
   - Retry logic may attempt push again (P1 feature)

4. **Zapier Polls Inbox**
   - Zapier system periodically polls `/inbox` endpoint
   - **Endpoint:** `GET /inbox`
   - **Request Headers:**
     ```
     Authorization: Bearer <zapier_api_key>
     ```
   - **Query Parameters:**
     ```
     ?limit=100&status=pending
     ```
   - **Response:** `200 OK`
   - **Response Body:**
     ```json
     {
       "events": [
         {
           "event_id": "evt_abc123xyz",
           "event_type": "order.created",
           "payload": { ... },
           "metadata": { ... },
           "ingested_at": "2024-01-15T10:30:01Z",
           "status": "pending"
         }
       ],
       "next_cursor": "cursor_token"
     }
     ```

5. **Zapier Processes Events**
   - Zapier retrieves events from inbox
   - Routes events to appropriate workflows
   - Workflows process events

6. **Event Acknowledgment**
   - After successful processing, Zapier acknowledges events
   - **Endpoint:** `POST /events/{event_id}/acknowledge` or `DELETE /events/{event_id}`
   - **Request Headers:**
     ```
     Authorization: Bearer <zapier_api_key>
     ```
   - **Response:** `200 OK` or `204 No Content`
   - Event status updated to `delivered` or event deleted from inbox

### State Transitions

- **Event Created** → **Validated** → **Stored** → **Push Failed** → **In Inbox** → **Polled** → **Acknowledged/Deleted**
- Event status: `pending` → `undelivered` → `delivered` (or deleted)

### Error Scenarios

- **Push Fails:** Event stored in inbox, status set to `pending`
- **Inbox Poll Fails:** Zapier retries polling (exponential backoff)
- **Acknowledgment Fails:** Event remains in inbox, may be reprocessed
- **Event Expired:** Events may have TTL, expired events removed from inbox

### Retry Logic (P1 Feature)

- Triggers API may retry push delivery with exponential backoff
- After max retries, event remains in inbox for polling
- Retry attempts tracked in event metadata

### Connections to Other Journeys

- Originates from **Journey 2** when push fails
- Events in inbox can be replayed via **Journey 4: Event Replay**
- Inbox status can be monitored via **Journey 5: Event Monitoring**

---

## User Journey 4: Event Replay

**Goal:** Re-deliver an existing event, preserving original event identity and context, for testing or recovery purposes.

**Actors:** Developer, Triggers API, Zapier System

### Flow Sequence

1. **Identify Event to Replay**
   - Developer identifies event that needs replaying
   - May have failed delivery, or needs testing
   - Developer has event ID from previous response or monitoring

2. **Request Event Replay**
   - **Endpoint:** `POST /events/{event_id}/replay`
   - **Request Headers:**
     ```
     Authorization: Bearer <api_key>
     Content-Type: application/json
     ```
   - **Request Body (Optional):**
     ```json
     {
       "workflow_id": "workflow_123",  // Optional: replay to specific workflow
       "reason": "testing"  // Optional: reason for replay
     }
     ```

3. **Event Retrieval and Validation**
   - Triggers API retrieves original event from storage
   - Validates event exists and is replayable
   - Preserves original event ID, timestamp, and metadata

4. **Replay Delivery**
   - Original event is re-delivered with replay flag
   - If `workflow_id` specified, only that workflow receives event
   - If not specified, all matching workflows receive event
   - Replay metadata added: `replayed_at`, `replay_reason`, `original_event_id`

5. **Success Response**
   - **Response:** `200 OK`
   - **Response Body:**
     ```json
     {
       "event_id": "evt_abc123xyz",
       "original_event_id": "evt_abc123xyz",
       "status": "replayed",
       "replayed_at": "2024-01-15T14:30:00Z",
       "original_ingested_at": "2024-01-15T10:30:01Z",
       "workflows_triggered": 1
     }
     ```

6. **Workflow Processing**
   - Workflows receive event with replay indicator
   - Workflows can detect replay and handle idempotently
   - Original event context preserved (timestamp, payload)

### State Transitions

- **Original Event** → **Replay Requested** → **Replay Delivered** → **Workflow Processed**
- Event status: `delivered`/`failed` → `replaying` → `replayed`

### Error Scenarios

- **Event Not Found:** Returns `404 Not Found`
- **Event Not Replayable:** Returns `400 Bad Request` (e.g., event too old, already replayed max times)
- **Replay Delivery Fails:** Event may be stored in inbox (same as Journey 3)
- **Invalid Workflow ID:** Returns `400 Bad Request` if specified workflow doesn't exist

### Key Differences from Calling POST /events Again

- **Preserves Original Identity:** Same event ID, original timestamp maintained
- **Selective Replay:** Can target specific workflows that failed
- **Audit Trail:** Replay actions logged separately from original event
- **Idempotency:** Workflows can detect and skip already-processed events

### Connections to Other Journeys

- Often used after **Journey 3** when events fail to deliver
- Replay status can be monitored via **Journey 5: Event Monitoring**
- Replayed events follow same delivery flow as **Journey 2** or **Journey 3**

---

## User Journey 5: Event Monitoring

**Goal:** Developer checks event status, retrieves event details, and monitors delivery health.

**Actors:** Developer, Triggers API

### Flow Sequence

1. **Check Event Status**
   - Developer wants to verify event was delivered
   - **Endpoint:** `GET /events/{event_id}`
   - **Request Headers:**
     ```
     Authorization: Bearer <api_key>
     ```
   - **Response:** `200 OK`
   - **Response Body:**
     ```json
     {
       "event_id": "evt_abc123xyz",
       "event_type": "order.created",
       "status": "delivered",
       "ingested_at": "2024-01-15T10:30:01Z",
       "delivered_at": "2024-01-15T10:30:01Z",
       "payload": { ... },
       "metadata": { ... },
       "workflows_triggered": 3,
       "delivery_attempts": 1
     }
     ```

2. **List Recent Events**
   - Developer wants to see recent events
   - **Endpoint:** `GET /events`
   - **Query Parameters:**
     ```
     ?limit=50&status=delivered&since=2024-01-15T00:00:00Z
     ```
   - **Response:** `200 OK`
   - **Response Body:**
     ```json
     {
       "events": [
         {
           "event_id": "evt_abc123xyz",
           "event_type": "order.created",
           "status": "delivered",
           "ingested_at": "2024-01-15T10:30:01Z",
           ...
         }
       ],
       "next_cursor": "cursor_token",
       "total": 150
     }
     ```

3. **Check Inbox Status**
   - Developer wants to see undelivered events
   - **Endpoint:** `GET /inbox`
   - **Query Parameters:**
     ```
     ?status=pending&limit=100
     ```
   - **Response:** `200 OK`
   - **Response Body:**
     ```json
     {
       "events": [
         {
           "event_id": "evt_xyz789abc",
           "event_type": "order.created",
           "status": "pending",
           "ingested_at": "2024-01-15T11:00:00Z",
           "delivery_attempts": 3,
           "last_attempt_at": "2024-01-15T11:05:00Z"
         }
       ],
       "pending_count": 5
     }
     ```

4. **Filter by Status**
   - Developer filters events by delivery status
   - **Status Values:**
     - `pending`: Event ingested, delivery not yet attempted
     - `delivered`: Event successfully delivered to workflows
     - `undelivered`: Event in inbox, push failed
     - `replayed`: Event was replayed
     - `failed`: Event delivery failed after max retries

5. **Monitor Delivery Health**
   - Developer tracks delivery metrics
   - Can identify patterns (e.g., many events in inbox)
   - Uses status information to troubleshoot issues

### State Transitions

- No state transitions (read-only operations)
- Developer views current state of events

### Error Scenarios

- **Event Not Found:** Returns `404 Not Found`
- **Invalid Query Parameters:** Returns `400 Bad Request`
- **Unauthorized Access:** Returns `401 Unauthorized` or `403 Forbidden`
- **Rate Limit Exceeded:** Returns `429 Too Many Requests`

### Status Tracking (P1 Feature)

- Events track delivery attempts
- Timestamps for each delivery attempt
- Last attempt timestamp
- Retry count visible in event details

### Connections to Other Journeys

- Used to verify success of **Journey 2: Regular Event Sending**
- Identifies events that need attention from **Journey 3: Failed Delivery & Recovery**
- Helps identify events to replay in **Journey 4: Event Replay**
- Provides visibility into overall system health

---

## Cross-Journey Connections

### Event Lifecycle

```
Journey 1 (Setup)
    ↓
Journey 2 (Send Event)
    ├─→ Success → Journey 5 (Monitor)
    └─→ Failure → Journey 3 (Inbox Recovery)
                    ├─→ Success → Journey 5 (Monitor)
                    └─→ Still Failed → Journey 4 (Replay)
                                        └─→ Journey 5 (Monitor)
```

### Common Patterns

1. **Happy Path:** Journey 1 → Journey 2 → Journey 5
2. **Recovery Path:** Journey 1 → Journey 2 → Journey 3 → Journey 5
3. **Testing Path:** Journey 1 → Journey 2 → Journey 4 → Journey 5
4. **Troubleshooting Path:** Journey 5 → Journey 4 → Journey 5

### Key Endpoints Summary

- `POST /events` - Ingest new events (Journey 2, 3)
- `GET /events` - List events (Journey 5)
- `GET /events/{id}` - Get event details (Journey 5)
- `POST /events/{id}/replay` - Replay event (Journey 4)
- `GET /inbox` - List undelivered events (Journey 3, 5)
- `POST /events/{id}/acknowledge` or `DELETE /events/{id}` - Acknowledge/delete event (Journey 3)

---

## Notes

- All endpoints require authentication via `Authorization: Bearer <api_key>` header
- All timestamps are in ISO 8601 format (UTC)
- Event IDs are unique and immutable
- Events are stored durably and can be retrieved by ID
- Delivery status is tracked and visible via monitoring endpoints
- The hybrid push/pull model ensures events are never lost

