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
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class EventResponse(BaseModel):
    """
    Response model for event operations.

    This model structures the JSON response returned after successful
    event creation or retrieval operations.

    Attributes:
        event_id: Unique event identifier
        status: Current delivery status
        created_at: When the event was created
        delivered_at: When the event was delivered (nullable)
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
    message: str = Field(
        ...,
        description="Human-readable status message"
    )
