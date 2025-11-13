"""
Module: event.py
Description: Event data models for the Triggers API.

Defines the core Event model with validation rules for the event ingestion
and delivery system. Includes all event lifecycle states and metadata.

Key Components:
- Event: Core event model with full lifecycle tracking
- EventStatus: Enum for event delivery states
- Validation: Pydantic v2 with custom field validators

Dependencies: pydantic, datetime, typing
Author: Triggers API Team
"""

from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator


class Event(BaseModel):
    """
    Event model representing an ingested event.

    This is the core domain model for events in the Triggers API.
    Events track their lifecycle from ingestion through delivery,
    with comprehensive metadata for debugging and monitoring.

    Attributes:
        event_id: Unique event identifier (generated)
        event_type: Type of event (e.g., 'order.created')
        payload: Event data payload (flexible JSON)
        metadata: Optional metadata (source, custom fields)
        status: Delivery status (pending, delivered, failed, replayed)
        created_at: Timestamp when event was created
        delivered_at: Timestamp when event was delivered (nullable)
        delivery_attempts: Number of delivery attempts made
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        json_encoders={
            datetime: lambda v: v.isoformat() + 'Z'
        }
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
    user_id: Optional[str] = Field(
        default=None,
        description="User ID that created this event (for user-scoped idempotency)"
    )
    idempotency_key: Optional[str] = Field(
        default=None,
        description="Client-provided idempotency key to prevent duplicate events"
    )

    @field_validator('event_type')
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        """Validate event type follows naming conventions."""
        if not v or not isinstance(v, str):
            raise ValueError("event_type must be a non-empty string")

        # Allow lowercase letters, numbers, dots, and underscores
        import re
        if not re.match(r'^[a-z0-9._]+$', v):
            raise ValueError(
                "event_type must contain only lowercase letters, numbers, dots, and underscores"
            )

        return v

    @field_validator('payload', mode='before')
    @classmethod
    def validate_payload(cls, v: Any) -> Dict[str, Any]:
        """Validate payload is a non-empty dictionary, preserving all JSON types."""
        if not isinstance(v, dict):
            raise ValueError("payload must be a dictionary")

        if not v:
            raise ValueError("payload cannot be empty")

        # Return as-is to preserve all JSON types (numbers, strings, booleans, etc.)
        return v

    def mark_delivered(self) -> None:
        """Mark the event as successfully delivered."""
        from datetime import datetime, timezone
        self.status = "delivered"
        self.delivered_at = datetime.now(timezone.utc)
        self.delivery_attempts += 1

    def mark_failed(self) -> None:
        """Mark the event as failed delivery."""
        self.status = "failed"
        self.delivery_attempts += 1

    def increment_attempts(self) -> None:
        """Increment delivery attempts counter."""
        self.delivery_attempts += 1
