# Idempotency Keys Explained (Simple)

## The Problem: Duplicate Events

Imagine you're sending an event when a customer places an order:

```python
# Your app sends this when order is created
POST /events
{
  "event_type": "order.created",
  "payload": {
    "order_id": "12345",
    "amount": 99.99
  }
}
```

**What happens if your network request fails?**

Your app might retry the request, sending the **same event twice**:

```
Attempt 1: POST /events → Network timeout ❌
Attempt 2: POST /events → Success ✅
```

But wait... did the first attempt actually succeed? Or did it fail?

**Result:** You might send the same event twice, and Zapier processes it twice:
- Customer gets charged twice 💸
- Order gets created twice 📦📦
- Email gets sent twice 📧📧

## The Solution: Idempotency Keys

An **idempotency key** is like a unique fingerprint for your event. If you send the same event twice with the same key, the API recognizes it and returns the **same event** (doesn't create a duplicate).

### How It Works

```python
# First attempt
POST /events
{
  "event_type": "order.created",
  "payload": {
    "order_id": "12345",
    "amount": 99.99
  },
  "idempotency_key": "order-12345-2024-01-15"  # ← Unique fingerprint
}

# Response: Creates new event
{
  "event_id": "evt_abc123",
  "status": "pending"
}
```

```python
# Second attempt (retry with SAME idempotency_key)
POST /events
{
  "event_type": "order.created",
  "payload": {
    "order_id": "12345",
    "amount": 99.99
  },
  "idempotency_key": "order-12345-2024-01-15"  # ← Same key!
}

# Response: Returns the SAME event (doesn't create duplicate)
{
  "event_id": "evt_abc123",  # ← Same event_id!
  "status": "pending"
}
```

## Real-World Example

### Scenario: E-commerce Order Processing

**Without Idempotency Keys:**

```
1. Customer clicks "Place Order"
2. Your app sends event → Network glitch, request fails
3. Your app retries → Success!
4. But first request also succeeded (you just didn't get response)
5. Result: Two events sent, customer charged twice 😱
```

**With Idempotency Keys:**

```
1. Customer clicks "Place Order"
2. Your app sends event with idempotency_key: "order-12345-2024-01-15"
   → Network glitch, request fails
3. Your app retries with SAME idempotency_key: "order-12345-2024-01-15"
   → API recognizes: "I've seen this key before, return existing event"
4. Result: Only ONE event created, customer charged once ✅
```

## Who Generates the Idempotency Key?

**Answer: The user/client provides it** (not the API)

This is the standard pattern used by Stripe, Twilio, and other APIs. The client knows what makes their event unique and can retry with the same key.

### How It Works:

```python
# Client generates the key
def send_order_event(order_id, amount):
    # Client creates the idempotency key
    today = datetime.now().strftime("%Y-%m-%d")
    idempotency_key = f"order-{order_id}-{today}"
    
    # Client sends it to the API
    response = requests.post(
        "https://api.triggers.com/events",
        json={
            "event_type": "order.created",
            "payload": {"order_id": order_id, "amount": amount},
            "idempotency_key": idempotency_key  # ← Client provides this
        }
    )
```

### Why Client Provides It:

1. **Client knows what's unique**: Only the client knows what makes their event unique (order ID, transaction ID, etc.)
2. **Client can retry**: If request fails, client can retry with the same key
3. **Client controls deduplication**: Client decides what counts as "the same event"
4. **API is stateless**: API just stores and checks the key, doesn't need business logic

### API's Role:

The API just:
- Stores the idempotency_key with the event
- Checks if a key already exists
- Returns existing event if key found

```python
# API implementation (simplified)
def create_event(request):
    # Check if idempotency_key already exists
    if request.idempotency_key:
        existing = db.get_event_by_idempotency_key(
            request.idempotency_key
        )
        if existing:
            return existing  # Return existing event
    
    # Create new event
    event = Event(
        event_id=generate_id(),
        idempotency_key=request.idempotency_key  # Store what client provided
    )
    db.save_event(event)
    return event
```

## How to Generate Idempotency Keys (Client Side)

The client should generate keys that are:
- **Unique** for each distinct event
- **Deterministic** (same event = same key)
- **Include identifying information**

### Good Examples:

```python
# Option 1: Order ID + Date
idempotency_key = f"order-{order_id}-{date}"

# Option 2: Transaction ID (if you have one)
idempotency_key = transaction_id

# Option 3: Hash of event content
import hashlib
idempotency_key = hashlib.sha256(
    f"{event_type}-{order_id}-{timestamp}".encode()
).hexdigest()

# Option 4: Business ID + Action
idempotency_key = f"{resource_id}-{action}-{date}"
# Example: "user-123-signup-2024-01-15"
```

### Bad Examples:

```python
# ❌ Random UUID (different every time, defeats purpose)
idempotency_key = str(uuid.uuid4())

# ❌ Just the order ID (what if order is updated?)
idempotency_key = order_id  # Order might change

# ❌ Timestamp only (same order at different times = different keys)
idempotency_key = str(time.time())
```

## Alternative: API-Generated Keys (Not Recommended)

Some APIs auto-generate idempotency keys, but this is less useful:

```python
# API generates key (not recommended)
POST /events
{
  "event_type": "order.created",
  "payload": {...}
  # No idempotency_key provided
}

# Response includes generated key
{
  "event_id": "evt_abc123",
  "idempotency_key": "api-gen-xyz789"  # ← API generated
}
```

**Problems:**
- ❌ Client can't retry with same key (doesn't know the key)
- ❌ Client can't control what counts as "same event"
- ❌ Less useful for preventing duplicates from retries

