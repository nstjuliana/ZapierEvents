"""
Module: models
Description: Package initialization for Pydantic data models.

This package contains all data models used by the Triggers API:
- Event: Core event domain model with validation
- CreateEventRequest: API request model for event creation
- EventResponse: API response model for event operations

All models are exported here for convenient importing.
"""

from .event import Event
from .request import CreateEventRequest
from .response import EventResponse

__all__ = [
    "Event",
    "CreateEventRequest",
    "EventResponse",
]
