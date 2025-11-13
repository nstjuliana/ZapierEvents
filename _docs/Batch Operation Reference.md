# Batch Operations Quick Reference

A concise reference guide for the batch operations API endpoints. For detailed documentation, see [Event Batching API](event-batching.md).

## Overview

Batch operations allow you to process multiple events in a single API call:

- **POST /events/batch** - Create multiple events
- **PATCH /events/batch** - Update multiple events
- **DELETE /events/batch** - Delete multiple events

**Key Features:**
- Up to 100 events per request
- Best-effort semantics (continues even if some items fail)
- Detailed per-item results with error information
- Automatic delivery attempts for created events
- Ownership validation for update/delete operations

---

## POST /events/batch - Batch Create Events

**Use when:** Creating multiple events at once with automatic delivery attempts.

### Request

```http
POST /events/batch
Authorization: Bearer <your_api_key>
Content-Type: application/json

{
  "events": [
    {
      "event_type": "order.created",
      "payload": {
        "order_id": "12345",
        "amount": 99.99
      },
      "metadata": {
        "source": "api"
      },
      "idempotency_key": "order-12345-2024-01-15"
    },
    {
      "event_type": "user.registered",
      "payload": {
        "user_id": "67890",
        "email": "user@example.com"
      }
    }
  ]
}
```

### Response

```json
{
  "results": [
    {
      "index": 0,
      "success": true,
      "event": {
        "event_id": "evt_abc123xyz456",
        "event_type": "order.created",
        "status": "delivered",
        "created_at": "2024-01-15T10:30:01Z",
        "delivered_at": "2024-01-15T10:30:01Z",
        "delivery_attempts": 1,
        "payload": {
          "order_id": "12345",
          "amount": 99.99
        },
        "metadata": {
          "source": "api"
        },
        "idempotency_key": "order-12345-2024-01-15",
        "message": "Event created and delivered"
      }
    },
    {
      "index": 1,
      "success": true,
      "event": {
        "event_id": "evt_def789uvw012",
        "event_type": "user.registered",
        "status": "pending",
        "created_at": "2024-01-15T10:30:02Z",
        "delivery_attempts": 0,
        "payload": {
          "user_id": "67890",
          "email": "user@example.com"
        },
        "message": "Event created"
      }
    }
  ],
  "summary": {
    "total": 2,
    "successful": 2,
    "failed": 0
  }
}
```

### Key Features

- Up to 100 events per request
- Automatic delivery attempts for each event
- Per-event idempotency keys prevent duplicates
- Continues processing even if some events fail
- Returns existing event if idempotency key matches

---

## PATCH /events/batch - Batch Update Events

**Use when:** Updating multiple events' payload, metadata, or idempotency keys.

**Supports two modes:**
1. **List Mode** (traditional): Provide a list of event updates with specific event IDs
2. **Filter Mode** (new): Use query parameters to filter events and apply updates to all matches

### List Mode Request

```http
PATCH /events/batch
Authorization: Bearer <your_api_key>
Content-Type: application/json

{
  "events": [
    {
      "event_id": "evt_abc123xyz456",
      "payload": {
        "order_id": "12345",
        "amount": 150.00,
        "status": "updated"
      },
      "metadata": {
        "updated_at": "2024-01-15T11:00:00Z"
      }
    },
    {
      "event_id": "evt_def789uvw012",
      "idempotency_key": "user-67890-updated"
    }
  ]
}
```

### Filter Mode Request

```http
PATCH /events/batch?payload.status=pending&payload.amount[gte]=100
Authorization: Bearer <your_api_key>
Content-Type: application/json

{
  "payload": {
    "status": "processing",
    "updated": true
  },
  "metadata": {
    "batch_updated": "2024-01-15T11:00:00Z"
  }
}
```

