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
from typing import Optional, List
from datetime import datetime, timezone
import base64
import json

from models.event import Event
from utils.logger import get_logger

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

            # Serialize payload and metadata as JSON strings to preserve types
            # This ensures numbers, booleans, etc. are preserved correctly
            if 'payload' in item:
                item['payload'] = json.dumps(item['payload'])
            if 'metadata' in item and item.get('metadata') is not None:
                item['metadata'] = json.dumps(item['metadata'])

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

            # Deserialize payload and metadata from JSON strings to preserve types
            # Handle both new format (JSON string) and old format (dict) for backward compatibility
            if 'payload' in item:
                if isinstance(item['payload'], str):
                    item['payload'] = json.loads(item['payload'])
            if 'metadata' in item and item.get('metadata') is not None:
                if isinstance(item['metadata'], str):
                    item['metadata'] = json.loads(item['metadata'])

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

    async def list_events(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        cursor: Optional[str] = None
    ) -> List[Event]:
        """
        List events with optional status filter and pagination.

        Uses cursor-based pagination with DynamoDB LastEvaluatedKey.
        When status is provided, queries the StatusIndex GSI for efficient filtering.
        When no status filter, scans the table (less efficient but necessary).

        Args:
            status: Optional status to filter by (pending, delivered, failed, replayed)
            limit: Maximum number of events to return (default 50)
            cursor: Base64-encoded pagination cursor from previous response

        Returns:
            List of Event objects sorted by created_at descending

        Raises:
            ClientError: If DynamoDB operation fails
            ValueError: If parameters are invalid
        """
        if limit <= 0 or limit > 100:
            raise ValueError("limit must be between 1 and 100")

        try:
            kwargs = {'Limit': limit}

            # Decode pagination cursor if provided
            if cursor:
                try:
                    kwargs['ExclusiveStartKey'] = json.loads(base64.b64decode(cursor).decode('utf-8'))
                except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as e:
                    logger.warning("Invalid pagination cursor", cursor=cursor, error=str(e))
                    raise ValueError("Invalid pagination cursor")

            # Query by status using GSI or scan all
            if status:
                response = self.table.query(
                    IndexName='StatusIndex',
                    KeyConditionExpression='#status = :status',
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={':status': status},
                    ScanIndexForward=False,  # Most recent first
                    **kwargs
                )
            else:
                response = self.table.scan(**kwargs)

            # Convert items to Event objects
            events = []
            for item in response.get('Items', []):
                # Deserialize payload and metadata from JSON strings to preserve types
                # Handle both new format (JSON string) and old format (dict) for backward compatibility
                if 'payload' in item:
                    if isinstance(item['payload'], str):
                        item['payload'] = json.loads(item['payload'])
                if 'metadata' in item and item.get('metadata') is not None:
                    if isinstance(item['metadata'], str):
                        item['metadata'] = json.loads(item['metadata'])

                # Convert ISO strings back to datetime objects
                if 'created_at' in item:
                    item['created_at'] = datetime.fromisoformat(item['created_at'])
                if 'delivered_at' in item and item['delivered_at'] is not None:
                    item['delivered_at'] = datetime.fromisoformat(item['delivered_at'])

                events.append(Event(**item))

            # Sort events by created_at descending for scan operations (no guaranteed order)
            if not status:
                events.sort(key=lambda e: e.created_at, reverse=True)

            # Create next cursor if more results available
            next_cursor = None
            if 'LastEvaluatedKey' in response:
                try:
                    next_cursor = base64.b64encode(
                        json.dumps(response['LastEvaluatedKey']).encode('utf-8')
                    ).decode('utf-8')
                except (TypeError, json.JSONDecodeError) as e:
                    logger.warning("Failed to encode pagination cursor", error=str(e))

            logger.info(
                "Events listed",
                count=len(events),
                status_filter=status,
                limit=limit,
                has_more=bool(next_cursor),
                table_name=self.table_name
            )

            return events

        except ClientError as e:
            logger.error(
                "Failed to list events from DynamoDB",
                status_filter=status,
                table_name=self.table_name,
                error_code=e.response['Error']['Code'],
                error_message=e.response['Error']['Message']
            )
            raise

        except Exception as e:
            logger.error(
                "Unexpected error listing events from DynamoDB",
                status_filter=status,
                table_name=self.table_name,
                error=str(e)
            )
            raise

    async def update_event(self, event: Event) -> None:
        """
        Update an existing event in DynamoDB.

        Converts the Event model to a DynamoDB item, serializing datetime
        objects to ISO 8601 strings before storage. Uses put_item for updates
        since we want to replace the entire item.

        Args:
            event: Event model to update

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

            # Serialize payload and metadata as JSON strings to preserve types
            # This ensures numbers, booleans, etc. are preserved correctly
            if 'payload' in item:
                item['payload'] = json.dumps(item['payload'])
            if 'metadata' in item and item.get('metadata') is not None:
                item['metadata'] = json.dumps(item['metadata'])

            # Update in DynamoDB (put_item will replace the entire item)
            self.table.put_item(Item=item)

            logger.info(
                "Event updated in DynamoDB",
                event_id=event.event_id,
                event_type=event.event_type,
                status=event.status,
                delivery_attempts=event.delivery_attempts,
                table_name=self.table_name
            )

        except ClientError as e:
            logger.error(
                "Failed to update event in DynamoDB",
                event_id=event.event_id if event else None,
                table_name=self.table_name,
                error_code=e.response['Error']['Code'],
                error_message=e.response['Error']['Message']
            )
            raise

        except Exception as e:
            logger.error(
                "Unexpected error updating event in DynamoDB",
                event_id=event.event_id if event else None,
                table_name=self.table_name,
                error=str(e)
            )
            raise