**When it might work:**
- If you want to prevent exact duplicate requests (same payload, same timestamp)
- But this is less flexible than client-provided keys

## Implementation Example

### In Your App:

```python
import requests
from datetime import datetime

def send_order_event(order_id, amount):
    # Generate idempotency key
    today = datetime.now().strftime("%Y-%m-%d")
    idempotency_key = f"order-{order_id}-{today}"
    
    # Send event (with retry logic)
    for attempt in range(3):
        try:
            response = requests.post(
                "https://api.triggers.com/events",
                json={
                    "event_type": "order.created",
                    "payload": {
                        "order_id": order_id,
                        "amount": amount
                    },
                    "idempotency_key": idempotency_key
                },
                timeout=10
            )
            return response.json()
        except requests.Timeout:
            # Retry with SAME idempotency_key
            continue
    
    raise Exception("Failed after retries")

# Safe to call multiple times
send_order_event("12345", 99.99)  # Creates event
send_order_event("12345", 99.99)  # Returns same event (no duplicate)
```

### In the API (How It Works):

```python
# Pseudocode
def create_event(request):
    # Check if we've seen this idempotency_key before
    if request.idempotency_key:
        existing_event = db.get_event_by_idempotency_key(
            request.idempotency_key
        )
        if existing_event:
            # Return existing event (don't create duplicate)
            return existing_event
    
    # Create new event
    event = Event(
        event_id=generate_id(),
        event_type=request.event_type,
        payload=request.payload,
        idempotency_key=request.idempotency_key
    )
    
    # Store idempotency_key for future lookups
    db.save_event(event)
    db.save_idempotency_key_mapping(
        idempotency_key=request.idempotency_key,
        event_id=event.event_id
    )
    
    return event
```

## Key Benefits

1. **Safe Retries**: Retry failed requests without creating duplicates
2. **Network Resilience**: Handle timeouts, connection errors safely
3. **Idempotent API**: Same request = same result (industry best practice)
4. **Prevent Double Processing**: Critical for financial/transactional events

## Common Use Cases

- **Payment Processing**: Don't charge customer twice
- **Order Creation**: Don't create duplicate orders
- **Email Sending**: Don't send duplicate emails
- **Inventory Updates**: Don't deduct inventory twice
- **Webhook Retries**: Safe to retry webhook calls

## When You DON'T Want Duplicates (Use Idempotency Keys)

