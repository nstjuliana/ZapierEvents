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

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


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


class UpdateEventRequest(BaseModel):
    """
    Request model for updating existing events.

    This model validates incoming PATCH /events/{event_id} requests.
    At least one field must be provided for update.

    Attributes:
        payload: Updated event payload data (optional)
        metadata: Updated event metadata (optional, can be null to remove)
        idempotency_key: Updated idempotency key (optional, set to null to remove)
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True
    )

    payload: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Updated event payload data"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Updated event metadata"
    )
    idempotency_key: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Updated idempotency key (set to null to remove)"
    )

    @field_validator('payload', mode='before')
    @classmethod
    def validate_payload(cls, v: Any) -> Optional[Dict[str, Any]]:
        """Validate payload is a non-empty dictionary if provided."""
        if v is None:
            return v

        if not isinstance(v, dict):
            raise ValueError("payload must be a dictionary")

        if not v:
            raise ValueError("payload cannot be empty")

        # Return as-is to preserve all JSON types (numbers, strings, booleans, etc.)
        return v

    @field_validator('metadata', mode='before')
    @classmethod
    def validate_metadata(cls, v: Any) -> Optional[Dict[str, Any]]:
        """Validate metadata is a dictionary if provided."""
        if v is None:
            return v

        if not isinstance(v, dict):
            raise ValueError("metadata must be a dictionary")

        # Return as-is to preserve all JSON types
        return v

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

    @model_validator(mode='after')
    def validate_at_least_one_field(self) -> 'UpdateEventRequest':
        """Ensure at least one field is provided."""
        # Check if at least one field is explicitly set (not None)
        # Note: idempotency_key can be explicitly set to None to remove it
        # We need to check the raw input to see if it was provided
        # This will be handled in the handler by checking model_dump(exclude_unset=True)
        return self


class BatchCreateEventRequest(BaseModel):
    """
    Request model for batch creating events.

    Contains a list of individual CreateEventRequest items to be processed
    as a batch operation with best-effort semantics (partial success allowed).

    Attributes:
        events: List of event creation requests (max 100)
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True
    )

    events: List[CreateEventRequest] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of events to create (max 100)"
    )

    @field_validator('events')
    @classmethod
    def validate_events_list(cls, v: List[CreateEventRequest]) -> List[CreateEventRequest]:
        """Validate the events list."""
        if not v:
            raise ValueError("events list cannot be empty")
        if len(v) > 100:
            raise ValueError("batch size cannot exceed 100 events")
        return v


class BatchUpdateEventItem(BaseModel):
    """
    Individual item in a batch update request.

    Contains the event_id to update plus the fields to modify.
    At least one of payload, metadata, or idempotency_key must be provided.

    Attributes:
        event_id: Unique identifier of the event to update
        payload: Updated event payload data (optional)
        metadata: Updated event metadata (optional, can be null to remove)
        idempotency_key: Updated idempotency key (optional, set to null to remove)
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True
    )

    event_id: str = Field(
        ...,
        pattern=r"^evt_[a-z0-9]{12}$",
        description="Unique event identifier to update"
    )
    payload: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Updated event payload data"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Updated event metadata"
    )
    idempotency_key: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Updated idempotency key (set to null to remove)"
    )

    @field_validator('payload', mode='before')
    @classmethod
    def validate_payload(cls, v: Any) -> Optional[Dict[str, Any]]:
        """Validate payload is a non-empty dictionary if provided."""
        if v is None:
            return v

        if not isinstance(v, dict):
            raise ValueError("payload must be a dictionary")

        if not v:
            raise ValueError("payload cannot be empty")

        # Return as-is to preserve all JSON types (numbers, strings, booleans, etc.)
        return v

    @field_validator('metadata', mode='before')
    @classmethod
    def validate_metadata(cls, v: Any) -> Optional[Dict[str, Any]]:
        """Validate metadata is a dictionary if provided."""
        if v is None:
            return v

        if not isinstance(v, dict):
            raise ValueError("metadata must be a dictionary")

        # Return as-is to preserve all JSON types
        return v

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

    @model_validator(mode='after')
    def validate_at_least_one_field(self) -> 'BatchUpdateEventItem':
        """Ensure at least one field is provided."""
        # Check if at least one field is explicitly set (not None)
        # Note: idempotency_key can be explicitly set to None to remove it
        # We need to check the raw input to see if it was provided
        # This will be handled in the handler by checking model_dump(exclude_unset=True)
        return self


class BatchUpdateEventRequest(BaseModel):
    """
    Request model for batch updating events.

    Contains a list of BatchUpdateEventItem objects to be processed
    as a batch operation with best-effort semantics.

    Attributes:
        events: List of event update requests (max 100)
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True
    )

    events: List[BatchUpdateEventItem] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of events to update (max 100)"
    )

    @field_validator('events')
    @classmethod
    def validate_events_list(cls, v: List[BatchUpdateEventItem]) -> List[BatchUpdateEventItem]:
        """Validate the events list."""
        if not v:
            raise ValueError("events list cannot be empty")
        if len(v) > 100:
            raise ValueError("batch size cannot exceed 100 events")
        return v


class BatchDeleteEventRequest(BaseModel):
    """
    Request model for batch deleting events.

    Contains a list of event_ids to delete with best-effort semantics.
    Missing events are treated as successful (idempotent delete).

    Attributes:
        event_ids: List of event IDs to delete (max 100)
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True
    )

    event_ids: List[str] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of event IDs to delete (max 100)"
    )

    @field_validator('event_ids')
    @classmethod
    def validate_event_ids_list(cls, v: List[str]) -> List[str]:
        """Validate the event_ids list."""
        if not v:
            raise ValueError("event_ids list cannot be empty")
        if len(v) > 100:
            raise ValueError("batch size cannot exceed 100 events")

        # Validate each event_id format
        for event_id in v:
            if not isinstance(event_id, str):
                raise ValueError("all event_ids must be strings")
            if not event_id.strip():
                raise ValueError("event_ids cannot be empty strings")
            import re
            if not re.match(r'^evt_[a-z0-9]{12}$', event_id):
                raise ValueError(f"invalid event_id format: {event_id}")

        return v