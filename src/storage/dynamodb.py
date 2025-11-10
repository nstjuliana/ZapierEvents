"""
Module: dynamodb.py
Description: DynamoDB client for event storage and retrieval.

Provides async operations for storing, retrieving, and querying events
in DynamoDB with proper error handling and logging.

Key Components:
- DynamoDBClient: Main client class for DynamoDB operations
- Event storage: put_event() with datetime serialization
- Event retrieval: get_event() with datetime deserialization
- Error handling: Comprehensive exception handling with logging

Dependencies: boto3, botocore, datetime, typing
Author: Triggers API Team
"""

import boto3
from botocore.exceptions import ClientError
from typing import Optional
from datetime import datetime, timezone

from src.models.event import Event
from src.utils.logger import get_logger

logger = get_logger(__name__)


class DynamoDBClient:
    """
    DynamoDB client for event operations.

    This class handles all DynamoDB operations for the Triggers API,
    including event CRUD operations, querying by status, and TTL management.

    Attributes:
        table_name: Name of the DynamoDB events table
        dynamodb: boto3 DynamoDB resource
        table: boto3 DynamoDB table resource

    Example:
        >>> client = DynamoDBClient(table_name="triggers-api-events")
        >>> await client.put_event(event)
        >>> retrieved = await client.get_event("evt_123")
    """

    def __init__(self, table_name: str):
        """
        Initialize DynamoDB client.

        Args:
            table_name: Name of the DynamoDB events table

        Raises:
            ValueError: If table_name is empty or invalid
        """
        if not table_name or not isinstance(table_name, str):
            raise ValueError("table_name must be a non-empty string")

        self.table_name = table_name
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table(table_name)

        logger.info(
            "DynamoDB client initialized",
            table_name=table_name
        )

    async def put_event(self, event: Event) -> None:
        """
        Store an event in DynamoDB.

        Converts the Event model to a DynamoDB item, serializing datetime
        objects to ISO 8601 strings before storage.

        Args:
            event: Event model to store

        Raises:
            ClientError: If DynamoDB operation fails
            ValueError: If event is invalid
        """
        if not isinstance(event, Event):
            raise ValueError("event must be an Event instance")

        try:
            # Convert Event model to DynamoDB item
            item = event.model_dump()

            # Convert datetime objects to ISO strings
            item['created_at'] = item['created_at'].isoformat()
            if item.get('delivered_at') and item['delivered_at'] is not None:
                item['delivered_at'] = item['delivered_at'].isoformat()

            # Store in DynamoDB
            self.table.put_item(Item=item)

            logger.info(
                "Event stored in DynamoDB",
                event_id=event.event_id,
                event_type=event.event_type,
                status=event.status,
                table_name=self.table_name
            )

        except ClientError as e:
            logger.error(
                "Failed to store event in DynamoDB",
                event_id=event.event_id if event else None,
                table_name=self.table_name,
                error_code=e.response['Error']['Code'],
                error_message=e.response['Error']['Message']
            )
            raise

        except Exception as e:
            logger.error(
                "Unexpected error storing event in DynamoDB",
                event_id=event.event_id if event else None,
                table_name=self.table_name,
                error=str(e)
            )
            raise

    async def get_event(self, event_id: str) -> Optional[Event]:
        """
        Retrieve an event by ID.

        Fetches an event from DynamoDB and converts it back to an Event model,
        deserializing ISO datetime strings back to datetime objects.

        Args:
            event_id: Unique event identifier

        Returns:
            Event model if found, None otherwise

        Raises:
            ClientError: If DynamoDB operation fails
            ValueError: If event_id is invalid
        """
        if not event_id or not isinstance(event_id, str):
            raise ValueError("event_id must be a non-empty string")

        try:
            response = self.table.get_item(Key={'event_id': event_id})

            if 'Item' not in response:
                logger.warning(
                    "Event not found in DynamoDB",
                    event_id=event_id,
                    table_name=self.table_name
                )
                return None

            item = response['Item']

            # Convert ISO strings back to datetime objects
            if 'created_at' in item:
                item['created_at'] = datetime.fromisoformat(item['created_at'])
            if 'delivered_at' in item and item['delivered_at'] is not None:
                item['delivered_at'] = datetime.fromisoformat(item['delivered_at'])

            # Convert to Event model
            event = Event(**item)

            logger.info(
                "Event retrieved from DynamoDB",
                event_id=event_id,
                status=event.status,
                table_name=self.table_name
            )

            return event

        except ClientError as e:
            logger.error(
                "Failed to retrieve event from DynamoDB",
                event_id=event_id,
                table_name=self.table_name,
                error_code=e.response['Error']['Code'],
                error_message=e.response['Error']['Message']
            )
            raise

        except Exception as e:
            logger.error(
                "Unexpected error retrieving event from DynamoDB",
                event_id=event_id,
                table_name=self.table_name,
                error=str(e)
            )
            raise
