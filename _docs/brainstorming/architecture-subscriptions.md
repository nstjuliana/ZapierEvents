# Subscription-Based Delivery Architecture

## Problem Statement

The current architecture doesn't explicitly track which Zaps should receive an event. The 1-to-many relationship between events and Zaps is implicit and handled by Zapier's internal system.

## Proposed Solution: Subscription System

### Core Concept

1. **Zaps subscribe to event types** (not to individual events)
2. **Events reference event_type** (not individual Zaps)
3. **Delivery system queries subscriptions** by event_type to find all Zaps to notify
4. **Track delivery per Zap** (not just per event)

### Architecture Components

#### 1. Subscription Model

```python
class ZapSubscription(BaseModel):
    """
    Represents a Zap's subscription to an event type.
    
    Attributes:
        subscription_id: Unique subscription identifier
        zap_id: Zap identifier (from Zapier)
        zap_webhook_url: Webhook URL for this Zap
        event_type: Event type this Zap subscribes to
        is_active: Whether subscription is active
        created_at: When subscription was created
        updated_at: When subscription was last updated
    """
    subscription_id: str  # e.g., "sub_abc123"
    zap_id: str  # e.g., "zap_xyz789"
    zap_webhook_url: str
    event_type: str
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
```

#### 2. Enhanced Event Model

Events should track delivery status **per Zap**, not just overall:

```python
class EventDeliveryStatus(BaseModel):
    """Delivery status for a single Zap."""
    zap_id: str
    zap_webhook_url: str
    status: str  # pending, delivered, failed
    delivered_at: Optional[datetime]
    attempts: int
    last_error: Optional[str]

class Event(BaseModel):
    # ... existing fields ...
    
    # NEW: Track delivery per Zap
    delivery_statuses: List[EventDeliveryStatus] = Field(
        default_factory=list,
        description="Delivery status for each subscribed Zap"
    )
    
    # Computed properties
    @property
    def total_zaps_subscribed(self) -> int:
        """Total number of Zaps subscribed to this event type."""
        return len(self.delivery_statuses)
    
    @property
    def delivered_zaps_count(self) -> int:
        """Number of Zaps that successfully received the event."""
        return sum(1 for ds in self.delivery_statuses if ds.status == "delivered")
    
    @property
    def is_fully_delivered(self) -> bool:
        """True if all subscribed Zaps have received the event."""
        return all(ds.status == "delivered" for ds in self.delivery_statuses)
```

#### 3. Subscription Storage

**DynamoDB Table: `ZapSubscriptions`**

```
Partition Key: event_type
Sort Key: zap_id
Attributes:
  - subscription_id
  - zap_webhook_url
  - is_active
  - created_at
  - updated_at
```

**GSI: `ZapIdIndex`**
```
Partition Key: zap_id
Sort Key: event_type
```

#### 4. Delivery Flow

```
1. Event Created (event_type: "order.created")
   ↓
2. Query Subscriptions by event_type
   → Find all active Zaps subscribed to "order.created"
   → Returns: [zap_1, zap_2, zap_3]
   ↓
3. Initialize delivery_statuses for event
   → Create EventDeliveryStatus for each Zap
   ↓
4. Push to each Zap individually
   → POST to zap_1.webhook_url
   → POST to zap_2.webhook_url
   → POST to zap_3.webhook_url
   ↓
5. Update delivery_statuses
   → Mark successful deliveries
   → Track failures for retry
   ↓
6. Event status = "delivered" only when ALL Zaps delivered
```

### Implementation Details

#### Subscription Management Endpoints

```python
# Register a Zap subscription
POST /subscriptions
{
    "zap_id": "zap_xyz789",
    "zap_webhook_url": "https://hooks.zapier.com/hooks/catch/abc/123/",
    "event_type": "order.created"
}

# List subscriptions for an event type
GET /subscriptions?event_type=order.created

# List subscriptions for a Zap
GET /subscriptions?zap_id=zap_xyz789

# Deactivate subscription
DELETE /subscriptions/{subscription_id}
```

#### Enhanced Delivery Client

```python
class PushDeliveryClient:
    async def deliver_event_to_zaps(
        self, 
        event: Event,
        subscriptions: List[ZapSubscription]
    ) -> Dict[str, EventDeliveryStatus]:
        """
        Deliver event to all subscribed Zaps.
        
        Returns:
            Dictionary mapping zap_id to delivery status
        """
        delivery_statuses = {}
        
        for subscription in subscriptions:
            if not subscription.is_active:
                continue
                
            status = await self._deliver_to_zap(event, subscription)
            delivery_statuses[subscription.zap_id] = status
        
        return delivery_statuses
    
    async def _deliver_to_zap(
        self, 
        event: Event, 
        subscription: ZapSubscription
    ) -> EventDeliveryStatus:
        """Deliver event to a single Zap."""
        # ... HTTP POST to subscription.zap_webhook_url ...
```

#### Event Creation Flow

```python
@router.post("", status_code=status.HTTP_201_CREATED)
async def create_event(
    request: CreateEventRequest,
    db_client: DynamoDBClient = Depends(get_db_client),
    subscription_client: SubscriptionClient = Depends(get_subscription_client),
    delivery_client: PushDeliveryClient = Depends(get_delivery_client)
) -> EventResponse:
    # 1. Create event
    event = Event(...)
    await db_client.put_event(event)
    
    # 2. Query subscriptions for this event_type
    subscriptions = await subscription_client.get_subscriptions_by_event_type(
        event_type=event.event_type
    )
    
    # 3. Initialize delivery statuses
    event.delivery_statuses = [
        EventDeliveryStatus(
            zap_id=sub.zap_id,
            zap_webhook_url=sub.zap_webhook_url,
            status="pending",
            attempts=0
        )
        for sub in subscriptions if sub.is_active
    ]
    
    # 4. Attempt delivery to all Zaps
    if event.delivery_statuses:
        delivery_results = await delivery_client.deliver_event_to_zaps(
            event, subscriptions
        )
        
        # Update delivery statuses
        for status in event.delivery_statuses:
            if status.zap_id in delivery_results:
                status = delivery_results[status.zap_id]
        
        # Update event status
        if event.is_fully_delivered:
            event.status = "delivered"
        elif any(ds.status == "delivered" for ds in event.delivery_statuses):
            event.status = "partially_delivered"
        else:
            event.status = "pending"
            # Queue to SQS for retry
    else:
        # No subscriptions - event is pending
        event.status = "pending"
    
    # 5. Update event with delivery statuses
    await db_client.update_event(event)
    
    return EventResponse(...)
```

### Benefits

1. **Explicit 1-to-many relationship**: Clear tracking of which Zaps receive each event
2. **Per-Zap delivery tracking**: Know exactly which Zaps succeeded/failed
3. **Decoupled**: Event creation doesn't need to know about Zaps
4. **Scalable**: Easy to add/remove subscriptions without modifying events
5. **Observable**: Can query "which Zaps received this event?" or "which events did this Zap receive?"

### Migration Path

1. Add `ZapSubscriptions` table
2. Add subscription management endpoints
3. Enhance `Event` model with `delivery_statuses`
4. Update delivery logic to query subscriptions
5. Migrate existing events (can start with empty `delivery_statuses`)

### Alternative: Event-Embedded Approach (Not Recommended)

You could put Zap IDs directly in the event:

```python
class Event(BaseModel):
    zap_ids: List[str]  # Which Zaps to notify
```

**Problems:**
- Couples event creation to Zap management
- Can't add a new Zap subscription without modifying all future events
- Harder to query "all Zaps subscribed to event_type X"
- Less flexible for dynamic subscriptions

