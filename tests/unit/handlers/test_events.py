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

    @pytest.mark.asyncio
    async def test_get_event_success(self, db_client):
        """Test get_event function with valid event."""
        from src.handlers.events import get_event
        from src.models.event import Event

        # Create mock event
        mock_event = Event(
            event_id="evt_test123456",
            event_type="order.created",
            payload={"order_id": "123"},
            metadata={"source": "test"},
            status="pending",
            created_at=datetime(2024, 1, 15, 10, 30, 1, tzinfo=timezone.utc),
            delivered_at=None,
            delivery_attempts=0
        )

        with patch.object(db_client, 'get_event', new_callable=AsyncMock, return_value=mock_event):
            response = await get_event("evt_test123456", db_client)

            assert isinstance(response, EventResponse)
            assert response.event_id == "evt_test123456"
            assert response.event_type == "order.created"
            assert response.payload == {"order_id": "123"}
            assert response.metadata == {"source": "test"}
            assert response.status == "pending"
            assert response.delivery_attempts == 0
            assert response.message == "Event retrieved successfully"

    @pytest.mark.asyncio
    async def test_get_event_not_found(self, db_client):
        """Test get_event function with non-existent event."""
        from src.handlers.events import get_event

        with patch.object(db_client, 'get_event', new_callable=AsyncMock, return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await get_event("evt_nonexistent", db_client)

            assert exc_info.value.status_code == 404
            assert "Event evt_nonexistent not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_event_database_error(self, db_client):
        """Test get_event function with database error."""
        from src.handlers.events import get_event

        with patch.object(db_client, 'get_event', side_effect=Exception("DB error")):
            with pytest.raises(HTTPException) as exc_info:
                await get_event("evt_test123", db_client)

            assert exc_info.value.status_code == 500
            assert "Failed to retrieve event" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_list_events_success(self, db_client):
        """Test list_events function with valid parameters."""
        from src.handlers.events import list_events
        from src.models.event import Event

        # Create mock events
        mock_events = [
            Event(
                event_id="evt_test123456",
                event_type="order.created",
                payload={"order_id": "123"},
                status="pending",
                created_at=datetime(2024, 1, 15, 10, 30, 1, tzinfo=timezone.utc),
                delivered_at=None,
                delivery_attempts=0
            ),
            Event(
                event_id="evt_test789012",
                event_type="user.created",
                payload={"user_id": "456"},
                status="delivered",
                created_at=datetime(2024, 1, 15, 10, 30, 2, tzinfo=timezone.utc),
                delivered_at=datetime(2024, 1, 15, 10, 30, 3, tzinfo=timezone.utc),
                delivery_attempts=1
            )
        ]

        with patch.object(db_client, 'list_events', new_callable=AsyncMock, return_value=mock_events) as mock_list:
            response = await list_events(status="pending", limit=10, cursor=None, db_client=db_client)

            assert isinstance(response, list)
            assert len(response) == 2

            # Verify list_events was called with correct parameters
            mock_list.assert_called_once_with(status="pending", limit=10, cursor=None)

            # Check response structure
            assert response[0].event_id == "evt_test123456"
            assert response[0].event_type == "order.created"
            assert response[0].status == "pending"
            assert response[0].message == "Event retrieved successfully"

    @pytest.mark.asyncio
    async def test_list_events_limit_validation(self, db_client):
        """Test list_events function with invalid limit."""
        from src.handlers.events import list_events

        with pytest.raises(HTTPException) as exc_info:
            await list_events(status=None, limit=150, cursor=None, db_client=db_client)

        assert exc_info.value.status_code == 400
        assert "Limit cannot exceed 100" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_list_events_database_error(self, db_client):
        """Test list_events function with database error."""
        from src.handlers.events import list_events

        with patch.object(db_client, 'list_events', side_effect=Exception("DB error")):
            with pytest.raises(HTTPException) as exc_info:
                await list_events(status=None, limit=10, cursor=None, db_client=db_client)

            assert exc_info.value.status_code == 500
            assert "Failed to list events" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_acknowledge_event_success(self, db_client):
        """Test acknowledge_event function with valid event."""
        from src.handlers.events import acknowledge_event
        from src.models.event import Event

        # Create mock event
        mock_event = Event(
            event_id="evt_test123456",
            event_type="order.created",
            payload={"order_id": "123"},
            status="pending",
            created_at=datetime(2024, 1, 15, 10, 30, 1, tzinfo=timezone.utc),
            delivered_at=None,
            delivery_attempts=0
        )

        with patch.object(db_client, 'get_event', new_callable=AsyncMock, return_value=mock_event):
            with patch.object(db_client, 'update_event', new_callable=AsyncMock) as mock_update:
                # Call acknowledge_event
                result = await acknowledge_event("evt_test123456", db_client)

                # Should return None (204 No Content)
                assert result is None

                # Verify update_event was called
                mock_update.assert_called_once()
                updated_event = mock_update.call_args[0][0]

                # Verify event was updated
                assert updated_event.status == "delivered"
                assert updated_event.delivered_at is not None
                assert updated_event.delivery_attempts == 1

    @pytest.mark.asyncio
    async def test_acknowledge_event_not_found(self, db_client):
        """Test acknowledge_event function with non-existent event."""
        from src.handlers.events import acknowledge_event

        with patch.object(db_client, 'get_event', new_callable=AsyncMock, return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await acknowledge_event("evt_nonexistent", db_client)

            assert exc_info.value.status_code == 404
            assert "Event evt_nonexistent not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_acknowledge_event_database_error(self, db_client):
        """Test acknowledge_event function with database error."""
        from src.handlers.events import acknowledge_event
        from src.models.event import Event

        mock_event = Event(
            event_id="evt_test123456",
            event_type="order.created",
            payload={"order_id": "123"},
            status="pending",
            created_at=datetime(2024, 1, 15, 10, 30, 1, tzinfo=timezone.utc),
            delivered_at=None,
            delivery_attempts=0
        )

        with patch.object(db_client, 'get_event', new_callable=AsyncMock, return_value=mock_event):
            with patch.object(db_client, 'update_event', side_effect=Exception("DB error")):
                with pytest.raises(HTTPException) as exc_info:
                    await acknowledge_event("evt_test123456", db_client)

                assert exc_info.value.status_code == 500
                assert "Failed to acknowledge event" in exc_info.value.detail


class TestBatchEventHandlers:
    """Test cases for batch event handler endpoints."""

    @pytest.mark.asyncio
    async def test_batch_create_events_all_success(self, db_client, sqs_client, delivery_client, metrics_client):
        """Test successful batch creation of events."""
        from src.models.request import BatchCreateEventRequest, CreateEventRequest
        from src.models.response import BatchCreateResponse, BatchCreateItemResult, BatchOperationSummary
        from src.handlers.events import batch_create_events
        from unittest.mock import AsyncMock

        # Create test request
        events = [
            CreateEventRequest(
                event_type="order.created",
                payload={"order_id": "123", "amount": 99.99},
                metadata={"source": "test"}
            ),
            CreateEventRequest(
                event_type="order.updated",
                payload={"order_id": "123", "status": "shipped"}
            )
        ]
        request = BatchCreateEventRequest(events=events)

        # Mock dependencies
        with patch.object(db_client, 'batch_get_events_by_idempotency_keys', new_callable=AsyncMock, return_value={}) as mock_idempotency:
            with patch.object(db_client, 'batch_put_events', new_callable=AsyncMock, return_value={
                "successful_event_ids": ["evt_test123456", "evt_test789012"],
                "failed_items": []
            }) as mock_batch_put:
                with patch.object(delivery_client, 'deliver_event', new_callable=AsyncMock, return_value=True) as mock_deliver:
                    with patch.object(sqs_client, 'send_message', new_callable=AsyncMock) as mock_sqs:
                        with patch.object(db_client, 'update_event', new_callable=AsyncMock) as mock_update:
                            with patch('src.handlers.events.get_user_id_from_request', return_value=None):

                                # Create mock HTTP request
                                from unittest.mock import MagicMock
                                http_request = MagicMock()

                                # Call batch create
                                response = await batch_create_events(
                                    request, http_request, db_client, sqs_client, delivery_client, metrics_client
                                )

                                # Assert response type and structure
                                assert isinstance(response, BatchCreateResponse)
                                assert len(response.results) == 2
                                assert all(result.success for result in response.results)
                                assert all(result.event is not None for result in response.results)
                                assert all(result.error is None for result in response.results)
                                assert response.summary.total == 2
                                assert response.summary.successful == 2
                                assert response.summary.failed == 0

                                # Verify mocks were called
                                mock_idempotency.assert_called_once()
                                mock_batch_put.assert_called_once()
                                assert mock_deliver.call_count == 2
                                assert mock_update.call_count == 2

    @pytest.mark.asyncio
    async def test_batch_create_events_partial_failure(self, db_client, sqs_client, delivery_client, metrics_client):
        """Test batch creation with some events failing."""
        from src.models.request import BatchCreateEventRequest, CreateEventRequest
        from src.handlers.events import batch_create_events
        from unittest.mock import AsyncMock

        # Create test request with one valid, one invalid event
        events = [
            CreateEventRequest(
                event_type="order.created",
                payload={"order_id": "123"}
            ),
            CreateEventRequest(
                event_type="",  # Invalid - empty event_type
                payload={"order_id": "456"}
            )
        ]
        request = BatchCreateEventRequest(events=events)

        with patch.object(db_client, 'batch_get_events_by_idempotency_keys', new_callable=AsyncMock, return_value={}) as mock_idempotency:
            with patch.object(db_client, 'batch_put_events', new_callable=AsyncMock, return_value={
                "successful_event_ids": ["evt_test123456"],
                "failed_items": []
            }) as mock_batch_put:
                with patch.object(delivery_client, 'deliver_event', new_callable=AsyncMock, return_value=True):
                    with patch.object(db_client, 'update_event', new_callable=AsyncMock):
                        with patch('src.handlers.events.get_user_id_from_request', return_value=None):

                            http_request = MagicMock()
                            response = await batch_create_events(
                                request, http_request, db_client, sqs_client, delivery_client, metrics_client
                            )

                            # Should have 1 success and 1 failure
                            assert len(response.results) == 2
                            successful_results = [r for r in response.results if r.success]
                            failed_results = [r for r in response.results if not r.success]
                            assert len(successful_results) == 1
                            assert len(failed_results) == 1
                            assert response.summary.successful == 1
                            assert response.summary.failed == 1

    @pytest.mark.asyncio
    async def test_batch_create_events_idempotency_duplicate(self, db_client, sqs_client, delivery_client, metrics_client):
        """Test batch creation with idempotency key preventing duplicate."""
        from src.models.request import BatchCreateEventRequest, CreateEventRequest
        from src.models.event import Event
        from src.handlers.events import batch_create_events
        from datetime import datetime, timezone
        from unittest.mock import AsyncMock

        # Create existing event for idempotency check
        existing_event = Event(
            event_id="evt_existing123",
            event_type="order.created",
            payload={"order_id": "123"},
            status="delivered",
            created_at=datetime(2024, 1, 15, 10, 30, 1, tzinfo=timezone.utc),
            delivered_at=datetime(2024, 1, 15, 10, 30, 2, tzinfo=timezone.utc),
            delivery_attempts=1
        )

        events = [
            CreateEventRequest(
                event_type="order.created",
                payload={"order_id": "123"},
                idempotency_key="order-123-2024-01-15"
            )
        ]
        request = BatchCreateEventRequest(events=events)

        with patch.object(db_client, 'batch_get_events_by_idempotency_keys', new_callable=AsyncMock,
                        return_value={"order-123-2024-01-15": existing_event}) as mock_idempotency:
            with patch('src.handlers.events.get_user_id_from_request', return_value="user123"):

                http_request = MagicMock()
                response = await batch_create_events(
                    request, http_request, db_client, sqs_client, delivery_client, metrics_client
                )

                # Should return existing event as successful
                assert len(response.results) == 1
                result = response.results[0]
                assert result.success
                assert result.event is not None
                assert result.event.event_id == "evt_existing123"
                assert "already exists" in result.event.message

                # Should not call batch_put_events since it's a duplicate
                # (We can't easily test this without more complex mocking)

    @pytest.mark.asyncio
    async def test_batch_create_events_exceeds_max_size(self, db_client, sqs_client, delivery_client, metrics_client):
        """Test batch creation with too many events."""
        from src.models.request import BatchCreateEventRequest, CreateEventRequest
        from src.handlers.events import batch_create_events
        from fastapi import HTTPException

        # Create 101 events (exceeds limit)
        events = [
            CreateEventRequest(
                event_type="order.created",
                payload={"order_id": str(i)}
            ) for i in range(101)
        ]
        request = BatchCreateEventRequest(events=events)

        with patch('src.handlers.events.get_user_id_from_request', return_value=None):
            http_request = MagicMock()

            with pytest.raises(HTTPException) as exc_info:
                await batch_create_events(
                    request, http_request, db_client, sqs_client, delivery_client, metrics_client
                )

            assert exc_info.value.status_code == 400
            assert "batch size cannot exceed 100" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_batch_update_events_all_success(self, db_client, sqs_client, metrics_client):
        """Test successful batch update of events."""
        from src.models.request import BatchUpdateEventRequest, BatchUpdateEventItem
        from src.models.event import Event
        from src.handlers.events import batch_update_events
        from datetime import datetime, timezone
        from unittest.mock import AsyncMock

        # Create existing events
        existing_events = [
            Event(
                event_id="evt_test123456",
                event_type="order.created",
                payload={"order_id": "123"},
                status="delivered",
                created_at=datetime(2024, 1, 15, 10, 30, 1, tzinfo=timezone.utc),
                delivered_at=datetime(2024, 1, 15, 10, 30, 2, tzinfo=timezone.utc),
                delivery_attempts=1,
                user_id="user123"
            )
        ]

        # Create update request
        updates = [
            BatchUpdateEventItem(
                event_id="evt_test123456",
                payload={"order_id": "123", "amount": 150.00}
            )
        ]
        request = BatchUpdateEventRequest(events=updates)

        with patch.object(db_client, 'batch_get_events', new_callable=AsyncMock, return_value=existing_events) as mock_batch_get:
            with patch.object(db_client, 'update_event', new_callable=AsyncMock) as mock_update:
                with patch.object(sqs_client, 'send_message', new_callable=AsyncMock) as mock_sqs:
                    with patch('src.handlers.events.get_user_id_from_request', return_value="user123"):

                        http_request = MagicMock()
                        response = await batch_update_events(request, http_request, db_client, sqs_client)

                        # Assert success
                        assert len(response.results) == 1
                        result = response.results[0]
                        assert result.success
                        assert result.event is not None
                        assert "queued for redelivery" in result.event.message
                        assert response.summary.successful == 1
                        assert response.summary.failed == 0

                        # Verify SQS was called for redelivery
                        mock_sqs.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_update_events_ownership_check(self, db_client, sqs_client, metrics_client):
        """Test batch update with ownership validation."""
        from src.models.request import BatchUpdateEventRequest, BatchUpdateEventItem
        from src.models.event import Event
        from src.handlers.events import batch_update_events
        from datetime import datetime, timezone
        from unittest.mock import AsyncMock

        # Create event owned by different user
        existing_events = [
            Event(
                event_id="evt_test123456",
                event_type="order.created",
                payload={"order_id": "123"},
                status="pending",
                created_at=datetime(2024, 1, 15, 10, 30, 1, tzinfo=timezone.utc),
                user_id="other_user"
            )
        ]

        updates = [
            BatchUpdateEventItem(
                event_id="evt_test123456",
                payload={"order_id": "123", "amount": 150.00}
            )
        ]
        request = BatchUpdateEventRequest(events=updates)

        with patch.object(db_client, 'batch_get_events', new_callable=AsyncMock, return_value=existing_events):
            with patch('src.handlers.events.get_user_id_from_request', return_value="user123"):

                http_request = MagicMock()
                response = await batch_update_events(request, http_request, db_client, sqs_client)

                # Should fail due to ownership
                assert len(response.results) == 1
                result = response.results[0]
                assert not result.success
                assert result.error is not None
                assert result.error.code == "FORBIDDEN"
                assert response.summary.failed == 1

    @pytest.mark.asyncio
    async def test_batch_update_events_not_found(self, db_client, sqs_client, metrics_client):
        """Test batch update with non-existent event."""
        from src.models.request import BatchUpdateEventRequest, BatchUpdateEventItem
        from src.handlers.events import batch_update_events
        from unittest.mock import AsyncMock

        # Empty results - event not found
        updates = [
            BatchUpdateEventItem(
                event_id="evt_nonexistent",
                payload={"order_id": "123", "amount": 150.00}
            )
        ]
        request = BatchUpdateEventRequest(events=updates)

        with patch.object(db_client, 'batch_get_events', new_callable=AsyncMock, return_value=[]):
            with patch('src.handlers.events.get_user_id_from_request', return_value="user123"):

                http_request = MagicMock()
                response = await batch_update_events(request, http_request, db_client, sqs_client)

                # Should fail with NOT_FOUND
                assert len(response.results) == 1
                result = response.results[0]
                assert not result.success
                assert result.error is not None
                assert result.error.code == "NOT_FOUND"
                assert response.summary.failed == 1

    @pytest.mark.asyncio
    async def test_batch_delete_events_all_success(self, db_client, metrics_client):
        """Test successful batch deletion of events."""
        from src.models.request import BatchDeleteEventRequest
        from src.models.event import Event
        from src.handlers.events import batch_delete_events
        from datetime import datetime, timezone
        from unittest.mock import AsyncMock

        # Create existing events
        existing_events = [
            Event(
                event_id="evt_test123456",
                event_type="order.created",
                payload={"order_id": "123"},
                status="delivered",
                created_at=datetime(2024, 1, 15, 10, 30, 1, tzinfo=timezone.utc),
                user_id="user123"
            )
        ]

        # Create delete request
        request = BatchDeleteEventRequest(event_ids=["evt_test123456"])

        with patch.object(db_client, 'batch_get_events', new_callable=AsyncMock, return_value=existing_events) as mock_batch_get:
            with patch.object(db_client, 'batch_delete_events', new_callable=AsyncMock, return_value={
                "successful_event_ids": ["evt_test123456"],
                "failed_event_ids": []
            }) as mock_batch_delete:
                with patch('src.handlers.events.get_user_id_from_request', return_value="user123"):

                    http_request = MagicMock()
                    response = await batch_delete_events(request, http_request, db_client)

                    # Assert success
                    assert len(response.results) == 1
                    result = response.results[0]
                    assert result.success
                    assert result.event_id == "evt_test123456"
                    assert result.message == "Event deleted"
                    assert response.summary.successful == 1
                    assert response.summary.failed == 0

    @pytest.mark.asyncio
    async def test_batch_delete_events_idempotent(self, db_client, metrics_client):
        """Test batch deletion with non-existent events (idempotent)."""
        from src.models.request import BatchDeleteEventRequest
        from src.handlers.events import batch_delete_events
        from unittest.mock import AsyncMock

        # Event not found - should be treated as successful (idempotent delete)
        request = BatchDeleteEventRequest(event_ids=["evt_nonexistent"])

        with patch.object(db_client, 'batch_get_events', new_callable=AsyncMock, return_value=[]):
            with patch('src.handlers.events.get_user_id_from_request', return_value="user123"):

                http_request = MagicMock()
                response = await batch_delete_events(request, http_request, db_client)

                # Should succeed (idempotent)
                assert len(response.results) == 1
                result = response.results[0]
                assert result.success
                assert result.event_id == "evt_nonexistent"
                assert "idempotent" in result.message
                assert response.summary.successful == 1

    @pytest.mark.asyncio
    async def test_batch_delete_events_ownership_check(self, db_client, metrics_client):
        """Test batch deletion with ownership validation."""
        from src.models.request import BatchDeleteEventRequest
        from src.models.event import Event
        from src.handlers.events import batch_delete_events
        from datetime import datetime, timezone
        from unittest.mock import AsyncMock

        # Create event owned by different user
        existing_events = [
            Event(
                event_id="evt_test123456",
                event_type="order.created",
                payload={"order_id": "123"},
                status="pending",
                created_at=datetime(2024, 1, 15, 10, 30, 1, tzinfo=timezone.utc),
                user_id="other_user"
            )
        ]

        request = BatchDeleteEventRequest(event_ids=["evt_test123456"])

        with patch.object(db_client, 'batch_get_events', new_callable=AsyncMock, return_value=existing_events):
            with patch('src.handlers.events.get_user_id_from_request', return_value="user123"):

                http_request = MagicMock()
                response = await batch_delete_events(request, http_request, db_client)

                # Should fail due to ownership
                assert len(response.results) == 1
                result = response.results[0]
                assert not result.success
                assert result.error is not None
                assert result.error.code == "FORBIDDEN"
                assert response.summary.failed == 1