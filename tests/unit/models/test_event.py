"""
Module: test_event.py
Description: Unit tests for Event model validation.

Tests Pydantic model validation, field constraints, custom validators,
and model methods for the Event domain model.
"""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from src.models.event import Event


class TestEventModel:
    """Test cases for Event model validation and behavior."""

    def test_valid_event_creation(self, sample_event_model):
        """Test creating a valid Event instance."""
        assert sample_event_model.event_id == "evt_test123abc"
        assert sample_event_model.event_type == "order.created"
        assert sample_event_model.status == "pending"
        assert sample_event_model.delivery_attempts == 0
        assert sample_event_model.delivered_at is None

    def test_event_id_validation(self):
        """Test event_id pattern validation."""
        # Valid event ID
        event = Event(
            event_id="evt_abc123xyz456",
            event_type="test.event",
            payload={"test": "data"},
            created_at=datetime.now(timezone.utc)
        )
        assert event.event_id == "evt_abc123xyz456"

        # Invalid event IDs
        with pytest.raises(ValidationError):
            Event(
                event_id="invalid_id",
                event_type="test.event",
                payload={"test": "data"},
                created_at=datetime.now(timezone.utc)
            )

        with pytest.raises(ValidationError):
            Event(
                event_id="evt_short",
                event_type="test.event",
                payload={"test": "data"},
                created_at=datetime.now(timezone.utc)
            )

    def test_event_type_validation(self):
        """Test event_type field validation."""
        # Valid event types
        valid_types = ["order.created", "user.signed_up", "payment.processed"]
        for event_type in valid_types:
            event = Event(
                event_id="evt_test123abc",
                event_type=event_type,
                payload={"test": "data"},
                created_at=datetime.now(timezone.utc)
            )
            assert event.event_type == event_type

        # Invalid event types
        invalid_types = ["", "order created", "order.created!", "Order.Created"]
        for event_type in invalid_types:
            with pytest.raises(ValidationError):
                Event(
                    event_id="evt_test123abc",
                    event_type=event_type,
                    payload={"test": "data"},
                    created_at=datetime.now(timezone.utc)
                )

    def test_payload_validation(self):
        """Test payload field validation."""
        # Valid payloads
        valid_payloads = [
            {"key": "value"},
            {"order_id": 123, "amount": 99.99},
            {"nested": {"object": True}, "list": [1, 2, 3]}
        ]
        for payload in valid_payloads:
            event = Event(
                event_id="evt_test123abc",
                event_type="test.event",
                payload=payload,
                created_at=datetime.now(timezone.utc)
            )
            assert event.payload == payload

        # Invalid payloads
        invalid_payloads = [None, "", [], "string"]
        for payload in invalid_payloads:
            with pytest.raises(ValidationError):
                Event(
                    event_id="evt_test123abc",
                    event_type="test.event",
                    payload=payload,
                    created_at=datetime.now(timezone.utc)
                )

    def test_status_validation(self):
        """Test status field validation."""
        valid_statuses = ["pending", "delivered", "failed", "replayed"]

        for status in valid_statuses:
            event = Event(
                event_id="evt_test123abc",
                event_type="test.event",
                payload={"test": "data"},
                status=status,
                created_at=datetime.now(timezone.utc)
            )
            assert event.status == status

        # Invalid status
        with pytest.raises(ValidationError):
            Event(
                event_id="evt_test123abc",
                event_type="test.event",
                payload={"test": "data"},
                status="invalid_status",
                created_at=datetime.now(timezone.utc)
            )

    def test_delivery_attempts_validation(self):
        """Test delivery_attempts field validation."""
        # Valid values
        valid_attempts = [0, 1, 10, 100]
        for attempts in valid_attempts:
            event = Event(
                event_id="evt_test123abc",
                event_type="test.event",
                payload={"test": "data"},
                delivery_attempts=attempts,
                created_at=datetime.now(timezone.utc)
            )
            assert event.delivery_attempts == attempts

        # Invalid values
        invalid_attempts = [-1, -10]
        for attempts in invalid_attempts:
            with pytest.raises(ValidationError):
                Event(
                    event_id="evt_test123abc",
                    event_type="test.event",
                    payload={"test": "data"},
                    delivery_attempts=attempts,
                    created_at=datetime.now(timezone.utc)
                )

    def test_optional_metadata(self):
        """Test optional metadata field."""
        # With metadata
        event_with_metadata = Event(
            event_id="evt_test123abc",
            event_type="test.event",
            payload={"test": "data"},
            metadata={"source": "test", "version": "1.0"},
            created_at=datetime.now(timezone.utc)
        )
        assert event_with_metadata.metadata == {"source": "test", "version": "1.0"}

        # Without metadata (should default to None)
        event_without_metadata = Event(
            event_id="evt_test123abc",
            event_type="test.event",
            payload={"test": "data"},
            created_at=datetime.now(timezone.utc)
        )
        assert event_without_metadata.metadata is None

    def test_mark_delivered_method(self, sample_event_model):
        """Test mark_delivered method."""
        assert sample_event_model.status == "pending"
        assert sample_event_model.delivered_at is None
        assert sample_event_model.delivery_attempts == 0

        sample_event_model.mark_delivered()

        assert sample_event_model.status == "delivered"
        assert sample_event_model.delivered_at is not None
        assert isinstance(sample_event_model.delivered_at, datetime)
        assert sample_event_model.delivery_attempts == 1

    def test_mark_failed_method(self, sample_event_model):
        """Test mark_failed method."""
        sample_event_model.delivery_attempts = 2
        sample_event_model.mark_failed()

        assert sample_event_model.status == "failed"
        assert sample_event_model.delivery_attempts == 3

    def test_increment_attempts_method(self, sample_event_model):
        """Test increment_attempts method."""
        initial_attempts = sample_event_model.delivery_attempts
        sample_event_model.increment_attempts()

        assert sample_event_model.delivery_attempts == initial_attempts + 1

    def test_datetime_serialization(self, sample_event_model):
        """Test datetime field serialization."""
        # Test that datetime fields are properly handled
        assert isinstance(sample_event_model.created_at, datetime)
        assert sample_event_model.created_at.tzinfo is not None

        # Test delivered_at handling
        assert sample_event_model.delivered_at is None

        # Mark as delivered and check delivered_at
        sample_event_model.mark_delivered()
        assert isinstance(sample_event_model.delivered_at, datetime)
        assert sample_event_model.delivered_at.tzinfo is not None
