"""
Module: response.py
Description: API response models for the Triggers API.

Defines response models for outgoing API calls. These models structure
the JSON responses returned by API endpoints.

Key Components:
- EventResponse: Model for event creation responses

Dependencies: pydantic, datetime, typing
Author: Triggers API Team
"""

from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict


class EventResponse(BaseModel):
    """
    Response model for event operations.

    This model structures the JSON response returned after successful
    event creation or retrieval operations.

    Attributes:
        event_id: Unique event identifier
        event_type: Type of event (e.g., 'order.created')
        payload: Event data payload (flexible JSON)
        metadata: Optional metadata (source, custom fields)
        status: Current delivery status
        created_at: When the event was created
        delivered_at: When the event was delivered (nullable)
        delivery_attempts: Number of delivery attempts made
        message: Human-readable status message
    """

    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat() + 'Z'
        }
    )

    event_id: str = Field(
        ...,
        description="Unique event identifier"
    )
    event_type: str = Field(
        ...,
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
        ...,
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
        ...,
        description="Number of delivery attempts"
    )
    user_id: Optional[str] = Field(
        default=None,
        description="User ID that created this event"
    )
    idempotency_key: Optional[str] = Field(
        default=None,
        description="Client-provided idempotency key"
    )
    message: str = Field(
        ...,
        description="Human-readable status message"
    )