**Filter Mode:**
- Use query parameters (e.g., `?payload.field=value`) to select events
- Provide a single `payload`, `metadata`, and/or `idempotency_key` to apply to ALL matching events
- Supports all filter operators: `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `contains`, `startswith`
- Limited to 100 matching events per request
- See [Event Filtering Documentation](event-filtering.md) for complete filter syntax

### Response

```json
{
  "results": [
    {
      "index": 0,
      "success": true,
      "event": {
        "event_id": "evt_abc123xyz456",
        "event_type": "order.created",
        "status": "pending",
        "created_at": "2024-01-15T10:30:01Z",
        "delivery_attempts": 0,
        "payload": {
          "order_id": "12345",
          "amount": 150.00,
          "status": "updated"
        },
        "metadata": {
          "updated_at": "2024-01-15T11:00:00Z"
        },
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
```

### Key Features

- **List Mode**: Update specific events by event_id
- **Filter Mode**: Update all events matching filter criteria
- Update `payload`, `metadata`, or `idempotency_key`
- Ownership validation (can only update your events)
- Auto-redelivers events that were previously delivered
- At least one field must be provided per update
- Events with status "delivered" or "replayed" reset to "pending"

### Filter Mode Examples

```bash
# Update all pending high-value orders
PATCH /events/batch?status=pending&payload.amount[gte]=1000
Body: {"metadata": {"priority": "high"}}

# Update all events from a specific source
PATCH /events/batch?metadata.source=legacy_system
Body: {"metadata": {"migrated": true}}

# Update all failed payment events
PATCH /events/batch?event_type[startswith]=payment.&status=failed
Body: {"payload": {"retry_scheduled": true}}
```

---

## DELETE /events/batch - Batch Delete Events

**Use when:** Removing multiple events from the system.

**Supports two modes:**
1. **List Mode** (traditional): Provide a list of event IDs to delete
2. **Filter Mode** (new): Use query parameters to filter and delete matching events
3. **Combined Mode**: Combine filter results with specific event IDs (union)

### List Mode Request

```http
DELETE /events/batch
Authorization: Bearer <your_api_key>
Content-Type: application/json

{
  "event_ids": [
    "evt_abc123xyz456",
    "evt_def789uvw012"
  ]
}
```

### Filter Mode Request

```http
DELETE /events/batch?status=failed&payload.error[contains]=timeout
Authorization: Bearer <your_api_key>
```

### Combined Mode Request

```http
DELETE /events/batch?status=failed
Authorization: Bearer <your_api_key>
Content-Type: application/json

{
  "event_ids": [
    "evt_abc123xyz456"
  ]
}
```

**Filter Mode:**
- Use query parameters to select events to delete
- Body with `event_ids` is optional
- If both filters and `event_ids` provided, deletes the union of both sets
- Limited to 100 total events per request
- See [Event Filtering Documentation](event-filtering.md) for complete filter syntax

### Response

```json
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
      "success": true,
      "event_id": "evt_def789uvw012",
      "message": "Event already deleted (idempotent)"
    }
  ],
  "summary": {
    "total": 2,
    "successful": 2,
    "failed": 0
  }
}
```

### Key Features

- **List Mode**: Delete specific events by event_id
- **Filter Mode**: Delete all events matching filter criteria
- **Combined Mode**: Delete union of filtered events + specific event_ids
- Ownership validation (can only delete your events)
- Idempotent - deleting non-existent events succeeds
- Up to 100 events per request
- Safe to retry without side effects

### Filter Mode Examples

```bash
# Delete all failed events
DELETE /events/batch?status=failed

# Delete all events from a specific source older than a date
DELETE /events/batch?metadata.source=legacy&created_before=2024-01-01T00:00:00Z

# Delete events matching specific payload criteria
DELETE /events/batch?payload.status=cancelled&payload.refunded=true

# Combine filter with specific event IDs (union)
DELETE /events/batch?status=failed
Body: {"event_ids": ["evt_specific123"]}
```

---

## Common Patterns

### Error Handling

```javascript
const response = await fetch('/events/batch', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer your_api_key',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({ events: [...] })
});

const data = await response.json();

// Check overall success
if (data.summary.failed > 0) {
  console.log(`${data.summary.failed} items failed`);
  
  // Handle individual failures
  data.results.forEach((result) => {
    if (!result.success) {
      console.log(`Item ${result.index} failed: ${result.error.message}`);
    }
  });
}
```

### Retry Logic

```javascript
// Collect failed items for retry
const failedItems = data.results
  .filter(result => !result.success)
  .map(result => originalRequest.events[result.index]);

// Retry with just the failed items
if (failedItems.length > 0) {
  const retryRequest = { events: failedItems };
  // Make another request...
}
```

### Python Example

```python
import requests

response = requests.post(
    'https://api.triggers.zapier.com/events/batch',
    headers={
        'Authorization': 'Bearer your_api_key',
        'Content-Type': 'application/json'
    },
    json={
        'events': [
            {
                'event_type': 'order.created',
                'payload': {'order_id': '123', 'amount': 99.99}
            }
        ]
    }
)

data = response.json()

# Check results
if data['summary']['failed'] > 0:
    print(f"{data['summary']['failed']} items failed")
    for result in data['results']:
        if not result['success']:
            print(f"Item {result['index']} failed: {result['error']['message']}")
```

---

## Performance Tips

- **Batch size:** 10-50 items typically optimal for balance of throughput and error isolation
- **Idempotency:** Use descriptive keys for duplicate prevention (e.g., "order-12345-2024-01-15")
- **Monitoring:** Check `summary.failed` for partial failures
- **Rate limits:** Batch operations count as single API calls regardless of item count
- **Error handling:** Always check both `summary` and individual `results` for complete status

---

## Error Codes

| Code | Description |
|------|-------------|
| `VALIDATION_ERROR` | Invalid event data (missing required fields, wrong types) |
| `STORAGE_ERROR` | Failed to store/delete event in database |
| `DUPLICATE` | Event with same idempotency key already exists |
| `NOT_FOUND` | Event with specified event_id does not exist |
| `FORBIDDEN` | User does not own the event (ownership validation) |

---

## HTTP Status Codes

| Code | Description |
|------|-------------|
| `201` | Batch create successful (some or all items may have failed) |
| `200` | Batch update/delete successful |
| `400` | Invalid request (malformed JSON, validation errors, size limits) |
| `401` | Authentication required |
| `403` | Authorization failed |
| `500` | Internal server error |
