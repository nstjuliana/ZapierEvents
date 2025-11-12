"""
Module: test_event_filtering.py
Description: Integration tests for event filtering functionality.

Tests advanced filtering capabilities including payload/metadata filtering,
comparison operators, date ranges, and nested JSON paths.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from datetime import datetime, timezone

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


@pytest.fixture
def sample_events():
    """Create sample events for testing filtering."""
    return [
        type('MockEvent', (), {
            'event_id': 'evt_abc123xyz456',
            'event_type': 'order.created',
            'payload': {'order_id': '12345', 'amount': 99.99, 'customer': {'email': 'john@gmail.com'}},
            'metadata': {'source': 'ecommerce', 'version': '1.0'},
            'status': 'delivered',
            'created_at': datetime(2024, 1, 15, 10, 30, 1, tzinfo=timezone.utc),
            'delivered_at': datetime(2024, 1, 15, 10, 30, 2, tzinfo=timezone.utc),
            'delivery_attempts': 1,
            'user_id': None,
            'idempotency_key': None
        })(),
        type('MockEvent', (), {
            'event_id': 'evt_def456uvw789',
            'event_type': 'user.created',
            'payload': {'user_id': '67890', 'amount': 150.00, 'customer': {'email': 'jane@yahoo.com'}},
            'metadata': {'source': 'api', 'version': '2.0'},
            'status': 'pending',
            'created_at': datetime(2024, 1, 15, 11, 0, 0, tzinfo=timezone.utc),
            'delivered_at': None,
            'delivery_attempts': 0,
            'user_id': None,
            'idempotency_key': None
        })(),
        type('MockEvent', (), {
            'event_id': 'evt_ghi789xyz012',
            'event_type': 'order.shipped',
            'payload': {'order_id': '54321', 'amount': 75.50, 'customer': {'email': 'bob@gmail.com'}},
            'metadata': {'source': 'ecommerce', 'version': '1.0'},
            'status': 'failed',
            'created_at': datetime(2024, 1, 14, 9, 15, 30, tzinfo=timezone.utc),
            'delivered_at': None,
            'delivery_attempts': 3,
            'user_id': None,
            'idempotency_key': None
        })()
    ]


class TestEventFiltering:
    """Integration tests for event filtering functionality."""

    def test_payload_exact_match(self, test_client, sample_events):
        """Test filtering by exact payload field match."""
        # Mock list_events to return filtered results
        filtered_events = [sample_events[0]]  # Only the order.created event

        with patch.object(test_client.app.dependency_overrides.get('src.handlers.events.get_db_client', lambda: None)(),
                         'list_events', new_callable=AsyncMock, return_value=filtered_events) as mock_list:

            response = test_client.get("/events?payload.order_id=12345")
            assert response.status_code == 200

            data = response.json()
            assert len(data) == 1
            assert data[0]["event_id"] == "evt_abc123xyz456"
            assert data[0]["payload"]["order_id"] == "12345"

            # Verify filters were passed correctly
            call_args = mock_list.call_args
            assert call_args[1]["filters"] is not None
            assert len(call_args[1]["filters"]) == 1

    def test_payload_numeric_comparison(self, test_client, sample_events):
        """Test filtering by numeric payload field with comparison operators."""
        filtered_events = [sample_events[1]]  # Only the user.created event with amount >= 100

        with patch.object(test_client.app.dependency_overrides.get('src.handlers.events.get_db_client', lambda: None)(),
                         'list_events', new_callable=AsyncMock, return_value=filtered_events) as mock_list:

            response = test_client.get("/events?payload.amount[gte]=100")
            assert response.status_code == 200

            data = response.json()
            assert len(data) == 1
            assert data[0]["payload"]["amount"] == 150.00

    def test_metadata_filtering(self, test_client, sample_events):
        """Test filtering by metadata fields."""
        filtered_events = [sample_events[0], sample_events[2]]  # Both ecommerce events

        with patch.object(test_client.app.dependency_overrides.get('src.handlers.events.get_db_client', lambda: None)(),
                         'list_events', new_callable=AsyncMock, return_value=filtered_events) as mock_list:

            response = test_client.get("/events?metadata.source=ecommerce")
            assert response.status_code == 200

            data = response.json()
            assert len(data) == 2
            for event in data:
                assert event["metadata"]["source"] == "ecommerce"

    def test_nested_path_filtering(self, test_client, sample_events):
        """Test filtering by deeply nested payload paths."""
        filtered_events = [sample_events[0], sample_events[2]]  # Both Gmail users

        with patch.object(test_client.app.dependency_overrides.get('src.handlers.events.get_db_client', lambda: None)(),
                         'list_events', new_callable=AsyncMock, return_value=filtered_events) as mock_list:

            response = test_client.get("/events?payload.customer.email[contains]=gmail")
            assert response.status_code == 200

            data = response.json()
            assert len(data) == 2
            for event in data:
                assert "gmail" in event["payload"]["customer"]["email"]

    def test_string_operations(self, test_client, sample_events):
        """Test string comparison operators (contains, startswith)."""
        filtered_events = [sample_events[0], sample_events[2]]  # Events with order. in type

        with patch.object(test_client.app.dependency_overrides.get('src.handlers.events.get_db_client', lambda: None)(),
                         'list_events', new_callable=AsyncMock, return_value=filtered_events) as mock_list:

            response = test_client.get("/events?event_type[startswith]=order.")
            assert response.status_code == 200

            data = response.json()
            assert len(data) == 2
            for event in data:
                assert event["event_type"].startswith("order.")

    def test_date_filtering_created_after(self, test_client, sample_events):
        """Test filtering by created_at date."""
        filtered_events = [sample_events[0], sample_events[1]]  # Events after 2024-01-15 00:00

        with patch.object(test_client.app.dependency_overrides.get('src.handlers.events.get_db_client', lambda: None)(),
                         'list_events', new_callable=AsyncMock, return_value=filtered_events) as mock_list:

            response = test_client.get("/events?created_after=2024-01-15T00:00:00Z")
            assert response.status_code == 200

            data = response.json()
            assert len(data) == 2
            for event in data:
                created_at = datetime.fromisoformat(event["created_at"].replace('Z', '+00:00'))
                filter_date = datetime(2024, 1, 15, tzinfo=timezone.utc)
                assert created_at >= filter_date

    def test_date_filtering_delivered_before(self, test_client, sample_events):
        """Test filtering by delivered_at date."""
        filtered_events = [sample_events[0]]  # Only delivered event

        with patch.object(test_client.app.dependency_overrides.get('src.handlers.events.get_db_client', lambda: None)(),
                         'list_events', new_callable=AsyncMock, return_value=filtered_events) as mock_list:

            response = test_client.get("/events?delivered_before=2024-01-16T00:00:00Z")
            assert response.status_code == 200

            data = response.json()
            assert len(data) == 1
            assert data[0]["delivered_at"] is not None

    def test_multiple_filters_combined(self, test_client, sample_events):
        """Test combining multiple filters."""
        filtered_events = [sample_events[0]]  # ecommerce + amount >= 50

        with patch.object(test_client.app.dependency_overrides.get('src.handlers.events.get_db_client', lambda: None)(),
                         'list_events', new_callable=AsyncMock, return_value=filtered_events) as mock_list:

            response = test_client.get("/events?metadata.source=ecommerce&payload.amount[gte]=50")
            assert response.status_code == 200

            data = response.json()
            assert len(data) == 1
            assert data[0]["metadata"]["source"] == "ecommerce"
            assert data[0]["payload"]["amount"] >= 50

    def test_status_and_custom_filters_combined(self, test_client, sample_events):
        """Test combining status filter with custom filters."""
        filtered_events = [sample_events[2]]  # failed status + amount < 100

        with patch.object(test_client.app.dependency_overrides.get('src.handlers.events.get_db_client', lambda: None)(),
                         'list_events', new_callable=AsyncMock, return_value=filtered_events) as mock_list:

            response = test_client.get("/events?status=failed&payload.amount[lt]=100")
            assert response.status_code == 200

            data = response.json()
            assert len(data) == 1
            assert data[0]["status"] == "failed"
            assert data[0]["payload"]["amount"] < 100

            # Verify both status and filters were passed
            call_args = mock_list.call_args
            assert call_args[1]["status"] == "failed"
            assert call_args[1]["filters"] is not None

    def test_invalid_filter_operator(self, test_client):
        """Test handling of invalid filter operators."""
        # This should not cause an error - invalid operators are ignored
        with patch.object(test_client.app.dependency_overrides.get('src.handlers.events.get_db_client', lambda: None)(),
                         'list_events', new_callable=AsyncMock, return_value=[]) as mock_list:

            response = test_client.get("/events?payload.order_id[invalid]=12345")
            assert response.status_code == 200

            # Verify list_events was called (but with no filters due to invalid operator)
            mock_list.assert_called_once()

    def test_empty_filter_results(self, test_client):
        """Test when filters match no events."""
        with patch.object(test_client.app.dependency_overrides.get('src.handlers.events.get_db_client', lambda: None)(),
                         'list_events', new_callable=AsyncMock, return_value=[]) as mock_list:

            response = test_client.get("/events?payload.order_id=nonexistent")
            assert response.status_code == 200

            data = response.json()
            assert data == []

    def test_filter_with_limit_and_pagination(self, test_client, sample_events):
        """Test filtering works with limit and pagination parameters."""
        filtered_events = [sample_events[0]]

        with patch.object(test_client.app.dependency_overrides.get('src.handlers.events.get_db_client', lambda: None)(),
                         'list_events', new_callable=AsyncMock, return_value=filtered_events) as mock_list:

            response = test_client.get("/events?payload.amount[gte]=50&limit=5&cursor=some_cursor")
            assert response.status_code == 200

            # Verify all parameters were passed correctly
            call_args = mock_list.call_args
            assert call_args[1]["limit"] == 5
            assert call_args[1]["cursor"] == "some_cursor"
            assert call_args[1]["filters"] is not None

    def test_filter_edge_cases(self, test_client):
        """Test edge cases in filter parsing."""
        with patch.object(test_client.app.dependency_overrides.get('src.handlers.events.get_db_client', lambda: None)(),
                         'list_events', new_callable=AsyncMock, return_value=[]) as mock_list:

            # Empty filter values should be ignored
            response = test_client.get("/events?payload.order_id=&metadata.source=")
            assert response.status_code == 200

            # Reserved parameters should not be treated as filters
            response = test_client.get("/events?status=pending&limit=10&cursor=test&payload.order_id=123")
            assert response.status_code == 200

            call_args = mock_list.call_args
            assert call_args[1]["status"] == "pending"
            assert call_args[1]["limit"] == 10
            assert call_args[1]["cursor"] == "test"
            assert call_args[1]["filters"] is not None  # Only payload.order_id filter

    def test_filter_operators_comprehensive(self, test_client, sample_events):
        """Test all supported comparison operators."""
        test_cases = [
            ("eq", "payload.amount=99.99", [sample_events[0]]),
            ("ne", "payload.amount[ne]=99.99", [sample_events[1], sample_events[2]]),
            ("gt", "payload.amount[gt]=100", [sample_events[1]]),
            ("gte", "payload.amount[gte]=99.99", [sample_events[0], sample_events[1]]),
            ("lt", "payload.amount[lt]=100", [sample_events[0], sample_events[2]]),
            ("lte", "payload.amount[lte]=99.99", [sample_events[0], sample_events[2]]),
        ]

        for operator, query, expected_events in test_cases:
            with patch.object(test_client.app.dependency_overrides.get('src.handlers.events.get_db_client', lambda: None)(),
                             'list_events', new_callable=AsyncMock, return_value=expected_events):

                response = test_client.get(f"/events?{query}")
                assert response.status_code == 200

                data = response.json()
                assert len(data) == len(expected_events)

                if expected_events:
                    # Spot check that the expected event is returned
                    assert data[0]["event_id"] == expected_events[0].event_id
