# Event Batching API

This document describes the batch operations feature for the Zapier Triggers API, which allows processing multiple events in a single API call for improved performance and efficiency.

## Overview

The batch API provides three main operations:

- **POST /events/batch** - Create multiple events
- **PATCH /events/batch** - Update multiple events
- **DELETE /events/batch** - Delete multiple events

All batch operations follow the same design principles:

- **Best-effort semantics**: Operations continue even if individual items fail
- **Detailed responses**: Each item returns success/failure status with specific error details
- **Idempotent behavior**: Safe to retry failed operations
- **Ownership validation**: Update/delete operations respect user ownership

## Batch Size Limits

- Maximum **100 events** per batch request
- Internally chunked into DynamoDB batches of 25 items
- Recommended batch sizes: 10-50 items for optimal performance

## Authentication

All batch endpoints require the same authentication as individual endpoints:

```bash
Authorization: Bearer <your_api_key>
Content-Type: application/json
```

## POST /events/batch - Batch Create Events

Create multiple events in a single request with automatic delivery attempts.

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
        "customer_id": "67890",
        "amount": 99.99
      },
      "metadata": {
        "source": "ecommerce-platform",
        "version": "1.0"
      },
      "idempotency_key": "order-12345-2024-01-15"
    },
    {
      "event_type": "order.updated",
      "payload": {
        "order_id": "12345",
        "status": "shipped"
      }
    }
  ]
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `events` | Array | Yes | List of events to create (1-100 items) |
| `event_type` | String | Yes | Event type identifier (e.g., "order.created") |
| `payload` | Object | Yes | Event data payload (any valid JSON) |
| `metadata` | Object | No | Optional metadata for the event |
| `idempotency_key` | String | No | Client-provided key to prevent duplicates |

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
          "customer_id": "67890",
          "amount": 99.99
        },
        "metadata": {
          "source": "ecommerce-platform",
          "version": "1.0"
        },
        "idempotency_key": "order-12345-2024-01-15",
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
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `results` | Array | Individual results for each item in the request |
| `index` | Integer | Position in the original request array (0-based) |
| `success` | Boolean | Whether this item was processed successfully |
| `event` | Object | Event details (only present if success=true) |
| `error` | Object | Error details (only present if success=false) |
| `summary` | Object | Overall statistics for the batch operation |

### Error Codes

| Code | Description |
|------|-------------|
| `VALIDATION_ERROR` | Invalid event data (missing required fields, wrong types) |
| `STORAGE_ERROR` | Failed to store event in database |
| `DUPLICATE` | Event with same idempotency key already exists |

### Idempotency Behavior

- Each event can have its own `idempotency_key`
- If a duplicate key is found, returns the existing event as successful
- Prevents duplicate processing for retries and network issues

## PATCH /events/batch - Batch Update Events

Update multiple events with ownership validation and automatic redelivery.

### Request

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
        "amount": 150.00
      },
      "metadata": {
        "updated": true
      }
    },
    {
      "event_id": "evt_def789uvw012",
      "idempotency_key": "order-67890-2024-01-15"
    }
  ]
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `events` | Array | Yes | List of events to update (1-100 items) |
| `event_id` | String | Yes | Event ID to update (format: evt_xxxxxxxxxxx) |
| `payload` | Object | No | Updated event payload |
| `metadata` | Object | No | Updated event metadata (null to remove) |
| `idempotency_key` | String | No | Updated idempotency key (null to remove) |

