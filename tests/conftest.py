"""
Module: conftest.py
Description: Shared pytest fixtures for Triggers API tests.

Provides reusable test fixtures for database clients, mock data,
and common test setup/teardown operations. Uses moto for AWS
service mocking to enable fast, isolated unit tests.
"""

import pytest
from moto import mock_dynamodb
import boto3
from datetime import datetime, timezone

from src.config.settings import Settings
from src.models.event import Event
from src.models.request import CreateEventRequest
from src.storage.dynamodb import DynamoDBClient


@pytest.fixture
def test_settings():
    """
    Provide test configuration settings.

    Overrides production settings with test-appropriate values.
    Disables environment variable loading for predictable tests.
    """
    return Settings(
        app_name="Triggers API Test",
        app_version="0.1.0-test",
        log_level="DEBUG",
        aws_region="us-east-1",
        stage="test",
        events_table_name="test-events-table",
        api_keys_table_name="test-api-keys-table",
        bcrypt_work_factor=4,  # Faster for tests
    )


@pytest.fixture
def sample_event():
    """
    Provide sample event data for testing.

    Returns a typical event payload that can be used across tests.
    """
    return {
        "event_type": "order.created",
        "payload": {
            "order_id": "12345",
            "customer_id": "67890",
            "amount": 99.99,
            "currency": "USD"
        },
        "metadata": {
            "source": "ecommerce-platform",
            "user_agent": "test-client/1.0"
        }
    }


@pytest.fixture
def sample_create_event_request(sample_event):
    """
    Provide sample CreateEventRequest for testing.

    Creates a properly typed request object from sample event data.
    """
    return CreateEventRequest(**sample_event)


@pytest.fixture
def sample_event_model(sample_event):
    """
    Provide sample Event model instance for testing.

    Creates a fully populated Event model with test data.
    """
    return Event(
        event_id="evt_test123abc",
        event_type=sample_event["event_type"],
        payload=sample_event["payload"],
        metadata=sample_event["metadata"],
        status="pending",
        created_at=datetime.now(timezone.utc),
        delivered_at=None,
        delivery_attempts=0
    )


@pytest.fixture
@mock_dynamodb
def mock_dynamodb_table(test_settings):
    """
    Create mock DynamoDB table for events testing.

    Uses moto to mock AWS DynamoDB and creates a test table
    with the same schema as production.
    """
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

    # Create events table
    table = dynamodb.create_table(
        TableName=test_settings.events_table_name,
        KeySchema=[
            {
                'AttributeName': 'event_id',
                'KeyType': 'HASH'
            }
        ],
        AttributeDefinitions=[
            {
                'AttributeName': 'event_id',
                'AttributeType': 'S'
            },
            {
                'AttributeName': 'status',
                'AttributeType': 'S'
            },
            {
                'AttributeName': 'created_at',
                'AttributeType': 'S'
            }
        ],
        GlobalSecondaryIndexes=[
            {
                'IndexName': 'StatusIndex',
                'KeySchema': [
                    {
                        'AttributeName': 'status',
                        'KeyType': 'HASH'
                    },
                    {
                        'AttributeName': 'created_at',
                        'KeyType': 'RANGE'
                    }
                ],
                'Projection': {
                    'ProjectionType': 'ALL'
                }
            }
        ],
        BillingMode='PAY_PER_REQUEST'
    )

    yield table

    # Cleanup is handled automatically by moto


@pytest.fixture
@mock_dynamodb
def mock_api_keys_table(test_settings):
    """
    Create mock DynamoDB table for API keys testing.

    Uses moto to mock AWS DynamoDB and creates a test table
    for storing API key hashes.
    """
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

    # Create API keys table
    table = dynamodb.create_table(
        TableName=test_settings.api_keys_table_name,
        KeySchema=[
            {
                'AttributeName': 'key_id',
                'KeyType': 'HASH'
            }
        ],
        AttributeDefinitions=[
            {
                'AttributeName': 'key_id',
                'AttributeType': 'S'
            }
        ],
        BillingMode='PAY_PER_REQUEST'
    )

    yield table

    # Cleanup is handled automatically by moto


@pytest.fixture
def db_client(test_settings, mock_dynamodb_table):
    """
    Provide DynamoDBClient instance for testing.

    Creates a client configured for the test environment
    with mocked DynamoDB table.
    """
    return DynamoDBClient(table_name=test_settings.events_table_name)
