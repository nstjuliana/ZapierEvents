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
from typing import Dict, Any, Optional, List
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


class BatchItemError(BaseModel):
    """
    Error information for a failed batch operation item.

    Contains error code and human-readable message for debugging
    failed batch operations.

    Attributes:
        code: Error code for programmatic handling
        message: Human-readable error description
    """

    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat() + 'Z'
        }
    )

    code: str = Field(
        ...,
        description="Error code for programmatic handling"
    )
    message: str = Field(
        ...,
        description="Human-readable error description"
    )


class BatchCreateItemResult(BaseModel):
    """
    Result for a single item in batch create operation.

    Contains either a successful event response or error information.
    Index corresponds to position in original request array.

    Attributes:
        index: Position in the original request array (0-based)
        success: Whether this item was processed successfully
        event: Event response data (only present if success=True)
        error: Error information (only present if success=False)
    """

    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat() + 'Z'
        }
    )

    index: int = Field(
        ...,
        ge=0,
        description="Position in the original request array (0-based)"
    )
    success: bool = Field(
        ...,
        description="Whether this item was processed successfully"
    )
    event: Optional[EventResponse] = Field(
        default=None,
        description="Event response data (only present if success=True)"
    )
    error: Optional[BatchItemError] = Field(
        default=None,
        description="Error information (only present if success=False)"
    )


class BatchUpdateItemResult(BaseModel):
    """
    Result for a single item in batch update operation.

    Contains either a successful event response or error information.
    Index corresponds to position in original request array.

    Attributes:
        index: Position in the original request array (0-based)
        success: Whether this item was processed successfully
        event: Updated event response data (only present if success=True)
        error: Error information (only present if success=False)
    """

    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat() + 'Z'
        }
    )

    index: int = Field(
        ...,
        ge=0,
        description="Position in the original request array (0-based)"
    )
    success: bool = Field(
        ...,
        description="Whether this item was processed successfully"
    )
    event: Optional[EventResponse] = Field(
        default=None,
        description="Updated event response data (only present if success=True)"
    )
    error: Optional[BatchItemError] = Field(
        default=None,
        description="Error information (only present if success=False)"
    )


class BatchDeleteItemResult(BaseModel):
    """
    Result for a single item in batch delete operation.

    Contains either success information or error details.
    Index corresponds to position in original request array.

    Attributes:
        index: Position in the original request array (0-based)
        success: Whether this item was processed successfully
        event_id: The event ID that was processed
        message: Success message or error information
        error: Error information (only present if success=False)
    """

    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat() + 'Z'
        }
    )

    index: int = Field(
        ...,
        ge=0,
        description="Position in the original request array (0-based)"
    )
    success: bool = Field(
        ...,
        description="Whether this item was processed successfully"
    )
    event_id: str = Field(
        ...,
        description="The event ID that was processed"
    )
    message: str = Field(
        ...,
        description="Success message or error information"
    )
    error: Optional[BatchItemError] = Field(
        default=None,
        description="Error information (only present if success=False)"
    )


class BatchOperationSummary(BaseModel):
    """
    Summary statistics for batch operations.

    Provides high-level overview of batch operation results.

    Attributes:
        total: Total number of items processed
        successful: Number of items that succeeded (newly created/updated/deleted)
        idempotent: Number of items that were idempotent (already existed, counted separately)
        failed: Number of items that failed
    """

    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat() + 'Z'
        }
    )

    total: int = Field(
        ...,
        ge=0,
        description="Total number of items processed"
    )
    successful: int = Field(
        ...,
        ge=0,
        description="Number of items that succeeded (newly created/updated/deleted)"
    )
    idempotent: int = Field(
        default=0,
        ge=0,
        description="Number of items that were idempotent (already existed, for create operations)"
    )
    failed: int = Field(
        ...,
        ge=0,
        description="Number of items that failed"
    )


class BatchCreateResponse(BaseModel):
    """
    Response for batch create operations.

    Contains detailed results for each item plus summary statistics.
    Supports partial success - some items may succeed while others fail.

    Attributes:
        results: List of individual item results
        summary: Summary statistics for the entire batch
    """

    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat() + 'Z'
        }
    )

    results: List[BatchCreateItemResult] = Field(
        ...,
        description="List of individual item results"
    )
    summary: BatchOperationSummary = Field(
        ...,
        description="Summary statistics for the entire batch"
    )


class BatchUpdateResponse(BaseModel):
    """
    Response for batch update operations.

    Contains detailed results for each item plus summary statistics.
    Supports partial success - some items may succeed while others fail.

    Attributes:
        results: List of individual item results
        summary: Summary statistics for the entire batch
    """

    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat() + 'Z'
        }
    )

    results: List[BatchUpdateItemResult] = Field(
        ...,
        description="List of individual item results"
    )
    summary: BatchOperationSummary = Field(
        ...,
        description="Summary statistics for the entire batch"
    )


class BatchDeleteResponse(BaseModel):
    """
    Response for batch delete operations.

    Contains detailed results for each item plus summary statistics.
    Supports partial success - some items may succeed while others fail.
    Missing events are treated as successful (idempotent delete).

    Attributes:
        results: List of individual item results
        summary: Summary statistics for the entire batch
    """

    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat() + 'Z'
        }
    )

    results: List[BatchDeleteItemResult] = Field(
        ...,
        description="List of individual item results"
    )
    summary: BatchOperationSummary = Field(
        ...,
        description="Summary statistics for the entire batch"
    )