"""
Module: test_api.py
Description: Integration tests for Triggers API endpoints.

Tests end-to-end API flows including POST /events with mocked
DynamoDB, validation errors, and authentication scenarios.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
import json

from src.main import app
from src.storage.dynamodb import DynamoDBClient


@pytest.fixture
def test_client(mock_dynamodb_table, mock_api_keys_table, test_settings):
    """Create FastAPI test client with mocked dependencies."""
    # Override settings for testing
    with patch('src.config.settings.settings', test_settings):
        with patch('src.handlers.events.get_db_client') as mock_get_client:
            # Create mock DynamoDB client
            mock_client = DynamoDBClient(test_settings.events_table_name)
            mock_get_client.return_value = mock_client

            yield TestClient(app)


class TestApiIntegration:
    """Integration tests for API endpoints."""

    def test_health_endpoint(self, test_client):
        """Test health check endpoint."""
        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "ok"
        assert "Triggers API is healthy" in data["message"]
        assert data["version"] == "0.1.0-test"
        assert data["environment"] == "test"

    def test_post_events_success(self, test_client, sample_event, mock_dynamodb_table):
        """Test successful POST /events request."""
        # Mock the put_event method
        with patch.object(test_client.app.dependency_overrides.get('src.handlers.events.get_db_client', lambda: None)(),
                         'put_event', new_callable=AsyncMock) as mock_put:

            response = test_client.post("/events", json=sample_event)

            assert response.status_code == 201
            data = response.json()

            # Validate response structure
            assert "event_id" in data
            assert data["event_id"].startswith("evt_")
            assert len(data["event_id"]) == 16
            assert data["status"] == "pending"
            assert "created_at" in data
            assert data["delivered_at"] is None
            assert data["message"] == "Event created successfully"

            # Verify put_event was called with correct event
            mock_put.assert_called_once()
            stored_event = mock_put.call_args[0][0]

            assert stored_event.event_type == sample_event["event_type"]
            assert stored_event.payload == sample_event["payload"]
            assert stored_event.metadata == sample_event["metadata"]
            assert stored_event.status == "pending"
            assert stored_event.delivery_attempts == 0

    def test_post_events_validation_errors(self, test_client):
        """Test POST /events with various validation errors."""
        validation_cases = [
            # Missing required fields
            {
                "payload": {"test": "data"},
                "expected_error": "event_type"
            },
            {
                "event_type": "test.event",
                "expected_error": "payload"
            },
            # Invalid event_type
            {
                "event_type": "",
                "payload": {"test": "data"},
                "expected_error": "event_type"
            },
            {
                "event_type": "Test.Event",  # Uppercase not allowed
                "payload": {"test": "data"},
                "expected_error": "event_type"
            },
            {
                "event_type": "test event",  # Space not allowed
                "payload": {"test": "data"},
                "expected_error": "event_type"
            },
            # Invalid payload
            {
                "event_type": "test.event",
                "payload": None,
                "expected_error": "payload"
            },
            {
                "event_type": "test.event",
                "payload": [],
                "expected_error": "payload"
            },
            {
                "event_type": "test.event",
                "payload": {},
                "expected_error": "payload"
            },
        ]

        for test_case in validation_cases:
            response = test_client.post("/events", json=test_case)
            assert response.status_code == 400

            data = response.json()
            assert "error" in data
            assert data["error"]["code"] == 400

    def test_post_events_database_error(self, test_client, sample_event):
        """Test POST /events with database error."""
        # Mock put_event to raise an exception
        mock_client = test_client.app.dependency_overrides.get('src.handlers.events.get_db_client', lambda: None)()

        with patch.object(mock_client, 'put_event', side_effect=Exception("Database connection failed")):
            response = test_client.post("/events", json=sample_event)

            assert response.status_code == 500
            data = response.json()

            assert "error" in data
            assert data["error"]["code"] == 500
            assert "Failed to create event" in data["error"]["message"]

    def test_post_events_with_metadata(self, test_client, mock_dynamodb_table):
        """Test POST /events with optional metadata."""
        event_data = {
            "event_type": "user.created",
            "payload": {"user_id": "123", "email": "test@example.com"},
            "metadata": {
                "source": "registration-form",
                "version": "2.1.0",
                "campaign": "summer-promo"
            }
        }

        with patch.object(test_client.app.dependency_overrides.get('src.handlers.events.get_db_client', lambda: None)(),
                         'put_event', new_callable=AsyncMock) as mock_put:

            response = test_client.post("/events", json=event_data)

            assert response.status_code == 201

            # Verify metadata was stored
            mock_put.assert_called_once()
            stored_event = mock_put.call_args[0][0]
            assert stored_event.metadata == event_data["metadata"]

    def test_post_events_content_type_validation(self, test_client, sample_event):
        """Test POST /events with different content types."""
        # Test without Content-Type header
        response = test_client.post("/events", data=json.dumps(sample_event))
        # Should still work as FastAPI handles JSON parsing

        # Test with wrong Content-Type
        response = test_client.post(
            "/events",
            data=json.dumps(sample_event),
            headers={"Content-Type": "text/plain"}
        )
        # FastAPI should still parse JSON, but this tests the header handling

    def test_api_openapi_schema(self, test_client):
        """Test that OpenAPI schema is available."""
        response = test_client.get("/docs")
        assert response.status_code == 200

        response = test_client.get("/redoc")
        assert response.status_code == 200

        response = test_client.get("/openapi.json")
        assert response.status_code == 200

        schema = response.json()
        assert "paths" in schema
        assert "/events" in schema["paths"]
        assert "post" in schema["paths"]["/events"]

    def test_cors_headers(self, test_client):
        """Test CORS headers are present."""
        # OPTIONS request
        response = test_client.options("/events")
        assert response.status_code == 200

        # Check CORS headers
        assert "access-control-allow-origin" in response.headers
        assert "access-control-allow-methods" in response.headers
        assert "access-control-allow-headers" in response.headers

    def test_event_id_uniqueness(self, test_client, sample_event):
        """Test that generated event IDs are unique."""
        event_ids = set()

        # Make multiple requests
        for _ in range(5):
            with patch.object(test_client.app.dependency_overrides.get('src.handlers.events.get_db_client', lambda: None)(),
                             'put_event', new_callable=AsyncMock):

                response = test_client.post("/events", json=sample_event)
                assert response.status_code == 201

                data = response.json()
                event_ids.add(data["event_id"])

        # All IDs should be unique
        assert len(event_ids) == 5

    def test_response_format(self, test_client, sample_event):
        """Test response format matches specification."""
        with patch.object(test_client.app.dependency_overrides.get('src.handlers.events.get_db_client', lambda: None)(),
                         'put_event', new_callable=AsyncMock):

            response = test_client.post("/events", json=sample_event)

            assert response.status_code == 201
            data = response.json()

            # Validate required fields
            required_fields = ["event_id", "status", "created_at", "delivered_at", "message"]
            for field in required_fields:
                assert field in data

            # Validate data types
            assert isinstance(data["event_id"], str)
            assert isinstance(data["status"], str)
            assert isinstance(data["created_at"], str)  # ISO format
            assert data["delivered_at"] is None  # Should be null for pending events
            assert isinstance(data["message"], str)

            # Validate event_id format
            assert data["event_id"].startswith("evt_")
            assert len(data["event_id"]) == 16

            # Validate timestamp format (should be ISO with Z)
            assert data["created_at"].endswith("Z")

    def test_error_response_format(self, test_client):
        """Test error response format is consistent."""
        # Trigger validation error
        response = test_client.post("/events", json={"event_type": "test"})

        assert response.status_code == 400
        data = response.json()

        # Should have error structure
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]

        assert data["error"]["code"] == 400
        assert isinstance(data["error"]["message"], str)
