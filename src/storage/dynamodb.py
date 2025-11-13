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
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import base64
import json

from models.event import Event
from utils.logger import get_logger
from utils.filters import EventFilter, build_dynamodb_filter, apply_filters_to_events

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

            # Remove None values - DynamoDB doesn't allow None/null values
            # Only include attributes that have actual values
            item = {k: v for k, v in item.items() if v is not None}

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

    async def get_event_by_idempotency_key(
        self,
        user_id: Optional[str],
        idempotency_key: str
    ) -> Optional[Event]:
        """
        Retrieve an event by user-scoped idempotency key.

        Queries the IdempotencyIndex GSI to find events by (user_id, idempotency_key)
        combination. This enables user-scoped deduplication of events.

        Args:
            user_id: User identifier (required for proper user scoping)
            idempotency_key: Client-provided idempotency key

        Returns:
            Event model if found, None otherwise

        Raises:
            ClientError: If DynamoDB operation fails
            ValueError: If parameters are invalid

        Note:
            When auth is disabled, user_id will be None. In this case, the method
            currently returns None (no global deduplication). When auth is enabled,
            user_id will be required and populated from the authorizer context.
        """
        if not idempotency_key or not isinstance(idempotency_key, str):
            raise ValueError("idempotency_key must be a non-empty string")

        # When auth is disabled, user_id is None. For now, we don't support
        # global deduplication - only user-scoped deduplication when user_id is provided.
        # TODO: When auth is enabled, make user_id required and remove this check.
        if user_id is None:
            logger.warning(
                "Cannot check idempotency without user_id - auth is currently disabled",
                idempotency_key=idempotency_key,
                table_name=self.table_name
            )
            return None

        try:
            # Query the IdempotencyIndex GSI
            response = self.table.query(
                IndexName='IdempotencyIndex',
                KeyConditionExpression='#user_id = :user_id AND #idempotency_key = :idempotency_key',
                ExpressionAttributeNames={
                    '#user_id': 'user_id',
                    '#idempotency_key': 'idempotency_key'
                },
                ExpressionAttributeValues={
                    ':user_id': user_id,
                    ':idempotency_key': idempotency_key
                },
                Limit=1  # We only expect one result per (user_id, idempotency_key) pair
            )

            items = response.get('Items', [])
            if not items:
                logger.info(
                    "No existing event found for idempotency key",
                    user_id=user_id,
                    idempotency_key=idempotency_key,
                    table_name=self.table_name
                )
                return None

            item = items[0]

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
                "Existing event found for idempotency key",
                user_id=user_id,
                idempotency_key=idempotency_key,
                event_id=event.event_id,
                table_name=self.table_name
            )

            return event

        except ClientError as e:
            logger.error(
                "Failed to query event by idempotency key",
                user_id=user_id,
                idempotency_key=idempotency_key,
                table_name=self.table_name,
                error_code=e.response['Error']['Code'],
                error_message=e.response['Error']['Message']
            )
            raise

        except Exception as e:
            logger.error(
                "Unexpected error querying event by idempotency key",
                user_id=user_id,
                idempotency_key=idempotency_key,
                table_name=self.table_name,
                error=str(e)
            )
            raise

    async def list_events(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        cursor: Optional[str] = None,
        filters: Optional[Dict[str, EventFilter]] = None
    ) -> List[Event]:
        """
        List events with optional status filter, custom filters, and pagination.

        Uses cursor-based pagination with DynamoDB LastEvaluatedKey.
        When status is provided, queries the StatusIndex GSI for efficient filtering.
        When custom filters are provided, applies them after retrieving data.
        When no filters, scans the table (less efficient but necessary).

        Args:
            status: Optional status to filter by (pending, delivered, failed, replayed)
            limit: Maximum number of events to return (default 50)
            cursor: Base64-encoded pagination cursor from previous response
            filters: Optional dictionary of EventFilter objects for custom filtering

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

            # Check if we have any JSON-based filters that require in-memory filtering
            has_json_filters = any(f.field_type == 'json' for f in (filters or {}).values())

            # If we have JSON filters, we need to potentially fetch more data since filtering happens after retrieval
            if has_json_filters:
                # Increase limit to account for filtered-out events, but cap at a reasonable maximum
                fetch_limit = min(limit * 3, 300)  # Fetch up to 3x requested limit, max 300
                kwargs['Limit'] = fetch_limit

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

            # Apply custom filters if provided
            if filters:
                events = apply_filters_to_events(events, filters)

                # Limit to requested number after filtering
                events = events[:limit]

            # Create next cursor if more results available
            # Note: This is simplified - proper cursor handling with filters would be more complex
            # For now, we don't support cursors with custom filters
            next_cursor = None
            if not filters and 'LastEvaluatedKey' in response:
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
                custom_filters=bool(filters),
                limit=limit,
                has_more=bool(next_cursor),
                table_name=self.table_name
            )

            return events

        except ClientError as e:
            logger.error(
                "Failed to list events from DynamoDB",
                status_filter=status,
                custom_filters=bool(filters),
                table_name=self.table_name,
                error_code=e.response['Error']['Code'],
                error_message=e.response['Error']['Message']
            )
            raise

        except Exception as e:
            logger.error(
                "Unexpected error listing events from DynamoDB",
                status_filter=status,
                custom_filters=bool(filters),
                table_name=self.table_name,
                error=str(e)
            )
            raise

    async def delete_event(self, event_id: str) -> None:
        """
        Delete an event from DynamoDB.

        Removes an event from the DynamoDB table by its event_id.

        Args:
            event_id: Unique event identifier to delete

        Raises:
            ClientError: If DynamoDB operation fails
            ValueError: If event_id is invalid
        """
        if not event_id or not isinstance(event_id, str):
            raise ValueError("event_id must be a non-empty string")

        try:
            self.table.delete_item(Key={'event_id': event_id})

            logger.info(
                "Event deleted from DynamoDB",
                event_id=event_id,
                table_name=self.table_name
            )

        except ClientError as e:
            logger.error(
                "Failed to delete event from DynamoDB",
                event_id=event_id,
                table_name=self.table_name,
                error_code=e.response['Error']['Code'],
                error_message=e.response['Error']['Message']
            )
            raise

        except Exception as e:
            logger.error(
                "Unexpected error deleting event from DynamoDB",
                event_id=event_id,
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

            # Remove None values - DynamoDB doesn't allow None/null values
            # Only include attributes that have actual values
            item = {k: v for k, v in item.items() if v is not None}

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

    async def batch_put_events(self, events: List[Event]) -> Dict[str, Any]:
        """
        Store multiple events in DynamoDB with internal chunking.

        Processes events in chunks of 25 (DynamoDB batch_write_item limit).
        Uses batch_write_item for efficiency and handles UnprocessedItems.
        Continues processing remaining chunks even if some fail.

        Args:
            events: List of Event models to store

        Returns:
            Dict with 'successful_event_ids' list and 'failed_items' list (with reasons)

        Raises:
            ValueError: If events list is invalid
        """
        if not isinstance(events, list):
            raise ValueError("events must be a list")
        if not events:
            return {"successful_event_ids": [], "failed_items": []}
        if len(events) > 100:
            raise ValueError("batch size cannot exceed 100 events")

        # Validate all events
        for event in events:
            if not isinstance(event, Event):
                raise ValueError("all items must be Event instances")

        from utils.batch_helpers import chunk_list
        successful_event_ids = []
        failed_items = []

        # Process events in chunks of 25 (DynamoDB batch limit)
        chunks = chunk_list(events, 25)

        for chunk_idx, chunk in enumerate(chunks):
            try:
                # Prepare batch write request
                request_items = {}
                event_map = {}  # Map event_id to event for error handling

                for event in chunk:
                    item = event.model_dump()
                    item['created_at'] = item['created_at'].isoformat()
                    if item.get('delivered_at') and item['delivered_at'] is not None:
                        item['delivered_at'] = item['delivered_at'].isoformat()

                    # Serialize payload and metadata
                    if 'payload' in item:
                        item['payload'] = json.dumps(item['payload'])
                    if 'metadata' in item and item.get('metadata') is not None:
                        item['metadata'] = json.dumps(item['metadata'])

                    # Remove None values
                    item = {k: v for k, v in item.items() if v is not None}

                    request_items[f"{self.table_name}"] = request_items.get(f"{self.table_name}", [])
                    request_items[f"{self.table_name}"].append({"PutRequest": {"Item": item}})
                    event_map[event.event_id] = event

                # Execute batch write
                response = self.dynamodb.batch_write_item(RequestItems=request_items)

                # Handle unprocessed items (retry logic could be added here)
                unprocessed = response.get('UnprocessedItems', {}).get(self.table_name, [])
                if unprocessed:
                    logger.warning(
                        f"Some items not processed in chunk {chunk_idx}",
                        unprocessed_count=len(unprocessed),
                        total_in_chunk=len(chunk),
                        table_name=self.table_name
                    )
                    # For now, mark unprocessed items as failed
                    for unprocessed_item in unprocessed:
                        item = unprocessed_item.get('PutRequest', {}).get('Item', {})
                        if 'event_id' in item:
                            failed_items.append({
                                "event_id": item['event_id'],
                                "reason": "Unprocessed by DynamoDB"
                            })

                # Mark successful items
                processed_event_ids = [event.event_id for event in chunk]
                for unprocessed_item in unprocessed:
                    item = unprocessed_item.get('PutRequest', {}).get('Item', {})
                    if 'event_id' in item and item['event_id'] in processed_event_ids:
                        processed_event_ids.remove(item['event_id'])

                successful_event_ids.extend(processed_event_ids)

                logger.info(
                    f"Processed batch chunk {chunk_idx}",
                    chunk_size=len(chunk),
                    successful=len(processed_event_ids),
                    failed=len(unprocessed),
                    table_name=self.table_name
                )

            except ClientError as e:
                logger.error(
                    f"Failed to batch write chunk {chunk_idx}",
                    chunk_size=len(chunk),
                    table_name=self.table_name,
                    error_code=e.response['Error']['Code'],
                    error_message=e.response['Error']['Message']
                )
                # Mark entire chunk as failed
                for event in chunk:
                    failed_items.append({
                        "event_id": event.event_id,
                        "reason": f"DynamoDB error: {e.response['Error']['Message']}"
                    })

            except Exception as e:
                logger.error(
                    f"Unexpected error in batch write chunk {chunk_idx}",
                    chunk_size=len(chunk),
                    table_name=self.table_name,
                    error=str(e)
                )
                # Mark entire chunk as failed
                for event in chunk:
                    failed_items.append({
                        "event_id": event.event_id,
                        "reason": f"Unexpected error: {str(e)}"
                    })

        logger.info(
            "Batch put events completed",
            total_events=len(events),
            successful=len(successful_event_ids),
            failed=len(failed_items),
            table_name=self.table_name
        )

        return {
            "successful_event_ids": successful_event_ids,
            "failed_items": failed_items
        }

    async def batch_get_events(self, event_ids: List[str]) -> List[Event]:
        """
        Retrieve multiple events by ID with internal chunking.

        Processes event_ids in chunks of 25 (DynamoDB batch_get_item limit).
        Uses batch_get_item for efficiency and handles UnprocessedKeys.
        Returns found events in arbitrary order (DynamoDB doesn't guarantee order).

        Args:
            event_ids: List of event IDs to retrieve

        Returns:
            List of found Event models (missing events not included)

        Raises:
            ValueError: If event_ids list is invalid
        """
        if not isinstance(event_ids, list):
            raise ValueError("event_ids must be a list")
        if not event_ids:
            return []
        if len(event_ids) > 100:
            raise ValueError("batch size cannot exceed 100 events")

        # Validate event IDs
        for event_id in event_ids:
            if not isinstance(event_id, str) or not event_id.strip():
                raise ValueError("all event_ids must be non-empty strings")

        from utils.batch_helpers import chunk_list
        all_events = []

        # Process event_ids in chunks of 25 (DynamoDB batch limit)
        chunks = chunk_list(event_ids, 25)

        for chunk_idx, chunk in enumerate(chunks):
            try:
                # Prepare batch get request
                keys = [{"event_id": event_id} for event_id in chunk]

                response = self.dynamodb.batch_get_item(
                    RequestItems={
                        self.table_name: {
                            "Keys": keys
                        }
                    }
                )

                # Process found items
                items = response.get('Responses', {}).get(self.table_name, [])
                for item in items:
                    # Deserialize payload and metadata
                    if 'payload' in item:
                        if isinstance(item['payload'], str):
                            item['payload'] = json.loads(item['payload'])
                    if 'metadata' in item and item.get('metadata') is not None:
                        if isinstance(item['metadata'], str):
                            item['metadata'] = json.loads(item['metadata'])

                    # Convert datetime strings
                    if 'created_at' in item:
                        item['created_at'] = datetime.fromisoformat(item['created_at'])
                    if 'delivered_at' in item and item['delivered_at'] is not None:
                        item['delivered_at'] = datetime.fromisoformat(item['delivered_at'])

                    # Convert to Event model
                    event = Event(**item)
                    all_events.append(event)

                # Handle unprocessed keys (retry logic could be added here)
                unprocessed = response.get('UnprocessedKeys', {})
                if unprocessed:
                    logger.warning(
                        f"Some keys not processed in chunk {chunk_idx}",
                        unprocessed_count=len(unprocessed.get('Keys', [])),
                        total_in_chunk=len(chunk),
                        table_name=self.table_name
                    )
                    # For now, we don't retry unprocessed keys

                logger.info(
                    f"Processed batch get chunk {chunk_idx}",
                    chunk_size=len(chunk),
                    found=len(items),
                    unprocessed=len(unprocessed.get('Keys', [])),
                    table_name=self.table_name
                )

            except ClientError as e:
                logger.error(
                    f"Failed to batch get chunk {chunk_idx}",
                    chunk_size=len(chunk),
                    table_name=self.table_name,
                    error_code=e.response['Error']['Code'],
                    error_message=e.response['Error']['Message']
                )
                # Skip failed chunks (items in this chunk won't be returned)

            except Exception as e:
                logger.error(
                    f"Unexpected error in batch get chunk {chunk_idx}",
                    chunk_size=len(chunk),
                    table_name=self.table_name,
                    error=str(e)
                )
                # Skip failed chunks

        logger.info(
            "Batch get events completed",
            requested=len(event_ids),
            found=len(all_events),
            table_name=self.table_name
        )

        return all_events

    async def batch_delete_events(self, event_ids: List[str]) -> Dict[str, Any]:
        """
        Delete multiple events by ID with internal chunking.

        Processes event_ids in chunks of 25 (DynamoDB batch_write_item limit).
        Uses batch_write_item with DeleteRequest for efficiency.
        Continues processing even if some deletions fail.

        Args:
            event_ids: List of event IDs to delete

        Returns:
            Dict with 'successful_event_ids' list and 'failed_event_ids' list

        Raises:
            ValueError: If event_ids list is invalid
        """
        if not isinstance(event_ids, list):
            raise ValueError("event_ids must be a list")
        if not event_ids:
            return {"successful_event_ids": [], "failed_event_ids": []}
        if len(event_ids) > 100:
            raise ValueError("batch size cannot exceed 100 events")

        # Validate event IDs
        for event_id in event_ids:
            if not isinstance(event_id, str) or not event_id.strip():
                raise ValueError("all event_ids must be non-empty strings")

        from utils.batch_helpers import chunk_list
        successful_event_ids = []
        failed_event_ids = []

        # Process event_ids in chunks of 25 (DynamoDB batch limit)
        chunks = chunk_list(event_ids, 25)

        for chunk_idx, chunk in enumerate(chunks):
            try:
                # Prepare batch delete request
                request_items = {}
                for event_id in chunk:
                    request_items[f"{self.table_name}"] = request_items.get(f"{self.table_name}", [])
                    request_items[f"{self.table_name}"].append({
                        "DeleteRequest": {"Key": {"event_id": event_id}}
                    })

                # Execute batch delete
                response = self.dynamodb.batch_write_item(RequestItems=request_items)

                # Handle unprocessed items
                unprocessed = response.get('UnprocessedItems', {}).get(self.table_name, [])
                if unprocessed:
                    logger.warning(
                        f"Some items not deleted in chunk {chunk_idx}",
                        unprocessed_count=len(unprocessed),
                        total_in_chunk=len(chunk),
                        table_name=self.table_name
                    )
                    # Mark unprocessed items as failed
                    for unprocessed_item in unprocessed:
                        key = unprocessed_item.get('DeleteRequest', {}).get('Key', {})
                        if 'event_id' in key:
                            failed_event_ids.append(key['event_id'])

                # Mark successful deletions
                processed_event_ids = list(chunk)  # Copy chunk
                for unprocessed_item in unprocessed:
                    key = unprocessed_item.get('DeleteRequest', {}).get('Key', {})
                    if 'event_id' in key and key['event_id'] in processed_event_ids:
                        processed_event_ids.remove(key['event_id'])

                successful_event_ids.extend(processed_event_ids)

                logger.info(
                    f"Processed batch delete chunk {chunk_idx}",
                    chunk_size=len(chunk),
                    successful=len(processed_event_ids),
                    failed=len(unprocessed),
                    table_name=self.table_name
                )

            except ClientError as e:
                logger.error(
                    f"Failed to batch delete chunk {chunk_idx}",
                    chunk_size=len(chunk),
                    table_name=self.table_name,
                    error_code=e.response['Error']['Code'],
                    error_message=e.response['Error']['Message']
                )
                # Mark entire chunk as failed
                failed_event_ids.extend(chunk)

            except Exception as e:
                logger.error(
                    f"Unexpected error in batch delete chunk {chunk_idx}",
                    chunk_size=len(chunk),
                    table_name=self.table_name,
                    error=str(e)
                )
                # Mark entire chunk as failed
                failed_event_ids.extend(chunk)

        logger.info(
            "Batch delete events completed",
            total_events=len(event_ids),
            successful=len(successful_event_ids),
            failed=len(failed_event_ids),
            table_name=self.table_name
        )

        return {
            "successful_event_ids": successful_event_ids,
            "failed_event_ids": failed_event_ids
        }

    async def batch_get_events_by_idempotency_keys(
        self,
        user_id: Optional[str],
        idempotency_keys: List[str]
    ) -> Dict[str, Event]:
        """
        Retrieve multiple events by user-scoped idempotency keys.

        Since DynamoDB doesn't support batch queries on GSIs, this method
        makes individual queries for each key. Uses concurrent execution
        for better performance when multiple keys are requested.

        Args:
            user_id: User identifier (required for user-scoped deduplication)
            idempotency_keys: List of idempotency keys to look up

        Returns:
            Dict mapping idempotency_key -> Event (only found events included)

        Raises:
            ValueError: If parameters are invalid
        """
        if not isinstance(idempotency_keys, list):
            raise ValueError("idempotency_keys must be a list")
        if not idempotency_keys:
            return {}
        if len(idempotency_keys) > 100:
            raise ValueError("batch size cannot exceed 100 keys")

        # Validate idempotency keys
        for key in idempotency_keys:
            if not isinstance(key, str) or not key.strip():
                raise ValueError("all idempotency_keys must be non-empty strings")

        # When auth is disabled, user_id is None. For now, we don't support
        # global deduplication - only user-scoped deduplication when user_id is provided.
        if user_id is None:
            logger.warning(
                "Cannot batch check idempotency without user_id - auth is currently disabled",
                keys_count=len(idempotency_keys),
                table_name=self.table_name
            )
            return {}

        import asyncio
        from typing import Dict

        async def get_event_by_key(key: str) -> tuple[str, Optional[Event]]:
            """Get event for a single idempotency key."""
            try:
                event = await self.get_event_by_idempotency_key(user_id, key)
                return key, event
            except Exception as e:
                logger.warning(
                    "Error checking idempotency key",
                    user_id=user_id,
                    idempotency_key=key,
                    error=str(e)
                )
                return key, None

        # Execute queries concurrently for better performance
        tasks = [get_event_by_key(key) for key in idempotency_keys]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build result dictionary
        events_by_key: Dict[str, Event] = {}
        for result in results:
            if isinstance(result, tuple) and len(result) == 2:
                key, event = result
                if event is not None:
                    events_by_key[key] = event
            elif isinstance(result, Exception):
                logger.error(
                    "Exception during idempotency key lookup",
                    error=str(result)
                )

        logger.info(
            "Batch idempotency key lookup completed",
            requested=len(idempotency_keys),
            found=len(events_by_key),
            user_id=user_id,
            table_name=self.table_name
        )

        return events_by_key