"""
Module: test_phase3_delivery.py
Description: Integration tests for Phase 3 delivery features.

Tests end-to-end event delivery flow including push delivery,
SQS queuing, retry logic, and DLQ handling with mocked AWS services.
"""

import pytest
import json
import boto3
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock
import httpx

from moto import mock_dynamodb, mock_sqs, mock_cloudwatch
from models.event import Event
from storage.dynamodb import DynamoDBClient
from delivery.worker import SyncPushDeliveryClient
from delivery.worker import handler as sqs_handler


@pytest.fixture
def mock_zapier_webhook():
    """Mock Zapier webhook responses."""
    return {
        "success": {"status_code": 200, "response": {"received": True}},
        "failure": {"status_code": 500, "response": {"error": "Internal Server Error"}},
        "timeout": None,  # Simulate timeout
    }


@pytest.fixture
def sample_event_data():
    """Sample event data for testing."""
    return {
        "event_type": "order.created",
        "payload": {"order_id": "12345", "amount": 99.99},
        "metadata": {"source": "ecommerce-platform"}
    }


@pytest.fixture
def sqs_message(sample_event_data):
    """Sample SQS message structure."""
    event = Event(
        event_id="evt_test123",
        event_type=sample_event_data["event_type"],
        payload=sample_event_data["payload"],
        metadata=sample_event_data["metadata"],
        status="pending",
        created_at=datetime.now(timezone.utc),
        delivered_at=None,
        delivery_attempts=0
    )

    return {
        "messageId": "msg_test123",
        "body": json.dumps(event.model_dump()),
        "receiptHandle": "receipt_test123"
    }


