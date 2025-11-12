"""
Module: request.py
Description: API request models for the Triggers API.

Defines request models for incoming API calls. These models handle
input validation and transformation for API endpoints.

Key Components:
- CreateEventRequest: Model for POST /events requests

Dependencies: pydantic, typing
Author: Triggers API Team
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator


class CreateEventRequest(BaseModel):
    """
    Request model for creating new events.

    This model validates incoming POST /events requests and ensures
    the required fields are present with appropriate validation.

    Attributes:
        event_type: Type of event (required, e.g., 'order.created')
        payload: Event data payload (required, flexible JSON)
        metadata: Optional metadata for the event
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True
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
    idempotency_key: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Optional idempotency key to prevent duplicate events"
    )
    user_id: Optional[str] = Field(
        default=None,
        description="Optional user ID (will be populated from auth context when enabled)"
    )

    @field_validator('idempotency_key')
    @classmethod
    def validate_idempotency_key(cls, v: Optional[str]) -> Optional[str]:
        """Validate idempotency key format if provided."""
        if v is None:
            return v

        if not isinstance(v, str) or not v.strip():
            raise ValueError("idempotency_key must be a non-empty string")

        # Allow alphanumeric characters, hyphens, underscores, dots, and colons
        # This supports common patterns like "order-12345-2024-01-15" or UUIDs
        import re
        if not re.match(r'^[a-zA-Z0-9._:-]+$', v):
            raise ValueError(
                "idempotency_key must contain only letters, numbers, dots, underscores, hyphens, and colons"
            )

        return v.strip()
