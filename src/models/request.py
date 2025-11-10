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
from pydantic import BaseModel, Field, ConfigDict


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
