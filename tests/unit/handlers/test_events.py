"""
Module: test_events.py
Description: Unit tests for event handlers.

Tests POST /events endpoint with mocked dependencies.
Covers request validation, event creation, database operations,
and error handling scenarios.
"""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from fastapi.testclient import TestClient
from datetime import datetime, timezone

from src.handlers.events import router, create_event, get_db_client
from src.models.request import CreateEventRequest
from src.models.response import EventResponse
from src.storage.dynamodb import DynamoDBClient


class TestEventHandlers:
    """Test cases for event handler endpoints."""

    def test_create_event_success(self, sample_create_event_request, db_client):
        """Test successful event creation."""
        # Mock the db_client.put_event method
        with patch.object(db_client, 'put_event', new_callable=AsyncMock) as mock_put:
            # Create test client
            from fastapi import FastAPI
            app = FastAPI()
            app.include_router(router)
            client = TestClient(app)

            # Override the dependency
            app.dependency_overrides[get_db_client] = lambda: db_client

            try:
                # Make request
                response = client.post("/events", json=sample_create_event_request.model_dump())

                # Assert response
                assert response.status_code == 201
                data = response.json()

                assert "event_id" in data
                assert data["event_id"].startswith("evt_")
                assert len(data["event_id"]) == 16  # evt_ + 12 chars
                assert data["status"] == "pending"
                assert "created_at" in data
                assert data["delivered_at"] is None
                assert data["message"] == "Event created successfully"

                # Verify put_event was called
                mock_put.assert_called_once()
                called_event = mock_put.call_args[0][0]

                assert called_event.event_type == sample_create_event_request.event_type
                assert called_event.payload == sample_create_event_request.payload
                assert called_event.status == "pending"
                assert called_event.delivery_attempts == 0

            finally:
                # Clean up overrides
                app.dependency_overrides = {}

    def test_create_event_validation_error(self, db_client):
        """Test event creation with invalid request data."""
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        app.dependency_overrides[get_db_client] = lambda: db_client

        try:
            # Test missing required fields
            invalid_requests = [
                {"event_type": "test.event"},  # Missing payload
                {"payload": {"test": "data"}},  # Missing event_type
                {"event_type": "", "payload": {"test": "data"}},  # Empty event_type
                {"event_type": "test.event", "payload": {}},  # Empty payload
            ]

            for invalid_request in invalid_requests:
                response = client.post("/events", json=invalid_request)
                assert response.status_code == 400
                assert "error" in response.json()

        finally:
            app.dependency_overrides = {}

    def test_create_event_database_error(self, sample_create_event_request, db_client):
        """Test event creation with database error."""
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        # Mock put_event to raise an exception
        with patch.object(db_client, 'put_event', side_effect=Exception("Database error")):
            app.dependency_overrides[get_db_client] = lambda: db_client

            try:
                response = client.post("/events", json=sample_create_event_request.model_dump())

                assert response.status_code == 500
                data = response.json()
                assert "error" in data
                assert data["error"]["code"] == 500
                assert "Failed to create event" in data["error"]["message"]

            finally:
                app.dependency_overrides = {}

    def test_create_event_with_metadata(self, db_client):
        """Test event creation with metadata."""
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        request_data = {
            "event_type": "order.created",
            "payload": {"order_id": "12345"},
            "metadata": {"source": "test", "version": "1.0"}
        }

        with patch.object(db_client, 'put_event', new_callable=AsyncMock) as mock_put:
            app.dependency_overrides[get_db_client] = lambda: db_client

            try:
                response = client.post("/events", json=request_data)

                assert response.status_code == 201

                # Verify metadata was passed to event
                mock_put.assert_called_once()
                called_event = mock_put.call_args[0][0]
                assert called_event.metadata == request_data["metadata"]

            finally:
                app.dependency_overrides = {}

    def test_create_event_idempotency(self, db_client):
        """Test that event IDs are unique."""
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        request_data = {
            "event_type": "order.created",
            "payload": {"order_id": "12345"}
        }

        app.dependency_overrides[get_db_client] = lambda: db_client

        try:
            # Make multiple requests
            responses = []
            for _ in range(3):
                with patch.object(db_client, 'put_event', new_callable=AsyncMock):
                    response = client.post("/events", json=request_data)
                    responses.append(response.json())

            # All should succeed and have different event IDs
            event_ids = [r["event_id"] for r in responses]
            assert len(set(event_ids)) == 3  # All unique
            assert all(eid.startswith("evt_") for eid in event_ids)
            assert all(len(eid) == 16 for eid in event_ids)

        finally:
            app.dependency_overrides = {}

    def test_get_db_client_dependency(self, test_settings):
        """Test the get_db_client dependency function."""
        # Mock settings to return our test settings
        with patch('src.handlers.events.settings', test_settings):
            client = get_db_client()
            assert isinstance(client, DynamoDBClient)
            assert client.table_name == test_settings.events_table_name

    def test_router_configuration(self):
        """Test that router is properly configured."""
        assert router.prefix == "/events"
        assert len(router.tags) == 1
        assert "events" in router.tags

    # Integration-style tests with actual function calls
    @pytest.mark.asyncio
    async def test_create_event_function_success(self, sample_create_event_request, db_client):
        """Test create_event function directly."""
        with patch.object(db_client, 'put_event', new_callable=AsyncMock) as mock_put:
            response = await create_event(sample_create_event_request, db_client)

            assert isinstance(response, EventResponse)
            assert response.event_id.startswith("evt_")
            assert response.status == "pending"
            assert response.delivered_at is None
            assert response.message == "Event created successfully"

            mock_put.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_event_function_validation_error(self, db_client):
        """Test create_event function with validation error."""
        # Create invalid request
        invalid_request = CreateEventRequest(
            event_type="",  # Invalid: empty
            payload={"test": "data"}
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_event(invalid_request, db_client)

        assert exc_info.value.status_code == 400
        assert "Invalid event data" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_create_event_function_database_error(self, sample_create_event_request, db_client):
        """Test create_event function with database error."""
        with patch.object(db_client, 'put_event', side_effect=Exception("DB error")):
            with pytest.raises(HTTPException) as exc_info:
                await create_event(sample_create_event_request, db_client)

            assert exc_info.value.status_code == 500
            assert "Failed to create event" in exc_info.value.detail