@mock_dynamodb
@mock_sqs
@mock_cloudwatch
class TestPhase3Delivery:
    """Integration tests for Phase 3 delivery features."""

    @pytest.fixture(autouse=True)
    def setup_mocks(self, mock_dynamodb_table, mock_sqs_queue, mock_api_keys_table):
        """Set up mocked AWS services."""
        self.db_client = DynamoDBClient("test-events")
        self.sqs = boto3.client("sqs", region_name="us-east-1")
        self.cloudwatch = boto3.client("cloudwatch", region_name="us-east-1")

    def test_immediate_push_delivery_success(self, sample_event_data, httpx_mock):
        """Test event created and immediately delivered successfully."""
        # Mock successful webhook response
        httpx_mock.add_response(
            method="POST",
            url="https://hooks.zapier.com/hooks/catch/mock/",
            status_code=200,
            json={"received": True}
        )

        # Create event
        from src.handlers.events import create_event
        from src.models.request import CreateEventRequest

        request = CreateEventRequest(**sample_event_data)

        # Mock dependencies
        with patch('src.handlers.events.get_db_client') as mock_get_db, \
             patch('src.handlers.events.get_sqs_client') as mock_get_sqs, \
             patch('src.handlers.events.get_delivery_client') as mock_get_delivery, \
             patch('src.handlers.events.get_metrics_client') as mock_get_metrics:

            # Setup mocks
            mock_db = AsyncMock()
            mock_sqs = AsyncMock()
            mock_delivery = AsyncMock()
            mock_metrics = AsyncMock()

            mock_get_db.return_value = mock_db
            mock_get_sqs.return_value = mock_sqs
            mock_get_delivery.return_value = mock_delivery
            mock_get_metrics.return_value = mock_metrics

            mock_delivery.deliver_event.return_value = True

            # Execute
            result = await create_event(request, mock_db, mock_sqs, mock_delivery, mock_metrics)

            # Verify
            assert result.status == "delivered"
            assert result.delivery_attempts == 1
            assert result.delivered_at is not None
            mock_db.put_event.assert_called_once()
            mock_delivery.deliver_event.assert_called_once()
            mock_db.update_event.assert_called_once()
            mock_sqs.send_message.assert_not_called()  # Should not queue on success

    def test_push_failure_queues_to_sqs(self, sample_event_data, httpx_mock):
        """Test push failure queues event to SQS."""
        # Mock failed webhook response
        httpx_mock.add_response(
            method="POST",
            url="https://hooks.zapier.com/hooks/catch/mock/",
            status_code=500,
            json={"error": "Internal Server Error"}
        )

        # Create event
        from src.handlers.events import create_event
        from src.models.request import CreateEventRequest

        request = CreateEventRequest(**sample_event_data)

        # Mock dependencies
        with patch('src.handlers.events.get_db_client') as mock_get_db, \
             patch('src.handlers.events.get_sqs_client') as mock_get_sqs, \
             patch('src.handlers.events.get_delivery_client') as mock_get_delivery, \
             patch('src.handlers.events.get_metrics_client') as mock_get_metrics:

            # Setup mocks
            mock_db = AsyncMock()
            mock_sqs = AsyncMock()
            mock_delivery = AsyncMock()
            mock_metrics = AsyncMock()

            mock_get_db.return_value = mock_db
            mock_get_sqs.return_value = mock_sqs
            mock_get_delivery.return_value = mock_delivery
            mock_get_metrics.return_value = mock_metrics

            mock_delivery.deliver_event.return_value = False

            # Execute
            result = await create_event(request, mock_db, mock_sqs, mock_delivery, mock_metrics)

            # Verify
            assert result.status == "pending"
            assert result.delivery_attempts == 0  # Not incremented on initial failure
            assert result.delivered_at is None
            mock_db.put_event.assert_called_once()
            mock_delivery.deliver_event.assert_called_once()
            mock_sqs.send_message.assert_called_once()  # Should queue on failure

    def test_sqs_worker_processes_and_delivers(self, sqs_message, httpx_mock):
        """Test SQS worker processes message and delivers successfully."""
        # Mock successful webhook response
        httpx_mock.add_response(
            method="POST",
            url="https://hooks.zapier.com/hooks/catch/mock/",
            status_code=200,
            json={"received": True}
        )

        # Mock SQS event
        sqs_event = {
            "Records": [sqs_message]
        }

        # Mock settings
        with patch('src.delivery.worker.settings') as mock_settings:
            mock_settings.events_table_name = "test-events"
            mock_settings.zapier_webhook_url = "https://hooks.zapier.com/hooks/catch/mock/"

            # Mock DynamoDB operations
            with patch.object(self.db_client, 'update_event') as mock_update:
                # Execute handler
                result = sqs_handler(sqs_event, {})

                # Verify
                assert result == {"batchItemFailures": []}
                assert mock_update.call_count == 1

                # Verify event was updated with delivered status
                updated_event = mock_update.call_args[0][0]
                assert updated_event.status == "delivered"
                assert updated_event.delivery_attempts == 1
                assert updated_event.delivered_at is not None

    def test_delivery_retry_with_backoff(self):
        """Test retry logic with exponential backoff."""
        from src.delivery.retry import retry_delivery

        delivery_fn = AsyncMock()
        delivery_fn.return_value = False  # Always fail

        event = Event(
            event_id="evt_test123",
            event_type="test.event",
            payload={},
            metadata={},
            status="pending",
            created_at=datetime.now(timezone.utc)
        )

        # Execute retry
        result = await retry_delivery(delivery_fn, event)

        # Verify
        assert result is False
        # Should be called 5 times (max retries)
        assert delivery_fn.call_count == 5

    def test_max_retries_moves_to_dlq(self, sqs_message, httpx_mock):
        """Test that after max retries, message moves to DLQ."""
        # Mock failed webhook responses
        httpx_mock.add_response(
            method="POST",
            url="https://hooks.zapier.com/hooks/catch/mock/",
            status_code=500,
            json={"error": "Internal Server Error"}
        )

        # Set up event with max retry attempts
        event_data = json.loads(sqs_message["body"])
        event_data["delivery_attempts"] = 5  # Max attempts reached
        sqs_message["body"] = json.dumps(event_data)

        # Mock SQS event
        sqs_event = {
            "Records": [sqs_message]
        }

        # Mock settings
        with patch('src.delivery.worker.settings') as mock_settings:
            mock_settings.events_table_name = "test-events"
            mock_settings.zapier_webhook_url = "https://hooks.zapier.com/hooks/catch/mock/"

            # Mock DynamoDB operations
            with patch.object(self.db_client, 'update_event') as mock_update:
                # Execute handler
                result = sqs_handler(sqs_event, {})

                # Verify message is marked as failed to retry (goes to DLQ)
                assert result == {"batchItemFailures": [sqs_message["messageId"]]}

                # Verify event attempts were incremented
                assert mock_update.call_count == 1
                updated_event = mock_update.call_args[0][0]
                assert updated_event.delivery_attempts == 6

    def test_acknowledgment_updates_status(self):
        """Test acknowledgment endpoint updates event status."""
        from src.handlers.events import acknowledge_event

        event_id = "evt_test123"

        # Mock dependencies
        with patch('src.handlers.events.get_db_client') as mock_get_db, \
             patch('src.handlers.events.get_metrics_client') as mock_get_metrics:

            mock_db = AsyncMock()
            mock_metrics = AsyncMock()

            mock_get_db.return_value = mock_db
            mock_get_metrics.return_value = mock_metrics

            # Mock event retrieval
            event = Event(
                event_id=event_id,
                event_type="test.event",
                payload={},
                metadata={},
                status="pending",
                created_at=datetime.now(timezone.utc)
            )
            mock_db.get_event.return_value = event

            # Execute
            result = await acknowledge_event(event_id, mock_db, mock_metrics)

            # Verify
            assert result is None  # 204 No Content
            mock_db.get_event.assert_called_once_with(event_id)

            # Verify event was updated
            mock_db.update_event.assert_called_once()
            updated_event = mock_db.update_event.call_args[0][0]
            assert updated_event.status == "delivered"
            assert updated_event.delivered_at is not None

    @mock_cloudwatch
    def test_metrics_published(self, httpx_mock):
        """Test CloudWatch metrics are published."""
        # Mock successful webhook response
        httpx_mock.add_response(
            method="POST",
            url="https://hooks.zapier.com/hooks/catch/mock/",
            status_code=200,
            json={"received": True}
        )

        # Create event
        from src.handlers.events import create_event
        from src.models.request import CreateEventRequest

        request = CreateEventRequest(
            event_type="order.created",
            payload={"order_id": "123"}
        )

        # Mock dependencies
        with patch('src.handlers.events.get_db_client') as mock_get_db, \
             patch('src.handlers.events.get_sqs_client') as mock_get_sqs, \
             patch('src.handlers.events.get_delivery_client') as mock_get_delivery, \
             patch('src.handlers.events.get_metrics_client') as mock_get_metrics:

            # Setup mocks
            mock_db = AsyncMock()
            mock_sqs = AsyncMock()
            mock_delivery = AsyncMock()
            mock_metrics = AsyncMock()

            mock_get_db.return_value = mock_db
            mock_get_sqs.return_value = mock_sqs
            mock_get_delivery.return_value = mock_delivery
            mock_get_metrics.return_value = mock_metrics

            mock_delivery.deliver_event.return_value = True

            # Execute
            result = await create_event(request, mock_db, mock_sqs, mock_delivery, mock_metrics)

            # Verify metrics were published
            assert mock_metrics.put_metric.call_count == 2  # EventCreated and EventDelivered

            # Check EventCreated metric
            event_created_call = mock_metrics.put_metric.call_args_list[0]
            assert event_created_call[1]["metric_name"] == "EventCreated"
            assert event_created_call[1]["dimensions"] == {"EventType": "order.created"}

            # Check EventDelivered metric
            event_delivered_call = mock_metrics.put_metric.call_args_list[1]
            assert event_delivered_call[1]["metric_name"] == "EventDelivered"
            assert event_delivered_call[1]["dimensions"] == {"EventType": "order.created"}