*Note: At least one of `payload`, `metadata`, or `idempotency_key` must be provided.*

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
        "payload": {
          "order_id": "12345",
          "amount": 150.00
        },
        "metadata": {
          "updated": true
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

### Redelivery Logic

- If an event has status "delivered" or "replayed", updating it resets status to "pending"
- Updated events are automatically queued for redelivery via SQS
- This ensures Zapier workflows receive the updated event data

### Error Codes

| Code | Description |
|------|-------------|
| `NOT_FOUND` | Event with specified event_id does not exist |
| `FORBIDDEN` | User does not own the event (ownership validation) |
| `VALIDATION_ERROR` | Invalid update data or no fields provided |

## DELETE /events/batch - Batch Delete Events

Delete multiple events with ownership validation and idempotent behavior.

### Request

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

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `event_ids` | Array | Yes | List of event IDs to delete (1-100 items) |

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
```

### Idempotent Behavior

- Deleting non-existent events returns success (idempotent delete)
- Safe to retry delete operations without side effects

### Error Codes

| Code | Description |
|------|-------------|
| `FORBIDDEN` | User does not own the event (ownership validation) |
| `STORAGE_ERROR` | Failed to delete event from database |

## Common Error Responses

All batch endpoints return detailed error information:

```json
{
  "error": {
    "code": 400,
    "message": "batch size cannot exceed 100 events"
  }
}
```

### HTTP Status Codes

| Code | Description |
|------|-------------|
| `201` | Batch create successful (some or all items may have failed) |
| `200` | Batch update/delete successful |
| `400` | Invalid request (malformed JSON, validation errors, size limits) |
| `401` | Authentication required |
| `403` | Authorization failed (ownership checks) |
| `500` | Internal server error |

## Performance Considerations

### Batch Size Recommendations

- **Small batches (1-10)**: Good for real-time processing, low latency
- **Medium batches (10-50)**: Best balance of throughput and error isolation
- **Large batches (50-100)**: Maximum throughput for bulk operations

### Rate Limiting

Batch operations count toward your API rate limits. Each batch request counts as one API call, regardless of the number of items.

### Database Performance

- Events are processed in DynamoDB batches of 25 items
- Failed batches don't block successful items
- All operations are eventually consistent

## Example Client Code

### Python

```python
import requests

# Batch create events
response = requests.post(
    "https://api.triggers.zapier.com/events/batch",
    headers={
        "Authorization": "Bearer your_api_key",
        "Content-Type": "application/json"
    },
    json={
        "events": [
            {
                "event_type": "order.created",
                "payload": {"order_id": "123", "amount": 99.99}
            },
            {
                "event_type": "order.updated",
                "payload": {"order_id": "123", "status": "shipped"}
            }
        ]
    }
)

data = response.json()

# Check results
successful = data["summary"]["successful"]
failed = data["summary"]["failed"]

print(f"Processed {successful} events successfully, {failed} failed")

# Handle failures
for result in data["results"]:
    if not result["success"]:
        print(f"Item {result['index']} failed: {result['error']['message']}")
```

### JavaScript/Node.js

```javascript
const response = await fetch('https://api.triggers.zapier.com/events/batch', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer your_api_key',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    events: [
      {
        event_type: 'order.created',
        payload: { order_id: '123', amount: 99.99 }
      },
      {
        event_type: 'order.updated',
        payload: { order_id: '123', status: 'shipped' }
      }
    ]
  })
});

const data = await response.json();

// Check results
const { successful, failed } = data.summary;
console.log(`Processed ${successful} events successfully, ${failed} failed`);

// Handle failures
data.results.forEach((result, index) => {
  if (!result.success) {
    console.log(`Item ${result.index} failed: ${result.error.message}`);
  }
});
```

## Best Practices

### Error Handling

1. **Always check the summary** before processing individual results
2. **Handle partial failures** gracefully - some items may succeed even if others fail
3. **Retry failed items** individually or in smaller batches
4. **Log detailed errors** for debugging and monitoring

### Idempotency

1. **Use idempotency keys** for events that shouldn't be duplicated
2. **Include business identifiers** in idempotency keys (e.g., "order-12345-2024-01-15")
3. **Handle duplicate responses** as successful operations

### Performance

1. **Batch similar operations** together (all creates, all updates)
2. **Monitor response times** and adjust batch sizes accordingly
3. **Use appropriate batch sizes** for your use case (latency vs throughput)

### Security

1. **Validate ownership** on the client side when possible
2. **Use HTTPS** for all API calls
3. **Store API keys securely** and rotate regularly

## Monitoring and Metrics

Batch operations publish the following metrics to CloudWatch:

- `BatchCreateEvents`: Count of batch create operations
- `BatchUpdateEvents`: Count of batch update operations
- `BatchDeleteEvents`: Count of batch delete operations
- `EventDelivered`: Count of successfully delivered events (from batch operations)

Use these metrics to monitor batch operation health and performance.
