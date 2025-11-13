"""
Module: test_dynamodb.py
Description: Unit tests for DynamoDB client operations.

Tests DynamoDBClient put_event and get_event methods with mocked
AWS services using moto. Covers success cases, error handling,
and data serialization/deserialization.
"""

import pytest
from unittest.mock import patch, AsyncMock
from botocore.exceptions import ClientError
from datetime import datetime, timezone
from moto import mock_aws

from src.storage.dynamodb import DynamoDBClient
from src.models.event import Event


class TestDynamoDBClient:
    """Test cases for DynamoDBClient operations."""

    def test_client_initialization(self, test_settings):
        """Test DynamoDBClient initialization."""
        client = DynamoDBClient(table_name=test_settings.events_table_name)

        assert client.table_name == test_settings.events_table_name
        assert hasattr(client, 'dynamodb')
        assert hasattr(client, 'table')

    def test_client_initialization_invalid_table_name(self):
        """Test DynamoDBClient with invalid table name."""
        with pytest.raises(ValueError, match="table_name must be a non-empty string"):
            DynamoDBClient(table_name="")

        with pytest.raises(ValueError, match="table_name must be a non-empty string"):
            DynamoDBClient(table_name=None)

    @pytest.mark.asyncio
    async def test_put_event_success(self, db_client, sample_event_model, mock_dynamodb_table):
        """Test successful event storage."""
        # Act
        await db_client.put_event(sample_event_model)

        # Assert - check that item was stored
        response = mock_dynamodb_table.get_item(Key={'event_id': sample_event_model.event_id})
        assert 'Item' in response

        item = response['Item']
        assert item['event_id'] == sample_event_model.event_id
        assert item['event_type'] == sample_event_model.event_type
        assert item['status'] == sample_event_model.status

        # Check datetime serialization
        assert 'created_at' in item
        assert isinstance(item['created_at'], str)
        # Should be ISO format with Z suffix
        assert item['created_at'].endswith('Z')

    @pytest.mark.asyncio
    async def test_put_event_with_delivered_at(self, db_client, sample_event_model, mock_dynamodb_table):
        """Test event storage with delivered_at timestamp."""
        # Arrange
        sample_event_model.mark_delivered()

        # Act
        await db_client.put_event(sample_event_model)

        # Assert
        response = mock_dynamodb_table.get_item(Key={'event_id': sample_event_model.event_id})
        item = response['Item']

        assert 'delivered_at' in item
        assert isinstance(item['delivered_at'], str)
        assert item['delivered_at'].endswith('Z')

    @pytest.mark.asyncio
    async def test_put_event_invalid_event(self, db_client):
        """Test put_event with invalid event object."""
        with pytest.raises(ValueError, match="event must be an Event instance"):
            await db_client.put_event("not an event")

        with pytest.raises(ValueError, match="event must be an Event instance"):
            await db_client.put_event(None)

    @pytest.mark.asyncio
    async def test_put_event_dynamodb_error(self, db_client, sample_event_model):
        """Test put_event error handling."""
        # Mock DynamoDB table to raise an error
        with patch.object(db_client.table, 'put_item', side_effect=ClientError(
            error_response={'Error': {'Code': 'ValidationException', 'Message': 'Test error'}},
            operation_name='PutItem'
        )):
            with pytest.raises(ClientError):
                await db_client.put_event(sample_event_model)

    @pytest.mark.asyncio
    async def test_get_event_success(self, db_client, sample_event_model, mock_dynamodb_table):
        """Test successful event retrieval."""
        # Arrange - store event first
        await db_client.put_event(sample_event_model)

        # Act
        retrieved_event = await db_client.get_event(sample_event_model.event_id)

        # Assert
        assert retrieved_event is not None
        assert retrieved_event.event_id == sample_event_model.event_id
        assert retrieved_event.event_type == sample_event_model.event_type
        assert retrieved_event.status == sample_event_model.status

        # Check datetime deserialization
        assert isinstance(retrieved_event.created_at, datetime)
        assert retrieved_event.created_at.tzinfo is not None

    @pytest.mark.asyncio
    async def test_get_event_with_delivered_at(self, db_client, sample_event_model, mock_dynamodb_table):
        """Test event retrieval with delivered_at timestamp."""
        # Arrange
        sample_event_model.mark_delivered()
        await db_client.put_event(sample_event_model)

        # Act
        retrieved_event = await db_client.get_event(sample_event_model.event_id)

        # Assert
        assert retrieved_event is not None
        assert retrieved_event.delivered_at is not None
        assert isinstance(retrieved_event.delivered_at, datetime)
        assert retrieved_event.delivered_at.tzinfo is not None

    @pytest.mark.asyncio
    async def test_get_event_not_found(self, db_client):
        """Test get_event when event doesn't exist."""
        result = await db_client.get_event("evt_nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_event_invalid_id(self, db_client):
        """Test get_event with invalid event ID."""
        with pytest.raises(ValueError, match="event_id must be a non-empty string"):
            await db_client.get_event("")

        with pytest.raises(ValueError, match="event_id must be a non-empty string"):
            await db_client.get_event(None)

    @pytest.mark.asyncio
    async def test_get_event_dynamodb_error(self, db_client):
        """Test get_event error handling."""
        # Mock DynamoDB table to raise an error
        with patch.object(db_client.table, 'get_item', side_effect=ClientError(
            error_response={'Error': {'Code': 'InternalServerError', 'Message': 'Test error'}},
            operation_name='GetItem'
        )):
            with pytest.raises(ClientError):
                await db_client.get_event("evt_test123")

    def test_datetime_serialization_roundtrip(self, db_client, sample_event_model, mock_dynamodb_table):
        """Test that datetime serialization/deserialization is reversible."""
        import asyncio

        async def test():
            # Store event
            await db_client.put_event(sample_event_model)

            # Retrieve event
            retrieved = await db_client.get_event(sample_event_model.event_id)

            # Check datetime fields are preserved
            assert retrieved.created_at == sample_event_model.created_at
            assert retrieved.delivered_at == sample_event_model.delivered_at

        asyncio.run(test())

    @mock_aws
    def test_list_events_no_filter(self, db_client):
        """Test list_events without status filter (scan operation)."""
        import asyncio

        async def test():
            # Arrange - create mock table
            import boto3
            dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
            table = dynamodb.create_table(
                TableName=db_client.table_name,
                KeySchema=[{'AttributeName': 'event_id', 'KeyType': 'HASH'}],
                AttributeDefinitions=[
                    {'AttributeName': 'event_id', 'AttributeType': 'S'},
                    {'AttributeName': 'status', 'AttributeType': 'S'},
                    {'AttributeName': 'created_at', 'AttributeType': 'S'}
                ],
                GlobalSecondaryIndexes=[{
                    'IndexName': 'StatusIndex',
                    'KeySchema': [
                        {'AttributeName': 'status', 'KeyType': 'HASH'},
                        {'AttributeName': 'created_at', 'KeyType': 'RANGE'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'}
                }],
                BillingMode='PAY_PER_REQUEST'
            )

            # Create test events
            event1 = Event(
                event_id="evt_abc123xyz456",
                event_type="order.created",
                payload={"order_id": "123"},
                status="pending",
                created_at=datetime(2024, 1, 15, 10, 30, 1, tzinfo=timezone.utc)
            )
            event2 = Event(
                event_id="evt_def456uvw789",
                event_type="user.created",
                payload={"user_id": "456"},
                status="delivered",
                created_at=datetime(2024, 1, 15, 10, 30, 2, tzinfo=timezone.utc)
            )

            await db_client.put_event(event1)
            await db_client.put_event(event2)

            # Act
            events = await db_client.list_events(limit=10)

            # Assert
            assert len(events) == 2
            # Events should be in descending order by created_at (most recent first)
            assert events[0].event_id == "evt_def456uvw789"  # Most recent
            assert events[1].event_id == "evt_abc123xyz456"  # Older

        asyncio.run(test())

    @pytest.mark.asyncio
    @mock_aws
    async def test_list_events_with_status_filter(self, db_client):
        """Test list_events with status filter (query operation)."""
        # Arrange - create mock table
        import boto3
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.create_table(
            TableName=db_client.table_name,
            KeySchema=[{'AttributeName': 'event_id', 'KeyType': 'HASH'}],
            AttributeDefinitions=[
                {'AttributeName': 'event_id', 'AttributeType': 'S'},
                {'AttributeName': 'status', 'AttributeType': 'S'},
                {'AttributeName': 'created_at', 'AttributeType': 'S'}
            ],
            GlobalSecondaryIndexes=[{
                'IndexName': 'StatusIndex',
                'KeySchema': [
                    {'AttributeName': 'status', 'KeyType': 'HASH'},
                    {'AttributeName': 'created_at', 'KeyType': 'RANGE'}
                ],
                'Projection': {'ProjectionType': 'ALL'}
            }],
            BillingMode='PAY_PER_REQUEST'
        )

        # Create test events
        event1 = Event(
            event_id="evt_abc123xyz456",
            event_type="order.created",
            payload={"order_id": "123"},
            status="pending",
            created_at=datetime(2024, 1, 15, 10, 30, 1, tzinfo=timezone.utc)
        )
        event2 = Event(
            event_id="evt_def456uvw789",
            event_type="user.created",
            payload={"user_id": "456"},
            status="delivered",
            created_at=datetime(2024, 1, 15, 10, 30, 2, tzinfo=timezone.utc)
        )

        await db_client.put_event(event1)
        await db_client.put_event(event2)

        # Act - filter for pending events
        events = await db_client.list_events(status="pending", limit=10)

        # Assert
        assert len(events) == 1
        assert events[0].event_id == "evt_abc123xyz456"
        assert events[0].status == "pending"

    @pytest.mark.asyncio
    async def test_list_events_with_limit(self, db_client, mock_dynamodb_table):
        """Test list_events respects limit parameter."""
        # Arrange - create multiple events
        for i in range(5):
            event = Event(
                event_id=f"evt_test{i:03d}",
                event_type="test.event",
                payload={"id": i},
                status="pending",
                created_at=datetime(2024, 1, 15, 10, 30, i, tzinfo=timezone.utc)
            )
            await db_client.put_event(event)

        # Act
        events = await db_client.list_events(limit=3)

        # Assert
        assert len(events) == 3

    @pytest.mark.asyncio
    async def test_list_events_limit_validation(self, db_client):
        """Test list_events validates limit parameter."""
        with pytest.raises(ValueError, match="limit must be between 1 and 100"):
            await db_client.list_events(limit=0)

        with pytest.raises(ValueError, match="limit must be between 1 and 100"):
            await db_client.list_events(limit=150)

    @pytest.mark.asyncio
    async def test_list_events_invalid_cursor(self, db_client):
        """Test list_events with invalid cursor."""
        with pytest.raises(ValueError, match="Invalid pagination cursor"):
            await db_client.list_events(cursor="invalid_cursor")

    @pytest.mark.asyncio
    async def test_update_event_success(self, db_client, sample_event_model, mock_dynamodb_table):
        """Test successful event update."""
        # Arrange - store initial event
        await db_client.put_event(sample_event_model)

        # Modify event
        sample_event_model.status = "delivered"
        sample_event_model.delivered_at = datetime.now(timezone.utc)
        sample_event_model.delivery_attempts = 1

        # Act
        await db_client.update_event(sample_event_model)

        # Assert - check that item was updated
        response = mock_dynamodb_table.get_item(Key={'event_id': sample_event_model.event_id})
        assert 'Item' in response

        item = response['Item']
        assert item['status'] == "delivered"
        assert item['delivery_attempts'] == 1
        assert 'delivered_at' in item

    @pytest.mark.asyncio
    async def test_update_event_invalid_event(self, db_client):
        """Test update_event with invalid event object."""
        with pytest.raises(ValueError, match="event must be an Event instance"):
            await db_client.update_event("not an event")

        with pytest.raises(ValueError, match="event must be an Event instance"):
            await db_client.update_event(None)

    @pytest.mark.asyncio
    async def test_update_event_dynamodb_error(self, db_client, sample_event_model):
        """Test update_event error handling."""
        # Mock DynamoDB table to raise an error
        with patch.object(db_client.table, 'put_item', side_effect=ClientError(
            error_response={'Error': {'Code': 'ConditionalCheckFailedException', 'Message': 'Test error'}},
            operation_name='PutItem'
        )):
            with pytest.raises(ClientError):
                await db_client.update_event(sample_event_model)


class TestBatchDynamoDBOperations:
    """Test cases for batch DynamoDB operations."""

    @pytest.mark.asyncio
    async def test_batch_put_events_single_chunk(self, db_client, mock_dynamodb_table):
        """Test batch_put_events with single chunk (under 25 items)."""
        # Create test events
        events = []
        for i in range(3):
            event = Event(
                event_id=f"evt_test{i:03d}",
                event_type="order.created",
                payload={"order_id": f"{i}", "amount": 99.99},
                status="pending",
                created_at=datetime(2024, 1, 15, 10, 30, 1, tzinfo=timezone.utc)
            )
            events.append(event)

        # Call batch put
        result = await db_client.batch_put_events(events)

        # Assert results
        assert "successful_event_ids" in result
        assert "failed_items" in result
        assert len(result["successful_event_ids"]) == 3
        assert len(result["failed_items"]) == 0

        # Verify events were stored
        for event in events:
            response = mock_dynamodb_table.get_item(Key={'event_id': event.event_id})
            assert 'Item' in response

    @pytest.mark.asyncio
    async def test_batch_put_events_multiple_chunks(self, db_client, mock_dynamodb_table):
        """Test batch_put_events with multiple chunks (over 25 items)."""
        # Create 30 test events (will be split into 2 chunks of 25, then 5)
        events = []
        for i in range(30):
            event = Event(
                event_id=f"evt_test{i:03d}",
                event_type="order.created",
                payload={"order_id": f"{i}", "amount": 99.99},
                status="pending",
                created_at=datetime(2024, 1, 15, 10, 30, 1, tzinfo=timezone.utc)
            )
            events.append(event)

        # Call batch put
        result = await db_client.batch_put_events(events)

        # Assert results
        assert len(result["successful_event_ids"]) == 30
        assert len(result["failed_items"]) == 0

        # Verify all events were stored
        for event in events:
            response = mock_dynamodb_table.get_item(Key={'event_id': event.event_id})
            assert 'Item' in response

    @pytest.mark.asyncio
    async def test_batch_put_events_unprocessed_items(self, db_client):
        """Test batch_put_events with unprocessed items (simulated throttling)."""
        # Create test events
        events = []
        for i in range(2):
            event = Event(
                event_id=f"evt_test{i:03d}",
                event_type="order.created",
                payload={"order_id": f"{i}"},
                status="pending",
                created_at=datetime(2024, 1, 15, 10, 30, 1, tzinfo=timezone.utc)
            )
            events.append(event)

        # Mock batch_write_item to return unprocessed items
        mock_response = {
            'UnprocessedItems': {
                db_client.table_name: [
                    {
                        'PutRequest': {
                            'Item': {
                                'event_id': 'evt_test001',
                                'event_type': 'order.created'
                            }
                        }
                    }
                ]
            }
        }

        with patch.object(db_client.dynamodb, 'batch_write_item', return_value=mock_response):
            result = await db_client.batch_put_events(events)

            # One successful, one failed due to unprocessed
            assert len(result["successful_event_ids"]) == 1
            assert len(result["failed_items"]) == 1
            assert result["failed_items"][0]["event_id"] == "evt_test001"
            assert "Unprocessed" in result["failed_items"][0]["reason"]

    @pytest.mark.asyncio
    async def test_batch_put_events_validation_errors(self, db_client):
        """Test batch_put_events with validation errors."""
        # Test with invalid inputs
        with pytest.raises(ValueError, match="events must be a list"):
            await db_client.batch_put_events("not a list")

        with pytest.raises(ValueError, match="all items must be Event instances"):
            await db_client.batch_put_events(["not an event"])

        # Create 101 events (exceeds limit)
        events = []
        for i in range(101):
            event = Event(
                event_id=f"evt_test{i:03d}",
                event_type="order.created",
                payload={"order_id": f"{i}"},
                status="pending",
                created_at=datetime(2024, 1, 15, 10, 30, 1, tzinfo=timezone.utc)
            )
            events.append(event)

        with pytest.raises(ValueError, match="batch size cannot exceed 100 events"):
            await db_client.batch_put_events(events)

    @pytest.mark.asyncio
    async def test_batch_get_events_success(self, db_client, mock_dynamodb_table, sample_event_model):
        """Test batch_get_events with successful retrieval."""
        # First store an event
        await db_client.put_event(sample_event_model)

        # Get the event via batch get
        event_ids = [sample_event_model.event_id]
        events = await db_client.batch_get_events(event_ids)

        # Assert we got the event back
        assert len(events) == 1
        assert events[0].event_id == sample_event_model.event_id

    @pytest.mark.asyncio
    async def test_batch_get_events_some_missing(self, db_client, mock_dynamodb_table, sample_event_model):
        """Test batch_get_events with some events missing."""
        # Store one event
        await db_client.put_event(sample_event_model)

        # Try to get two events (one exists, one doesn't)
        event_ids = [sample_event_model.event_id, "evt_nonexistent"]
        events = await db_client.batch_get_events(event_ids)

        # Should only return the existing event
        assert len(events) == 1
        assert events[0].event_id == sample_event_model.event_id

    @pytest.mark.asyncio
    async def test_batch_get_events_validation_errors(self, db_client):
        """Test batch_get_events with validation errors."""
        with pytest.raises(ValueError, match="event_ids must be a list"):
            await db_client.batch_get_events("not a list")

        with pytest.raises(ValueError, match="all event_ids must be non-empty strings"):
            await db_client.batch_get_events([""])

        # Create 101 event IDs (exceeds limit)
        event_ids = [f"evt_test{i:03d}" for i in range(101)]
        with pytest.raises(ValueError, match="batch size cannot exceed 100 events"):
            await db_client.batch_get_events(event_ids)

    @pytest.mark.asyncio
    async def test_batch_delete_events_success(self, db_client, mock_dynamodb_table, sample_event_model):
        """Test batch_delete_events with successful deletion."""
        # First store an event
        await db_client.put_event(sample_event_model)

        # Verify it exists
        response = mock_dynamodb_table.get_item(Key={'event_id': sample_event_model.event_id})
        assert 'Item' in response

        # Delete via batch delete
        event_ids = [sample_event_model.event_id]
        result = await db_client.batch_delete_events(event_ids)

        # Assert successful deletion
        assert len(result["successful_event_ids"]) == 1
        assert len(result["failed_event_ids"]) == 0
        assert result["successful_event_ids"][0] == sample_event_model.event_id

        # Verify it's gone
        response = mock_dynamodb_table.get_item(Key={'event_id': sample_event_model.event_id})
        assert 'Item' not in response

    @pytest.mark.asyncio
    async def test_batch_delete_events_unprocessed(self, db_client):
        """Test batch_delete_events with unprocessed items."""
        event_ids = ["evt_test001", "evt_test002"]

        # Mock batch_write_item to return unprocessed items
        mock_response = {
            'UnprocessedItems': {
                db_client.table_name: [
                    {
                        'DeleteRequest': {
                            'Key': {'event_id': 'evt_test002'}
                        }
                    }
                ]
            }
        }

        with patch.object(db_client.dynamodb, 'batch_write_item', return_value=mock_response):
            result = await db_client.batch_delete_events(event_ids)

            # One successful, one failed
            assert len(result["successful_event_ids"]) == 1
            assert len(result["failed_event_ids"]) == 1
            assert result["failed_event_ids"][0] == "evt_test002"

    @pytest.mark.asyncio
    async def test_batch_delete_events_validation_errors(self, db_client):
        """Test batch_delete_events with validation errors."""
        with pytest.raises(ValueError, match="event_ids must be a list"):
            await db_client.batch_delete_events("not a list")

        with pytest.raises(ValueError, match="all event_ids must be non-empty strings"):
            await db_client.batch_delete_events([""])

        # Create 101 event IDs (exceeds limit)
        event_ids = [f"evt_test{i:03d}" for i in range(101)]
        with pytest.raises(ValueError, match="batch size cannot exceed 100 events"):
            await db_client.batch_delete_events(event_ids)

    @pytest.mark.asyncio
    async def test_batch_get_events_by_idempotency_keys_success(self, db_client, mock_dynamodb_table):
        """Test batch_get_events_by_idempotency_keys with successful lookup."""
        # Create event with idempotency key
        event = Event(
            event_id="evt_test123456",
            event_type="order.created",
            payload={"order_id": "123"},
            status="delivered",
            created_at=datetime(2024, 1, 15, 10, 30, 1, tzinfo=timezone.utc),
            user_id="user123",
            idempotency_key="order-123-2024-01-15"
        )

        # Store the event
        await db_client.put_event(event)

        # Look up by idempotency key
        result = await db_client.batch_get_events_by_idempotency_keys(
            user_id="user123",
            idempotency_keys=["order-123-2024-01-15", "nonexistent-key"]
        )

        # Should find the one existing event
        assert len(result) == 1
        assert "order-123-2024-01-15" in result
        assert result["order-123-2024-01-15"].event_id == "evt_test123456"

    @pytest.mark.asyncio
    async def test_batch_get_events_by_idempotency_keys_no_user(self, db_client):
        """Test batch_get_events_by_idempotency_keys with no user (auth disabled)."""
        result = await db_client.batch_get_events_by_idempotency_keys(
            user_id=None,
            idempotency_keys=["any-key"]
        )

        # Should return empty dict when auth is disabled
        assert result == {}

    @pytest.mark.asyncio
    async def test_batch_get_events_by_idempotency_keys_validation_errors(self, db_client):
        """Test batch_get_events_by_idempotency_keys with validation errors."""
        with pytest.raises(ValueError, match="idempotency_keys must be a list"):
            await db_client.batch_get_events_by_idempotency_keys("user123", "not a list")

        with pytest.raises(ValueError, match="all idempotency_keys must be non-empty strings"):
            await db_client.batch_get_events_by_idempotency_keys("user123", [""])

        # Create 101 keys (exceeds limit)
        keys = [f"key{i}" for i in range(101)]
        with pytest.raises(ValueError, match="batch size cannot exceed 100 keys"):
            await db_client.batch_get_events_by_idempotency_keys("user123", keys)