**Use idempotency keys for:**
- ✅ Payment processing (don't charge twice)
- ✅ Order creation (don't create duplicate orders)
- ✅ Email sending (don't spam customers)
- ✅ Inventory updates (don't deduct twice)
- ✅ Any action that has side effects or costs money

**Example:**
```python
# Payment event - MUST be idempotent
POST /events
{
  "event_type": "payment.processed",
  "payload": {"amount": 99.99, "customer_id": "123"},
  "idempotency_key": "payment-txn-abc123"  # ← Prevents duplicate charges
}
```

## When You DO Want Duplicates (Don't Use Idempotency Keys)

**Don't use idempotency keys for:**
- ✅ Analytics events (each view is a new event)
- ✅ Logging events (want all occurrences)
- ✅ State change events (order.updated happens multiple times)
- ✅ Sensor readings (each reading is unique)
- ✅ Events where duplicates are harmless or desired

**Example:**
```python
# Analytics event - WANT duplicates
POST /events
{
  "event_type": "page.viewed",
  "payload": {"page": "/products", "user_id": "123"},
  # No idempotency_key - each view is a separate event
}

# If user refreshes page, we want TWO events (two views)
```

## Real-World Examples

### Example 1: E-commerce Order Lifecycle

```python
# Order created - Use idempotency (don't create duplicate orders)
POST /events
{
  "event_type": "order.created",
  "payload": {"order_id": "12345"},
  "idempotency_key": "order-12345-created"  # ← Prevents duplicates
}

# Order updated - DON'T use idempotency (order changes multiple times)
POST /events
{
  "event_type": "order.updated",
  "payload": {"order_id": "12345", "status": "shipped"},
  # No idempotency_key - each update is a new event
}

# Order shipped - Use idempotency (don't send shipping email twice)
POST /events
{
  "event_type": "order.shipped",
  "payload": {"order_id": "12345", "tracking": "ABC123"},
  "idempotency_key": "order-12345-shipped"  # ← Prevents duplicate emails
}
```

### Example 2: Analytics Platform

```python
# User clicks button - WANT duplicates (each click is separate)
POST /events
{
  "event_type": "button.clicked",
  "payload": {"button_id": "checkout", "user_id": "123"},
  # No idempotency_key - track every click
}

# User signs up - DON'T want duplicates (don't create duplicate accounts)
POST /events
{
  "event_type": "user.signed_up",
  "payload": {"user_id": "123", "email": "user@example.com"},
  "idempotency_key": "signup-user-123"  # ← Prevents duplicate accounts
}
```

### Example 3: IoT Sensor Data

```python
# Temperature reading - WANT duplicates (each reading is unique)
POST /events
{
  "event_type": "sensor.temperature",
  "payload": {"sensor_id": "temp-1", "value": 72.5, "timestamp": "2024-01-15T10:00:00Z"},
  # No idempotency_key - each reading is a new event
}

# Sensor calibration - DON'T want duplicates (calibrate once)
POST /events
{
  "event_type": "sensor.calibrated",
  "payload": {"sensor_id": "temp-1", "offset": 0.5},
  "idempotency_key": "calibrate-temp-1-2024-01-15"  # ← Prevents duplicate calibration
}
```

## API Design: Optional Idempotency

The API should make idempotency keys **optional**:

```python
# With idempotency key (prevents duplicates)
POST /events
{
  "event_type": "order.created",
  "payload": {...},
  "idempotency_key": "order-12345"  # ← Optional
}

# Without idempotency key (allows duplicates)
POST /events
{
  "event_type": "page.viewed",
  "payload": {...}
  # No idempotency_key - each request creates new event
}
```

### Implementation:

```python
def create_event(request):
    # If idempotency_key provided, check for duplicates
    if request.idempotency_key:
        existing = db.get_event_by_idempotency_key(
            request.idempotency_key
        )
        if existing:
            return existing  # Return existing event
    
    # Create new event (whether or not idempotency_key was provided)
    event = Event(
        event_id=generate_id(),
        event_type=request.event_type,
        payload=request.payload,
        idempotency_key=request.idempotency_key  # Can be None
    )
    
    db.save_event(event)
    return event
```

## Best Practices

### Use Idempotency Keys When:
- ✅ Action has side effects (charge, create, send)
- ✅ Duplicates would cause problems
- ✅ You're retrying a failed request
- ✅ Event represents a "one-time" action

### Don't Use Idempotency Keys When:
- ✅ Event represents a state change (can happen multiple times)
- ✅ Each occurrence is meaningful (analytics, logs)
- ✅ Duplicates are harmless or desired
- ✅ Event is naturally unique (has timestamp, unique ID)

## Summary

**Idempotency Key = Optional Safety Feature**

- **With key**: Same key = Same event (prevents duplicates)
- **Without key**: Each request = New event (allows duplicates)
- **Your choice**: Use when you need protection, skip when you want duplicates

**Think of it like:**
- **With key**: "Receipt number" - same receipt = same order
- **Without key**: "Log entry" - each entry is separate, even if similar

The API should support both patterns!

